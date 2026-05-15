"""
Run a single IDA time-history using the OpenSees Tcl executable (OpenSees.exe).

Why Tcl runner?
--------------
On some Windows Python versions, OpenSeesPy wheels may not load (DLL issues).
This runner avoids Python bindings and calls the official OpenSees executable.

Per-run outputs under `run_dir/`:
- run_meta.json
- model.tcl
- recorders/disp.out, recorders/steel_strain_*.out, recorders/conc_strain.out
- edp_summary.json (derived from recorders)
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..ground_motion import read_at2
from ..postprocess import write_edp_summary


@dataclass(frozen=True, slots=True)
class SingleTclRunConfig:
    specimen_id: str
    gm_id: str
    analysis_protocol_id: str
    im_grid_id: str
    im_type: str
    im_level: int
    im_value: float
    scale_factor: float
    at2_path: Path

    # geometry for demo model
    H: float
    D: float
    t_steel: float

    # OpenSees executable path
    opensees_exe: Path


def _write_accel_txt(path: Path, accel_g: np.ndarray) -> None:
    path.write_text("\n".join(f"{x:.8e}" for x in accel_g.tolist()) + "\n", encoding="utf-8")


def _read_plain_accel(path: Path) -> np.ndarray:
    vals: list[float] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s:
            continue
        vals.append(float(s))
    return np.asarray(vals, dtype=float)


def _dt_file_for_sorted_eq(path: Path) -> Path:
    m = re.search(r"\((\d+)\)", path.name)
    if not m:
        raise ValueError(f"Cannot infer DtFile name from {path.name}")
    return path.with_name(f"DtFile_({m.group(1)}).txt")


def _read_input_motion(path: Path) -> tuple[float, np.ndarray]:
    """Read either PEER/NGA AT2 files or ATC-63 sorted acceleration text files."""
    if path.suffix.upper() == ".AT2":
        m = read_at2(path)
        return float(m.dt), m.accel_g

    if path.name.startswith("SortedEQFile_") and path.suffix.lower() == ".txt":
        dt_path = _dt_file_for_sorted_eq(path)
        if not dt_path.exists():
            raise FileNotFoundError(f"Missing paired DtFile for {path}: {dt_path}")
        dt = float(dt_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[0])
        return dt, _read_plain_accel(path)

    raise ValueError(f"Unsupported ground-motion file format: {path}")


def _write_model_tcl(
    path: Path,
    *,
    H: float,
    D: float,
    t_steel: float,
    dt: float,
    accel_file: str,
    scale_factor: float,
    rec_dir: str,
) -> None:
    # Explicit key fibers at 4 cardinal points + concrete center.
    R_out = D / 2.0
    R_in = max(R_out - t_steel, 1e-6)
    # crude areas (demo); research model can replace later
    import math

    A_steel_total = math.pi * (R_out**2 - R_in**2)
    A_steel_key = A_steel_total / 4.0
    A_conc = math.pi * (R_in**2)

    tcl = f"""
wipe
model basic -ndm 2 -ndf 3

# nodes
node 1 0.0 0.0
node 2 0.0 {H:.8e}
fix 1 1 1 1
# assign a non-trivial mass so base excitation produces measurable response
mass 2 1.0e5 1.0e5 0.0

# materials (placeholders)
uniaxialMaterial Steel02 1 3.55e8 2.00e11 0.02
uniaxialMaterial Concrete02 2 -4.00e7 -0.002 -8.00e6 -0.012 0.6 0.0 0.0

# section with explicit key fibers
section Fiber 1 {{
    fiber 0.0 0.0 {A_conc:.8e} 2
    fiber {R_out:.8e} 0.0 {A_steel_key:.8e} 1
    fiber {-R_out:.8e} 0.0 {A_steel_key:.8e} 1
    fiber 0.0 {R_out:.8e} {A_steel_key:.8e} 1
    fiber 0.0 {-R_out:.8e} {A_steel_key:.8e} 1
}}

geomTransf Linear 1
beamIntegration Lobatto 1 1 5
element dispBeamColumn 1 1 2 1 1

file mkdir {rec_dir}

# recorders: base+top disp (dof 1)
recorder Node -file {rec_dir}/disp.out -time -node 1 2 -dof 1 disp
# steel key fibers (4 files)
recorder Element -file {rec_dir}/steel_strain_0.out -time -ele 1 section 1 fiber {R_out:.8e} 0.0 strain
recorder Element -file {rec_dir}/steel_strain_1.out -time -ele 1 section 1 fiber {-R_out:.8e} 0.0 strain
recorder Element -file {rec_dir}/steel_strain_2.out -time -ele 1 section 1 fiber 0.0 {R_out:.8e} strain
recorder Element -file {rec_dir}/steel_strain_3.out -time -ele 1 section 1 fiber 0.0 {-R_out:.8e} strain
# concrete center
recorder Element -file {rec_dir}/conc_strain.out -time -ele 1 section 1 fiber 0.0 0.0 strain

# ground motion: file in g, convert to m/s^2 and apply scale_factor
timeSeries Path 1 -dt {dt:.8e} -filePath {accel_file} -factor [expr {{9.81*{scale_factor:.8e}}}]
pattern UniformExcitation 1 1 -accel 1

constraints Plain
numberer RCM
system BandGeneral
test NormDispIncr 1.0e-7 30
algorithm Newton
integrator Newmark 0.5 0.25
analysis Transient

set nSteps [expr {{int(ceil([llength [split [read [open {accel_file} r]] \\n]]))}}]
set dt {dt:.8e}
set ok 0
for {{set i 0}} {{$i < $nSteps}} {{incr i}} {{
    set ok [analyze 1 $dt]
    if {{$ok != 0}} {{ break }}
}}

if {{$ok != 0}} {{
    puts "ANALYSIS_FAILED"
}} else {{
    puts "ANALYSIS_OK"
}}
"""
    path.write_text(tcl.strip() + "\n", encoding="utf-8")


def run_single_opensees_tcl_ida(run_dir: Path, cfg: SingleTclRunConfig) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rec_dir = run_dir / "recorders"
    rec_dir.mkdir(parents=True, exist_ok=True)

    dt, accel_g = _read_input_motion(cfg.at2_path)
    # keep in g; Tcl timeSeries applies scale_factor*9.81
    accel_txt = run_dir / "accel_g.txt"
    _write_accel_txt(accel_txt, accel_g)

    model_tcl = run_dir / "model.tcl"
    _write_model_tcl(
        model_tcl,
        H=float(cfg.H),
        D=float(cfg.D),
        t_steel=float(cfg.t_steel),
        dt=dt,
        accel_file=str(accel_txt.name),
        scale_factor=float(cfg.scale_factor),
        rec_dir=str(rec_dir.name),
    )

    # run OpenSees.exe with cwd=run_dir so relative paths work
    proc = subprocess.run(
        [str(Path(cfg.opensees_exe)), str(model_tcl.name)],
        cwd=str(run_dir),
        capture_output=True,
        text=True,
        timeout=60 * 10,
    )
    # write log
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (run_dir / "opensees_log.txt").write_text(combined, encoding="utf-8", errors="ignore")
    converged = proc.returncode == 0 and ("ANALYSIS_OK" in combined)
    meta = {
        "run_id": f"{cfg.specimen_id}/{cfg.gm_id}/{cfg.analysis_protocol_id}/{cfg.im_grid_id}/{cfg.im_type}/{cfg.im_level}",
        "specimen_id": cfg.specimen_id,
        "gm_id": cfg.gm_id,
        "analysis_protocol_id": cfg.analysis_protocol_id,
        "im_grid_id": cfg.im_grid_id,
        "im_type": cfg.im_type,
        "im_level": int(cfg.im_level),
        "im_value": float(cfg.im_value),
        "scale_factor": float(cfg.scale_factor),
        "converged": bool(converged),
        "analysis_status": "ok" if converged else "nonconverged",
        "gm_file": str(Path(cfg.at2_path).name),
        "dt": dt,
        "npts": int(len(accel_g)),
        "opensees_returncode": int(proc.returncode),
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # edp summary (if recorders exist)
    if converged:
        write_edp_summary(run_dir, height_h=float(cfg.H))
    else:
        # still write empty/NaN summary for bookkeeping
        nan_edp = {
            "edp_max_drift_ratio": float("nan"),
            "edp_residual_drift_ratio": float("nan"),
            "steel_tube_eps_t_max": float("nan"),
            "steel_tube_eps_c_min": float("nan"),
            "concrete_core_eps_c_min": float("nan"),
        }
        (run_dir / "edp_summary.json").write_text(
            json.dumps(nan_edp, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return run_dir

