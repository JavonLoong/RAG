# 公开书籍 Label Studio JSON 入库前检测报告

- 检测时间：2026-05-24 22:09:40
- 使用快照：`project-1-at-2026-05-21-06-17-203caed5.json`
- 快照任务数：3961
- 抽取文本块数：54443

## 结论

1. 这 27 个 JSON 是同一项目的连续导出快照，后一个基本包含前一个；入库时应使用最新快照，避免重复入库。
2. JSON 里人工标注是图片页上的框和转写文本，不能直接把整页 JSON 入库；必须先按框抽出文本块，再筛掉表格噪声、图片说明、页眉页脚和过短片段。
3. 当前正文 `Para` 不是完整自然段，很多是按行切开的短片段；入 ChromaDB 前必须按同一页的坐标顺序合并相邻 `Para`，否则检索会碎。
4. `Table`、`Figure`、`Formula` 不能默认作为正文入库；建议进入人工复核或只作为 metadata/caption。

## 快照检查

| 文件 | 大小MB | 任务数 | 新增任务 | 是否包含上一版 |
|---|---:|---:|---:|---|
| project-1-at-2026-05-19-02-14-66b32a99.json | 45.49 | 3583 | 3583 |  |
| project-1-at-2026-05-19-02-30-a7ea9edc.json | 46.19 | 3598 | 15 | True |
| project-1-at-2026-05-19-02-40-27eaf957.json | 46.94 | 3613 | 15 | True |
| project-1-at-2026-05-19-03-03-1d8ef200.json | 47.76 | 3628 | 15 | True |
| project-1-at-2026-05-19-03-05-578140b7.json | 48.47 | 3643 | 15 | True |
| project-1-at-2026-05-19-04-14-ef170eef.json | 49.04 | 3654 | 11 | True |
| project-1-at-2026-05-19-05-54-186dcedb.json | 49.65 | 3665 | 11 | True |
| project-1-at-2026-05-19-06-02-56b1befb.json | 50.14 | 3675 | 10 | True |
| project-1-at-2026-05-19-06-10-152b4d0d.json | 50.77 | 3685 | 10 | True |
| project-1-at-2026-05-19-06-21-0dedc144.json | 51.29 | 3695 | 10 | True |
| project-1-at-2026-05-19-07-38-d1daa5dd.json | 51.84 | 3707 | 12 | True |
| project-1-at-2026-05-19-07-45-c25af092.json | 52.4 | 3719 | 12 | True |
| project-1-at-2026-05-19-07-55-30513816.json | 53.12 | 3731 | 12 | True |
| project-1-at-2026-05-19-08-03-207b64fa.json | 53.75 | 3742 | 11 | True |
| project-1-at-2026-05-19-08-10-28b5dbce.json | 54.31 | 3753 | 11 | True |
| project-1-at-2026-05-20-02-57-883eb4bc.json | 55.3 | 3771 | 18 | True |
| project-1-at-2026-05-20-03-14-bfd5082b.json | 56.09 | 3789 | 18 | True |
| project-1-at-2026-05-20-05-25-33f2af43.json | 56.84 | 3806 | 17 | True |
| project-1-at-2026-05-20-06-09-6da74160.json | 57.51 | 3823 | 17 | True |
| project-1-at-2026-05-20-06-24-eeec792a.json | 58.35 | 3841 | 18 | True |
| project-1-at-2026-05-20-07-01-e88df5ba.json | 59.28 | 3859 | 18 | True |
| project-1-at-2026-05-20-07-50-7df8ce0b.json | 60.12 | 3876 | 17 | True |
| project-1-at-2026-05-20-08-14-e54947d3.json | 60.97 | 3893 | 17 | True |
| project-1-at-2026-05-21-01-04-f35e219b.json | 61.74 | 3909 | 16 | True |
| project-1-at-2026-05-21-01-45-6dfa4ce9.json | 62.53 | 3927 | 18 | True |
| project-1-at-2026-05-21-02-52-d6b03b38.json | 63.3 | 3944 | 17 | True |
| project-1-at-2026-05-21-06-17-203caed5.json | 64.31 | 3961 | 17 | True |

## 每本书/文件覆盖情况

| 文件 | 页数 | 标注页 | 文本块 | 可直接入库 | 需复核 | 建议不入库 |
|---|---:|---:|---:|---:|---:|---:|
| 0001-0075_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__1.pdf | 15 | 13 | 550 | 180 | 61 | 301 |
| 0001-0075_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__2.pdf | 15 | 15 | 665 | 321 | 141 | 173 |
| 0001-0075_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__3.pdf | 15 | 15 | 732 | 316 | 153 | 217 |
| 0001-0075_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__4.pdf | 15 | 15 | 785 | 265 | 269 | 229 |
| 0001-0075_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__5.pdf | 15 | 15 | 677 | 321 | 152 | 184 |
| 0076-0127_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_5.pdf | 10 | 10 | 470 | 348 | 43 | 55 |
| 0076-0127_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__Qing_Hua_Da_Xue_Re_Neng_Gong_Cheng_Xi_Dong_Li_Ji_Jie_Yu_Gong_Cheng_Yan_Jiu_Suo___1.pdf | 11 | 11 | 535 | 301 | 111 | 92 |
| 0076-0127_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang___4.pdf | 10 | 10 | 584 | 309 | 137 | 123 |
| 0076-0127_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang____2.pdf | 11 | 11 | 560 | 309 | 133 | 107 |
| 0076-0127_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang____3.pdf | 10 | 10 | 432 | 275 | 87 | 64 |
| 0128-0185_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_1.pdf | 12 | 12 | 497 | 313 | 76 | 91 |
| 0128-0185_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_3.pdf | 12 | 12 | 687 | 259 | 216 | 200 |
| 0128-0185_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_4.pdf | 11 | 11 | 618 | 183 | 232 | 189 |
| 0128-0185_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_5.pdf | 11 | 11 | 505 | 209 | 175 | 108 |
| 0128-0185_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__2_Drec1w6.pdf | 12 | 12 | 521 | 265 | 142 | 98 |
| 0186-0238_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_3.pdf | 17 | 17 | 674 | 448 | 82 | 97 |
| 0186-0238_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__1.pdf | 18 | 18 | 893 | 420 | 244 | 177 |
| 0186-0238_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__2.pdf | 18 | 18 | 727 | 509 | 53 | 108 |
| 0239-0292_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_2.pdf | 18 | 18 | 777 | 422 | 177 | 155 |
| 0239-0292_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__1.pdf | 18 | 17 | 599 | 381 | 64 | 119 |
| 0239-0292_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__3.pdf | 18 | 18 | 855 | 482 | 231 | 114 |
| 0293-0342_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang___1.pdf | 17 | 17 | 749 | 448 | 172 | 97 |
| 0293-0342_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang___2.pdf | 17 | 17 | 751 | 522 | 108 | 98 |
| 0293-0342_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang____3_LUZK4cU.pdf | 16 | 16 | 681 | 538 | 36 | 81 |
| 0343-0394_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang_2.pdf | 17 | 17 | 687 | 467 | 55 | 115 |
| 0343-0394_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__3.pdf | 17 | 17 | 939 | 437 | 297 | 176 |
| 0343-0394_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang___1.pdf | 18 | 18 | 698 | 522 | 21 | 110 |
| 1-Gu_Zhang_Xin_Xi_Bao_Gao_Dan_-Wu_Zhou_Da_Xiao_Di_Jia_Luo_Shuan_Kong_Cuo_Wei_-Wai_Ti_.pdf | 7 | 7 | 31 | 6 | 4 | 15 |
| 11Yue_18Ri_Yan_Dun_2Ji_Zu_Gu_Zhang_Bao_Gao_.pdf | 1 | 1 | 34 | 18 | 10 | 3 |
| 11Yue_18Ri_Yan_Dun_2Ji_Zu_Gu_Zhang_Bao_Gao__snF9RrS.pdf | 1 | 1 | 34 | 18 | 10 | 3 |
| 1Ran_Ji_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_La_Gan_Duan_Lie_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 37 | 22 | 3 | 9 |
| 1Ran_Ji_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_La_Gan_Duan_Lie_Xiu_Fu_Fang_An__TGYgYXx.pdf | 7 | 7 | 37 | 22 | 3 | 9 |
| 20191103Wu_Zhou_Zhan_Ri_Bao_--Nei_Bu_.pdf | 3 | 3 | 21 | 8 | 1 | 5 |
| 20200817Yan_Dun_Ri_Bao_.pdf | 12 | 12 | 45 | 8 | 12 | 22 |
| 20200817Yan_Dun_Ri_Bao__DB64Pxk.pdf | 12 | 12 | 45 | 8 | 12 | 22 |
| 2020Nian_7Yue_Yan_Dun_Xian_Chang_Gong_Zuo_Zong_Jie_.pdf | 41 | 41 | 568 | 350 | 33 | 128 |
| 2020Nian_7Yue_Yan_Dun_Xian_Chang_Gong_Zuo_Zong_Jie__P5vR3BU.pdf | 41 | 30 | 401 | 248 | 24 | 86 |
| 2020Nian_7Yue_Yan_Dun_Xian_Chang_Gong_Zuo_Zong_Jie__q8eqYli.pdf | 41 | 41 | 569 | 352 | 33 | 127 |
| 2024.05.13_Wu_Zhou_Chuan_Dong_Xiang_Zhui_Chi_Lun_Duan_Lie_Shi_Xiao_Fen_Xi_-Zhong_Ban_.pdf | 46 | 45 | 437 | 279 | 14 | 81 |
| 2024.10.17_Yan_Dun_1Ji_Zu_Gao_Ya_Fang_Qi_Fa_Zhi_Guan_Duan_Han_Kou_Kai_Lie_.pdf | 2 | 1 | 4 | 0 | 1 | 3 |
| 2024.10.21_Yan_Fa_Gei_De_Fang_An__Guan_Yu_Yan_Dun_1Dian_Ci_Fa_Pai_Shui_Wen_Ti_20240724.pdf | 2 | 2 | 12 | 8 | 0 | 3 |
| 2024.11.11_Yan_Dun_Lou_Qi_Qing_Kuang_Shuo_Ming__Yi_Dao_Ru_Nei_Wang_Zou_Gu_Zhang_Xin_Xi_Dan__Ji_Xia_Lou_Qi_1Xiang_Yi_Liu_.pdf | 7 | 7 | 56 | 18 | 6 | 14 |
| 2024_7t7lyKU.10.17_Yan_Dun_1Ji_Zu_Gao_Ya_Fang_Qi_Fa_Zhi_Guan_Duan_Han_Kou_Kai_Lie_.pdf | 2 | 1 | 4 | 0 | 1 | 3 |
| 2024_GcNPL0I.10.21_Yan_Fa_Gei_De_Fang_An__Guan_Yu_Yan_Dun_1Dian_Ci_Fa_Pai_Shui_Wen_Ti_20240724.pdf | 2 | 2 | 11 | 7 | 0 | 3 |
| 2024_nYptxNa.11.11_Yan_Dun_Lou_Qi_Qing_Kuang_Shuo_Ming__Yi_Dao_Ru_Nei_Wang_Zou_Gu_Zhang_Xin_Xi_Dan__Ji_Xia_Lou_Qi_1Xiang_Yi_Liu_.pdf | 7 | 7 | 56 | 18 | 6 | 14 |
| 2025-09-18_Xia_Bu_Chuan_Dong_Xiang_Gu_Zhang_Yuan_Yin_Fen_Xi_Bao_Gao_-v5.pdf | 54 | 53 | 605 | 290 | 120 | 94 |
| 2025.01.26GH25-E-026-1-1910Di_Ya_Liu_Ji_Fang_Qi_Fa_Yi_Zu_Da_Bu_Kai_.pdf | 3 | 3 | 21 | 13 | 2 | 5 |
| 20250714-038-0725.pdf | 11 | 11 | 277 | 229 | 2 | 45 |
| 2Ji_Zu_Ke_Diao_Dao_Xie_Gu_Zhang_Bao_Gao_-Yao_20201220.pdf | 2 | 2 | 27 | 12 | 7 | 0 |
| 2Ji_Zu_Ke_Diao_Dao_Xie_Gu_Zhang_Bao_Gao_-Yao_20201220_cZWCMjQ.pdf | 2 | 2 | 27 | 12 | 7 | 0 |
| 322007Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 59 | 8 | 2 | 48 |
| 322007Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 60 | 8 | 2 | 49 |
| 322008Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 58 | 9 | 2 | 46 |
| 322008Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 59 | 8 | 3 | 47 |
| 322014Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 58 | 9 | 2 | 46 |
| 322014Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 60 | 9 | 2 | 48 |
| 322015Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 59 | 8 | 2 | 48 |
| 322015Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 60 | 8 | 2 | 49 |
| 322020Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 60 | 9 | 2 | 48 |
| 322020Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 60 | 8 | 2 | 49 |
| 322025Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 59 | 8 | 2 | 48 |
| 322026Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 59 | 9 | 2 | 47 |
| 322032Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 56 | 7 | 2 | 46 |
| 322033Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 57 | 8 | 2 | 46 |
| 322033Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 59 | 8 | 2 | 48 |
| 322037Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 58 | 8 | 2 | 47 |
| 322037Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 60 | 8 | 2 | 49 |
| 322038Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 58 | 9 | 2 | 46 |
| 322038Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 60 | 8 | 2 | 49 |
| 322039Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 59 | 8 | 2 | 48 |
| 322039Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 60 | 8 | 2 | 49 |
| 322042Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 63 | 8 | 3 | 51 |
| 322042Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 63 | 7 | 4 | 51 |
| 322045Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 57 | 9 | 2 | 45 |
| 322048Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322049Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 7 | 2 | 46 |
| 322049Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 57 | 6 | 2 | 48 |
| 322051Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 56 | 6 | 2 | 47 |
| 322055Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 56 | 7 | 2 | 46 |
| 322055Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_Ya_Qi_Ji_Gu_Zhang_Chu_Cang_.pdf | 7 | 7 | 64 | 9 | 2 | 52 |
| 322058Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 62 | 8 | 2 | 51 |
| 322058Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 62 | 7 | 3 | 51 |
| 322060Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322060Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 6 | 2 | 49 |
| 322065Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322065Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 57 | 6 | 2 | 48 |
| 322066Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322066Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 57 | 6 | 2 | 48 |
| 322067Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 57 | 8 | 2 | 46 |
| 322067Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 57 | 7 | 2 | 47 |
| 322069Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 57 | 8 | 2 | 46 |
| 322069Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 57 | 7 | 2 | 47 |
| 322073Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322074Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 57 | 7 | 2 | 47 |
| 322075Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322075Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 7 | 2 | 48 |
| 322076Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322076Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 6 | 2 | 49 |
| 322078Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322079Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322079Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 57 | 6 | 2 | 48 |
| 322080Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 61 | 6 | 2 | 52 |
| 322080Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 62 | 6 | 3 | 52 |
| 322082Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 57 | 6 | 2 | 48 |
| 322082Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 6 | 2 | 49 |
| 322083Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 57 | 6 | 2 | 48 |
| 322083Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 6 | 2 | 49 |
| 322085Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 60 | 6 | 3 | 50 |
| 322085Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 6 | 2 | 49 |
| 322090Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 58 | 8 | 2 | 47 |
| 322090Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 7 | 2 | 48 |
| 322092Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 57 | 7 | 2 | 47 |
| 322092Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 7 | 3 | 47 |
| 322095Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 56 | 6 | 2 | 47 |
| 322095Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 57 | 6 | 2 | 48 |
| 322096Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 56 | 6 | 2 | 47 |
| 322096Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 6 | 2 | 49 |
| 322097Dong_Li_Wo_Lun_Gu_Zhang_Gui_Ling_Bao_Gao_.pdf | 28 | 27 | 379 | 239 | 36 | 49 |
| 322100Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 60 | 10 | 2 | 47 |
| 322100Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 61 | 10 | 2 | 48 |
| 322101Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 59 | 7 | 2 | 49 |
| 322101Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 61 | 6 | 4 | 50 |
| 322102Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 57 | 8 | 2 | 46 |
| 322107Dong_Li_Wo_Lun_Xiu_Fu_Fang_An__.pdf | 7 | 7 | 60 | 6 | 2 | 51 |
| 322107Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie__.pdf | 7 | 7 | 62 | 6 | 3 | 52 |
| 322108Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 62 | 7 | 3 | 51 |
| 322108Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 62 | 6 | 4 | 51 |
| 322109Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 57 | 7 | 2 | 47 |
| 322109Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 7 | 2 | 48 |
| 322110Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 7 | 2 | 46 |
| 322110Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 58 | 7 | 2 | 48 |
| 322111Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 6 | 6 | 56 | 6 | 2 | 47 |
| 322112Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322117Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 56 | 6 | 2 | 47 |
| 322164Dong_Li_Wo_Lun_Xiu_Fu_Fang_An_.pdf | 7 | 7 | 61 | 6 | 3 | 51 |
| 322164Dong_Li_Wo_Lun_Xiu_Fu_Zong_Jie_.pdf | 7 | 7 | 62 | 6 | 4 | 51 |
| Bei_Ji_LNG2Jin_Shu_Bo_Wen_Guan_Gu_Zhang_Yuan_Yin_Fen_Xi_Bao_Gao__.pdf | 5 | 5 | 65 | 31 | 2 | 24 |
| CGT25-DARan_Qu_Ya_Suo_Ji_Zu_Zong_Jie_Bao_Gao_lastsss.pdf | 147 | 143 | 1713 | 929 | 231 | 275 |
| CGT25-DARan_Qu_Ya_Suo_Ji_Zu_Zong_Jie_Bao_Gao_lastsss_AY4S0dp.pdf | 147 | 143 | 1809 | 973 | 246 | 311 |
| CGT25-DARan_Qu_Ya_Suo_Ji_Zu_Zong_Jie_Bao_Gao_lastsss_ilLvaKv.pdf | 147 | 143 | 1808 | 972 | 246 | 311 |
| Cheng_Lin_Ti_Gong_-Dong_Hai_Ping_Tai_Tong_Feng_Feng_Ji_Xie_Pian_Duan_Lie_Zheng_Gai_-L21.pdf | 7 | 7 | 59 | 23 | 4 | 16 |
| Cu_Lu_Lu_Xin_.pdf | 2 | 2 | 7 | 0 | 1 | 5 |
| Cu_Lu_Lu_Xin__eIWBLv8.pdf | 2 | 2 | 7 | 0 | 1 | 5 |
| Cu_Lu_Lu_Xin__oLooygL.pdf | 2 | 2 | 7 | 0 | 1 | 5 |
| Cu_Lu_Lu_Xin__t73rIEq.pdf | 2 | 2 | 7 | 0 | 1 | 5 |
| DH01-20250511_CJi_Feng_Ji_Xie_Pian_Duan_Lie_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| DH02-20250522_BJi_Ke_Zhuan_Dao_Xie_Zhi_Xing_Ji_Gou_Gu_Zhang_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| DH03-20250523_BJi_Feng_Ji_Xie_Pian_Duan_Lie_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| DH04-20250523_CJi_Guo_Du_Duan_Xiang_Gao_Ya_Hou_Ji_Xia_Gong_Qi_Bo_Wen_Guan_Bo_Wen_Guan_Duan_Lie_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| DH05-20250603_BJi_Dong_Li_Wo_Lun_Zhuan_Su_Chuan_Gan_Qi_Tiao_Bian_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| DH06-20250614_BJi_Gong_You_Ya_Li_Di_Jian_Cha_.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| DH07-20250616_BJi_Gao_Ya_Wu_Ji_Fang_Qi_Fa_Guan_Lu_Guan_Qia_Duan_Lie_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| DH08-20250616_CJi_Xia_Chuan_Dong_Jin_Shu_Xie_Bao_Jing_.pdf | 6 | 6 | 12 | 0 | 1 | 11 |
| DH09-20250619_BJi_XS113Jin_Shu_Xie_Tan_Tou_Bao_Jing_.pdf | 4 | 4 | 7 | 0 | 1 | 6 |
| DH10-20250706_BJi_Yin_Ya_Guan_Gan_She_Mo_Sun_.pdf | 4 | 4 | 9 | 0 | 1 | 8 |
| DH11-20250707_BJi_Yan_Dao_Yin_Qi_Guan_Tuo_Luo_.pdf | 6 | 6 | 11 | 0 | 1 | 10 |
| DH12-202507015BJi_Gao_Ya_Zhuan_Su_Chuan_Gan_Qi_Bo_Dong_.pdf | 3 | 3 | 4 | 0 | 2 | 2 |
| DH13-20250818BJi_Gao_Ya_Fang_Qi_Fa_Fa_Lan_Kou_Duan_Lie_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| DH14-20250818BPai_Qi_Kuo_Zhang_Duan_Bao_Wen_Mian_Tuo_Luo_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| DH15-20250825BJi_Ran_Ji_Hua_You_Qiao_You_Wu_Feng_Ji_De_Dian_Ji_Gu_Zhang__-_Fu_Ben_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| DH16-20250810_BJi_Di_Ya_Liu_Ji_Fang_Qi_Fa_Wei_Zheng_Chang_Kai_Qi_.pdf | 2 | 2 | 3 | 0 | 1 | 1 |
| DH16-20250909_CJi_Di_Ya_Liu_Ji_Fang_Qi_Fa_Wei_Zheng_Chang_Kai_Qi_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| DH17-20250909-ABCJi_Qi_Dong_Dian_Ji_Bian_Pin_Qi_Re_Bao_Hu_Ding_Zhi_.pdf | 1 | 0 | 0 | 0 | 0 | 0 |
| DH18-20251026AJi_Ran_Liao_Guan_Lu_YXing_Lu_Nei_You_Xu_Zhuang_Wu_Lu_Xin_Han_Kou_Chu_You_Lie_Wen_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| DH19-20251101Shui_Xi_Xiao_Che_Lu_Wang__Hu_Xi_Fa_Sheng_Xiu_.pdf | 3 | 3 | 8 | 0 | 1 | 7 |
| DH20-20251102AJi_Jin_Qi_Shi_Lu_Xin_You_Sun_Pi_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| DH22-20251104AJi_Ran_Ji_Guo_Du_Duan_Xiang_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_Yin_Qi_Guan_Fa_Lan_Han_Kou_Chu_Kai_Lie_1.pdf | 3 | 3 | 5 | 0 | 1 | 4 |
| DH23-20251110_CJi_Xia_Jin_Qi_Wo_Ke_Di_Bu_You_Shao_Liang_Lei_Si_Yan_Jie_Jing_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| DH24-202511061BJi_Ya_Suo_Ji_Hua_You_Qiao_You_Wu_Feng_Ji_Gu_Zhang_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| DH25-20251222Ran_Ji_Ben_Ti_Guan_Lu_Guan_Gu_Xiang_Xiao_Kai_Lie_.pdf | 4 | 4 | 7 | 0 | 1 | 6 |
| DH26-20251230AJi_Man_Che_Zhi_Ya_Suo_Ji_Zui_Di_Zhuan_Su_Sheng_Su_Man_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| DH27-20260114BJi_Qi_Ji_Guo_Cheng_4Ge_Xiang_Ti_Tong_Feng_Dang_Ban_Fa_Quan_Bu_Guan_Bi_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| DH28-20260118CJi_Feng_Ji_Gu_Zhang_.pdf | 4 | 4 | 6 | 0 | 1 | 5 |
| DH29-20260315_A_Ji_Gong_You_Ya_Li_Di_Jian_Cha_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| DH30-20260314_BJi_Dian_Huo_Dian_Lan_Dian_Ji_Tou_Sun_Pi_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| Di_Ya_Wo_Lun_Lou_You_Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Di_Ya_Wo_Lun_Lou_You_Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan__DFH1eis.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Dong_Hai_Ran_Ya_25MW_CJi_Pai_Qi_Wai_Bao_Wen_Po_Sun_Fen_Xi_52.pdf | 6 | 6 | 53 | 22 | 0 | 27 |
| EAB-BOP-X-2702-IS-001_Shui_Qing_Xi_Xi_Tong_Cao_Zuo_Wei_Hu_Shou_Ce_BOP-X-2702_.pdf | 15 | 17 | 266 | 197 | 6 | 47 |
| EAB-BOP-X-2702-SPC-002_Xi_Hu_Qu_Yu_Tian_Ran_Qi_Wai_Shu_Yu_Zhong_Duan_She_Shi_Neng_Li_Ti_Sheng_Xiang_Mu_Ran_Qu_Ya_Suo_Ji_Zu_Fang_Fu_Zhuan_Pian_.pdf | 17 | 17 | 280 | 136 | 21 | 78 |
| EAB-BOP-X-2702-TIC-001_BOPXiang_Mu__CGT25-DRan_Qu_Ya_Suo_Ji_Zu_An_Zhuang_Fang_An_.pdf | 164 | 160 | 2206 | 988 | 159 | 770 |
| EAB-BOP-X-2702-TIC-002_Ji_Zu_Huan_Zhuang_Zuo_Ye_Zhi_Dao_Shu_.pdf | 32 | 32 | 336 | 190 | 23 | 78 |
| EAB-BOP-X-2754-IS-001_Ya_Suo_Ji_Hua_You_Qiao_Shuo_Ming_Shu_BOP-X-2754ABC_.pdf | 473 | 468 | 9921 | 5251 | 515 | 3234 |
| ET150Re_Dian_Ou_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan_.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Fu_Jian_-Dian_Huo_Qi_Xian_Lan_Tong_Ji_Yi_Ji_Diao_Yan_Qing_Kuang_.pdf | 1 | 1 | 2 | 0 | 0 | 2 |
| Fu_Jian_-Dian_Huo_Qi_Xian_Lan_Wen_Du_Gao_Sun_Pi_Pai_Cha_.pdf | 6 | 6 | 72 | 37 | 4 | 19 |
| Fu_Jian_-Dong_Hai_Ran_Ya_Xiang_Mu_Ri_Bao_20250617.pdf | 8 | 8 | 14 | 2 | 5 | 6 |
| Fu_Jian_-GCZJ-16Zhuan_Su_Chuan_Gan_Qi_Dian_Lan_Cha_Tou_Lian_Jie_Fang_An_1.pdf | 6 | 6 | 57 | 20 | 10 | 3 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF01_20221013_1Ji_Dong_Li_Wo_Lun_Zhi_Cheng_Huan_Xiu_Shi_Qing_Kuang_Ji_Pai_Qi_Gua_Ke_Ji_You_.pdf | 8 | 8 | 38 | 9 | 6 | 19 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF02_20230521_2Fa_Dian_Ji_Hua_You_Xiang_Ban_Shi_Huan_Re_Qi_Lou_You_.pdf | 7 | 7 | 16 | 0 | 3 | 12 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF03_20230707_1Ran_Ji_Gao_Ya_Pan_Che_Gan_Qing_Kuang_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF04_20230726_12Ran_Ji_Ben_Ti_Hua_You_Guan_Dao_Shen_You_Wen_Ti_.pdf | 3 | 3 | 20 | 8 | 3 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF05_20231217_2Ran_Ji_PT003Yu_PT103Ya_Li_Chuan_Gan_Qi_Cai_Ji_Shu_Ju_Chai_Zhi_Lin_Jin_Gao_Bao_Jing_.pdf | 2 | 2 | 13 | 6 | 2 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF06_20231225_2Ran_Ji_Shui_Gao_Ya_Qing_Xi_Qia_Tao_Guan_.pdf | 2 | 2 | 8 | 2 | 1 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF07_20231226_2Ran_Ji_Guo_Du_Duan_Yu_Cheng_Li_Ji_Xia_Lian_Jie_Luo_Shuan_Wu_Fa_Jin_Gu_.pdf | 2 | 2 | 9 | 3 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF08_20240226_2Ran_Ji_Di_Ya_Zhuan_Zi_Pan_Che_Wei_Zhi_Lou_You_.pdf | 2 | 1 | 4 | 0 | 1 | 3 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF09_20240321_1Ran_Ji_Pai_Qi_Gua_Ke_Wu_Zi_Ji_Zhuan_Su_Chuan_Gan_Qi_Shi_Xiao_.pdf | 3 | 3 | 13 | 4 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF10_20240321_1Ran_Ji_Kong_Qi_Jing_Hua_Leng_Que_Zu_Jian_Lu_Xin_Po_Sun_.pdf | 3 | 3 | 9 | 1 | 1 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF11_20240322_1Ran_Ji_Gao_Ya_Hou_Ji_Gao_Ya_Wu_Ji_Dian_Ci_Fa_Gu_Zhang_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF12_20240324_2Ran_Ji_Gao_Ya_Hou_Ji_Gao_Ya_Wu_Ji_Dian_Ci_Fa_Gu_Zhang_.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF13_20240408_2IGVJiang_Fu_He_Gu_Zhang_.pdf | 7 | 7 | 37 | 13 | 2 | 19 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF14_20240408_1Ran_Ji_Xiang_Ti_Wen_Du_Ce_Dian_TE602Wen_Du_Pian_Gao_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF15_20240408_1Ran_Ji_Xiang_Ti_Nei_Wen_Du_Dan_Ce_Pian_Gao_Gu_Zhang_.pdf | 3 | 2 | 5 | 0 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF16_20240411_12Ji_Zu_Pai_Qi_Gua_Ke_Yin_Qi_Guan_Ji_Wen_Du_Ce_Liang_Guan_Wei_Feng_Du_.pdf | 3 | 2 | 5 | 0 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF17_20240630_2Ran_Ji_You_Qi_Fen_Chi_Xiang_Duan_Bu_Dian_Pian_Yi_Chang_.pdf | 2 | 2 | 7 | 1 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF18_20240629_2Ran_Ji_Gao_Ya_Wu_Ji_Dian_Ci_Fa_Yi_Chang_.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF19_20240619_2Ran_Ji_Dian_Huo_Shi_Bai_Ji_Huo_Yan_Tong_Xi_Huo_Gu_Zhang_.pdf | 2 | 2 | 17 | 7 | 3 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF20_20241005_1Fa_Dian_Ji_Nei_Bu_You_Wu_.pdf | 5 | 5 | 28 | 9 | 6 | 12 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF21_20240625_2Ran_Ji_GH25-EXing_Yan_Fa_Zhan_Xian_Chang_Dian_Huo_Dian_Lan_Wen_Ti_.pdf | 6 | 6 | 32 | 16 | 1 | 8 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF22_20240625_1Ran_Ji_Dong_Wo_Zhuan_Su_Tiao_Bian_.pdf | 3 | 3 | 29 | 15 | 1 | 8 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF23_20240728_1Ran_Ji_Di_Ya_Hou_Qia_Tao_Guan_Duan_Lie_.pdf | 2 | 2 | 9 | 2 | 1 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF24_20240728_1Ran_Ji_Dian_Ci_Fa_.pdf | 2 | 2 | 7 | 1 | 1 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF25_20240728_1Ran_Ji_Lou_Qi_Jian_Cha_.pdf | 3 | 3 | 13 | 3 | 2 | 6 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF26_20240906_1Ran_Ji_Ya_Jiang_Diao_Jie_Qi_Guan_Duan_Lie_.pdf | 2 | 2 | 9 | 1 | 1 | 6 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF27_20240930_1Ran_Ji_Re_Dian_Ou_Ce_Liang_De_Wen_Du_Chang_Pian_Chai_Jiao_Da_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF28_20240930_2Ran_Ji_Re_Dian_Ou_Ce_Liang_Wen_Du_Chang_Pian_Chai_Jiao_Da_.pdf | 2 | 2 | 6 | 1 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF29_20241005_1Di_Ya_Hou_Dian_Ci_Fa_Zhi_Di_Ya_Hou_Fang_Qi_Fa_Jian_Qia_Tao_Guan_Mo_Sun_.pdf | 3 | 2 | 13 | 5 | 1 | 5 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF30_20241002_12Ran_Ji_Tong_Feng_Xi_Tong_Feng_Ji_Dang_Ban_Fa_Zhi_Xing_Qi_Qia_Huang_Tuo_Luo_.pdf | 3 | 2 | 10 | 2 | 1 | 6 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF31_20240625_2Ran_Ji_GH25-EXing_Yan_Fa_Zhan_Xian_Chang_Dian_Huo_Dian_Lan_Wen_Ti_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF33_20250426_2Ran_Ji_Dong_Li_Wo_Lun_Zhuan_Su_Chuan_Gan_Qi_Gu_Zhang_.pdf | 11 | 11 | 116 | 64 | 9 | 18 |
| Fu_Jian_-Gu_Zhang_Xin_Xi_Dan_-GF37_20250312_2Ran_Ji_Di_Ya_Ya_Qi_Ji_Zhuan_Su_Tiao_Bian_Ji_Er_Qi_Lu_Ran_Liao_Diao_Jie_Fa_Gu_Zhang_.pdf | 2 | 2 | 14 | 8 | 2 | 4 |
| Fu_Jian_1-20190522-Hai_Shang_Ping_Tai_Xiang_Mu_Xian_Chang_Gong_Zuo_Ri_Bao_.pdf | 9 | 9 | 42 | 24 | 5 | 11 |
| Fu_Jian_1_Xiao_Fang_Xi_Tong_Zheng_Gai_Bao_Gao_.pdf | 17 | 17 | 304 | 189 | 4 | 70 |
| Fu_Jian_1_Xiao_Fang_Xi_Tong_Zheng_Gai_Bao_Gao__bZin6ND.pdf | 17 | 17 | 304 | 189 | 4 | 70 |
| Fu_Jian_1_Xiao_Fang_Xi_Tong_Zheng_Gai_Bao_Gao__kipkD9v.pdf | 17 | 17 | 304 | 189 | 4 | 70 |
| Fu_Jian_2_Yan_Dun_Zhan_1Ji_Zu_Ke_Ran_Qi_Ti_Tan_Ce_Qi_Wen_Ti_Chu_Li_Bao_Gao_.pdf | 8 | 8 | 81 | 33 | 5 | 28 |
| Fu_Jian_2_Yan_Dun_Zhan_1Ji_Zu_Ke_Ran_Qi_Ti_Tan_Ce_Qi_Wen_Ti_Chu_Li_Bao_Gao__dNHqwji.pdf | 8 | 8 | 82 | 34 | 5 | 28 |
| Fu_Jian_2_Yan_Dun_Zhan_1Ji_Zu_Ke_Ran_Qi_Ti_Tan_Ce_Qi_Wen_Ti_Chu_Li_Bao_Gao__iNE2ZA5.pdf | 8 | 8 | 82 | 34 | 5 | 28 |
| Fu_Jian_3-20190522-Qi_Ji_Ji_Qie_Huan_Guo_Cheng_Wen_Du_Bao_Jing_De_Shuo_Ming_.pdf | 3 | 3 | 46 | 33 | 2 | 5 |
| G25Z1.000FA81-Mou_Xing_Ran_Ji_Gao_Ya_Ya_Qi_Ji_Hou_Ya_Jin_Luo_Mu_An_Zhuang_Zheng_Gai_Shi_Shi_Fang_An_.pdf | 11 | 11 | 90 | 55 | 6 | 18 |
| G25Z1.000GF3-Ran_Ji_Gao_Ya_Hou_Ji_Xia_Hua_You_Qiang_Nei_Zhuan_Zi_Ling_Jian_Zheng_Gai_Xiu_Fu_Ji_Zhu_Yao_Qiu__.pdf | 18 | 18 | 87 | 31 | 2 | 45 |
| G25Z1_HJeRybV.000BG250-GT25-028-Z022Hao_Ran_Ji_Gao_Wo_Qian_Shi_Mo_Huan_Mo_Sun_Gu_Zhang_Fen_Xi_Bao_Gao_.pdf | 26 | 26 | 322 | 188 | 32 | 71 |
| GF01_20221013_1Ji_Dong_Li_Wo_Lun_Zhi_Cheng_Huan_Xiu_Shi_Qing_Kuang_Ji_Pai_Qi_Gua_Ke_Ji_You_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| GF02_20230521_2Fa_Dian_Ji_Hua_You_Xiang_Ban_Shi_Huan_Re_Qi_Lou_You_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF03_20230707_1Ran_Ji_Gao_Ya_Pan_Che_Gan_Qing_Kuang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF04_20230726_12Ran_Ji_Ben_Ti_Hua_You_Guan_Dao_Shen_You_Wen_Ti_.pdf | 3 | 3 | 4 | 0 | 3 | 1 |
| GF05_20231217_2Ran_Ji_PT003Yu_PT103Ya_Li_Chuan_Gan_Qi_Cai_Ji_Shu_Ju_Chai_Zhi_Lin_Jin_Gao_Bao_Jing_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF06_20231225_2Ran_Ji_Shui_Gao_Ya_Qing_Xi_Qia_Tao_Guan_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF07_20231226_2Ran_Ji_Guo_Du_Duan_Yu_Cheng_Li_Ji_Xia_Lian_Jie_Luo_Shuan_Wu_Fa_Jin_Gu_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF08_20240226_2Ran_Ji_Di_Ya_Zhuan_Zi_Pan_Che_Wei_Zhi_Lou_You_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF09_20240321_1Ran_Ji_Pai_Qi_Gua_Ke_Wu_Zi_Ji_Zhuan_Su_Chuan_Gan_Qi_Shi_Xiao_.pdf | 4 | 4 | 12 | 4 | 3 | 1 |
| GF10_20240321_1Ran_Ji_Kong_Qi_Jing_Hua_Leng_Que_Zu_Jian_Lu_Xin_Po_Sun_.pdf | 3 | 3 | 3 | 0 | 2 | 1 |
| GF11_20240322_1Ran_Ji_Gao_Ya_Hou_Ji_Gao_Ya_Wu_Ji_Dian_Ci_Fa_Gu_Zhang_.pdf | 3 | 3 | 5 | 1 | 2 | 2 |
| GF12_20240324_2Ran_Ji_Gao_Ya_Hou_Ji_Gao_Ya_Wu_Ji_Dian_Ci_Fa_Gu_Zhang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF13_20240408_2IGVJiang_Fu_He_Gu_Zhang_.pdf | 8 | 8 | 29 | 10 | 3 | 11 |
| GF14_20240408_1Ran_Ji_Xiang_Ti_Wen_Du_Ce_Dian_TE602Wen_Du_Pian_Gao_.pdf | 3 | 3 | 10 | 3 | 2 | 5 |
| GF15_20240408_1Ran_Ji_Xiang_Ti_Nei_Wen_Du_Dan_Ce_Pian_Gao_Gu_Zhang_.pdf | 4 | 4 | 15 | 9 | 3 | 3 |
| GF16_20240411_12Ji_Zu_Pai_Qi_Gua_Ke_Yin_Qi_Guan_Ji_Wen_Du_Ce_Liang_Guan_Wei_Feng_Du_.pdf | 3 | 3 | 4 | 1 | 1 | 2 |
| GF17_20240630_2Ran_Ji_You_Qi_Fen_Chi_Xiang_Duan_Bu_Dian_Pian_Yi_Chang_.pdf | 3 | 3 | 4 | 0 | 2 | 2 |
| GF18_20240629_2Ran_Ji_Gao_Ya_Wu_Ji_Dian_Ci_Fa_Yi_Chang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF19_20240619_2Ran_Ji_Dian_Huo_Shi_Bai_Ji_Huo_Yan_Tong_Xi_Huo_Gu_Zhang_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| GF20_20241005_1Fa_Dian_Ji_Nei_Bu_You_Wu_.pdf | 6 | 6 | 18 | 5 | 5 | 7 |
| GF21_20240625_2Ran_Ji_GH25-EXing_Yan_Fa_Zhan_Xian_Chang_Dian_Huo_Dian_Lan_Wen_Ti_.pdf | 6 | 6 | 23 | 10 | 2 | 4 |
| GF22_20240625_1Ran_Ji_Dong_Wo_Zhuan_Su_Tiao_Bian_.pdf | 4 | 4 | 13 | 4 | 2 | 5 |
| GF23_20240728_1Ran_Ji_Di_Ya_Hou_Qia_Tao_Guan_Duan_Lie_.pdf | 3 | 3 | 3 | 0 | 1 | 2 |
| GF24_20240728_1Ran_Ji_Dian_Ci_Fa_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF25_20240728_1Ran_Ji_Lou_Qi_Jian_Cha_.pdf | 3 | 3 | 3 | 0 | 1 | 2 |
| GF26_20240906_1Ran_Ji_Ya_Jiang_Diao_Jie_Qi_Guan_Duan_Lie_.pdf | 3 | 3 | 4 | 0 | 2 | 2 |
| GF27_20240930_1Ran_Ji_Re_Dian_Ou_Ce_Liang_De_Wen_Du_Chang_Pian_Chai_Jiao_Da_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| GF28_20240930_2Ran_Ji_Re_Dian_Ou_Ce_Liang_Wen_Du_Chang_Pian_Chai_Jiao_Da_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| GF29_20241005_1Di_Ya_Hou_Dian_Ci_Fa_Zhi_Di_Ya_Hou_Fang_Qi_Fa_Jian_Qia_Tao_Guan_Mo_Sun_.pdf | 3 | 3 | 3 | 0 | 3 | 0 |
| GF30_20241002_12Ran_Ji_Tong_Feng_Xi_Tong_Feng_Ji_Dang_Ban_Fa_Zhi_Xing_Qi_Qia_Huang_Tuo_Luo_.pdf | 3 | 3 | 4 | 0 | 2 | 2 |
| GF31_20240625_2Ran_Ji_GH25-EXing_Yan_Fa_Zhan_Xian_Chang_Dian_Huo_Dian_Lan_Wen_Ti_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF32_20250411_2Ran_Ji_Jin_Shu_Guan_Lu_Duan_Lie_.pdf | 2 | 2 | 2 | 0 | 2 | 0 |
| GF33_20250426_2Ran_Ji_Dong_Li_Wo_Lun_Zhuan_Su_Chuan_Gan_Qi_Gu_Zhang_.pdf | 2 | 2 | 2 | 0 | 2 | 0 |
| GF33_Fu_Jian__Yan_Fa_Zhan_2Hao_Ran_Ji_Dong_Li_Wo_Lun_Zhuan_Su_Chuan_Gan_Qi_Gu_Zhang_Gu_Zhang_Fen_Xi_Bao_Gao_.pdf | 11 | 11 | 116 | 64 | 9 | 18 |
| GF34_20250607_1Ran_Ji_Feng_Ji_Dang_Ban_Fa_Xie_Zha_Zhou_Duan_Lie_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF35_20250607_1Ran_Ji_Wen_Du_Ce_Liang_Xian_Lan_Sun_Shang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF36_20250606_1Ran_Ji_Jin_Qi_Gua_Ke_Meng_Pi_Kai_Lie_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| GF37_20250312_2Ran_Ji_Di_Ya_Ya_Qi_Ji_Zhuan_Su_Tiao_Bian_Ji_Er_Qi_Lu_Ran_Liao_Diao_Jie_Fa_Gu_Zhang_.pdf | 2 | 2 | 2 | 0 | 2 | 0 |
| GF38-20250703_2Ji_Gao_Ya_Zhuan_Su_Chuan_Gan_Qi__Guo_Du_Duan_Gong_You_Yi_Ji_Xia_Chuan_Dong_Xiang_Lu_Qi_Lou_You_.pdf | 2 | 2 | 6 | 0 | 1 | 5 |
| GF39-20251018_1Ji_Di_Ya_Hou_Fang_Qi_Fa_Lou_Qi_Yi_Chang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF40-20251018_1Ji_Gao_Ya_Hou_Fang_Qi_Fa_Lou_Qi_Yi_Chang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| GF41-20251021_1Ji_T4Wen_Chai_Luo_Ji_Geng_Gai__Rev2.pdf | 3 | 3 | 3 | 0 | 1 | 1 |
| GF42-20251021_1Ji_Ran_Diao_Fa_Liang_Duan_Dian_Ya_Guo_Di_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| GF43-20251021_1Ji_16Hao_Huo_Yan_Tong_Xi_Huo_Tiao_Ji_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| Gao_Ya_Pan_Che_Gai_Ban_Chu_Lou_You_Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Gao_Ya_Pan_Che_Gai_Ban_Chu_Lou_You_Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan__5LFRTBI.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Gao_Ya_Wo_Lun_Dong_Xie_Qing_Xi_Hou_Tu_Ceng_Bo_Luo_Fen_Xi_Bao_Gao_Ti_Jiao_Jun_Gong_Bu_He_Jun_Dai_Biao_.pdf | 8 | 8 | 90 | 28 | 24 | 28 |
| Gao_Ya_Wo_Lun_Dong_Xie_Tu_Ceng_Lie_Wen_Fen_Xi_Bao_Gao_20240315Di_Shi_Gao_.pdf | 64 | 64 | 484 | 233 | 64 | 117 |
| Gu_Zhang_Chu_Li_Bao_Gao_Pen_Zui_Dian_Pian_.pdf | 5 | 5 | 42 | 18 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao_Pen_Zui_Dian_Pian__6iYU3Sm.pdf | 5 | 5 | 42 | 18 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao_Pen_Zui_Dian_Pian__A3GlcP5.pdf | 5 | 5 | 42 | 18 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao_Pen_Zui_Dian_Pian__noFEmOI.pdf | 5 | 5 | 43 | 18 | 0 | 21 |
| Gu_Zhang_Chu_Li_Bao_Gao_Tong_Dian_Quan_.pdf | 5 | 5 | 42 | 18 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao_Tong_Dian_Quan__YdzPctw.pdf | 5 | 5 | 42 | 18 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao_Tong_Dian_Quan__eIGgaGu.pdf | 5 | 5 | 42 | 18 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao__1Ji_Zu_.pdf | 6 | 6 | 45 | 18 | 0 | 24 |
| Gu_Zhang_Chu_Li_Bao_Gao__1Ji_Zu_Dian_Huo_Qi_Dian_Pian_.pdf | 5 | 5 | 32 | 9 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao__1Ji_Zu_Dian_Huo_Qi_Dian_Pian__p6mcPEg.pdf | 5 | 5 | 32 | 9 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao__1Ji_Zu_Dian_Huo_Qi_Dian_Pian__qAmV8ky.pdf | 5 | 5 | 32 | 9 | 0 | 20 |
| Gu_Zhang_Chu_Li_Bao_Gao__1Ji_Zu__8Gsilw1.pdf | 6 | 6 | 45 | 18 | 0 | 24 |
| Gu_Zhang_Chu_Li_Bao_Gao__1Ji_Zu__t6961rT.pdf | 6 | 6 | 45 | 18 | 0 | 24 |
| Gu_Zhang_Chu_Li_Bao_Gao__3Ji_Zu_.pdf | 6 | 6 | 53 | 24 | 1 | 25 |
| Gu_Zhang_Chu_Li_Bao_Gao__3Ji_Zu__F7rw6A0.pdf | 6 | 6 | 53 | 24 | 1 | 25 |
| Gu_Zhang_Chu_Li_Bao_Gao__3Ji_Zu__hcdz2wX.pdf | 6 | 6 | 53 | 24 | 1 | 25 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_1Dian_Huo_Qi_Dian_Pian_.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_1Dian_Huo_Qi_Dian_Pian__0APLrUC.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_1Dian_Huo_Qi_Dian_Pian__avTzyij.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_1Ji_Zu_Pen_Zui_Dian_Pian_.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_1Ji_Zu_Pen_Zui_Dian_Pian__Wt8ph38.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_1Ji_Zu_Pen_Zui_Dian_Pian__v1K1XIk.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_3Ji_Zu_Pen_Zui_Dian_Pian_.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_3Ji_Zu_Pen_Zui_Dian_Pian__d34eSYH.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_3Ji_Zu_Pen_Zui_Dian_Pian__egVVBdW.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei_.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__1tawzWJ.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__4OQgqDP.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__52xgod2.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__6oaXaUq.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__8gfRCVS.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__Af83i8N.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__MZuyidJ.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__Nkn2QB7.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__Pk1VnRH.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__SOM4vHt.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__VxD8zF9.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__crqHmBA.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__cv8IQd2.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__fuJpTip.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__gdln62U.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__i8AVO0M.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__j2AiLng.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__kp1eduP.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__kwIY1Y2.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__neiNGNM.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__ryVULEu.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__sajPqN5.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__uL1mZxc.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__yX7E9cB.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_Ji_Gui_Ling_Dan_Suo_Nei__zbwga9b.pdf | 2 | 2 | 4 | 1 | 2 | 1 |
| Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan___LGHQGS1022-2018__Fu_Biao_2.pdf | 3 | 3 | 9 | 0 | 2 | 7 |
| Gu_Zhang_Miao_Shu_.pdf | 5 | 5 | 21 | 12 | 5 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_----Wu_Zhou_Zhan_Zhan_Xiang_Ti_Feng_Ji_Pin_Lu_Yi_Chang_.pdf | 2 | 2 | 6 | 0 | 1 | 5 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_-Wu_Zhou_1Ji_Pen_Zui_Xi_Huo_20241101.pdf | 2 | 2 | 6 | 0 | 1 | 5 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_-Wu_Zhou_2Ji_Xia_Chuan_Dong_Xiang_Gu_Zhang_20240103.pdf | 3 | 3 | 7 | 0 | 2 | 5 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_-Wu_Zhou_Zhan_Ran_Ji_Qi_Ji_Shi_Bai_Wen_Ti_.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_1Ji_Zu_Dian_Huo_Qi_Dian_Pian_.pdf | 3 | 3 | 8 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_1Ji_Zu_Dian_Huo_Qi_Dian_Pian__W26pEQL.pdf | 3 | 3 | 8 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_1Ji_Zu_Dian_Huo_Qi_Dian_Pian__j4GYWSq.pdf | 3 | 3 | 8 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_1Ji_Zu_Pen_Zui_Dian_Pian_.pdf | 3 | 3 | 8 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_1Ji_Zu_Pen_Zui_Dian_Pian__46sCMOa.pdf | 3 | 3 | 8 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_1Ji_Zu_Pen_Zui_Dian_Pian__cQIwkce.pdf | 3 | 3 | 8 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_3Ji_Zu_Pen_Zui_Dian_Pian_.pdf | 2 | 2 | 6 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_3Ji_Zu_Pen_Zui_Dian_Pian__5cvT3s9.pdf | 2 | 2 | 6 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_3Ji_Zu_Pen_Zui_Dian_Pian__aIPDEjT.pdf | 2 | 2 | 6 | 1 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Qu_Zhou_1Ji_20181115.pdf | 4 | 4 | 13 | 3 | 3 | 7 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei__.pdf | 4 | 4 | 8 | 0 | 3 | 4 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___0O9vynZ.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___0fJ63dB.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___2cw3olt.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___2gNvGrn.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___3NdzRKP.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___5mAJPu6.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___Dz6DHrg.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___Ef4KGC0.pdf | 3 | 3 | 9 | 0 | 2 | 6 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___F69RspT.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___GCBerk7.pdf | 4 | 4 | 8 | 0 | 3 | 4 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___Hq7ZkMV.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___HwAuFYW.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___KbIC6pa.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___NG5FUr7.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___NzSz5P3.pdf | 3 | 3 | 9 | 0 | 2 | 6 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___O1cExeE.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___P81NMWv.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___PCLhCaP.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___RMItUYB.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___TUyqG5x.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___UrLBP6m.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___UwJ0Y4f.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___Vpk4yNQ.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___ZPtv55X.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___ckUqhzR.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___exMbLMh.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Suo_Nei___vyKAb0B.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Xiao_Fang_Shi_Fang_.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Xiao_Fang_Shi_Fang__jcy4GXA.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Gu_Zhang_Xin_Xi_Bao_Gao_Dan_Xiao_Fang_Shi_Fang__xE0bIEe.pdf | 1 | 1 | 4 | 0 | 1 | 3 |
| Guan_Yu_OPPXian_Chang_Xia_Chuan_Dong_Bao_Jing_De_Jie_Shao_-0713.pdf | 9 | 9 | 17 | 4 | 5 | 8 |
| Guan_Yu_OPPXian_Chang_Xia_Chuan_Dong_Bao_Jing_De_Jie_Shao_.pdf | 7 | 7 | 13 | 4 | 3 | 6 |
| JCZB2019002_Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Bao_Gao_Dan__Ma_Ran__20190523.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019002_Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Bao_Gao_Dan__Ma_Ran__20190523_tuIrqSJ.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019002_Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Bao_Gao_Dan__Ma_Ran__20190523_vd1D2L3.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019003_Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__Ma_Ran__20190523.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019003_Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__Ma_Ran__20190523_17NW7P8.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019003_Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__Ma_Ran__20190523_81vSEvK.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019004_CGT25-D-001-1801Nei_Bu__Zhang_Jian_Guo__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190523.pdf | 2 | 2 | 5 | 1 | 1 | 3 |
| JCZB2019004_CGT25-D-001-1801Nei_Bu__Zhang_Jian_Guo__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190523_ADZUC6C.pdf | 2 | 2 | 5 | 1 | 1 | 3 |
| JCZB2019004_CGT25-D-001-1801Nei_Bu__Zhang_Jian_Guo__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190523_MffWpfh.pdf | 2 | 2 | 5 | 1 | 1 | 3 |
| JCZB2019009_Ren_Bo_Cheng__Hai_Shang_Ping_Tai_Shuang_Ran_Liao_Qie_Huan_Guo_Cheng_Zhong_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190613.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019010_Ren_Bo_Cheng__Hai_Shang_Ping_Tai_Hua_You_Shen_Lou_Dian_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190613.pdf | 2 | 2 | 14 | 3 | 4 | 6 |
| JCZB2019012_Yan_Dun_3Ran_Liao_Guan_Lu_Mo_Ca_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__Zhang_Jian_Guo__20190704.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019012_Yan_Dun_3Ran_Liao_Guan_Lu_Mo_Ca_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__Zhang_Jian_Guo__20190704_qBL5OvU.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| JCZB2019030_Ma_Ran__Yan_Dun_123-Hou_Ji_Xia_Hui_You_Guan_Jie_Jiao_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190924.pdf | 6 | 5 | 11 | 0 | 4 | 7 |
| JCZB2019030_Ma_Ran__Yan_Dun_123-Hou_Ji_Xia_Hui_You_Guan_Jie_Jiao_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190924_ZaKiel3.pdf | 5 | 5 | 13 | 0 | 4 | 8 |
| JCZB2019031_Ma_Ran__Yan_Dun_123Gao_Ya_Pan_Che_Kou_Nei_Jie_Jiao_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190924.pdf | 2 | 1 | 3 | 0 | 1 | 2 |
| JCZB2019031_Ma_Ran__Yan_Dun_123Gao_Ya_Pan_Che_Kou_Nei_Jie_Jiao_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190924_jJSsvTf.pdf | 2 | 1 | 3 | 0 | 1 | 2 |
| JCZB2019032_Zhang_Jian_Guo__3Re_Dian_Ou_Wen_Du_Shi_Shu_Tiao_Bian__Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190930.pdf | 2 | 2 | 4 | 0 | 1 | 3 |
| JCZB2019032_Zhang_Jian_Guo__3Re_Dian_Ou_Wen_Du_Shi_Shu_Tiao_Bian__Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20190930_AoF4KzM.pdf | 2 | 1 | 3 | 0 | 1 | 2 |
| JCZB2019033_Ren_Bo_Cheng__Hai_Shang_Ping_Tai_Ran_Ji_Ben_Ti_Bu_Fen_Wei_Zhi_Xiu_Shi_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20191021.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZB2019034_Liu_Bo__Wu_Zhou_Zhan_Zhan_Xiang_Ti_Feng_Ji_Pin_Lu_Yi_Chang_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20191101.pdf | 2 | 2 | 6 | 0 | 1 | 5 |
| JCZB2019035_Ren_Bo_Cheng__Hai_Shang_Ping_Tai_5Pen_Zui_Fang_Fa_Lan_Yu_Ran_Shao_Shi_Gai_Ban_Jian_Kong_Qi_Lou_Dian_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20191108.pdf | 2 | 2 | 6 | 0 | 1 | 5 |
| JCZB2019036_Ren_Bo_Cheng__Hai_Shang_Ping_Tai_Bao_Xian_Chen_Tao_Duan_Lie_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20191112.pdf | 2 | 2 | 6 | 0 | 2 | 4 |
| JCZB2019037_Ren_Bo_Cheng__Hai_Shang_Ping_Tai_Ji_Cang_Nei_Hua_You_Xi_Tong_Lou_Dian_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__20191114.pdf | 4 | 4 | 21 | 0 | 4 | 15 |
| JCZC2019001_Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Xin_Xi_Chu_Li_Dan__Kang_Wen_Wu__20190522.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019001_Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Xin_Xi_Chu_Li_Dan__Kang_Wen_Wu__20190522_1U2P1D6.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019001_Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Xin_Xi_Chu_Li_Dan__Kang_Wen_Wu__20190522_hS6WeQF.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019002_Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Bao_Gao_Dan__Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan__20190522.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019002_Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Bao_Gao_Dan__Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan__20190522_Uhitxqf.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019002_Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Bao_Gao_Dan__Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan__20190522_weT8o2h.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019003_Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Xin_Xi_Chu_Li_Dan__20190523.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019003_Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Xin_Xi_Chu_Li_Dan__20190523_6aWOCFV.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZC2019003_Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Xin_Xi_Chu_Li_Dan__20190523_mXF9F8l.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| JCZF2019001-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190531.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190531_LwdxhQm.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190531_XuxZTvc.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-2_H25Xi_Lie_Xiang_Mu__Zheng_Lu_Song__Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190612.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-2_H25Xi_Lie_Xiang_Mu__Zheng_Lu_Song__Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190612_WlmZLjn.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-2_H25Xi_Lie_Xiang_Mu__Zheng_Lu_Song__Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190612_YLUkmDa.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-3_Xi_Men_Zi_Xi_Lie_Xiang_Mu__Zheng_Tao___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190604.pdf | 3 | 3 | 24 | 8 | 1 | 14 |
| JCZF2019001-3_Xi_Men_Zi_Xi_Lie_Xiang_Mu__Zheng_Tao___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190604_ha447dl.pdf | 3 | 3 | 24 | 8 | 1 | 14 |
| JCZF2019001-3_Xi_Men_Zi_Xi_Lie_Xiang_Mu__Zheng_Tao___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190604_zpIbSJo.pdf | 3 | 3 | 24 | 8 | 1 | 14 |
| JCZF2019001-4_Wu_Zhou_Zhan__Liu_Bo___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190610.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-4_Wu_Zhou_Zhan__Liu_Bo___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190610_0zShxUf.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-4_Wu_Zhou_Zhan__Liu_Bo___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190610_jitYxHj.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-5_Qu_Zhou_Zhan__Guo_Hong_Liang___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190611.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-5_Qu_Zhou_Zhan__Guo_Hong_Liang___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190611_0pAm32k.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-5_Qu_Zhou_Zhan__Guo_Hong_Liang___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190611_e9kjiIR.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-6_UGT15000Xi_Lie_Xiang_Mu__Ren_Bo_Cheng___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190617.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-6_UGT15000Xi_Lie_Xiang_Mu__Ren_Bo_Cheng___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190617_JCBnPwE.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-6_UGT15000Xi_Lie_Xiang_Mu__Ren_Bo_Cheng___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190617_cDHDWkM.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-7_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190617.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-7_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190617_Nc6Eplu.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019001-7_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping___Yan_Dun_1Ke_Ran_Qi_Ti_Tan_Ce_Qi_Guo_Gao_Ju_Yi_Fan_San_Bao_Gao__20190617_znZUpUO.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-1_H25Xi_Lie_Xiang_Mu__Zheng_Lu_Song__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190612.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-1_H25Xi_Lie_Xiang_Mu__Zheng_Lu_Song__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190612_At13wIz.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-1_H25Xi_Lie_Xiang_Mu__Zheng_Lu_Song__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190612_v0LozrE.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-2_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190531.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-2_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190531_6euFkyN.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-2_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190531_HaNGJRu.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-3_Xi_Men_Zi_Xi_Lie_Xiang_Mu__Zheng_Tao__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190604.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-3_Xi_Men_Zi_Xi_Lie_Xiang_Mu__Zheng_Tao__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190604_a8NQdko.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-3_Xi_Men_Zi_Xi_Lie_Xiang_Mu__Zheng_Tao__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190604_nSHX9IX.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-4_Wu_Zhou_Zhan__Liu_Bo__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190610.pdf | 2 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-4_Wu_Zhou_Zhan__Liu_Bo__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190610_7ObO5eK.pdf | 2 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-4_Wu_Zhou_Zhan__Liu_Bo__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190610_M86mpN6.pdf | 2 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-5_Qu_Zhou_Zhan__Guo_Hong_Liang__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190611.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-5_Qu_Zhou_Zhan__Guo_Hong_Liang__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190611_8ExBXLG.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-5_Qu_Zhou_Zhan__Guo_Hong_Liang__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190611_iO91dS5.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-6_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190617.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-6_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190617_ew1QDPw.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019002-6_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping__Yan_Dun_Zhan_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Ting_Ji_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao__20190617_tCTYS0p.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__201190531.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__201190531_NxaaEPp.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__201190531_OIIH6KO.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-2_Wu_Zhou_Zhan__Liu_Bo__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190531.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-2_Wu_Zhou_Zhan__Liu_Bo__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190531_eiiMvEe.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-2_Wu_Zhou_Zhan__Liu_Bo__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190531_fBaimX7.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-3_Qu_Zhou_Zhan__Guo_Hong_Liang__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190603.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-3_Qu_Zhou_Zhan__Guo_Hong_Liang__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190603_9pbheM7.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-3_Qu_Zhou_Zhan__Guo_Hong_Liang__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190603_nicSkGV.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-4_6000Xi_Lie_Xiang_Mu___Luo_Ping_Ping__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190603.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-4_6000Xi_Lie_Xiang_Mu___Luo_Ping_Ping__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190603_3m0HC2X.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019003-4_6000Xi_Lie_Xiang_Mu___Luo_Ping_Ping__Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190603_NXDyxeN.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190531.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190531_HOGPXVp.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-1_Hai_Shang_Ping_Tai_Xiang_Mu__Ren_Bo_Cheng__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190531_V3mnPrX.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-2_Wu_Zhou_Zhan__Liu_Bo__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190610.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-2_Wu_Zhou_Zhan__Liu_Bo__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190610_C0hnpsl.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-2_Wu_Zhou_Zhan__Liu_Bo__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190610_JU3lZOf.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-2_Wu_Zhou_Zhan__Liu_Bo__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190610_W3ThiBD.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-3_Qu_Zhou_Zhan__Guo_Hong_Liang__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190611.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-3_Qu_Zhou_Zhan__Guo_Hong_Liang__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190611_14J3GAg.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-3_Qu_Zhou_Zhan__Guo_Hong_Liang__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190611_l6Cl93G.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-4_UGT15000Xi_Lie_Xiang_Mu__Ren_Bo_Cheng__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190617.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-4_UGT15000Xi_Lie_Xiang_Mu__Ren_Bo_Cheng__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190617_7oxD6Qo.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-4_UGT15000Xi_Lie_Xiang_Mu__Ren_Bo_Cheng__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190617_h5UGjyW.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-4_UGT15000Xi_Lie_Xiang_Mu__Ren_Bo_Cheng__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190617_jw3vJMP.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-5_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190617.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-5_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190617_8TQFmaX.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| JCZF2019004-5_6000Xi_Lie_Xiang_Mu__Luo_Ping_Ping__Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Gu_Zhang_Ju_Yi_Fan_San_Bao_Gao_Dan__20190617_KYZKrcJ.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Jin_Shu_Bo_Wen_Guan_Gu_Zhang_Jian_Cha_Shuo_Ming_.pdf | 4 | 4 | 33 | 19 | 2 | 6 |
| Jin_Shu_Bo_Wen_Guan_Gu_Zhang_Jian_Cha_Shuo_Ming__4E08H3o.pdf | 4 | 4 | 33 | 19 | 2 | 6 |
| Ju_Yi_Fan_San_Bao_Gao_Dan_-Pai_Qi_Dao_Gang_Cao_Tuo_Luo_-Yan_Dun_Zhan_Ju_Yi_Fan_San_Pai_Cha_.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Ju_Yi_Fan_San_Bao_Gao_Dan_-Qu_Zhou_CO2Pen_Fang_Wen_Ti_-Yan_Dun_Zhan_Ju_Yi_Fan_San_Pai_Cha__-_Fu_Ben_.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Ju_Yi_Fan_San_Bao_Gao_Dan_Yang_Biao_-Yan_Dun_Zhan_Guan_Lu_Mo_Ca_Gu_Zhang_Xin_Xi_-Xi_Men_Zi_Ji_Zu_Ju_Yi_Fan_San_Pai_Cha_.pdf | 2 | 2 | 4 | 0 | 1 | 3 |
| Ju_Yi_Fan_San_Bao_Gao_Dan_Yang_Biao_-Yan_Dun_Zhan_Guan_Lu_Mo_Ca_Gu_Zhang_Xin_Xi_-Xi_Men_Zi_Ji_Zu_Ju_Yi_Fan_San_Pai_Cha__NxyJ1FA.pdf | 2 | 2 | 4 | 0 | 1 | 3 |
| Ju_Yi_Fan_San_Bao_Gao_Dan_Yang_Biao_.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| MGTG4Gao_Ya_5Ji_Fang_Qi_Fa_Duan_Lie_Yuan_Yin_Fen_Xi__.pdf | 12 | 12 | 150 | 108 | 2 | 19 |
| OPP01-20250311_910EJi_You_Wu_Fen_Chi_Qi_Dian_Ji_Cun_Zai_Yi_Xiang_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP02-20250313_920CJi_Mo_Ni_Liang_Shu_Ru_Dian_Liu_Xian_Shi_Bu_Zhun_Que_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP03-20250326_920BJi_Fa_Dian_Ji_Li_Ci_Duan_Cun_Zai_Yi_Xiang_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP05-20250402_920DJi_Dian_Huo_Wei_Chu_Xian_Wen_Du_Chang_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| OPP06-20250406_920DJi_Xiang_Ti_Leng_Que_Feng_Ji_Fan_Xiang_.pdf | 2 | 2 | 4 | 0 | 1 | 2 |
| OPP07-20250406_920EJi_PI701ACe_Dian_Ya_Li_Di_.pdf | 2 | 2 | 4 | 0 | 2 | 2 |
| OPP08-20250407_920E_920CJi_Ji_Shang_Hua_You_Shuang_Lian_Lu_Qi_Yin_Ya_Guan_Jie_Fan_.pdf | 2 | 2 | 4 | 0 | 1 | 2 |
| OPP09-20250411_910AJi_Fa_Dian_Ji_Hua_You_Zhan_Shuang_Lian_Lu_Qi_Yin_Ya_Guan_Jie_Fan_.pdf | 2 | 2 | 4 | 0 | 1 | 2 |
| OPP10-20250412_920AJi_Hua_You_Qiao_Chu_Chu_Xian_Feng_Ming_Sheng_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP11-20250412_920BJi_Er_Qi_Lu_Ran_Diao_Fa_Wu_Dong_Zuo_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| OPP12-20250413_920CJi_Geng_Huan_Ran_Liao_Pen_Zui_Jie_Liu_Huan_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| OPP13-20250415_910BJi_Fa_Dian_Ji_Nei_Bu_You_Wu_Jiao_Duo_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP14-20250416_910EJi_Tian_Ran_Qi_Liu_Liang_Ji_Xian_Shi_Yi_Chang_.pdf | 2 | 2 | 5 | 1 | 1 | 2 |
| OPP15-20250416_920DJi_Xiang_Ti_Tong_Feng_Feng_Ji_Pin_Lu_Bian_Hua_Shi_You_Yi_Xiang_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| OPP16-20250417_910AJi_Jie_Hong_Mi_Feng_Ya_Jiang_Gao_Bao_Jing_.pdf | 2 | 2 | 4 | 0 | 1 | 3 |
| OPP17-20250417_910AJi_You_Qi_Fen_Chi_Qi_Dian_Ji_Zhen_Dong_Gao_.pdf | 2 | 2 | 4 | 0 | 1 | 2 |
| OPP18-20250424_910BJi_You_Qi_Fen_Chi_Qi_Dian_Ji_Zhen_Dong_Gao_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| OPP19-20250426_910BJi_Jin_Xing_MCCDian_Yuan_Qie_Huan_Shi_UPSQie_Pang_Lu_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP20-20250426_920DJi_Di_Ya_Liu_Ji_Fang_Qi_Fa_Pai_Qi_Guan_Dao_Shang_Fang_Bi_Ban_Bei_Chui_Pi_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| OPP21-20250622_920CJi_Wo_Lun_Yi_Ji_Dao_Xiang_Qi_Yu_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_Jie_He_Mian_Fu_Jin_Lou_You__Lou_Qi_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP25-20250515_920DXia_Chuan_Dong_Jin_Shu_Xie_Bao_Jing_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP26-20250528_Suo_You_Fa_Dian_Ji_You_Zhan_Ying_Ji_You_Beng_He_Fu_Zhu_You_Beng_Wu_Fa_Li_Ji_Jian_Ya_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP27-20250529_920AXia_Chuan_Dong_Jin_Shu_Xie_Bao_Jing_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP28-20250530_920CDi_Ya_Fang_Qi_Fa_Wei_Kai_Qi_Luo_Ji_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| OPP29-20250530_920ACDHua_You_Zhan_San_Tong_Wen_Kong_Fa_Mei_You_Fan_Kui_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP30-20250530_Suo_You_You_Zhan_Hua_You_You_Qi_Fen_Chi_Qi_Feng_Ji_Lou_You__Shen_You_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP31-20250529_910BFa_Dian_Ji_Ping_Heng_Qi_Ya_De_Xiao_Pi_Guan_Po_Lie_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP32-20250608_920AGao_Ya_Wu_Ji_Fang_Qi_Fa_Han_Kou_Duan_Lie_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP33-20250610_920CYi_Ji_Dong_Xie_Duan_Lie_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP34-20250613_920DXia_Chuan_Dong_Jin_Shu_Xie_Bao_Jing_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP35-20250615_920AXia_Chuan_Dong_Jin_Shu_Xie_Bao_Jing_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP36-20250622_920CWo_Lun_Yi_Ji_Dao_Xiang_Qi_Yu_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_Jie_He_Mian_Fu_Jin_Lou_You__Lou_Qi_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP37-20250701_920CGao_Ya_Zhuan_Su_Bo_Dong_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| OPP38-20250702_920AJi_De_Gao_Ya_Ya_Qi_Ji_Qian_Xie_He_Qiang_Fang_Qi_Bo_Wen_Guan_Duan_Lie_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP39-20250702_920CHong_Fa_Ya_Jiang_Diao_Jie_Qi_Ya_Chai_Gao_Bao_Jing_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP40-20250701_920CXiang_Ti_Wen_Du_Yi_Chang_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| OPP41-20250707_920CLiu_Liang_Ji_Yi_Chang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| OPP42-20250713_910BXia_Chuan_Dong_Jin_Shu_Xie_Bao_Jing_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP43-20250713_920AFa_Dian_Ji_Hua_You_Zhan_You_Wu_Fen_Chi_Qi_Feng_Ji_Lian_Jie_Zhou_Yu_Lian_Zhou_Qi_De_Jian_Xiao_Fa_Sheng_Mo_Sun_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP44-20250715_910C_920B_920CJin_Xing_Tu_Zeng_3_4_5MWShi_Yan_Shi_Bu_Fu_He_He_Tong_Zhong_Yao_Qiu_De_Ji_Zu_Xing_Neng_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP45-20250726_910AJi_La_Ba_Kou_Jin_Qi_Xiang_Xiao_Jia_Bu_Ban_Xiao_Pi_You_Lie_Wen_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| OPP46-20250802_910A-920ERan_Ji_Xiang_Ti_Wen_Du_Chuan_Gan_Qi_Liang_Tong_Dao_Dian_Zu_Yi_Chang_Qing_Kuang_Ji_Re_Dian_Zu_Liang_Cheng_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| OPP47-20250802_910C910DTu_Zeng_Wen_Ti_.pdf | 3 | 3 | 6 | 0 | 2 | 4 |
| OPP48-20250802Fa_Dian_Ji_Hua_You_Zhan_You_Wu_Fen_Chi_Qi_Feng_Ji_You_Lou_You_Shen_You_Xian_Xiang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| OPP49-20250914_910EYou_Wu_Fen_Chi_Feng_Ji_Zhou_Cheng_Qia_Zhi_.pdf | 3 | 3 | 6 | 0 | 1 | 4 |
| OPP50-20250918_910DXiang_Ti_Men_Jin_Kai_Guan_Gu_Zhang_.pdf | 3 | 3 | 5 | 0 | 1 | 4 |
| OPP51-20250918_920CGao_Ya_Shui_Qing_Xi_Guan_Dao_Duan_Lie_.pdf | 2 | 2 | 4 | 0 | 1 | 3 |
| OPP52-20250929_920EYou_Wu_Fen_Chi_Feng_Ji_Jian_Cao_Sun_Pi_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| OPP53-20251008_920BTI709Wen_Du_Zou_Jiang_ESD.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| OPP54-20251025_910DTian_Ran_Qi_Guan_Dao_Qi_Dong_Jie_Zhi_Fa_SDV701Fa_Gan_Gen_Bu_Lou_Qi_.pdf | 2 | 2 | 10 | 3 | 1 | 6 |
| OPP55-20251106_910EDi_Ya_Liu_Ji_Fang_Qi_Fa_Yin_Chu_Guan_Dao_Wan_Tou_Chu_Han_Feng_Wei_Zhi_Kai_Lie_.pdf | 2 | 2 | 3 | 0 | 1 | 2 |
| OPP56-20251118_910AYa_Jiang_Diao_Jie_Qi_Diao_Jie_.pdf | 2 | 2 | 6 | 0 | 1 | 3 |
| OPP57-20251119_910DGao_Ya_Xie_He_Qiang_Fang_Qi_Lu_Bo_Wen_Guan_Duan_Lie_.pdf | 3 | 3 | 6 | 0 | 1 | 5 |
| OPP58-20251122_910DGao_Ya_Ya_Qi_Ji_Qian_Xie_He_Qiang_Fang_Qi_Bo_Wen_Guan_Duan_Lie_.pdf | 2 | 2 | 4 | 0 | 1 | 3 |
| OPP59-20251205__920DJi_Kong_Tan_Kou_A7Dui_Ce_Du_Gai_Luo_Shuan_Duan_Lie_.pdf | 3 | 3 | 3 | 0 | 1 | 2 |
| OPP60-20251207_910D_AOQia_Jian_Gu_Zhang_.pdf | 2 | 2 | 5 | 0 | 2 | 3 |
| OPP61-20251209_920DYa_Li_Bian_Song_Qi_Gu_Zhang_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| OPP62-20251212_920D_DOQia_Jian_Gu_Zhang_.pdf | 3 | 3 | 5 | 0 | 1 | 4 |
| OPP63-20251214_920CDian_Dong_Gong_You_Beng_Zhi_Hua_You_Zu_Jian_Guan_Lu_Zhi_Jing_8Lian_Jie_Chu_Qia_Tao_Jie_Tou_Sun_Pi_.pdf | 2 | 2 | 3 | 0 | 1 | 1 |
| OPP64-20251215_920BFeng_Ji_Pin_Lu_Bo_Dong_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| OPP65-20251226_920CFa_Dian_Ji_Hua_You_Ya_Li_Di_ESD.pdf | 2 | 2 | 6 | 0 | 2 | 4 |
| OPP66-20260103__920AJi_Kong_Tan_Kong_A7_A8Diao_Zheng_.pdf | 2 | 2 | 3 | 0 | 1 | 1 |
| OPP67-20260108__910A-920ERan_Ji_Wai_Guan_Lu_Yin_Qi_Guan_Lu_Gan_She_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| OPP68-20250107__910A-920ERan_Ji_Hua_You_Zhan_Dian_Lan_Qiao_Jia_Gan_She_.pdf | 2 | 2 | 2 | 0 | 1 | 0 |
| OPPYing_Ji_You_Beng_He_Fu_Zhu_You_Beng_Kuai_Su_Jian_Ya_Fang_An_.pdf | 4 | 4 | 53 | 34 | 5 | 9 |
| OPPYing_Ji_You_Beng_Zeng_Jia_Zhi_Hui_Fa_Ce_Shi_Bao_Gao_.pdf | 8 | 8 | 37 | 21 | 4 | 6 |
| Pei_Dian_Xiang_Xuan_Niu_Ju_Yi_Fan_San_Bao_Gao_Dan_.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Pei_Dian_Xiang_Xuan_Niu_Ju_Yi_Fan_San_Bao_Gao_Dan__joYsWxA.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Pei_Dian_Xiang_Xuan_Niu_Ju_Yi_Fan_San_Bao_Gao_Dan__tH1Xqmb.pdf | 1 | 1 | 3 | 0 | 1 | 2 |
| Pei_Dian_Xiang_Xuan_Niu_Wu_Peng_Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan_.pdf | 4 | 4 | 10 | 0 | 3 | 7 |
| Pei_Dian_Xiang_Xuan_Niu_Wu_Peng_Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan__tZKYYN6.pdf | 4 | 4 | 10 | 0 | 3 | 7 |
| Pei_Dian_Xiang_Xuan_Niu_Wu_Peng_Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan__wmc2r6D.pdf | 4 | 4 | 10 | 0 | 3 | 7 |
| Qu_Zhou_1Hui_You_Guan_Jie_Jiao_.pdf | 6 | 6 | 21 | 5 | 5 | 11 |
| Shuang_Lian_Lu_Ya_Chai_Jie_Fan_Gu_Zhang_Xin_Xi_Bao_Gao_Dan_20181227.pdf | 2 | 2 | 5 | 1 | 1 | 3 |
| Shuang_Lian_Lu_Ya_Chai_Jie_Fan_Gu_Zhang_Xin_Xi_Bao_Gao_Dan_20181227_MR50IHz.pdf | 2 | 2 | 5 | 1 | 1 | 3 |
| Shuang_Lian_Lu_Ya_Chai_Jie_Fan_Gu_Zhang_Xin_Xi_Bao_Gao_Dan_20181227_XzszrKn.pdf | 2 | 2 | 11 | 3 | 2 | 6 |
| Wen_Ti_Shuo_Ming_Ji_Chu_Li__26815.pdf | 2 | 2 | 50 | 30 | 0 | 12 |
| Wu_Zhou_Zhan_Xiang_Mu_Zhou_Bao_----Nei_Bu_.pdf | 2 | 2 | 11 | 0 | 4 | 3 |
| XM17-224_Wu_Zhou_30MW_Pai_Feng_Dang_Ban_Fa_Xie_Pian_Po_Sun_Yuan_Yin_Fen_Xi_Ji_Zheng_Gai_Cuo_Shi__2021.06.04.pdf | 4 | 4 | 44 | 26 | 4 | 6 |
| Xian_Chang_Pai_Cha_Fang_An_-Yan_Fa_Zhan_2Ji__1909_Lou_You_Jian_Cha_Yao_Dian_.pdf | 2 | 2 | 10 | 2 | 0 | 5 |
| Xian_Chang_Xiang_Ti_Feng_Ji_Ce_Shi_Ji_You_Hua_Jian_Yi_.pdf | 5 | 5 | 108 | 70 | 0 | 27 |
| YD001-20151111Hua_You_Qiao_Wen_Ti_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD002-20160527_Yan_Dun_2Ji_Zu_Dian_Huo_T4Chao_Wen_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD003-20160821_Yan_Dun_3Ji_Zu_Xiang_Ti_Shang_Fang_You_Qi_Fen_Chi_Qi_Cun_Zai_Sha_Yan_Dao_Zhi_Lou_You_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD004-20161011_Ke_Ran_Qi_Ti_Tan_Tou_Xu_Bao_Wen_Ti_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD005-20161014_Yan_Dun_2Ji_Zu_Pai_Qi_Wo_Ke_Bao_Wen_Tie_Pi_Tuo_Luo_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD006-20161127_Yan_Dun_23Ji_Zu_Di_Ya_Wo_Lun_Hou_Ran_Qi_Wen_Du_Pian_Chai_Da_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD007-20161212_Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD008-20161214_Yan_Dun_2Ran_Ji_Ke_Zhuan_Dao_Xie_Gu_Zhang_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD009-20161222_Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD010-20170120_Yan_Dun_1Ran_Ji_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_La_Gan_Duan_Lie_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD011-20170306_Yan_Dun_3Ji_Zu_Ran_Ji_Hui_You_Ya_Li_Gao_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD012-20170608_Yan_Dun_1Ji_Zu_Shen_Ceng_Fang_Qi_Qiang_Tong_Dian_Quan_Shi_Xiao_Dao_Zhi_Lou_Qi_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD013-20170716_Yan_Dun_1Ji_Zu_Ke_Ran_Qi_Ti_Tan_Ce_Qi_Gu_Zhang_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD014-20170720_Yan_Dun_13Ji_Zu_Ran_Ji_Pen_Zui_Dian_Pian_Chu_Lou_Qi_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD015-20171026_Yan_Dun_1Ji_Zu_Ran_Ji_Dian_Huo_Qi_Dian_Pian_Sun_Pi_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD016-20180705_Yan_Dun_3Ji_Zu_Xiao_Fang_CO2Pen_She_.pdf | 2 | 2 | 3 | 1 | 1 | 1 |
| YD017-20181227_Yan_Dun_Ji_Dai_Shuang_Lian_Lu_Ya_Chai_Kai_Guan_Lian_Jie_You_Wu_Wen_Ti_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD018-20190219_Yan_Dun_3Ji_Zu_Ran_Ji_Ting_Ji_Guo_Cheng_Yi_Xiang_Zhen_Dong_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD019-20190515_Ran_Ji_Cu_Lu_Lu_Xin_Wu_Fa_An_Zhuang_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD020-20190518_Yan_Dun_Zhan_3Ji_Zu_Bei_Wu_Peng_Pei_Dian_Xiang_Xuan_Niu_Dao_Zhi_You_Beng_Ting_Ji_Gu_Zhang_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD021-20190519_Yan_Dun_3Ji_Zu_You_Beng_Yi_Xiang_Gu_Zhang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD022-20190620_Yan_Dun_3Ji_Zu_Ran_Ji_Er_Qi_Lu_Huan_Guan_Yu_Dong_Li_Wo_Lun_Gong_Leng_Que_Qi_Guan_Mo_Ca_Mo_Sun_.pdf | 2 | 2 | 2 | 0 | 1 | 1 |
| YD023-20190702_Ji_Zu_Ke_Ran_Qi_Ti_Nong_Du_Tan_Ce_Qi_Bu_Wei_0Zai_1-2Zuo_You_Tiao_Dong_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD024-20190704_Yan_Dun_3Ji_Zu_Di_San_Ji_Dong_Xie_Cun_Zai_Liang_Ge_Xiao_Que_Kou_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD025-20190918_Yan_Dun_123Ji_Zu_Gao_Ya_Pan_Che_Kou_Nei_Jie_Jiao_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD026-20190918_Yan_Dun_3Ji_Zu_ET350Re_Dian_Ou_Wen_Du_Shi_Shu_Tiao_Bian_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD027-20190922_Yan_Dun_123Ji_Zu_Hou_Ji_Xia_Hui_You_Guan_Jie_Jiao_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD028-20200806_Yan_Dun_Zhan_1Ji_Zu_RACK5Kuang_Jia_Gu_Zhang_Zhi_Ji_Zu_Ting_Ji_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD029-20200817_Yan_Dun_1Ji_Zu_Ran_Ji_Xiang_Ti_Tong_Feng_Dang_Ban_Fa_Kai_Du_Xian_Shi_You_Wu_1Ji_Zu_T4Wen_Chai_Da_Dao_Zhi_Qi_Ji_Shi_Bai_.pdf | 1 | 1 | 1 | 0 | 1 | 0 |
| YD030-20201123_Yan_Dun_2Ji_Zu_Ke_Zhuan_Dao_Xie_Dong_Zuo_Yi_Chang_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD31-20251007_3Ji_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_Ji_Xia_La_Gan_Duan_Lie_.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| YD31-20251007_3Ji_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_Ji_Xia_La_Gan_Duan_Lie__WUvruG1.pdf | 2 | 2 | 3 | 0 | 2 | 1 |
| Yan_Dun_1Ji_Chan_Pin_Er_Shou_Tai_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_La_Gan_Duan_Lie_Xiu_Fu_-20251015.pdf | 7 | 7 | 38 | 22 | 6 | 7 |
| Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_Fen_Xi_-R1.pdf | 8 | 8 | 81 | 32 | 17 | 28 |
| Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_Fen_Xi_-R1_9Zn90Yp.pdf | 8 | 8 | 81 | 32 | 17 | 28 |
| Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_Fen_Xi_-R1_CpQvsXj.pdf | 8 | 8 | 81 | 32 | 17 | 28 |
| Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_Fen_Xi_-R1_F2ltIDe.pdf | 8 | 8 | 81 | 32 | 17 | 28 |
| Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_Fen_Xi_-R1_JaqP5bK.pdf | 8 | 8 | 82 | 32 | 17 | 29 |
| Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_Fen_Xi_-R1_SfMzq4S.pdf | 8 | 8 | 82 | 32 | 17 | 29 |
| Yan_Dun_1Ji_Zu_Xiang_Ti_Wen_Du_Gao_Wen_Ti_Fen_Xi_-R1_sBUm9yZ.pdf | 8 | 8 | 82 | 32 | 17 | 29 |
| Yan_Dun_1Ran_Ji_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_Jian_Xiu_Qing_Kuang_Shuo_Ming_.pdf | 5 | 5 | 40 | 28 | 3 | 6 |
| Yan_Dun_1Ran_Ji_Di_Ya_Wo_Lun_Zhi_Cheng_Huan_Jian_Xiu_Qing_Kuang_Shuo_Ming__d1kQ1uF.pdf | 5 | 5 | 40 | 28 | 3 | 6 |
| Yan_Dun_2Ji_Ke_Zhuan_Dao_Xie_Dong_Zuo_Yi_Chang_.pdf | 2 | 2 | 12 | 8 | 1 | 3 |
| Yan_Dun_2Ji_Ke_Zhuan_Dao_Xie_Dong_Zuo_Yi_Chang__089DIQW.pdf | 2 | 2 | 12 | 8 | 1 | 3 |
| Yan_Dun_2Ji_Zu_Dian_Huo_T4Chao_Wen_Wen_Ti_Shuo_Ming_.pdf | 4 | 4 | 50 | 27 | 2 | 18 |
| Yan_Dun_2Ji_Zu_Dian_Huo_T4Chao_Wen_Wen_Ti_Shuo_Ming__5sorxmX.pdf | 4 | 4 | 50 | 27 | 2 | 18 |
| Yan_Dun_2Ji_Zu_Dian_Huo_T4Chao_Wen_Wen_Ti_Shuo_Ming__hpZZITV.pdf | 4 | 4 | 50 | 27 | 2 | 18 |
| Yan_Dun_2Ji_Zu_Ke_Zhuan_Dao_Xie_Gu_Zhang_Wen_Ti_Bao_Gao_.pdf | 7 | 7 | 77 | 35 | 7 | 23 |
| Yan_Dun_2Ji_Zu_Ke_Zhuan_Dao_Xie_Gu_Zhang_Wen_Ti_Bao_Gao__BtBsjV0.pdf | 7 | 7 | 77 | 35 | 7 | 23 |
| Yan_Dun_2Ji_Zu_Ke_Zhuan_Dao_Xie_Gu_Zhang_Wen_Ti_Bao_Gao__VWcTzng.pdf | 7 | 7 | 77 | 35 | 7 | 23 |
| Yan_Dun_2Ji_Zu_Ya_Suo_Ji_Hua_You_Ya_Li_Di_Ji_Zu_Ting_Ji_Bao_Gao_.pdf | 10 | 10 | 123 | 71 | 16 | 26 |
| Yan_Dun_2Ji_Zu_Ya_Suo_Ji_Hua_You_Ya_Li_Di_Ji_Zu_Ting_Ji_Bao_Gao__pMWJqxm.pdf | 10 | 10 | 123 | 71 | 16 | 26 |
| Yan_Dun_2_3Ji_Zu_Geng_Huan_Pen_Zui_Shuo_Ming_.pdf | 4 | 4 | 29 | 17 | 8 | 1 |
| Yan_Dun_2_3Ji_Zu_Geng_Huan_Pen_Zui_Shuo_Ming__7nTLH5u.pdf | 4 | 4 | 29 | 17 | 8 | 1 |
| Yan_Dun_2_3Ji_Zu_Geng_Huan_Pen_Zui_Shuo_Ming__LPDZXzL.pdf | 4 | 4 | 29 | 17 | 8 | 1 |
| Yan_Dun_3Ji_Zu_Hui_You_Ya_Li_Gao_Bao_Gao_-R2.pdf | 14 | 14 | 110 | 60 | 7 | 31 |
| Yan_Dun_3Ji_Zu_Hui_You_Ya_Li_Gao_Bao_Gao_-R2_ERkMf7C.pdf | 14 | 14 | 110 | 60 | 7 | 32 |
| Yan_Dun_3Ji_Zu_Hui_You_Ya_Li_Gao_Bao_Gao_-R2_FrPLghS.pdf | 14 | 14 | 110 | 60 | 7 | 31 |
| Yan_Dun_3Xiao_Fang_Pen_She_Gu_Zhang_Bao_Gao_Ji_Xin_Xi_Chu_Li_Dan_.pdf | 3 | 3 | 11 | 0 | 2 | 9 |
| Yan_Dun_3Xiao_Fang_Pen_She_Gu_Zhang_Bao_Gao_Ji_Xin_Xi_Chu_Li_Dan__dbIu5dR.pdf | 3 | 3 | 11 | 0 | 2 | 9 |
| Yan_Dun_3Xiao_Fang_Pen_She_Gu_Zhang_Bao_Gao_Ji_Xin_Xi_Chu_Li_Dan__wEe8n7d.pdf | 3 | 3 | 11 | 0 | 2 | 9 |
| Yan_Dun_3Xiao_Fang_Pen_She_Gui_Ling_Dan_.pdf | 5 | 5 | 74 | 52 | 2 | 12 |
| Yan_Dun_3Xiao_Fang_Pen_She_Gui_Ling_Dan__WyKNnWe.pdf | 5 | 5 | 75 | 53 | 2 | 12 |
| Yan_Dun_3Xiao_Fang_Pen_She_Gui_Ling_Dan__vWDPexB.pdf | 5 | 5 | 75 | 52 | 2 | 13 |
| Yan_Dun_Gu_Zhang_Xin_Xi_Bao_Gao_Dan_.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| Yan_Dun_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__GnXX9wE.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| Yan_Dun_Gu_Zhang_Xin_Xi_Bao_Gao_Dan__IXBpgYj.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| Yan_Dun_Xiang_Mu_Xian_Chang_Ri_Bao__20251023.pdf | 3 | 3 | 19 | 3 | 6 | 5 |
| Yan_Dun_Xiao_Fang_Wu_Bao_.pdf | 4 | 4 | 65 | 45 | 4 | 12 |
| Yan_Dun_Xiao_Fang_Wu_Bao__1QDBpbe.pdf | 4 | 4 | 70 | 47 | 6 | 13 |
| Yan_Dun_Xiao_Fang_Wu_Bao__ePAc7HW.pdf | 4 | 4 | 70 | 47 | 6 | 13 |
| Yan_Dun_Ya_Qi_Zhan_3Ji_Zu_Qie_Huan_Ji_Zu_Fen_Xi_Bao_Gao_2022.3.31.pdf | 3 | 3 | 36 | 22 | 1 | 6 |
| Yan_Dun_Ya_Qi_Zhan_3Ji_Zu_Qie_Huan_Ji_Zu_Fen_Xi_Bao_Gao_2022_0JCndj4.3.31.pdf | 3 | 3 | 36 | 22 | 1 | 6 |
| Yan_Dun_Ya_Qi_Zhan_Guo_Chan_2Ya_Suo_Ji_Zu_Ting_Ji_Fen_Xi_Bao_Gao_.pdf | 11 | 11 | 111 | 68 | 14 | 15 |
| Yan_Dun_Ya_Qi_Zhan_Guo_Chan_2Ya_Suo_Ji_Zu_Ting_Ji_Fen_Xi_Bao_Gao__cRK0wiA.pdf | 11 | 11 | 111 | 68 | 14 | 15 |
| Yan_Dun_Zhan_1Hao_Ji_Zu_RACK5Kuang_Jia_Gu_Zhang_Zhi_Ji_Zu_Ting_Ji_De_Zheng_Gai_Bao_Gao_-Yao_.pdf | 3 | 3 | 41 | 26 | 2 | 3 |
| Yan_Dun_Zhan_1Hao_Ji_Zu_RACK5Kuang_Jia_Gu_Zhang_Zhi_Ji_Zu_Ting_Ji_De_Zheng_Gai_Bao_Gao_-Yao__S0s5MgF.pdf | 3 | 3 | 41 | 26 | 2 | 3 |
| Yan_Dun_Zhan_1Hao_Ji_Zu_RACK5Kuang_Jia_Gu_Zhang_Zhi_Ji_Zu_Ting_Ji_De_Zheng_Gai_Bao_Gao_-Yao__ozAZa0M.pdf | 3 | 3 | 41 | 26 | 2 | 3 |
| Yan_Dun_Zhan_Pai_Qi_Yan_Dao_Xi_Sheng_Ceng_Gu_Zhang_Fen_Xi_Bao_Gao_.pdf | 8 | 8 | 75 | 18 | 8 | 31 |
| Yan_Dun_Zhan_Pai_Qi_Yan_Dao_Xi_Sheng_Ceng_Gu_Zhang_Fen_Xi_Bao_Gao__Zp5uGjd.pdf | 8 | 8 | 75 | 18 | 8 | 31 |
| Yan_Dun_Zhan_Ran_Liao_Guan_Lu_Mo_Ca_.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| Yan_Dun_Zhan_Ran_Liao_Guan_Lu_Mo_Ca__pHApTM0.pdf | 1 | 1 | 5 | 0 | 1 | 4 |
| You_Beng_Gu_Zhang_Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan__TonE7vg.pdf | 3 | 3 | 8 | 0 | 3 | 5 |
| You_Beng_Gu_Zhang_Gu_Zhang_Jiu_Zheng_Cuo_Shi_Bao_Gao_Dan__rkqzkoW.pdf | 3 | 3 | 8 | 0 | 3 | 5 |
| Z1Zhuang_Tai_B29Ran_Qi_Lun_Ji_Jie_He_Chuan_Zhong_Xiu_Chu_Cang_Xiu_Li_----Dong_Li_Wo_Lun_Fen_Jie_Jian_Cha_Yao_Qiu_.pdf | 15 | 15 | 343 | 232 | 29 | 66 |
| Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan_-0702Ke_Ran_Qi_Ti_Tan_Ce_Qi_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan_-0702Ke_Ran_Qi_Ti_Tan_Ce_Qi__aCdxeej.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan_-0704Kong_Tan_.pdf | 2 | 2 | 5 | 0 | 0 | 5 |
| Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan_-0704Kong_Tan__fHCJw8Z.pdf | 2 | 2 | 5 | 0 | 0 | 5 |
| Zhi_Liang_Xin_Xi_Ji_Chu_Li_Dan_-5Yue_18Ri__3Hao_Ji_Zu_Ting_Ji_Shi_Jian__-_Fu_Ben_.pdf | 2 | 2 | 5 | 0 | 1 | 4 |
| from_Ye_Zhu__2023.6.10__3Ji_Zu_Lei_Si_Gu_Zhang______Ran_Diao_Fa_Can_Shu_Yi_Chang_Bo_Dong_Gu_Zhang_Fen_Xi_Bao_Gao_2023.6.10.pdf | 11 | 11 | 111 | 43 | 11 | 18 |
| from_Ye_Zhu__2023_v2sYmoC.6.10__3Ji_Zu_Lei_Si_Gu_Zhang______Ran_Diao_Fa_Can_Shu_Yi_Chang_Bo_Dong_Gu_Zhang_Fen_Xi_Bao_Gao_2023.6.10.pdf | 11 | 11 | 111 | 43 | 11 | 18 |

## 标签分布

| 标签 | 数量 | 中位长度 |
|---|---:|---:|
| Para | 39631 | 32 |
| Title | 4966 | 9 |
| Formula | 4461 | 23 |
| Figure | 2800 | 11 |
| Table | 2082 | 239 |
| List | 503 | 25 |

## 入库筛选结果

| 结果 | 数量 |
|---|---:|
| accept | 26377 |
| reject | 16734 |
| review | 6845 |
| metadata | 4487 |

## 主要风险原因

| 原因 | 数量 |
|---|---:|
| main_text | 26079 |
| too_short | 7523 |
| repeated_header_footer | 5283 |
| high_symbol_noise | 4351 |
| title_metadata | 3226 |
| empty_text | 2174 |
| page_or_tiny_noise | 1308 |
| figure_caption | 1261 |
| short_domain_text | 1003 |
| table_needs_manual_check | 941 |
| table_too_short_or_no_domain_term | 446 |
| figure_caption_with_domain_term | 430 |
| list_text | 298 |
| formula_needs_context | 116 |
| short_domain_list | 4 |

## 标注结构问题

| 问题 | 次数 |
|---|---:|
| missing_text | 2174 |
| empty_result | 1 |

## 高频重复短文本

| 文本 | 次数 | 处理建议 |
|---|---:|---|
| 技术文件 | 133 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 审核 | 133 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 标 准 化 | 133 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 校对 | 130 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 故障信息报告单 | 125 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 1. 概述 | 118 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 编制 | 112 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 编号： | 110 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 批准 | 103 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 目 录 | 98 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 序号 \| 更改通知单号 \| 更改页码 \| 更改方式 \| 更改人 \| 更改日期 | 93 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 更 改 记 录 表 | 91 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 4.2.3—5 | 91 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 非密 | 89 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| \mathrm { N O } _ { x } | 89 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 中 国 船 舶集团有限公司 第七○三研究所 | 88 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 积碳：炭沉积物的积累。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 毛刺：母体材料的边缘或表面上的粗糙边或尖锐凸起。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 涂层磨损：零件表面涂层有材料缺失。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 亮痕：与相邻表面比较呈现金属光泽，无手感。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 磨痕：与相邻表面颜色一致，有摩擦痕迹，无手感。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 亮带磨痕：与相邻表面比较呈现金属光泽，有摩擦痕迹，无手感。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 压痕：材料表面被硬物压伤，底部光滑。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 发黑痕迹：表面粘接物呈黑色，无手感。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 压伤：孔边、接触面等有紧固、配合处出现的挤压损伤。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 碰伤：反复打击或碰撞所致的损伤（非人为所致）。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 刮伤：由尖物或微粒扫过表面时产生的轻微的、狭窄的、浅的痕迹。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 划伤：零件工作时，由外来颗粒的尖边造成的一条或多条深刮伤。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 伤：零件表面有损伤但无法确定形成原因。 | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |
| 版次：A | 86 | 若是页眉页脚/重复标题，应加入 reject 规则 |

## 给标注人员的反馈

1. `Para` 只标正文，不要把页码、页眉、单位署名、目录碎片、无意义短词标成正文。
2. 一段正文如果被 OCR 拆成多行，可以保持行级框，但要保证阅读顺序从上到下、从左到右稳定；入库侧会按坐标合并。
3. `Title` 只用于章节标题/小节标题，后续主要作为 metadata，不直接当正文证据。
4. `Figure` 只标图题或图注，不要框整张图；图题可保留为 caption，但默认不作为核心正文。
5. `Table` 只在表格内容对故障、机理、参数有价值时保留；复杂表格建议人工复核，不要默认入库。
6. `Formula` 只标公式本体；如果公式没有前后解释，默认不单独入库。
7. `List` 可以作为正文候选，但要保证不是目录、编号清单或空泛条目。
8. 如果发现 OCR 转写明显错字、乱码、左右栏串行，标注时应加 `needs_ocr_fix` 或在备注里说明，不能直接进入 ChromaDB。

## 建议入库规则

- 直接入库：`Para`，长度不少于 20 字，非重复页眉页脚，符号噪声比例不高。
- 元数据：短 `Title`、普通 `Figure` caption。
- 人工复核：`Table`、`Formula`、含领域词的短句、图注、符号比例偏高的文本。
- 不入库：空文本、页码、过短碎片、高频重复页眉页脚、无领域信息的表格/图注/公式。

