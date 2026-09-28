# 长文档检索包（本机标注 JSON 抽出）

源文件只在本机，不进 Git：

`%LOCALAPPDATA%\PowerRAG\current_console\uploads\project-1-at-2026-05-21-06-17-203caed5.json`

抽出的 `.txt` 同样不提交（见本目录 `.gitignore`）。作答线程只读这些正文。

| 文件 | 原 PDF | 页 | 用途 |
| --- | --- | ---: | --- |
| oil_skid_manual.txt | 压缩机滑油站 XYHZ-300 说明书（卷内含附件） | 468 | 超长检索 |
| cgt25_da_summary.txt | CGT25-DA 燃驱压缩机组经验总结 | 143 | 超长 + 统计表 |
| gearbox_failure_20250918.txt | 北极 LNG2 下部传动箱故障分析 | 53 | 综合结论 |
| yandun_july2020_summary.txt | 2020 年 7 月烟墩现场工作总结 | 41 | 跨文档综合 |
| yandun_unit2_trip.txt | 烟墩 2# 滑油总管压力低停机 | 11 | 跨文档综合 |
| hp_turbine_coating_crack.txt | X25 高压涡轮动叶涂层裂纹 | 64 | 跨项目对照 |
| wuzhou_bevel_gear_20240513.txt | 传动箱锥齿轮断裂（中科院金属所） | 45 | 传动箱干扰项 |
| power_turbine_zeroing_322097.txt | 322097 动力涡轮故障归零 | 27 | 第三处金属屑 |
