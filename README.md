# Paper C Reproducibility Package

This package supports the manuscript:

**Record-pool and protocol sensitivity in component-level seismic fragility estimation: censored IDA evidence from pilot CFST column models**

The package is prepared for the EEEV submission-preparation route and updated after the R36 full-pool repeated-subset run bank:

- a public GitHub repository for redistributable code, configuration, derived tables, generated figures, and run instructions;
- a private reviewer archive for submission-stage review where needed, maintained outside this public repository.

If this package is viewed through the GitHub repository, the repository is the public release of the redistributable reproducibility materials. No DOI or private reviewer archive identifier is claimed unless separately stated.

## Contents

- `scaffold/src/`: Python package for fragility fitting, IDA helpers, ground-motion reading, and post-processing.
- `scaffold/tools/`: analysis and figure-generation scripts.
- `scaffold/configs/`: configuration files.
- `scaffold/data/`: derived tables, manifests, and generated outputs included according to `DATASETS_AND_LINKS.csv`.
- `DATASETS_AND_LINKS.csv`: file-level manifest and redistribution boundary.
- `REPRODUCIBLE_RUNBOOK.md`: reviewer-facing setup and reproduction route.
- `EXECUTION_CHECKLIST.csv`: package execution status and remaining full-regeneration logs.

## Quick Test

```powershell
cd scaffold
python -m pip install ".[dev]"
python -m pytest
```

On 2026-05-15, the post-R36 local test route passed with 17 tests. Editable install is not the default reviewer command under the current Windows/NAS path because non-ASCII path handling previously produced a broken editable `.pth` file.

## Public-Release Boundary

The public package excludes raw third-party ground-motion records, active manuscript drafts, internal `rounds/`, internal `logs/`, credentials, local virtual environments, and files with unclear redistribution rights. Raw records should be accessed from their original citable sources where applicable.
