# Reproducible Runbook

Status: R34 scaffold, not final archive
Date: 2026-05-13

## Purpose

This runbook defines the reviewer-facing reproduction route for the Paper C diagnostic workflow. It is a packaging scaffold, not a claim that a public repository or DOI already exists.

## Package Boundary

Include:

- Source code under `scaffold/src/`.
- Configuration files under `scaffold/configs/`.
- Analysis scripts under `scaffold/tools/`, after removing local conflict duplicates from the public package.
- Derived metadata, derived result tables, and generated figures listed in `DATASETS_AND_LINKS.csv`.
- Generated manuscript figures and companion figure-statistics files.

Exclude:

- Raw third-party ground-motion records unless redistribution rights are explicitly verified.
- Downloaded archives, PDFs, active manuscripts, cover letters, reviewer responses, internal `rounds/`, internal `logs/`, credentials, `.env`, OAuth/session files, and local cache files.
- AI-generated visual assets as submission-facing scientific figures.
- Local NAS conflict duplicate scripts unless an author intentionally selects them for the package.

## Environment

The scaffold declares `requires-python = ">=3.11"` in `scaffold/pyproject.toml`; `.python-version` currently records Python 3.12. A clean-environment test was run on 2026-05-13 after fixing the wheel package target in `pyproject.toml`.

Preferred clean-environment setup:

```powershell
cd paper-c-eesd-package\scaffold
python -m pip install ".[dev]"
python -m pytest
```

Editable-install note: under the current Windows/NAS path containing Chinese characters, `python -m pip install -e ".[dev]"` generated an editable `.pth` path with mojibake and the package could not be imported. The non-editable install above succeeded and is the safer reviewer-facing command. Editable install may still be usable after cloning the public package into an ASCII-only path.

Offline fallback after dependencies are already installed and the package source is on `PYTHONPATH`:

```powershell
cd paper-c-eesd-package\scaffold
$env:PYTHONPATH="src"
python -m pytest
```

## Main Reproduction Commands

Script paths listed here have been path-checked in the local workspace on 2026-05-13. The package install/import/test smoke check passed in a clean virtual environment on 2026-05-13; full end-to-end regeneration command logs for every analysis script still need to be archived before public release.

```powershell
cd paper-c-eesd-package\scaffold
$env:PYTHONPATH="src"
python tools\build_gm_manifest_and_spectral_shape.py
python tools\build_nf28_sorted_manifest.py
python tools\run_formal_pilot_v1.py
python tools\run_expanded_pilot_v2.py
python tools\run_sensitivity_v3.py
python tools\run_threshold_sensitivity_v4.py
python tools\run_resampling_r1.py
python tools\run_protocol_split_r34.py
python tools\make_protocol_effect_ledger.py
python tools\make_manuscript_figures.py
```

## Command Verification Matrix

| Command | Script path checked | Expected output family | G4 status |
| --- | --- | --- | --- |
| `python -m pip install ".[dev]"` | yes | installed package importable as `paper_c_eesd` | Passed 2026-05-13 |
| `python -m pytest` | yes | test suite | Passed 2026-05-13: 17 passed |
| `python tools\build_gm_manifest_and_spectral_shape.py` | yes | `scaffold/data/ground_motions/_derived/` | Needs full regeneration run log |
| `python tools\build_nf28_sorted_manifest.py` | yes | `scaffold/data/ground_motions/_derived/nf28_sorted_manifest.csv` | Needs full regeneration run log |
| `python tools\run_formal_pilot_v1.py` | yes | `scaffold/data/formal_pilot_v1/figures/` | Needs full regeneration run log |
| `python tools\run_expanded_pilot_v2.py` | yes | `scaffold/data/expanded_pilot_v2/figures/` | Needs full regeneration run log |
| `python tools\run_sensitivity_v3.py` | yes | `scaffold/data/sensitivity_v3/figures/` | Needs full regeneration run log |
| `python tools\run_threshold_sensitivity_v4.py` | yes | `scaffold/data/threshold_sensitivity_v4/figures/` | Needs full regeneration run log |
| `python tools\run_resampling_r1.py` | yes | `scaffold/data/resampling_r1/`; `fig12_r1_delta_logtheta_distribution.png` | Passed 2026-05-13 for existing-record bootstrap screen |
| `python tools\run_protocol_split_r34.py` | yes | `scaffold/data/protocol_split_r34/`; `fig13_protocol_split_r34_delta_logtheta.png` | Passed 2026-05-13: 900 new OpenSees runs plus v3 Level-0 filtering |
| `python tools\make_protocol_effect_ledger.py` | yes | protocol-effect ledger CSV files | Needs full regeneration run log |
| `python tools\make_manuscript_figures.py` | yes | `scaffold/docs/manuscript_drafts/figures/` | Needs full regeneration run log |

## Expected Output Families

| Output family | Expected file or directory | Manuscript dependency |
| --- | --- | --- |
| Spectral-shape metadata | `scaffold/data/ground_motions/_derived/gm_manifest.csv`; `scaffold/data/ground_motions/_derived/spectral_shape_index.csv`; `scaffold/data/ground_motions/_derived/nf28_sorted_manifest.csv` | Figure 2; Section 4.1 |
| Formal Pilot v1 results | `scaffold/data/formal_pilot_v1/figures/formal_pilot_v1_summary.csv` | Figure 3 |
| Expanded Pilot v2 results | `scaffold/data/expanded_pilot_v2/figures/expanded_pilot_v2_summary.csv`; `scaffold/data/expanded_pilot_v2/figures/protocol_effect_ledger.csv` | Figures 6-7 |
| Sensitivity v3 results | `scaffold/data/sensitivity_v3/figures/sensitivity_v3_summary.csv`; `scaffold/data/sensitivity_v3/figures/sensitivity_v3_protocol_effect_ledger.csv` | Figure 8 |
| Threshold Sensitivity v4 results | `scaffold/data/threshold_sensitivity_v4/figures/threshold_sensitivity_v4_summary.csv`; `scaffold/data/threshold_sensitivity_v4/figures/threshold_sensitivity_v4_protocol_effect_ledger.csv` | Figures 9-10 |
| R1 existing-record bootstrap | `scaffold/data/resampling_r1/r1_summary_table.csv`; `scaffold/data/resampling_r1/r1_protocol_effect_distribution.csv`; `scaffold/docs/manuscript_drafts/figures/fig12_r1_delta_logtheta_distribution.png` | Figure 12; Section 4.8 |
| R34 protocol split | `scaffold/data/protocol_split_r34/figures/protocol_split_r34_summary.csv`; `scaffold/data/protocol_split_r34/figures/protocol_split_r34_protocol_effect_ledger.csv`; `scaffold/data/protocol_split_r34/figures/protocol_split_r34_decomposition.csv`; `scaffold/docs/manuscript_drafts/figures/fig13_protocol_split_r34_delta_logtheta.png` | Figure 13; Section 4.9 |
| Calibration diagnostics | `scaffold/data/calibration/` files listed in `DATASETS_AND_LINKS.csv` | Sections 3.7 6 7 8 |
| Manuscript figures | `scaffold/docs/manuscript_drafts/figures/`; `scaffold/data/calibration/curve_level_v1/figures/curve_level_v1_overlay_panels.png` | Figures 1-13 |

## Validation Checks Before G4

1. `python -m pytest` passes in a clean environment after installing `.[dev]`. Status: passed on 2026-05-13 with non-editable install.
2. All main reproduction commands above either run successfully or are replaced by a clearly documented archive-reproduction route.
3. All manuscript figure files exist and are regenerated or traceable from included scripts and tables.
4. Each number reported in the manuscript maps to a derived table or figure-statistics file.
5. `DATASETS_AND_LINKS.csv` is updated with exact included/excluded files and source-rights status.
6. Official Engineering Structures and Elsevier AI/data instructions are rechecked live immediately before submission.
7. No raw third-party records, active manuscript drafts, internal rounds/logs, credentials, or local conflict duplicate scripts are included in the public/reviewer package.

## Human Approval Points

- Public GitHub repository creation and push.
- Any repository sharing-permission changes.
- Final author declarations and AI-use disclosure.
- Final decision on whether to provide a private reviewer archive, a public reproducibility repository, or both.
- Final source-rights decision for derived ground-motion metadata and any third-party source-derived calibration tables.
