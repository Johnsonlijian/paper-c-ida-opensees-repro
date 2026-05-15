from __future__ import annotations

import json
from pathlib import Path

from paper_c_eesd.opensees_models import Cantilever2DSpec, build_cfst_cantilever_2d
from paper_c_eesd.postprocess import write_edp_summary


def main() -> int:
    """
    Run a *demo* OpenSeesPy analysis to generate recorder outputs + edp_summary.json.

    Notes:
    - This script requires OpenSeesPy installed (optional dependency).
    - It uses a small synthetic excitation (sine pulse) for smoke testing.
    """
    try:
        import numpy as np
        import openseespy.opensees as ops
    except Exception as e:
        raise SystemExit(
            "OpenSeesPy not available. Install with: python -m pip install openseespy"
        ) from e

    run_dir = Path("data/opensees_demo/run_000")
    run_dir.mkdir(parents=True, exist_ok=True)

    spec = Cantilever2DSpec(specimen_id="S01", H=3.0, D=0.4, t_steel=0.008)
    build_cfst_cantilever_2d(spec, out_dir=run_dir)

    # simple dynamic analysis with synthetic base excitation
    dt = 0.01
    t_end = 2.0
    t = np.arange(0.0, t_end + dt, dt)
    ag = 0.2 * np.sin(2.0 * np.pi * 2.0 * t) * np.exp(-2.0 * t)  # g units-ish

    ops.timeSeries("Path", 1, "-dt", dt, "-values", *ag.tolist())
    ops.pattern("UniformExcitation", 1, 1, "-accel", 1)

    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Plain")
    ops.integrator("Newmark", 0.5, 0.25)
    ops.algorithm("Newton")
    ops.analysis("Transient")
    ops.test("NormDispIncr", 1e-7, 20)

    ok = 0
    for _ in range(len(t)):
        ok = ops.analyze(1, dt)
        if ok != 0:
            break

    run_meta = {
        "run_id": "S01/GM_DEMO/P1/G1/SaT1/0",
        "specimen_id": "S01",
        "gm_id": "GM_DEMO",
        "analysis_protocol_id": "P1",
        "im_grid_id": "G1",
        "im_type": "SaT1",
        "im_level": 0,
        "im_value": 0.2,
        "scale_factor": 1.0,
        "converged": bool(ok == 0),
        "analysis_status": "ok" if ok == 0 else "nonconverged",
    }
    (run_dir / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # derive edp_summary.json from recorder outputs
    write_edp_summary(run_dir, height_h=spec.H)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

