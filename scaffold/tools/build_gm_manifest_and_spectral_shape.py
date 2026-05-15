from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from paper_c_eesd.ground_motion.at2 import read_at2


@dataclass(frozen=True, slots=True)
class SpectralShapeConfig:
    t_short: float = 0.2
    t_long: float = 1.0


def _pga_from_accel_g(accel_g: np.ndarray) -> float:
    return float(np.nanmax(np.abs(accel_g)))


def build_manifest_at2(root: Path, *, set_name: str) -> pd.DataFrame:
    files = sorted(Path(root).glob("**/*.AT2"))
    rows = []
    for p in files:
        try:
            m = read_at2(p)
            rows.append(
                {
                    "gm_set": set_name,
                    "gm_id": p.stem,
                    "path": str(p.as_posix()),
                    "dt": float(m.dt),
                    "npts": int(len(m.accel_g)),
                    "pga_g": _pga_from_accel_g(m.accel_g),
                }
            )
        except Exception as e:
            rows.append(
                {
                    "gm_set": set_name,
                    "gm_id": p.stem,
                    "path": str(p.as_posix()),
                    "dt": np.nan,
                    "npts": np.nan,
                    "pga_g": np.nan,
                    "error": str(e),
                }
            )
    return pd.DataFrame(rows)


def _tidy_spectra_csv(path: Path) -> pd.DataFrame:
    """
    Parse SP3Risk-exported spectra CSV where:
    - header spans multiple lines
    - there is a row containing 'EQ ID:' and one containing 'Period (sec)'
    - the numeric block starts at the row where col2 is period values.
    """
    raw = pd.read_csv(path, header=None)
    # find EQ ID row and first numeric period row
    eqid_row = None
    for i in range(min(40, len(raw))):
        if raw.iloc[i].astype(str).str.contains("EQ ID", case=False, na=False).any():
            eqid_row = i
            break
    if eqid_row is None:
        raise ValueError(f"EQ ID row not found in {path}")

    # EQ IDs start at column 3 onward in this file pattern
    eq_ids = raw.iloc[eqid_row, 3:].tolist()
    # numeric block starts after a row containing 'Period (sec)'
    start = None
    for i in range(eqid_row, eqid_row + 20):
        if raw.iloc[i].astype(str).str.contains("Period", case=False, na=False).any():
            start = i + 1
            break
    if start is None:
        raise ValueError(f"Period row not found in {path}")

    blk = raw.iloc[start:].copy()
    blk = blk.dropna(how="all")
    # period in col2
    period = pd.to_numeric(blk.iloc[:, 2], errors="coerce")
    data = blk.iloc[:, 3 : 3 + len(eq_ids)]
    data = data.apply(pd.to_numeric, errors="coerce")
    out = pd.concat([period.rename("T"), data], axis=1)
    out = out.dropna(subset=["T"])
    def _colname(x: object, i: int) -> str:
        if pd.isna(x):
            return f"col{i}"
        s = str(x).strip()
        # common form "120111.0" -> "120111"
        if s.endswith(".0"):
            s = s[:-2]
        return s

    out.columns = ["T"] + [_colname(x, i) for i, x in enumerate(eq_ids)]
    return out


def spectral_shape_index(spectra_tidy: pd.DataFrame, cfg: SpectralShapeConfig) -> pd.DataFrame:
    # interpolate Sa at t_short and t_long for each column
    T = spectra_tidy["T"].to_numpy(dtype=float)
    out_rows = []
    for col in spectra_tidy.columns[1:]:
        Sa = spectra_tidy[col].to_numpy(dtype=float)
        if np.all(~np.isfinite(Sa)):
            continue
        sa_s = float(np.interp(cfg.t_short, T, Sa))
        sa_l = float(np.interp(cfg.t_long, T, Sa))
        # guard against non-positive values (some tables may include inf/blank -> nan)
        if not (np.isfinite(sa_s) and np.isfinite(sa_l)) or sa_s <= 0 or sa_l <= 0:
            ssi = np.nan
        else:
            ssi = float(np.log(sa_l) - np.log(sa_s))
        out_rows.append({"eq_id": col, f"Sa_{cfg.t_short}": sa_s, f"Sa_{cfg.t_long}": sa_l, "ssi_ln_ratio": ssi})
    return pd.DataFrame(out_rows)


def main() -> int:
    out_dir = Path("data/ground_motions/_derived")
    out_dir.mkdir(parents=True, exist_ok=True)

    # A) FEMA P695 Far-Field AT2s (already downloaded)
    ff_root = Path("data/ground_motions/ATC-63_Far-Field_GroundMotionAccelTextFiles_Unscaled_Original")
    ff_manifest = build_manifest_at2(ff_root, set_name="P695_FF22_AT2_original")

    # A) Near-Field sorted EQ files are plain accel columns; we defer dt mapping to NF tables later.
    # For now record file list only.
    nf_root = Path("data/ground_motions/ATC-63_NearField_SortedEQFiles")
    nf_txt = sorted(nf_root.glob("**/*.txt"))
    nf_manifest = pd.DataFrame(
        [{"gm_set": "P695_NF28_sorted_txt", "gm_id": p.stem, "path": str(p.as_posix())} for p in nf_txt]
    )

    # C) FFext motions: extracted AT2 to a short directory (flattened)
    ffext_root = Path("data/gm_ffext")
    ffext_manifest = build_manifest_at2(ffext_root, set_name="FFext_AT2_flat")

    manifest = pd.concat([ff_manifest, nf_manifest, ffext_manifest], ignore_index=True, sort=False)
    manifest.to_csv(out_dir / "gm_manifest.csv", index=False)

    # B) spectral shape proxy from provided spectra tables (far-field + near-field)
    cfg = SpectralShapeConfig(t_short=0.2, t_long=1.0)

    ff_spec = _tidy_spectra_csv(
        Path("data/ground_motions/_p695_meta/3a_ATC-63_SpectraForAllRecords_FarFieldSet__Spectra_Sa_Unscaled.csv")
    )
    ff_ssi = spectral_shape_index(ff_spec, cfg)
    ff_ssi["gm_set"] = "P695_FF22"

    nf_spec = _tidy_spectra_csv(Path("data/ground_motions/_p695_meta/NF_3_ResponseSpectra__Spectra_Sa_Unscaled.csv"))
    nf_ssi = spectral_shape_index(nf_spec, cfg)
    nf_ssi["gm_set"] = "P695_NF28"

    ssi = pd.concat([ff_ssi, nf_ssi], ignore_index=True)
    ssi.to_csv(out_dir / "spectral_shape_index.csv", index=False)

    print("Wrote:")
    print("-", out_dir / "gm_manifest.csv")
    print("-", out_dir / "spectral_shape_index.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

