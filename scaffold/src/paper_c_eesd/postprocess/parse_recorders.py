"""
Parse OpenSees recorder outputs into `edp_summary.json`.

This module is intentionally small and robust:
- displacement recorder: `disp.out` with columns: time, disp_base, disp_top
- fiber strain recorder(s): `steel_strain*.out`, `conc_strain*.out`
  each file is either 2 columns (time, strain) or N columns (time, strain1, strain2, ...)

EDPs produced (ratio/strain units, no %/‰):
- edp_max_drift_ratio
- edp_residual_drift_ratio
- steel_tube_eps_t_max
- steel_tube_eps_c_min
- concrete_core_eps_c_min
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np


def _loadtxt_2d(path: Path) -> np.ndarray:
    a = np.loadtxt(path, dtype=float)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    return a


def parse_disp_base_top(disp_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = _loadtxt_2d(Path(disp_path))
    if a.shape[1] < 3:
        raise ValueError(f"{disp_path}: expected at least 3 cols (t, base, top), got {a.shape[1]}")
    t = a[:, 0]
    base = a[:, 1]
    top = a[:, 2]
    return t, base, top


def parse_strain_files(paths: list[Path]) -> np.ndarray:
    if not paths:
        raise FileNotFoundError("No strain recorder files found.")
    strains = []
    for p in paths:
        a = _loadtxt_2d(p)
        if a.shape[1] < 2:
            raise ValueError(f"{p}: expected at least 2 cols (t, strain...), got {a.shape[1]}")
        strains.append(a[:, 1:])  # drop time
    return np.hstack(strains)  # concat columns


def compute_edps(
    *,
    disp_path: Path,
    height_h: float,
    steel_strain_paths: list[Path],
    conc_strain_paths: list[Path],
) -> dict[str, float]:
    if height_h <= 0:
        raise ValueError("height_h must be positive.")

    _t, base, top = parse_disp_base_top(disp_path)
    drift_ts = (top - base) / float(height_h)
    edp_max_drift_ratio = float(np.nanmax(np.abs(drift_ts)))
    edp_residual_drift_ratio = float(np.nan_to_num(np.abs(drift_ts[-1]), nan=np.nan))

    steel = parse_strain_files(steel_strain_paths)
    conc = parse_strain_files(conc_strain_paths)

    steel_tube_eps_t_max = float(np.nanmax(steel))
    steel_tube_eps_c_min = float(np.nanmin(steel))
    concrete_core_eps_c_min = float(np.nanmin(conc))

    return {
        "edp_max_drift_ratio": edp_max_drift_ratio,
        "edp_residual_drift_ratio": edp_residual_drift_ratio,
        "steel_tube_eps_t_max": steel_tube_eps_t_max,
        "steel_tube_eps_c_min": steel_tube_eps_c_min,
        "concrete_core_eps_c_min": concrete_core_eps_c_min,
    }


def write_edp_summary(run_dir: Path, *, height_h: float) -> Path:
    run_dir = Path(run_dir)
    rec_dir = run_dir / "recorders"
    disp_path = rec_dir / "disp.out"
    if not disp_path.exists():
        raise FileNotFoundError(f"Missing {disp_path}")

    steel_paths = sorted(rec_dir.glob("steel_strain*.out"))
    conc_paths = sorted(rec_dir.glob("conc_strain*.out"))
    edps = compute_edps(
        disp_path=disp_path,
        height_h=height_h,
        steel_strain_paths=steel_paths,
        conc_strain_paths=conc_paths,
    )
    out_p = run_dir / "edp_summary.json"
    out_p.write_text(json.dumps(edps, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_p


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--height-h", type=float, required=True, help="Column height H (same unit as disp)")
    return ap.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    a = _parse_args(argv)
    out = write_edp_summary(a.run_dir, height_h=float(a.height_h))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

