"""YAML config with optional `extends:` inheritance (project root = configs/)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class IDANumerics(BaseModel):
    n_specimens: int
    n_ground_motions: int
    n_im_levels: int


class ProjectConfig(BaseModel):
    project: str
    ida: IDANumerics
    version: str = "0.1.0"
    ground_motion: dict[str, Any] = Field(default_factory=dict)
    opensees: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(name: str, *, configs_dir: Path | None = None) -> ProjectConfig:
    """
    Load `configs/{name}.yaml`. If the file contains `extends: other`, merge
    `configs/other.yaml` first (one level; chain not required for our use).
    """
    root = configs_dir or Path(__file__).resolve().parents[3] / "configs"
    path = root / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML root in {path}")
    if "extends" in data:
        base_name = data.pop("extends")
        base_path = root / f"{base_name}.yaml"
        base_data = yaml.safe_load(base_path.read_text(encoding="utf-8"))
        if not isinstance(base_data, dict):
            raise ValueError(f"Invalid base YAML {base_path}")
        data = _deep_merge(base_data, data)
    return ProjectConfig.model_validate(data)
