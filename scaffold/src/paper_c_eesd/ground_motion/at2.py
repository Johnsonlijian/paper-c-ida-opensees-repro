"""
PEER/NGA-style `.AT2` ground motion reader (minimal).

We aim for robustness, not perfect generality. Common format includes:
- a few header lines (may include NPTS and DT)
- then whitespace-separated acceleration values (in g)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True, slots=True)
class AT2Motion:
    dt: float
    accel_g: np.ndarray  # acceleration in g


_DT_RE = re.compile(r"\bDT\s*=\s*([0-9.]+)", re.IGNORECASE)
_NPTS_DT_RE = re.compile(r"NPTS\s*=\s*(\d+)\s*,\s*DT\s*=\s*([0-9.]+)", re.IGNORECASE)
_NPTS_DT_BARE_RE = re.compile(r"^\s*(\d+)\s+([0-9.]+)\s+NPTS\s*,\s*DT\b", re.IGNORECASE)


def read_at2(path: str | Path) -> AT2Motion:
    p = Path(path)
    txt = p.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    if len(lines) < 3:
        raise ValueError(f"{p}: too few lines for AT2")

    dt = None
    npts = None
    # scan header for DT/NPTS
    for ln in lines[:20]:
        m0 = _NPTS_DT_BARE_RE.search(ln)
        if m0:
            npts = int(m0.group(1))
            dt = float(m0.group(2))
            break
        m = _NPTS_DT_RE.search(ln)
        if m:
            npts = int(m.group(1))
            dt = float(m.group(2))
            break
        m2 = _DT_RE.search(ln)
        if m2:
            dt = float(m2.group(1))

    if dt is None:
        raise ValueError(f"{p}: DT not found in header")

    # data starts after the line that contains NPTS/DT if present; otherwise after first 4 lines
    start_idx = 4
    for i, ln in enumerate(lines[:30]):
        if "NPTS" in ln.upper() and "DT" in ln.upper():
            start_idx = i + 1
            break

    data_tokens: list[str] = []
    for ln in lines[start_idx:]:
        # skip non-numeric header markers that sometimes appear after DT line
        up = ln.upper()
        if any(k in up for k in ("ACCEL", "ACCELERATION", "TIME SERIES", "UNITS")):
            continue
        # allow commas
        ln = ln.replace(",", " ")
        data_tokens.extend([t for t in ln.split() if t])
    accel = np.array([float(t) for t in data_tokens], dtype=float)

    if npts is not None and accel.size >= npts:
        accel = accel[:npts]
    if accel.size < 10:
        raise ValueError(f"{p}: parsed too few accel points ({accel.size})")
    return AT2Motion(dt=float(dt), accel_g=accel)

