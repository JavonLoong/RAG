# OCR 交付前验收报告

- 生成时间：`2026-05-18T01:35:00`
- OCR 根目录：`D:\虚拟C盘\RAG\data_pipeline\ocr_layout_aware_tesseract_night_corrected\tsinghua_gas_turbine_books`

## 结论

可以交付为“带风险标注的 OCR 文本成果”，但不能承诺逐字完全正确。

更具体地说：工程完整性已经通过；OCR 内容适合做 RAG/GraphRAG 的候选证据库；如果用于论文引用、知识图谱抽取或精确结论，必须保留页码并人工复核高风险页。

## 完整性验收

- 文件数：13 本扫描 PDF。
- 页数：5483 / 5483。
- 有文字页：5481。
- 总字符数：14836326。
- 总行数：169946。
- 有坐标框页：5481。
- 完整性错误：0。

## 风险统计

- 低版面风险页：4317。
- 中版面风险页：62。
- 高版面风险页：1104。
- 平均置信度偏低页：344。
- 无文字页：2。
- 文字极短页：63。
- 短行过多页：78。
- 长文本但标点很少页：1。

风险页清单见：`D:\虚拟C盘\RAG\data_pipeline\reports\ocr_night_corrected_delivery_acceptance_20260518_risk_pages.csv`

## 每本书验收表

| 文件 | 页数 | 有文字页 | 坐标页 | 平均置信度 | 高风险页 | 中风险页 | 低置信页 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金... | 603/603 | 603 | 603 | 0.714 | 78 | 4 | 5 |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳能源集团月亮湾... | 410/410 | 410 | 410 | 0.7219 | 36 | 2 | 15 |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-l... | 442/442 | 442 | 442 | 0.7238 | 43 | 1 | 1 |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-library.sk,... | 423/423 | 422 | 422 | 0.4938 | 133 | 21 | 147 |
| 燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib.sk, z... | 62/62 | 62 | 62 | 0.7635 | 15 | 2 | 1 |
| 燃气轮机 (燃气轮机基本情况编写组编写) (z-library.sk, 1lib.sk... | 161/161 | 161 | 161 | 0.6703 | 14 | 2 | 5 |
| 燃气轮机与燃气-蒸汽联合循环装置 上 (清华大学热能工程系动力机械与工程研究所，深圳南... | 493/493 | 493 | 493 | 0.6825 | 158 | 2 | 10 |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研究所，深圳南... | 325/325 | 325 | 325 | 0.655 | 69 | 3 | 9 |
| 燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-l... | 485/485 | 485 | 485 | 0.7147 | 156 | 6 | 0 |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著, Pdg2... | 478/478 | 478 | 478 | 0.7666 | 128 | 1 | 39 |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library.sk, 1... | 263/263 | 263 | 263 | 0.6638 | 75 | 5 | 49 |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-library... | 813/813 | 812 | 812 | 0.6717 | 104 | 10 | 42 |
| 航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AERODYNAMIC... | 525/525 | 525 | 525 | 0.6905 | 95 | 3 | 21 |

## 优先人工抽检页

| 文件 | 页码 | 风险 | 置信度 | 字符数 | 预览 |
| --- | ---: | --- | ---: | ---: | --- |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-l... | 474 | 短行过多、平均置信度偏低、版面顺序high | 0.2759 | 11008 | 人 i) Ly uy 08 we a3 2, Me nr oe Wiis i: Wi i] i, sal ui ih Le iH ii h... |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-l... | 240 | 短行过多、平均置信度偏低、版面顺序high | 0.2941 | 505 | ie i) HM polyp (a ins hi Wan he ty cn mal) nl uy Hy Wt ee ee We in by... |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-l... | 30 | 短行过多、平均置信度偏低、版面顺序high | 0.2969 | 13977 | ee one He on pon Ge Hf ee ail fe if yy ys Cal oe ‘a ra uy uy 1) if ie... |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-l... | 286 | 短行过多、平均置信度偏低、版面顺序high | 0.3106 | 621 | My -一一 ie owe ina hi Mf ty) ay ye Hn ij it ile inn” i} rs ii eh i) ih... |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-l... | 162 | 短行过多、平均置信度偏低、版面顺序high | 0.3206 | 411 | 人 thas tf “i ioe) ie be oe ay ie ae i) fi inet i, iW) ey Hy) ii Nb i!... |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 229 | 短行过多、平均置信度偏低、版面顺序high | 0.3619 | 17136 | 燃气轮机可靠性维护理论及应 ae te RS Lk ae BE Se ie &R园 &Sg ERA KARA wee wR (C=# rH... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 298 | 短行过多、平均置信度偏低、版面顺序high | 0.3675 | 1457 | =tis)iG SE Be 3.OF ==YY fas CB 是.A,H Th:BS Hl In= )Wars i\|: Pt ees in... |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 245 | 短行过多、平均置信度偏低、版面顺序high | 0.3756 | 1013 | 燃气轮机可靠性维护理论及应用 we要 PP ip Ex RHRB =r giz a= xe属 We me Xa a ip<r cS SE ... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 96 | 短行过多、平均置信度偏低、版面顺序high | 0.3762 | 4964 | AN Sar 一一-一一一一一上-一 一一一 i= ti Y\| it al wk: unt 上- sal -om AS 了~ il SSS... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 13 | 短行过多、平均置信度偏低、版面顺序high | 0.3848 | 2564 | aie Py =] am cat\|4 +r i+ 3 a IK- oS,J ae ire aN “1. e- ~e aR BM:Yea i... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 17 | 短行过多、平均置信度偏低、版面顺序high | 0.3851 | 1857 | be eh iy she I BS EAT人 BY Ms on 在: »$b AY YGF 号人 $f" Le “6 of Tie ERA... |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 236 | 短行过多、平均置信度偏低、版面顺序high | 0.3874 | 1059 | ak Dik pg te ie RW ay 起党 Bs BS x al eH ys wR ts ee gf erRS oR省 ARB AR... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 289 | 短行过多、平均置信度偏低、版面顺序high | 0.3893 | 1327 | An领 1下去ti Wp aie Sa 24 vt Wy evi tele Pe 34 1人3 Tobe vere} my 24 tej,... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 78 | 短行过多、平均置信度偏低、版面顺序high | 0.3899 | 41771 | Arpt, 可被测的压: est 32 As 77 fst As. StF)《 ps rr iW a++e-第-4=- .nm == a0... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 25 | 短行过多、平均置信度偏低、版面顺序high | 0.3911 | 12674 | \3 Ms APs =ay 一ee ah KL Ne Oe 7/ “对 Ar *) siete peor AP Ati, ra Fe PP... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 84 | 短行过多、平均置信度偏低、版面顺序high | 0.3929 | 12940 | og?her Tay 4.4 ee G8 65 Uae&tees ily 7d tin.了 «$5 rey wie he 2 ORR Sy... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 244 | 短行过多、平均置信度偏低、版面顺序high | 0.3947 | 1258 | 将上述结论用于绝热过猩，因绝热过程中 >»Ree ds>0C T> —-一/> 工质BAS TaN or 4k:Hh whe ay fs ... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 108 | 短行过多、平均置信度偏低、版面顺序high | 0.3967 | 1226 | <% 大和= mo eer es 13 oa cs =e CLES res 一一-v eon ye Bq Jy 5 thw. “Ai we... |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 223 | 短行过多、平均置信度偏低、版面顺序high | 0.3967 | 1150 | 燃气轮机可靠性维护理论及应用 ie SK aW Se i AD Et xR 24 HK台 Boo KE& rs sew et HRE RE... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 310 | 短行过多、平均置信度偏低、版面顺序high | 0.3975 | 6375 | 闻的轴向间辽(见图11.3)。 ow O8 oo CY©GOD Wi i 4 i 中 \| = \| Th] \| iw a 习 ro Fa r... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 104 | 短行过多、平均置信度偏低、版面顺序high | 0.398 | 2014 | ps 7 Ree “ff: 74 “3 ~一 ax Zs“人= na <=. vA we “vv Zie- AeA ED TY au ta... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 330 | 短行过多、平均置信度偏低、版面顺序high | 0.4001 | 24343 | Ae as) -一re SR 让凡人 Gi vi te AL Se去二过 aa eens eeu re wer KK (27! An IY... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 109 | 短行过多、平均置信度偏低、版面顺序high | 0.4077 | 727 | BS s=t we Fe ort EIA] rk, VIER 9 4<« Yao REY 1720 Yeo ee aT Pa WEZ vt... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 380 | 短行过多、平均置信度偏低、版面顺序high | 0.4097 | 1143 | MARE,435°C)宙组，平均可以节约燃料2 5%, RIVE SUP SAIS. 前面所讲的循环 机中进行 了等yaw iat pea... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 18 | 短行过多、平均置信度偏低、版面顺序high | 0.4099 | 20090 | PLR, “ab SEV 73 meine Lor ennn 4b Hl ze, AG? aire ct tnz aL MANA oyX ... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 87 | 短行过多、平均置信度偏低、版面顺序high | 0.4102 | 669 | WAZ n> “Sat.x ye 4k> AES 2 AR EME Al te iH =— 44 ‘Ss 广1 aa 一2一 \|gag o... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 60 | 短行过多、平均置信度偏低、版面顺序high | 0.4105 | 28412 | ava yA 一~ -一 at 7 on c,ar Nit bes poy at tt Sor a. pe\| Lay 7, Ne号 at ... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 238 | 短行过多、平均置信度偏低、版面顺序high | 0.4111 | 1247 | 9， LACE， 经过一个本着循环后其变化人 im》12§e fe MRSS 过FED CK F WT be #4 Lr Sx Re eR... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 88 | 短行过多、平均置信度偏低、版面顺序high | 0.4115 | 982 | --3 if 功是能重 ASI HY EF 转换 siiedbenmy»qu Reon he RT EA SHEARS质的。 4K ART... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 325 | 短行过多、平均置信度偏低、版面顺序high | 0.4123 | 884 | < — if sty FHA 六AP 1 Le Lab Lora at et ue J+. pa AAS i) een MWA x?) Z... |

## 交付时建议说法

> OCR 已完成全量处理，并生成了带坐标和版面风险标记的 layout-aware 版本。工程完整性通过，但 OCR 不等于精校文本；高版面风险页、低置信页、表格公式页需要人工复核后才能用于论文结论或知识图谱三元组抽取。
