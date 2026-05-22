# 低置信度页高分辨率重识别报告

- 生成时间：`2026-05-17T16:52:29`
- 输出目录：`D:\虚拟C盘\RAG\data_pipeline\ocr_layout_aware_tesseract_highres_refined\tsinghua_gas_turbine_books`
- 低置信度阈值：`0.45`
- 高分辨率渲染比例：`3.0`

## 结果

- 需要重识别页：1984
- 已尝试页：1984
- 接受替换页：1666
- 失败页：0
- 重识别前平均置信度：0.3353
- 高分辨率候选平均置信度：0.7075

## 说明

只在高分辨率 OCR 的置信度明显更高、且没有丢掉大量文本时替换原页；否则保留原页，并记录原因。

## 前 30 条结果

| 文件 | 页码 | 是否替换 | 原置信度 | 新置信度 | 原字数 | 新字数 | 原因 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 123 | True | 0.4227 | 0.6921 | 6252 | 5542 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 131 | True | 0.4363 | 0.7743 | 456 | 487 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 151 | False | 0.4144 | 0.6288 | 5430 | 462 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 173 | True | 0.4269 | 0.6287 | 315 | 537 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 175 | True | 0.3450 | 0.4996 | 666 | 4500 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 176 | True | 0.3534 | 0.5616 | 709 | 3655 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 181 | False | 0.2834 | 0.7336 | 9141 | 572 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 191 | True | 0.4418 | 0.6498 | 507 | 589 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 204 | True | 0.2973 | 0.7126 | 332 | 463 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 222 | True | 0.4214 | 0.7464 | 330 | 532 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 227 | True | 0.4313 | 0.6819 | 561 | 686 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 254 | True | 0.4406 | 0.7143 | 375 | 503 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 305 | True | 0.3771 | 0.6941 | 141 | 304 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 308 | True | 0.4028 | 0.7859 | 85 | 165 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 350 | True | 0.3004 | 0.6201 | 77 | 175 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 353 | True | 0.3976 | 0.5579 | 235 | 8553 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 361 | True | 0.3348 | 0.4761 | 27 | 269 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 381 | False | 0.3902 | 0.6875 | 13934 | 788 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 386 | True | 0.4404 | 0.6826 | 338 | 406 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 393 | False | 0.3468 | 0.7064 | 11236 | 532 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 396 | False | 0.4270 | 0.5434 | 442 | 210 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 427 | True | 0.4218 | 0.7152 | 451 | 635 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 453 | True | 0.4391 | 0.8646 | 779 | 610 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 561 | True | 0.4072 | 0.7418 | 724 | 482 | confidence_improved |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 562 | False | 0.3708 | 0.7210 | 3350 | 305 | candidate_lost_too_much_text |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBU | 603 | True | 0.4415 | 0.8340 | 4775 | 11604 | confidence_improved |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 27 | False | 0.4336 | 0.8377 | 451 | 232 | candidate_lost_too_much_text |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 34 | True | 0.4128 | 0.5684 | 151 | 348 | confidence_improved |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 36 | True | 0.4148 | 0.6619 | 248 | 295 | confidence_improved |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳 | 54 | True | 0.3787 | 0.5953 | 339 | 529 | confidence_improved |
