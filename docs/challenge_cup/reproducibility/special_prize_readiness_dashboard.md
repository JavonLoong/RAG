# Special Prize Readiness Dashboard

- report_type: `challenge_cup_special_prize_readiness_dashboard`
- status: `special_prize_review_ready_with_external_evidence_gaps`
- no_award_guarantee=True
- completion_claim_allowed: `False`
- can_mark_goal_complete: `False`
- latest_public_result_source_id: `tsinghua_44th_2026`
- max_special_prize_count: `7`
- may_be_vacant: `True`

## Rubric Readiness

| Dimension | Readiness | Judge Message | Defense Action | Evidence Count |
| --- | --- | --- | --- | ---: |
| 学术/实用价值 | `strong_evidence_linked` | The project has a concrete power-equipment knowledge scenario and auditable evidence chain. | Lead with the fixed GT-07 maintenance scenario and show why evidence-bound retrieval matters. | 5 |
| 创新性 | `strong_evidence_linked` | The differentiator is evidence-bound GraphRAG plus failure analysis, not a generic RAG wrapper. | Contrast keyword/RAG/GraphRAG on the same-question subset and explain evidence-bound graph construction. | 5 |
| 作品完成度 | `strong_evidence_linked` | The submission package, verifier, demo smoke reports, and reproducibility gates are already packaged. | Open the package manifest, readiness gate, archive verifier, and browser smoke evidence. | 5 |
| 现场答辩 | `ready_with_external_gap` | The defense materials are ready, but a real timed rehearsal must still be archived. | Run the three-minute script against the scorecard and archive a real timed rehearsal. | 5 |
| 学术规范与严谨表述 | `strong_evidence_linked` | The package explicitly preserves unfinished external-evidence boundaries. | State boundaries before judges ask: no production claim, no expert approval claim, no award guarantee. | 4 |

## Top Risks

- `expert_feedback`: unclosed_external_hard_evidence -> `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md`
- `timed_rehearsal`: unclosed_external_hard_evidence -> `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md`
- `award_overclaim`: controlled_by_boundary -> `docs/challenge_cup/reproducibility/official_rubric_alignment.md`

## Next Action Files

- `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md`
- `docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md`

## Verification Commands

- `python scripts/build_challenge_cup_special_prize_readiness_dashboard.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`

## Boundary

This dashboard translates public Tsinghua Challenge Cup rubric signals into defense actions. It does not guarantee an award and does not close the goal while real expert feedback and real timed rehearsal evidence remain unarchived.
