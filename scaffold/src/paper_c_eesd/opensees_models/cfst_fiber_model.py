"""
CFST fiber section + steel–concrete fibre line element — **stub** for OpenSeesPy.

**You will implement**:
- section discretisation, Steel02 + Concrete02 / ConcreteCM parameters from `D,t,L,fy,fc`
- boundary: pinned–pinned vs fixed–fixed per specimen card
- optional P–delta / geometric stiffness

The public shape below keeps IDA driver code importable before OpenSees is installed
on a given machine (e.g. Apple Silicon build quirks).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class CFSTFiberModelSpec:
    specimen_id: str
    D_mm: float
    t_mm: float
    L_mm: float
    fy_mpa: float
    fc_mpa: float
    n_fiber_steel: int = 8
    n_fiber_concrete: int = 20
    damping_zeta: float = 0.02


@runtime_checkable
class OpenSeesModel(Protocol):
    def run_nonlinear_time_history(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...


def build_model(
    spec: CFSTFiberModelSpec,
) -> OpenSeesModel:
    """
    Return a model handle. **Default implementation** raises: wire OpenSeesPy here.

    When `opensees` extra is available, replace with a thin wrapper that calls
    `opensees` / `openseespy` and returns displacements, base shear, etc.
    """
    msg = (
        "build_model is a stub: install `openseespy` and implement "
        "discretised CFST section + force-based / displacement-based element."
    )
    raise NotImplementedError(msg)
