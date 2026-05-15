"""
Minimal, reproducible OpenSeesPy CFST cantilever model with explicit key fibers.

Design goal
-----------
Provide a *working* end-to-end path for Paper C data generation:
OpenSeesPy recorders -> `recorders/*.out` -> `edp_summary.json` -> Level-0/Level-1.

This is not the final research-grade model; it is a stable starting point that:
- uses explicit key fiber coordinates (recorder coordinates always hit)
- produces the three recorder files required by `postprocess.parse_recorders`
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Cantilever2DSpec:
    # geometry
    specimen_id: str
    H: float  # column height (m)
    D: float  # outer diameter (m)
    t_steel: float  # steel tube thickness (m)

    # materials (basic placeholders; calibrate later)
    fy: float = 355e6
    Es: float = 200e9
    b_steel: float = 0.02

    fc: float = 40e6
    eps_c0: float = -0.002
    fc_u: float = 8e6
    eps_u: float = -0.012
    Ets: float = 0.0

    # fibers (explicit key points)
    key_steel_points: int = 4  # 4 cardinal points


def build_cfst_cantilever_2d(
    spec: Cantilever2DSpec,
    *,
    out_dir: Path,
    base_node: int = 1,
    top_node: int = 2,
    ele_tag: int = 1,
    sec_tag: int = 1,
) -> dict[str, int]:
    """
    Build model and attach recorders.

    Recorders (relative to out_dir):
    - `recorders/disp.out`: time, disp_base, disp_top (dof 1)
    - `recorders/steel_strain_*.out`: time, strain (one file per key steel fiber)
    - `recorders/conc_strain.out`: time, strain at concrete core center (0,0)
    """
    try:
        import math

        import openseespy.opensees as ops
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "OpenSeesPy is required for model execution. Install extras: pip install '.[opensees]'"
        ) from e

    out_dir = Path(out_dir)
    rec_dir = out_dir / "recorders"
    rec_dir.mkdir(parents=True, exist_ok=True)

    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    # nodes (2D, cantilever)
    ops.node(base_node, 0.0, 0.0)
    ops.node(top_node, 0.0, float(spec.H))
    ops.fix(base_node, 1, 1, 1)

    # mass (placeholder; adjust to your specimen)
    ops.mass(top_node, 1.0, 1.0, 0.0)

    # materials
    mat_steel = 1
    mat_conc = 2
    ops.uniaxialMaterial("Steel02", mat_steel, float(spec.fy), float(spec.Es), float(spec.b_steel))
    # Concrete02 expects compression negative
    ops.uniaxialMaterial(
        "Concrete02",
        mat_conc,
        -float(spec.fc),
        float(spec.eps_c0),
        -float(spec.fc_u),
        float(spec.eps_u),
        0.6,
        0.0,
        float(spec.Ets),
    )

    # explicit key fibers
    R_out = float(spec.D) / 2.0
    R_in = max(R_out - float(spec.t_steel), 1e-6)
    A_steel_total = math.pi * (R_out**2 - R_in**2)
    A_steel_key = A_steel_total / float(spec.key_steel_points)
    A_conc = math.pi * (R_in**2)

    ops.section("Fiber", sec_tag)
    # concrete core center fiber (guaranteed coordinate match)
    ops.fiber(0.0, 0.0, A_conc, mat_conc)
    # steel key fibers at cardinal points (guaranteed coordinate match)
    key_coords: list[tuple[float, float]] = [(R_out, 0.0), (-R_out, 0.0), (0.0, R_out), (0.0, -R_out)]
    key_coords = key_coords[: int(spec.key_steel_points)]
    for (y, z) in key_coords:
        ops.fiber(float(y), float(z), float(A_steel_key), mat_steel)

    # beam integration / element
    # Minimal: dispBeamColumn with 5 integration points.
    ops.geomTransf("Linear", 1)
    ops.beamIntegration("Lobatto", 1, sec_tag, 5)
    ops.element("dispBeamColumn", ele_tag, base_node, top_node, 1, 1)

    # recorders
    ops.recorder(
        "Node",
        "-file",
        str((rec_dir / "disp.out").as_posix()),
        "-time",
        "-node",
        base_node,
        top_node,
        "-dof",
        1,
        "disp",
    )
    # steel strains at each key coordinate (one file per point)
    for i, (y, z) in enumerate(key_coords):
        ops.recorder(
            "Element",
            "-file",
            str((rec_dir / f"steel_strain_{i}.out").as_posix()),
            "-time",
            "-ele",
            ele_tag,
            "section",
            sec_tag,
            "fiber",
            float(y),
            float(z),
            "strain",
        )
    ops.recorder(
        "Element",
        "-file",
        str((rec_dir / "conc_strain.out").as_posix()),
        "-time",
        "-ele",
        ele_tag,
        "section",
        sec_tag,
        "fiber",
        0.0,
        0.0,
        "strain",
    )

    return {"base_node": base_node, "top_node": top_node, "ele_tag": ele_tag, "sec_tag": sec_tag}

