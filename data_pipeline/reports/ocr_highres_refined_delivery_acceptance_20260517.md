# OCR 交付前验收报告

- 生成时间：`2026-05-17T23:56:40`
- OCR 根目录：`D:\虚拟C盘\RAG\data_pipeline\ocr_layout_aware_tesseract_highres_refined\tsinghua_gas_turbine_books`

## 结论

可以交付为“带风险标注的 OCR 文本成果”，但不能承诺逐字完全正确。

更具体地说：工程完整性已经通过；OCR 内容适合做 RAG/GraphRAG 的候选证据库；如果用于论文引用、知识图谱抽取或精确结论，必须保留页码并人工复核高风险页。

## 完整性验收

- 文件数：13 本扫描 PDF。
- 页数：5483 / 5483。
- 有文字页：5479。
- 总字符数：12337422。
- 总行数：153542。
- 有坐标框页：5479。
- 完整性错误：0。

## 风险统计

- 低版面风险页：4116。
- 中版面风险页：73。
- 高版面风险页：1294。
- 平均置信度偏低页：443。
- 无文字页：4。
- 文字极短页：115。
- 短行过多页：15。
- 长文本但标点很少页：3。

风险页清单见：`D:\虚拟C盘\RAG\data_pipeline\reports\ocr_highres_refined_delivery_acceptance_20260517_risk_pages.csv`

## 每本书验收表

| 文件 | 页数 | 有文字页 | 坐标页 | 平均置信度 | 高风险页 | 中风险页 | 低置信页 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金... | 603/603 | 603 | 603 | 0.6806 | 118 | 7 | 6 |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳能源集团月亮湾... | 410/410 | 410 | 410 | 0.7016 | 55 | 1 | 12 |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-l... | 442/442 | 442 | 442 | 0.7009 | 78 | 1 | 3 |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-library.sk,... | 423/423 | 422 | 422 | 0.4688 | 84 | 42 | 193 |
| 燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib.sk, z... | 62/62 | 62 | 62 | 0.748 | 18 | 0 | 6 |
| 燃气轮机 (燃气轮机基本情况编写组编写) (z-library.sk, 1lib.sk... | 161/161 | 161 | 161 | 0.6355 | 15 | 0 | 17 |
| 燃气轮机与燃气-蒸汽联合循环装置 上 (清华大学热能工程系动力机械与工程研究所，深圳南... | 493/493 | 493 | 493 | 0.595 | 186 | 1 | 16 |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研究所，深圳南... | 325/325 | 325 | 325 | 0.6129 | 87 | 5 | 13 |
| 燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-l... | 485/485 | 485 | 485 | 0.6495 | 196 | 3 | 2 |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著, Pdg2... | 478/478 | 478 | 478 | 0.7423 | 154 | 1 | 50 |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library.sk, 1... | 263/263 | 263 | 263 | 0.651 | 68 | 4 | 48 |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-library... | 813/813 | 810 | 810 | 0.6322 | 115 | 7 | 44 |
| 航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AERODYNAMIC... | 525/525 | 525 | 525 | 0.6611 | 120 | 1 | 33 |

## 优先人工抽检页

| 文件 | 页码 | 风险 | 置信度 | 字符数 | 预览 |
| --- | ---: | --- | ---: | ---: | --- |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳能... | 375 | 短行过多、平均置信度偏低、版面顺序high | 0.3692 | 185 | 全)-PK也PN了 (的-上K[\|DK 5 ox)ae DK] @©-xK ®S re交 \|af A 4 fd\|ga\|aX 3中 IE &... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 131 | 平均置信度偏低、版面顺序high | 0.2051 | 3014 | emcees SRC MATRA BLOF SSSI,ES 66 AMMA IR.m a MNO A RCE TL BNI FRAGA R... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 451 | 平均置信度偏低、版面顺序high | 0.2497 | 2184 | Gy RNS.HOE LAA RR I SRA EERO mimcteaeR. CLI RRR re eel rererrr iy. AG... |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研... | 269 | 平均置信度偏低、版面顺序high | 0.2669 | 721 | Me MUeh ym eR eM ERE FMP AKG HRSG OE ‘em ce[TD ‘ome ce A amamE mre Po... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 95 | 平均置信度偏低、版面顺序high | 0.3073 | 509 | 负号意味著册过程中BARMTAR He tx. LF OMRRR PEP Sw pe Re HAE° BUR RARE© —_—~err ... |
| 燃气轮机 (燃气轮机基本情况编写组编写) (z-library.sk, 1... | 129 | 平均置信度偏低、版面顺序high | 0.31 | 498 | WHURME AA«Ai Reverch Mamtactriog Cox)I lea ae ne ed ee homeo, wena,me... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 109 | 平均置信度偏低、版面顺序high | 0.3136 | 234 | By TEAST REIN TL AA w 209 US© 例题”EAM 2-3 ne Ae而[ARSE ROU Bo UR +30884... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 46 | 平均置信度偏低、版面顺序high | 0.3226 | 376 | AAS a2)Ww REA TEES SHR SABA ARES Colbie«AL Seka?o> XARA* Rint i Olea ... |
| 燃气轮机与燃气-蒸汽联合循环装置 上 (清华大学热能工程系动力机械与工程研... | 116 | 平均置信度偏低、版面顺序high | 0.3269 | 8851 | HM_AL eye RA Mom RE 式中“口一分子扩用系数， Vix Ve AUR A CO PERI ie Se.OSEAN PS ... |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研... | 295 | 平均置信度偏低、版面顺序high | 0.3333 | 624 | ML_Behe eA aA MOORE 表246中给出了电厂的建设进度.。 表24.7中给出了电厂的运行性能指标. 表24.8中给出了进行... |
| 燃气轮机 (燃气轮机基本情况编写组编写) (z-library.sk, 1... | 141 | 平均置信度偏低、版面顺序high | 0.336 | 691 | [RE ‘PRS ston Gan Tuas URIEE Takes,RONEN.T RHSM Gear Doon Hm- Wis WAR... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 306 | 平均置信度偏低、版面顺序high | 0.341 | 415 | 六roayess at gorse! HER(9-66 FB $7+170(7814+9—3248+1) QRH CRS WBA-3 5)... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 417 | 平均置信度偏低、版面顺序high | 0.3483 | 5049 | Ba.72 BR HC MURR RM OM,He RRO Wh,该旅社在夏季每天平均所需电力 300K W 4825S ROH 1SOR... |
| 燃气轮机与燃气-蒸汽联合循环装置 上 (清华大学热能工程系动力机械与工程研... | 268 | 平均置信度偏低、版面顺序high | 0.3527 | 3688 | BEL*ieh bet anMommRE 关系，对阻尼较小的系统，接近实际， 一单位质量的阻尼系数.， BLA《结构内阴力)等。 式(9-... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 232 | 平均置信度偏低、版面顺序high | 0.3539 | 414 | Bel PgiZlel MIPI>Leg leet PAl>12, 功大于所得到的功*ARATE SHADE ALAA PG MH©bk ... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 291 | 平均置信度偏低、版面顺序high | 0.3548 | 824 | 1&人Ke A\|1 a sa i lj Ae laa ote one i P Mage5 wee Ibe as Ue ，ih,RA?APH... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 302 | 平均置信度偏低、版面顺序high | 0.3571 | 367 | Fe,RTS t: 式中，凡标注了的均为燃料的矢: tas tg AR,ABS 6 Re Ks HST ARAM ft Bk an Gag... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 330 | 平均置信度偏低、版面顺序high | 0.3584 | 783 | =oye aati所 a.a eS La I ae机Pee了4£2, ee nee we Ne :.i i\|_7 \|I w BONO fo... |
| 燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著... | 312 | 平均置信度偏低、版面顺序high | 0.3605 | 516 | 各种组成气体的低发热量,J/m;(或J/kg) on CT oor on or 196.2 oo ears 气体燃料中各组成气体的低发热其... |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.... | 421 | 平均置信度偏低、版面顺序high | 0.3621 | 906 | 402 SURE ARMANI(38 3版) te sex\|AST iene ee\|FMR]4, (no) aaa[sos m7 sane... |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 230 | 平均置信度偏低、版面顺序high | 0.3624 | 853 | #REEKE\|REKKE x a ae &\|x\|Lame\|Cae Re=en “\|@\|)Zeek\|Swe P坚 B\\|HEene\|ween... |
| 燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib... | 36 | 平均置信度偏低、版面顺序high | 0.3652 | 2412 | 5 2« 所= =\|S 3 se 2= «x= ~77 ae a) ee& a\|o 9 S 2.8 on q 3 er=te a=wer ... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 321 | 平均置信度偏低、版面顺序high | 0.3652 | 845 | rr i ee =See ee seats ee=sana ual=\|=aires west Soe \|a a oe a Gj-Ze \|2... |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 146 | 平均置信度偏低、版面顺序high | 0.366 | 1480 | FRY REML DL TRA A FET 9 aie A OL REE 6.3”燃气轮机结构强度相关故障的FMECA 际机组的故障记录5... |
| 燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib... | 37 | 平均置信度偏低、版面顺序high | 0.3672 | 1382 | 型 An &入= z= =Fa. x\|8= =Ee 长长 K bd Qg四 »<<<2<«<<z==z=26= ¥\»a 5 8 2 BE... |
| 航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AEROD... | 371 | 平均置信度偏低、版面顺序high | 0.3676 | 796 | r& 时\|# =}a] 员\|=\|® S\|\|&as Rie}=® iH he这 H Ne 后& a p Ft: Ee SESEEYS ESS... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 57 | 平均置信度偏低、版面顺序high | 0.3692 | 381 | 个压力 也压有语素为、为岂可-5 Ce室* Or TORRES /SPER SE SRE oD 5 REAM RES: BA 1-25 S... |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-libra... | 341 | 平均置信度偏低、版面顺序high | 0.3693 | 334 | 我位 Be 问题。 愉汽、液相互转化的根本原因 FR,Maks BR Hh iP ANZREPOBE ABA,BO RAB ARR?杰节就... |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳能... | 369 | 平均置信度偏低、版面顺序high | 0.3705 | 817 | 1OVCIne guide vane of compremer)Fee TE ROE 1PCinemeiate posse)hk TPCV... |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUS... | 562 | 平均置信度偏低、版面顺序high | 0.3708 | 3350 | 7a ee aoc,WE eee ne,\|iar awa\|aww\|oe ol eT mo\|wo\|0 oe TEAR,=»\|s meet H... |

## 交付时建议说法

> OCR 已完成全量处理，并生成了带坐标和版面风险标记的 layout-aware 版本。工程完整性通过，但 OCR 不等于精校文本；高版面风险页、低置信页、表格公式页需要人工复核后才能用于论文结论或知识图谱三元组抽取。
