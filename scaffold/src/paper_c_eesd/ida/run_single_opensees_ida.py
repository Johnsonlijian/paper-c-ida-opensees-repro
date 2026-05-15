"""
Run a single OpenSeesPy time-history at one IM scaling, writing the per-run folder.

Outputs under `run_dir/`:
- run_meta.json
- recorders/disp.out, recorders/steel_strain_*.out, recorders/conc_strain.out
- edp_summary.json (derived from recorders)

This module is designed for Pilot-scale execution and as the unit of HPC batching.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..ground_motion import read_at2
from ..opensees_models import Cantilever2DSpec, build_cfst_cantilever_2d
from ..postprocess import write_edp_summary


@dataclass(frozen=True, slots=True)
class SingleRunConfig:
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


def run_single_opensees_ida(run_dir: Path, cfg: SingleRunConfig) -> Path:
    try:
        import openseespy.opensees as ops
    except Exception as e:  # pragma: no cover
        raise RuntimeError("OpenSeesPy not available; install extra 'opensees'.") from e

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Build model + recorders
    spec = Cantilever2DSpec(specimen_id=cfg.specimen_id, H=cfg.H, D=cfg.D, t_steel=cfg.t_steel)
    build_cfst_cantilever_2d(spec, out_dir=run_dir)

    # Ground motion (AT2 accel in g)
    m = read_at2(cfg.at2_path)
    dt = float(m.dt)
    ag = (m.accel_g * float(cfg.scale_factor)).tolist()

    ops.timeSeries("Path", 1, "-dt", dt, "-values", *ag)
    ops.pattern("UniformExcitation", 1, 1, "-accel", 1)

    # analysis
    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Plain")
    ops.integrator("Newmark", 0.5, 0.25)
    ops.algorithm("Newton")
    ops.analysis("Transient")
    ops.test("NormDispIncr", 1e-7, 30)

    ok = 0
    n_steps = len(ag)
    for _ in range(n_steps):
        ok = ops.analyze(1, dt)
        if ok != 0:
            break

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
        "converged": bool(ok == 0),
        "analysis_status": "ok" if ok == 0 else "nonconverged",
        "gm_file": str(Path(cfg.at2_path).name),
        "dt": dt,
        "npts": int(n_steps),
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # edp summary (requires H)
    write_edp_summary(run_dir, height_h=float(cfg.H))
    return run_dir

