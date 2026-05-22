# 低置信度页高分辨率重识别报告

- 生成时间：`2026-05-18T00:10:24`
- 输出目录：`D:\虚拟C盘\RAG\data_pipeline\ocr_layout_aware_tesseract_highres_refined_pass2\tsinghua_gas_turbine_books`
- 低置信度阈值：`0.45`
- 高分辨率渲染比例：`4.0`

## 结果

- 需要重识别页：447
- 已尝试页：447
- 接受替换页：101
- 失败页：0
- 重识别前平均置信度：0.3611
- 高分辨率候选平均置信度：0.517

## 说明

只在高分辨率 OCR 的置信度明显更高、且没有丢掉大量文本时替换原页；否则保留原页，并记录原因。

## 前 30 条结果

| 文件 | 页码 | 是否替换 | 原置信度 | 新置信度 | 原字数 | 新字数 | 原因 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 151 | True | 0.4144 | 0.6100 | 5430 | 4525 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 181 | False | 0.2834 | 0.7631 | 9141 | 537 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 381 | False | 0.3902 | 0.7227 | 13934 | 755 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 393 | False | 0.3468 | 0.7436 | 11236 | 544 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 396 | False | 0.4270 | 0.5638 | 442 | 199 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 562 | False | 0.3708 | 0.7005 | 3350 | 261 | candidate_lost_too_much_text |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 27 | False | 0.4336 | 0.8306 | 451 | 232 | candidate_lost_too_much_text |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 301 | False | 0.4010 | 0.3275 | 44 | 159 | confidence_not_improved_enough |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 365 | False | 0.2991 | 0.7269 | 7686 | 510 | candidate_lost_too_much_text |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 368 | False | 0.4295 | 0.6791 | 1071 | 10 | candidate_lost_too_much_text |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 369 | False | 0.3705 | 0.6024 | 817 | 164 | candidate_lost_too_much_text |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 375 | True | 0.3692 | 0.4310 | 185 | 218 | confidence_improved |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 379 | False | 0.4481 | 0.4051 | 426 | 405 | confidence_not_improved_enough |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 384 | True | 0.4219 | 0.4484 | 46 | 215 | confidence_improved |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 387 | True | 0.4019 | 0.4744 | 152 | 153 | confidence_improved |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 397 | False | 0.4227 | 0.4294 | 142 | 159 | confidence_not_improved_enough |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 404 | False | 0.4326 | 0.5040 | 550 | 35 | candidate_lost_too_much_text |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 405 | False | 0.4055 | 0.3944 | 650 | 3091 | confidence_not_improved_enough |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc | 344 | False | 0.3658 | 0.7459 | 19245 | 796 | candidate_lost_too_much_text |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc | 421 | False | 0.3621 | 0.7029 | 906 | 451 | candidate_lost_too_much_text |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc | 423 | True | 0.4308 | 0.6619 | 2312 | 7676 | confidence_improved |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 2 | False | 0.3005 | 0.2815 | 10512 | 17305 | confidence_not_improved_enough |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 8 | True | 0.3563 | 0.3808 | 121 | 112 | confidence_improved |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 12 | False | 0.2971 | 0.3540 | 9428 | 630 | candidate_lost_too_much_text |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 13 | True | 0.3283 | 0.3486 | 905 | 631 | confidence_improved |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 14 | False | 0.3372 | 0.3126 | 651 | 682 | confidence_not_improved_enough |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 15 | True | 0.4028 | 0.4281 | 546 | 656 | confidence_improved |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 16 | False | 0.4225 | 0.3989 | 311 | 694 | confidence_not_improved_enough |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 17 | False | 0.3252 | 0.3263 | 617 | 583 | confidence_not_improved_enough |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libr | 18 | False | 0.3763 | 0.3005 | 56 | 821 | confidence_not_improved_enough |
