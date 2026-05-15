"""
Collect per-run outputs into the Level-0 table `ida_raw_all.csv`.

We assume each run is stored in its own directory, containing at minimum:

- `run_meta.json`
    Keys (minimal):
      specimen_id, gm_id, analysis_protocol_id, im_grid_id,
      im_type, im_level, im_value, scale_factor,
      converged, analysis_status

- `edp_summary.json`
    Keys (minimal):
      edp_max_drift_ratio, edp_residual_drift_ratio,
      steel_tube_eps_t_max, steel_tube_eps_c_min, concrete_core_eps_c_min

This keeps OpenSees recorder details out of the statistical pipeline.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .schema import IDARowSpec


REQUIRED_META_KEYS = {
    "specimen_id",
    "gm_id",
    "analysis_protocol_id",
    "im_grid_id",
    "im_type",
    "im_level",
    "im_value",
    "scale_factor",
    "converged",
    "analysis_status",
}
REQUIRED_EDP_KEYS = {
    "edp_max_drift_ratio",
    "edp_residual_drift_ratio",
    "steel_tube_eps_t_max",
    "steel_tube_eps_c_min",
    "concrete_core_eps_c_min",
}


def _read_json(p: Path) -> dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _make_run_id(meta: dict[str, Any], *, fallback_dir: str) -> str:
    parts = [
        str(meta.get("specimen_id", "")),
        str(meta.get("gm_id", "")),
        str(meta.get("analysis_protocol_id", "")),
        str(meta.get("im_type", "")),
        str(meta.get("im_level", "")),
    ]
    s = "/".join(parts)
    return s if s.strip("/") else fallback_dir


def collect_run_dir(run_dir: Path) -> dict[str, Any]:
    meta_p = run_dir / "run_meta.json"
    edp_p = run_dir / "edp_summary.json"
    if not meta_p.exists():
        raise FileNotFoundError(f"Missing {meta_p}")
    if not edp_p.exists():
        raise FileNotFoundError(f"Missing {edp_p}")

    meta = _read_json(meta_p)
    edp = _read_json(edp_p)

    missing_meta = REQUIRED_META_KEYS - set(meta.keys())
    missing_edp = REQUIRED_EDP_KEYS - set(edp.keys())
    if missing_meta:
        raise ValueError(f"{run_dir}: run_meta.json missing keys: {sorted(missing_meta)}")
    if missing_edp:
        raise ValueError(f"{run_dir}: edp_summary.json missing keys: {sorted(missing_edp)}")

    row: dict[str, Any] = {}
    row.update(meta)
    row.update(edp)
    row["run_id"] = str(meta.get("run_id") or _make_run_id(meta, fallback_dir=run_dir.name))
    return row


def collect_ida_raw_all(runs_root: Path, *, glob_pattern: str = "**/run_meta.json") -> pd.DataFrame:
    runs_root = Path(runs_root)
    meta_files = list(runs_root.glob(glob_pattern))
    if not meta_files:
        raise FileNotFoundError(f"No run_meta.json found under {runs_root}")

    rows = []
    for meta_p in meta_files:
        run_dir = meta_p.parent
        rows.append(collect_run_dir(run_dir))

    df = pd.DataFrame(rows)
    return df


def validate_ida_raw_all_df(df: pd.DataFrame) -> None:
    req_cols = set(asdict(IDARowSpec(**{k: _dummy(k) for k in IDARowSpec.__dataclass_fields__})).keys())
    missing = sorted(req_cols - set(df.columns))
    if missing:
        raise ValueError(f"ida_raw_all missing required columns: {missing}")


def _dummy(name: str) -> Any:
    if name in {"converged"}:
        return True
    if name in {"im_level"}:
        return 0
    if name.endswith("_id") or name.endswith("_type") or name in {"run_id", "analysis_status"}:
        return "X"
    return 0.0


def write_ida_raw_all_csv(df: pd.DataFrame, out_csv: Path) -> Path:
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return out_csv


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", type=Path, required=True, help="Root directory of per-run outputs")
    ap.add_argument("--out-csv", type=Path, required=True, help="Output path for ida_raw_all.csv")
    args = ap.parse_args(list(argv) if argv is not None else None)

    df = collect_ida_raw_all(args.runs_root)
    validate_ida_raw_all_df(df)
    write_ida_raw_all_csv(df, args.out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

