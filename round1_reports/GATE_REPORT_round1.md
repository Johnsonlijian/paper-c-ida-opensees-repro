# GATE_REPORT Round 1

Generated: 2026-05-15T17:14:16

GATE: PASS_WITH_LIMITS

Round 1 is now complete for the R36 full-pool repeated-subset resampling design. The run bank reached zero blocked runs, the final censored-MLE fitting step executed, and the Round-1 statistical summary files were generated.

## R36 Run-Bank Status

| Metric | Value |
| --- | ---: |
| Expected unique run-bank runs | 10740 |
| Completed OpenSees run-bank runs | 10740 |
| Blocked/not yet run | 0 |
| Completion rate | 100.000% |
| Subset repetitions | 10 |
| Records per pool/subset | 10 |

## Main Gate Results

| Contrast | median delta logtheta | 5% | 95% | P(delta logtheta < 0) | median capacity shift | Holm sign-test p | Gate interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| FFext vs FF22 | +0.096 | -0.194 | +0.328 | 0.30 | +10.0% | 0.344 | sign- and magnitude-sensitive |
| NF28 vs FF22 | -0.382 | -0.783 | -0.341 | 1.00 | -31.7% | 0.0039 | directionally stable negative within the pilot protocol |

## PASS Conditions Met

- R36 run bank completed with `blocked_not_run = 0`.
- `r36_censored_mle_by_subset.csv` generated.
- `r36_protocol_effect_distribution.csv` generated.
- `r36_summary_table.csv` generated.
- `r36_statistical_tests.csv` generated.
- `fig14_full_pool_resampling_delta_logtheta.png` generated.
- Duplicate-record leakage checks passed.
- Local package test suite passed: `17 passed in 116.78s`.

## Limits Attached To PASS

- `B = 10` is a diagnostic repeated-subset design, not a production-scale Monte Carlo campaign.
- The specimen set remains the five-specimen pilot set.
- The component model remains a controlled nonlinear response generator, not a final design-calibrated CFST fragility model.
- The FFext contrast must not be written as a stable directional effect because the interval crosses zero and the sign-test screen is not significant.

## Manuscript Action

Use `ai_autoboost/revised_manuscript/manuscript_v1_r36.md` as the next working manuscript. It adds a new R36 Results subsection and updates the Abstract, Discussion, Limitations, Data Availability, and Figure Inventory.
