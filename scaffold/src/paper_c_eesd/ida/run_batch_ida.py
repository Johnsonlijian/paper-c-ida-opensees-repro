"""
Batch incremental dynamic analysis (IDA) driver — **skeleton**.

Implements only **bookkeeping** helpers; per-run OpenSees execution is intentionally
omitted so CI can run `pytest` on laptops without a compiled OpenSees.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paper_c_eesd.utils.config import load_config, ProjectConfig


@dataclass(frozen=True, slots=True)
class IDABatchConfig:
    n_specimens: int
    n_ground_motions: int
    n_im_levels: int
    project_name: str

    @property
    def n_intensity_database_rows(self) -> int:
        return self.n_specimens * self.n_ground_motions * self.n_im_levels


def ida_intensity_point_count(config_name: str = "default", *, configs_dir: Path | None = None) -> int:
    """Convenience: product from YAML; used to avoid hard-coded 30*22*20 in source."""
    c: ProjectConfig = load_config(config_name, configs_dir=configs_dir)
    i = c.ida
    return int(i.n_specimens * i.n_ground_motions * i.n_im_levels)


def run_batch_ida(
    _output_csv: Path,
    _config: IDABatchConfig,
) -> None:
    """
    **TODO**: for each (spec, gm, im_level) write one row to ``ida_raw_all.csv``.

    Raises
    ------
    NotImplementedError
        Until OpenSees batch is wired to your cluster / workstation.
    """
    raise NotImplementedError("run_batch_ida: connect OpenSees + motion scaling + EDP post.")
