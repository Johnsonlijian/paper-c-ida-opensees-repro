# `paper-c-eesd` — Paper C (IDA) scaffold

Editable install (Python ≥3.11 recommended; 3.12 listed in `.python-version`):

```bash
cd scaffold
python -m pip install -e ".[dev]"
pytest -q
```

- If your environment cannot reach PyPI (e.g., HPC / offline), run tests without installing:

```powershell
$env:PYTHONPATH="src"
python -m pytest
```

- Core math: `src/paper_c_eesd/fragility/beta_decomposition.py`
- Fragility MLE: `src/paper_c_eesd/fragility/fit_fragility.py`
- Config: `configs/{default,pilot,full}.yaml` → `paper_c_eesd.utils.load_config`
- Stubs: `opensees_models/`, `ida/`

Implementation-stage deliverables (Paper C):

- Right-censored capacity MLE: `paper_c_eesd.fragility.fit_fragility.fit_lognormal_capacity_censored_mle`
- Run-level → collapse-level postprocess + mechanism labels: `paper_c_eesd.postprocess`
- Collect per-run outputs → Level-0 table: `python -m paper_c_eesd.postprocess.collect_runs --runs-root ... --out-csv ...`
- One-shot pipeline (Level-0 → Level-1 → censored MLE): `python -m paper_c_eesd.postprocess.pipeline --ida-raw-all-csv ... --out-dir ...`

Top-level **paper** markdown lives in the parent `paper-c-eesd-package/` directory (`00_README_MASTER.md` …).
