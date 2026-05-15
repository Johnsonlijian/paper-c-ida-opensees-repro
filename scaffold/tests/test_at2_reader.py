from pathlib import Path

import numpy as np

from paper_c_eesd.ground_motion import read_at2


def test_read_at2_parses_dt_and_values(tmp_path: Path) -> None:
    txt = """PEER NGA RECORD
SOME HEADER LINE
NPTS= 12, DT= 0.0100 SEC
ACCELERATION
 0.0 0.1 0.0 -0.1  0.0 0.2
 0.0 -0.2 0.0 0.0  0.1 0.0
"""
    p = tmp_path / "gm.AT2"
    p.write_text(txt, encoding="utf-8")
    m = read_at2(p)
    assert abs(m.dt - 0.01) < 1e-12
    assert m.accel_g.shape == (12,)
    assert np.isclose(m.accel_g[1], 0.1)

