# FOUR_MODEL_REVIEW Round 1 Post-R36 Synthesis

Generated: 2026-05-15

Input reviewed: `ai_autoboost/revised_manuscript/manuscript_v1_r36.md`

External panel status:

- DeepSeek: returned.
- Kimi: returned.
- MiniMax: failed with HTTP 429 insufficient balance.
- Doubao: returned.

## Main Findings Converted To Actions

| Source | Finding | Action taken |
| --- | --- | --- |
| DeepSeek | Central narrative should emphasize a reusable audit workflow, not a model-specific near-field conclusion. | R36 discussion keeps the claim as bounded protocol sensitivity and avoids universal correction language. |
| Kimi | `10,740 unique analyses` can look inconsistent with `10 subsets x 5 specimens x 10 records x 12 IM x 3 pools = 18,000`; explain cross-subset reuse. | Added explicit explanation in Section 4.10: each unique record-specimen-IM combination is run once and reused across subset appearances. |
| Doubao | Right-censored MLE and environment reproducibility need hard evidence. | Ran local tests: `17 passed in 116.78s`; added MLE test statement in Section 3.4 and reproducibility report. |
| Doubao | Statistical test wording needs the null hypothesis and small-B interpretation. | Added sign-test null, Holm-adjustment scope, and diagnostic interpretation after the R36 table. |

## Remaining Risks

- Model-form uncertainty remains the largest desk-risk; the paper must stay positioned as a diagnostic protocol-sensitivity manuscript.
- Public repository/archive URL is still not inserted.
- Final target-journal formatting and live author-instruction check remain pending.

## Gate Decision

Round 1 remains `PASS_WITH_LIMITS`: R36 evidence is now strong enough for the bounded manuscript claim, but not enough for production-scale CFST fragility claims.
