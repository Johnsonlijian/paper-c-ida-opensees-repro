# R34 Protocol Split Summary

Purpose: split the v2/v3 confounding between record selection/count and IM-grid definition.

Four cells are evaluated:

- `v2_N5_G5_existing`: existing Expanded Pilot v2, 5 records per pool and 5 IM levels.
- `r34_N5_G12_v2_records`: new R34 OpenSees runs for the v2-selected records on the 12-level fine grid.
- `r34_N10_G5_v3_records`: existing Sensitivity v3 Level-0 outputs filtered to the 5-level coarse grid.
- `v3_N10_G12_existing`: existing Sensitivity v3, 10 records per pool and 12 IM levels.

The v2 5-record selection is not a subset of the v3 10-record selection; each pool overlaps by only two records.
Therefore the record factor should be interpreted as a combined record-subset/count effect, not a pure count effect.

## Selection overlap

| Record set | v2 n | v3 n | overlap n | overlap gm_ids |
| --- | ---: | ---: | ---: | --- |
| FF22 | 5 | 10 | 2 | BOL090;CHY059-V |
| FFext | 5 | 10 | 2 | CHY059-V;STM090 |
| NF28 | 5 | 10 | 2 | NF8208252;NF8211652 |

## Record-pool ledger

| Scenario | Record set | theta | beta | shift vs FF22 (%) | delta logtheta | PSI |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v2_N5_G5_existing | FF22 | 0.3529 | 0.5919 | +0.0 | +0.000 | 0.000 |
| v2_N5_G5_existing | FFext | 0.2858 | 0.6165 | -19.0 | -0.211 | 0.105 |
| v2_N5_G5_existing | NF28 | 0.2173 | 0.2252 | -38.4 | -0.485 | 0.242 |
| r34_N5_G12_v2_records | FF22 | 0.2851 | 0.7281 | +0.0 | +0.000 | 0.000 |
| r34_N5_G12_v2_records | FFext | 0.2140 | 0.7761 | -24.9 | -0.287 | 0.143 |
| r34_N5_G12_v2_records | NF28 | 0.1401 | 0.4406 | -50.8 | -0.710 | 0.355 |
| r34_N10_G5_v3_records | FF22 | 0.2828 | 0.5329 | +0.0 | +0.000 | 0.000 |
| r34_N10_G5_v3_records | FFext | 0.3283 | 0.5381 | +16.1 | +0.149 | 0.075 |
| r34_N10_G5_v3_records | NF28 | 0.2144 | 0.2079 | -24.2 | -0.277 | 0.138 |
| v3_N10_G12_existing | FF22 | 0.2070 | 0.7160 | +0.0 | +0.000 | 0.000 |
| v3_N10_G12_existing | FFext | 0.2706 | 0.6321 | +30.7 | +0.268 | 0.134 |
| v3_N10_G12_existing | NF28 | 0.1326 | 0.4133 | -36.0 | -0.446 | 0.223 |

## Decomposition

| Contrast | grid effect, v2 records | grid effect, v3 records | subset/count effect, coarse grid | subset/count effect, fine grid | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| FFext_vs_FF22 | -0.076 | +0.118 | +0.360 | +0.554 | record_subset_count_sensitive_across_grids |
| NF28_vs_FF22 | -0.226 | -0.169 | +0.208 | +0.264 | negative_in_all_four_cells |

Gate interpretation:

- If a contrast changes sign across cells, the manuscript must not present it as a stable record-pool direction.
- If a contrast remains one-sided across all four cells, it can be described as stable across this protocol split, still conditional on the pilot specimen/model family.
- Large grid or subset/count deltas should be reported as active protocol factors rather than folded into a single record-pool claim.
