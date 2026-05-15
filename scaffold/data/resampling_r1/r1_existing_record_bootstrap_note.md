# R1 Existing-Record Bootstrap Summary

Bootstrap draws: B=1000; records per pool per draw=10; seed=20260513.

This is a record-level bootstrap over the completed Sensitivity v3 matrix. It reuses real
OpenSees-derived collapse observations and therefore does not add new ground motions beyond
the ten completed records per pool. It is a screening analysis for record-subset stability,
not a substitute for a full repeated OpenSees subset-resampling matrix over the broader pools.

| Contrast | B | median delta_logtheta | 5% | 95% | P(delta_logtheta < 0) | median PSI | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| FFext_vs_FF22 | 1000 | 0.272 | -0.148 | 0.710 | 0.147 | 0.141 | sign_sensitive_under_existing_record_bootstrap |
| NF28_vs_FF22 | 1000 | -0.436 | -0.820 | -0.046 | 0.972 | 0.218 | direction_stable_negative_in_existing_record_bootstrap |

Gate interpretation:

- If a contrast's 5-95% interval crosses zero, the manuscript must not report a stable directional shift for that contrast.
- If the interval is one-sided under this screening bootstrap, the manuscript may describe it as stable within the completed ten-record Sensitivity v3 set, not as production-scale evidence.

