from pathlib import Path

import numpy as np

from paper_c_eesd.ida.run_single_opensees_tcl_ida import _read_input_motion


def test_read_input_motion_supports_sorted_eq_with_dt_file(tmp_path: Path) -> None:
    gm = tmp_path / "SortedEQFile_(8201811).txt"
    dt = tmp_path / "DtFile_(8201811).txt"
    gm.write_text("0.1\n-0.2\n0.3\n", encoding="utf-8")
    dt.write_text("0.00500\n", encoding="utf-8")

    parsed_dt, accel_g = _read_input_motion(gm)

    assert parsed_dt == 0.005
    assert accel_g.shape == (3,)
    assert np.isclose(accel_g.max(), 0.3)

