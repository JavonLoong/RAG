# Layout-aware OCR 交付前质量审计

## 总判断

这批 OCR 已经完成工程层面的全量处理，可以作为 RAG 检索候选文本；但它仍不是精校文本。

- 运行完整性：高，所有目标页都处理完，脚本层面没有报错。
- 文字识别：整体可用，但封面、目录、表格、公式、页眉页脚仍可能有识别噪声。
- 句段关系：新版 layout-aware 输出已经比旧版更好，因为保存了坐标和版面顺序风险；但高风险页仍需要人工复核。

## 数字结果

- PDF 数量：13
- OCR 页数：5483 / 5483
- 有文字页：5430
- OCR 字符数：10093926
- OCR 行数：146139
- 运行错误数：0
- 每页字符数中位数：773
- 每页字符数 P90：3537
- 每页行数中位数：28
- 每页行数 P90：40
- 平均置信度均值：0.5291
- 平均置信度 P10：0.2975

## 风险统计

- 无文字页：53
- 文字极短页：145
- 长文本但标点很少：6
- 符号/公式比例偏高：0
- 短行过多：19
- 平均置信度偏低：1930
- 疑似编码乱码：0

## 版面顺序风险

- 低风险页：4265
- 中风险页：74
- 高风险页：1144
- 未知风险页：0

## 关于置信度

Confidence values are present; they are useful as rough risk indicators, not final correctness proof.

置信度只能帮助找风险页，不能证明文本完全正确。重要结论仍要回看原 PDF 页图。

## 建议用法

- 普通 RAG 检索：可以用，适合作为候选证据库。
- GraphRAG / 知识图谱抽取：建议优先使用 layout-aware 版，但跳过或人工复核高风险页。
- 论文引用：必须绑定页码和 evidence，关键句回看原 PDF。
- 下一步：抽 30 到 50 页人工核对，重点看高风险页、表格页、公式页和两栏页。

## 风险页样例

| 文件 | 页码 | 风险 | 字符数 | 行数 | 预览 |
| --- | ---: | --- | ---: | ---: | --- |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 3 | 文字极短 | 22 | 3 | enh Ree著 RFs kKMwBR 北京 |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 11 | 版面顺序high | 798 | 39 | 6.11大范围内分布的不均匀性及小范围内分布的均匀性~ 6.13 ASAI AYO 90"喷射在亚声速、室温和横 614 dea ARAL CL FAA 8.9 TURURRER... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 13 | 版面顺序medium | 761 | 71 | 12 10 ARBRE ATH 111结束请 第13章燃烧室总压损失“… 13.1 AH RB 13.2”无用总压损失与有用总压损失 13.3 ASE SFA FICS ACHE... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 14 | 版面顺序high | 728 | 43 | 6 ete se 15.16“定义与术语 15..17“考虑航空发动机的微粒子排放的原因 15.18对环境中微粒子浓度的政府规定要求 15.19”航空发动机非挥发性微粒子排放测量... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 15 | 版面顺序medium | 468 | 44 | 19.4燃油沉积试验 19.5”灼油沉积试验结果 19.6 MOURA(FALL) 19.7燃油沉积的计算分析 19.8纯化学动力学的机计泊和要村 19.9“工程性的燃油沉积计算... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 25 | 版面顺序high | 718 | 35 | 10 SestaLM 火焰简冷却空气《内、外)189%6 总体上，燃烧空气占85%% ke 2.3”火焰简有效流通面积4C。 先了解一个简单喷管的4C, 式中:qq,SEE Es... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 32 | 版面顺序medium | 465 | 24 | (4)进口有旋流与非旋流组合放流器的 组件，有液体喷射，这样就成了一个预混模， 很贴近预混模出口情况下的4C,，如图2-5(e)所示。 2.5.1单个轴流式空气旋流器的4C。 单... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 42 | 版面顺序high | 947 | 34 | 燃烧。这样变动太大，先不改。保持现有的火焰简内燃烧组织，只改扩压器。 3.4前置扩压器设计 这是对常规燃烧室，扩压器进口Ma不高、不分又的前置扩压器而言的 机的情况，如CR-50... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 43 | 版面顺序high | 771 | 37 | 28 Sse on pi iiiiin 1 3 20 um 线是在周向均匀、径向边界层型的速度分布下做的。 进行流场显示及室气流动性能试验- 以下讨论前置扩压器的设计。 《1)分... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 52 | 版面顺序high | 745 | 37 | 3.6.2 MEERA HS 8—§_HE RAL S, (swirl number) 其中:6一旋流器出口射流推力; 7一旋流器出口射流扭矩; 径。 后来奇吉尔(Chigier... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 75 | 版面顺序high | 694 | 31 | o ema 下面说明FN随液体通过喷嘴的流量(压力降)的变化情况- 而变化 20\|\| °»x0四0加7 wo se) HEM Bp/p的影响。 这里最主要说明一点:路咀的流量数F... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 76 | 版面顺序high | 823 | 33 | 19)- 18!\|上 ‘oo»wm Ww Ww 1%2 mm 20 2 stot(sn) 图4-2 ECO ecm Caachi Wm Ro Om 4.3 BEORARIDD 发... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 80 | 版面顺序high | 730 | 32 | XY 分布方程为 而有所不同，最常见的是: Du:体积平均直径。 径。Do最恰当地表达了雾化细度。 SMD也是4的函数 式中:了了一一伽玛函数。 用单一的参数来表征雾化进行CFD... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 83 | 版面顺序high | 806 | 28 | os先进仙气轮机烘烧室 (3)小状态下塌烧效率 在慢车状态下，不希望SMD超过60pm。液雾尺寸也影响到慢车炮火- 面积为 式中，S单位为cm SMD单位为cm。 S具有非常明确... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 85 | 版面顺序high | 713 | 28 | DREW SEA AEH 7.84~9信，因为慢车工况兢娆效率(UHC,CO)和慢车贫油炮 火的要求，慢车时喷嘴压力降希望达到120psi。这样在30%工癌时，就不可能只用副喷 ... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 89 | 版面顺序high | 560 | 25 | 0p so a a a 4.5 SNCS UT RS 和良好，而是燃烧室设计上的考虑。 组织上要重新考虑〔见第7章)。 至尾始终工作，是“长明灯”，在各种工况下要稳定火焰，尤其在... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 94 | 版面顺序high | 549 | 26 | Ey rn ron roe 距离，最后因为要与主模尺寸一致，又加了一个带角度的扩张段。 仍由要求的流量来决定。没有室气时，喷雾锥角常用90"。 \|\|\| \|\|\| M7\| cy rs... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 103 | 版面顺序high | 412 | 22 | 88 Eee eae 。液体-气体相对速度不变。 在以上条件下，内外雾化空气的比例有三种组合，见表4-2。 上wa 6 a 的外雾化室气是必有不可少的。 10}— ann 表4-... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 110 | 版面顺序medium | 22179 | 13 | leat【以停留时间来表达)/me ar,0K,Jos}\| 由试验数据可以得出以下有意义的结论: (1)液雾尺寸分布非常细 雾化细。例如，在12har，700K CH, 5 1 ... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 115 | 版面顺序high | 917 | 35 | 100 Sesame MR 经用上，以后先进航室燃烧室也会用，所以我们要讨论它。 首先讨论同轴顺流直喷空气雾化的机理， 射流长度P1。概括起来，有以下几。 -样。 内部由于喷嘴几... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 117 | 版面顺序high | 542 | 23 | 102 einen 情况下 压影响的试验结果如图4-43和图4-44 Br, @smu sno) ott es wR ee er 图4-43 GIR FR eC IR 对SMD的... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 118 | 版面顺序high | 799 | 32 | 图4 44 AGE FMR Pe MC Ca 随空气速度明显碱小，同时尺寸分布参数4亦明显下降。试验结果见表4-4 =120 8s SMD=p,-as 越高环境压力对SMD的影响... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 123 | 平均置信度偏低 | 6252 | 12 | sesame Mi am 2am stm -1 BPP 12%API=19% ele APP anin-20% iC AR mtn? 0和 图4-50不同反导下，雾化。 是在Mp... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 125 | 版面顺序high | 588 | 32 | 110 sae anima ne Er] pests miei 系式。 伦泽托的关系式为 SMD=0.95 WAR(4-20)，只是加以改进。 BiB. RATERIEI(4-2... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR ... | 127 | 版面顺序high | 751 | 33 | 1先进并气轮机燃烧室 这个比较结果相当不错，表明方程(4-21)可以为实际应用。 Wel(4-21) exit(39) 横向路流空气速度很低，在3个典型的工况下，计算的SM值。 ... |
