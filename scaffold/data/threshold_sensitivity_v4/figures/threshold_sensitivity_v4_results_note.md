# Threshold Sensitivity v4 Summary

This analysis reuses Sensitivity v3 Level-0 outputs and reruns only post-processing/MLE.
No additional OpenSees analyses are performed.

## Scenarios

- strict_0p8: all EDP limits scaled by 0.8.
- current_1p0: all EDP limits scaled by 1.0.
- relaxed_1p2: all EDP limits scaled by 1.2.

## Record-pool ledger

- current_1p0 | FF22 vs FF22: theta shift=+0.0%, beta_pool=0.000.
- current_1p0 | FFext vs FF22: theta shift=+30.7%, beta_pool=0.134.
- current_1p0 | NF28 vs FF22: theta shift=-36.0%, beta_pool=0.223.
- relaxed_1p2 | FF22 vs FF22: theta shift=+0.0%, beta_pool=0.000.
- relaxed_1p2 | FFext vs FF22: theta shift=+39.2%, beta_pool=0.165.
- relaxed_1p2 | NF28 vs FF22: theta shift=-35.9%, beta_pool=0.223.
- strict_0p8 | FF22 vs FF22: theta shift=+0.0%, beta_pool=0.000.
- strict_0p8 | FFext vs FF22: theta shift=+24.4%, beta_pool=0.109.
- strict_0p8 | NF28 vs FF22: theta shift=-34.0%, beta_pool=0.208.
