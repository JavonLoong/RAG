# Official Source Recheck Pack

- report_type: `challenge_cup_official_source_recheck_pack`
- status: `ready_for_final_submission_source_recheck`
- generated_from: `docs/challenge_cup/reproducibility/official_rubric_alignment.json`
- source_lock_current_as_of: `2026-06-07`
- latest_public_result_source_id: `tsinghua_44th_2026`
- manual_web_recheck_required: `True`
- completion_claim_allowed: `False`
- no_award_guarantee: `True`
- does_not_satisfy_goal_completion: `True`

## Source Recheck Items

| Source | Action | URL | Snapshot | Anchor Terms |
| --- | --- | --- | --- | --- |
| `tsinghua_44th_2026` | `open_official_url_and_compare_anchor_terms` | https://www.tsinghua.edu.cn/info/1177/125861.htm | `docs/challenge_cup/reproducibility/official_source_snapshots/tsinghua_44th_2026.md`<br>`snapshot_sha256=99e1fdc19cf890f00e124851d148d76f8039a7ab7c5c80cd0f913d0106869b5c` | 终审答辩于2026年4月25日开展<br>报名作品337件<br>173件本科生作品和9件研究生作品进入校级终审<br>主赛道共产生114项获奖作品 |
| `tsinghua_ee_44th_2026` | `open_official_url_and_compare_anchor_terms` | https://www.ee.tsinghua.edu.cn/info/1076/5199.htm | `docs/challenge_cup/reproducibility/official_source_snapshots/tsinghua_ee_44th_2026.md`<br>`snapshot_sha256=cb7742f7512ec30f06525477008198742c0909bed3e6a3422b43e27c849a0ec8` | 第44届竞赛中电子系获得特等奖1项、一等奖1项、二等奖2项<br>电子系在本届竞赛中院系总分第一，时隔22年再次荣获清华大学挑战杯<br>特等奖项目公开列明了问题、方法、评估结果和论文投稿等成果线索 |
| `tsinghua_auto_44th_2026` | `open_official_url_and_compare_anchor_terms` | https://www.au.tsinghua.edu.cn/info/1235/4520.htm | `docs/challenge_cup/reproducibility/official_source_snapshots/tsinghua_auto_44th_2026.md`<br>`snapshot_sha256=f6d09597adf1d2f69b15fb0552ee80014e54b5277877fc7ee65ffd92ccb61948` | 自动化系六组选手夺得团体第五名，时隔五年再次荣获竞赛优胜杯<br>自动化系最终收获四项二等奖、两项三等奖<br>优胜杯级院系表现仍可能没有特等奖，材料不得把准备充分写成获奖保证 |
| `tsinghua_43rd_2025` | `open_official_url_and_compare_anchor_terms` | https://www.tsinghua.edu.cn/info/1176/118626.htm | `docs/challenge_cup/reproducibility/official_source_snapshots/tsinghua_43rd_2025.md`<br>`snapshot_sha256=7df26049e1ef24f5b9a0947ae5d92a3dc00478d7266a408f59d527b412590d7a` | 2025年4月10日开展终审答辩<br>主赛道特等奖6项<br>清华挑战杯是学校历史最长、规模最大、水平最高的综合性学生课外学术科技作品竞赛<br>鼓励立足重要领域的关键应用场景，做勇于创新、善于创新的清华青年 |
| `tsinghua_39th_2021` | `open_official_url_and_compare_anchor_terms` | https://www.tsinghua.edu.cn/info/1175/82720.htm | `docs/challenge_cup/reproducibility/official_source_snapshots/tsinghua_39th_2021.md`<br>`snapshot_sha256=d91c594453d42c2573247eea498dc9599948483d20d3a6c3bc990118529f0344` | 评分维度包括学术/实用价值、创新性、作品完成度、现场答辩及墙报问辩表现<br>每个分场至多推荐一项作品参加特等奖评比<br>本届最终评选出特等奖6项 |
| `tsinghua_37th_2019` | `open_official_url_and_compare_anchor_terms` | https://www.tsinghua.edu.cn/info/1181/35383.htm | `docs/challenge_cup/reproducibility/official_source_snapshots/tsinghua_37th_2019.md`<br>`snapshot_sha256=1c83f88d215b2f01355a1771f438e11e96c47e7f6277262233a1255ee09ad82f` | 强调遵守比赛规则、恪守学术规范和学术成果表述严谨性<br>评委从学术价值或实用性、创新性、作品完成情况和现场答辩表现四个方面评分<br>特等奖候选作品参与公开答辩并由评委综合评定 |
| `tsinghua_rules_pdf_2017` | `open_official_url_and_compare_anchor_terms` | https://qiyuan.tsinghua.edu.cn/intro/2018/11024/%E6%94%AF%E6%92%91%E6%9D%90%E6%96%993-%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E8%AF%BE%E5%A4%96%E5%88%9B%E6%96%B0%E4%BA%BA%E6%89%8D%E5%9F%B9%E5%85%BB%E4%BD%93%E7%B3%BB%E5%88%B6%E5%BA%A6%E6%96%87%E4%BB%B6%E6%B1%87%E7%BC%96.pdf | `docs/challenge_cup/reproducibility/official_source_snapshots/tsinghua_rules_pdf_2017.md`<br>`snapshot_sha256=7990debef94f7e5bb10f5649d607135b780a66eaba6c1f4b7e1c54629b996101` | 评审应考虑作品实用性、创新性和学术价值<br>特等奖不超过6件，可空缺<br>竞赛规程由清华相关部门和学生科协共同发布 |

## Final Submission Checks

| Check | Required Action | Acceptance Signal |
| --- | --- | --- |
| `official_url_access` | open_each_official_tsinghua_url | Every official URL opens from the final review machine or has an archived official attachment. |
| `latest_public_result_not_superseded` | search_for_new_tsinghua_challenge_cup_notice_or_result_page | No new Tsinghua Challenge Cup official notice or result page supersedes the locked latest_public_result. |
| `rubric_dimension_recheck` | compare_locked_rubric_dimensions_against_public_sources | Academic/practical value, innovation, completion, and defense-performance dimensions remain supportable. |
| `department_benchmark_recheck` | reopen_44th_department_benchmark_sources | Department benchmark signals remain official Tsinghua-domain sources and are not used as award guarantees. |
| `boundary_recheck` | confirm_no_award_or_external_validation_overclaim | The package still says no award guarantee and does not satisfy goal completion without real hard evidence. |

## Rerun Commands

- `python scripts/build_challenge_cup_official_source_recheck_pack.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`

## Boundary

This pack is a final-submission work order for manual official-source freshness checks. It makes no award guarantee, does not claim expert approval, does not replace real external feedback or a real timed rehearsal, and does not satisfy goal completion.
