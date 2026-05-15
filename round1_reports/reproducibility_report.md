# R36 Round-1 Reproducibility Report

Updated: 2026-05-15T17:14:16

## Command

Run-bank completion used resumable calls to:

`python tools/run_full_pool_resampling_r36.py --max-new-runs <N> --run-bank-only --use-completion-cache`

Final fitting and summary generation used:

`python tools/run_full_pool_resampling_r36.py --use-completion-cache`

## Inputs

- `data/ground_motions/_derived/gm_manifest.csv`
- `data/ground_motions/_derived/nf28_sorted_manifest.csv`
- `data/specimen_table_pilot_v1.csv`
- OpenSees executable resolved by the project script under `tools/opensees_bin/OpenSees3.8.0/bin/OpenSees.exe`

## Sampling

| record_set | n_eligible_records | eligibility_rule |
| --- | ---: | --- |
| FF22 | 123 | FEMA P-695 far-field AT2 horizontal components, vertical/UP excluded, duplicate `gm_id` removed |
| FFext | 159 | Expanded far-field AT2 horizontal components, vertical/UP excluded, duplicate `gm_id` removed |
| NF28 | 28 | Ready near-field horizontal components; one strongest component per base earthquake ID |

- Subset repetitions: `B = 10`
- Records per pool and subset: `10`
- Random seed: `20260514`
- Sampling: without replacement within each subset and pool
- IM grid and post-processing: fixed R36 protocol, right-censored lognormal MLE

## Execution Summary

- Expected unique run-bank runs: `10740`
- Completed OpenSees run-bank runs: `10740`
- Blocked/not run: `0`
- Final fitting executed: yes
- Data leakage check: PASS, 0 failed checks
- Local package test command: `PYTHONPATH=src python -m pytest -q`
- Local package test result: `17 passed in 116.78s`

## Main Results

| Contrast | median delta logtheta | 5% | 95% | P(delta logtheta < 0) | median capacity shift | 5-95% capacity-shift interval | Holm sign-test p | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| FFext vs FF22 | +0.096 | -0.194 | +0.328 | 0.30 | +10.0% | -17.6% to +38.8% | 0.344 | sign- and magnitude-sensitive |
| NF28 vs FF22 | -0.382 | -0.783 | -0.341 | 1.00 | -31.7% | -54.3% to -28.9% | 0.0039 | directionally stable negative |

## Output Files

- `data/full_pool_resampling_r36/r36_full_pool_subset_manifest.csv`
- `data/full_pool_resampling_r36/r36_ida_raw_all.csv`
- `data/full_pool_resampling_r36/r36_collapse_observations.csv`
- `data/full_pool_resampling_r36/r36_censored_mle_by_subset.csv`
- `data/full_pool_resampling_r36/r36_protocol_effect_distribution.csv`
- `data/full_pool_resampling_r36/r36_summary_table.csv`
- `data/full_pool_resampling_r36/r36_statistical_tests.csv`
- `docs/manuscript_drafts/figures/fig14_full_pool_resampling_delta_logtheta.png`
