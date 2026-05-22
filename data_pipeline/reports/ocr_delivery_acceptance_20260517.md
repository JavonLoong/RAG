# OCR 交付前验收报告

- 生成时间：`2026-05-17T16:07:09`
- OCR 根目录：`D:\虚拟C盘\RAG\data_pipeline\ocr_layout_aware_tesseract\tsinghua_gas_turbine_books`

## 结论

可以交付为“带风险标注的 OCR 文本成果”，但不能承诺逐字完全正确。

更具体地说：工程完整性已经通过；OCR 内容适合做 RAG/GraphRAG 的候选证据库；如果用于论文引用、知识图谱抽取或精确结论，必须保留页码并人工复核高风险页。

## 完整性验收

- 文件数：13 本扫描 PDF。
- 页数：5483 / 5483。
- 有文字页：5430。
- 总字符数：10093926。
- 总行数：146139。
- 有坐标框页：5430。
- 完整性错误：0。

## 风险统计

- 低版面风险页：4265。
- 中版面风险页：74。
- 高版面风险页：1144。
- 平均置信度偏低页：1930。
- 无文字页：53。
- 文字极短页：145。
- 短行过多页：19。
- 长文本但标点很少页：6。

风险页清单见：`D:\虚拟C盘\RAG\data_pipeline\reports\ocr_delivery_acceptance_20260517_risk_pages.csv`

## 每本书验收表

| 文件 | 页数 | 有文字页 | 坐标页 | 平均置信度 | 高风险页 | 中风险页 | 低置信页 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金... | 603/603 | 603 | 603 | 0.6712 | 117 | 7 | 26 |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳能源集团月亮湾... | 410/410 | 404 | 404 | 0.7007 | 49 | 0 | 15 |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-l... | 442/442 | 442 | 442 | 0.6814 | 74 | 1 | 33 |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-library.sk,... | 423/423 | 416 | 416 | 0.4451 | 80 | 47 | 245 |
| 燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib.sk, z... | 62/62 | 59 | 59 | 0.3684 | 6 | 1 | 51 |
| 燃气轮机 (燃气轮机基本情况编写组编写) (z-library.sk, 1lib.sk... | 161/161 | 159 | 159 | 0.4309 | 12 | 1 | 102 |
| 燃气轮机与燃气-蒸汽联合循环装置 上 (清华大学热能工程系动力机械与工程研究所，深圳南... | 493/493 | 493 | 493 | 0.5476 | 196 | 1 | 83 |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研究所，深圳南... | 325/325 | 325 | 325 | 0.5149 | 86 | 2 | 105 |
| 燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-l... | 485/485 | 485 | 485 | 0.6392 | 193 | 4 | 18 |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著, Pdg2... | 478/478 | 474 | 474 | 0.2706 | 73 | 0 | 472 |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library.sk, 1... | 263/263 | 263 | 263 | 0.4023 | 54 | 7 | 194 |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-library... | 813/813 | 783 | 783 | 0.5218 | 117 | 3 | 232 |
| 航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AERODYNAMIC... | 525/525 | 524 | 524 | 0.4175 | 87 | 0 | 354 |

## 优先人工抽检页

| 文件 | 页码 | 风险 | 置信度 | 字符数 | 预览 |
| --- | ---: | --- | ---: | ---: | --- |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 228 | 短行过多、平均置信度偏低、版面顺序high | 0.3033 | 157 | aESSig ri PELPtEtEiPeLreeeces w\|Ese\|Sins €)3385 g)eee S\|gees Sehee 28... |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-l... | 810 | 长文本但标点很少、平均置信度偏低、版面顺序high | 0.3903 | 851 | MO Ai\|sk mae&Disk AAP Aimy Ait Foren MW van Mitr Wont EWG—Ate Eg inn\|... |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.... | 192 | 短行过多、平均置信度偏低、版面顺序high | 0.3945 | 272 | ns iim wok 2-7 FA Sars nb ne’ ” z 4 é f°reat f®ch 943mg 。四而加7° un(hs)... |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.... | 160 | 短行过多、平均置信度偏低、版面顺序high | 0.4297 | 271 | arch %os Ey os 01]Uetesoos of 19 Fy Fal To7K “x me: 图5-14 OA A ie 1 1... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 217 | 平均置信度偏低、版面顺序high | 0.0951 | 478 | MRR,EFI RIOT相近. esi HANAHAN ROHL 8 98, SAR ERM ARENA RE 6 20960 AB LA... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 378 | 平均置信度偏低、版面顺序high | 0.1602 | 930 | SIME ERR RINE Css AH.ON TAANARIR WILLEN. TeG2a@MAreE LL MARS:ANSHNCE ... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 184 | 平均置信度偏低、版面顺序high | 0.1679 | 852 | 933 Am dant aneannnn 人大的人江上去- oy wecaraese meanWasietcne Rar, saat an... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 107 | 平均置信度偏低、版面顺序high | 0.1802 | 567 | FPA&S 下 E26 a—MORI.OE SR-MARORR,COREA MET an: Ae oPR AO ERMUREE TRAE ... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 118 | 平均置信度偏低、版面顺序high | 0.1964 | 537 | meu eammennnt soem tL mA 2 Sh—NR ASAT eS SZ IT A ET mune, coe 让 有要NTR... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 131 | 平均置信度偏低、版面顺序high | 0.2051 | 3014 | emcees SRC MATRA BLOF SSSI,ES 66 AMMA IR.m a MNO A RCE TL BNI FRAGA R... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 450 | 平均置信度偏低、版面顺序high | 0.2074 | 924 | 5S RAS RRA EAL EA MAM Ew Syncheo Sle Sling Chatch PUL eERULh aia Geen... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 130 | 平均置信度偏低、版面顺序high | 0.2212 | 502 | Bis.63 EACH.Re(LEMAR PRA.GE公司的MSTOoIE FRA LALIT Pe NAY ANE, pr ail,rm... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 128 | 平均置信度偏低、版面顺序high | 0.2256 | 673 | Se PP A I ers AREREAMAR, 8 59 ESR RAN,Om DN RAN RARER. emmure. mee ne... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 408 | 平均置信度偏低、版面顺序high | 0.2258 | 639 | APSF bin PERCH RR—BPR AAT MUL RK, SC AREA CRF. 3.102 SRA AER RIOT, 18... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 101 | 平均置信度偏低、版面顺序high | 0.2299 | 970 | orem mi. 2 Ko OE AE A Sa AR LS A AH FECES BLE a RO A ALAR Peery sy AQ... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 102 | 平均置信度偏低、版面顺序high | 0.2308 | 596 | SYS,oP a A RAR POMC OL FMA AOL,LARCH A FMM MEE,HF IRAN COT.PAR PH,HE ... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 242 | 平均置信度偏低、版面顺序high | 0.231 | 497 | ion mame amr 2mHRR I 2 BRAY oe BRR Po WAR A 2,PORTO LTA A HR I SETTER... |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研... | 140 | 平均置信度偏低、版面顺序high | 0.2323 | 627 | mo]REE zee car am Har, La}manatee[一wrar 好所多机十完全补Lo *seca primed PA ar... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 44 | 平均置信度偏低、版面顺序high | 0.2324 | 713 | SALE ERM NFA HORA ARNEL OTE, se FCAT ARAB NE BL hI eee ec ee SE EAE A... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 213 | 平均置信度偏低、版面顺序high | 0.2334 | 760 | 伺.当我们以中心频率SRD URL,SAEED OAS FEI is.30, wwe woh Dos MLK SALA ARI AOR P... |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研... | 50 | 平均置信度偏低、版面顺序high | 0.2361 | 605 | \| care gaanasioe eared Bx shoe mer sammssior BK:ssw i se 了aa 有Be =m a... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 346 | 平均置信度偏低、版面顺序high | 0.2406 | 689 | ATH MLM Loin BR—Hk STRELA IAAT 12.24 OEM ERM PUNE 12.2461 RMROH ROK o... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 208 | 平均置信度偏低、版面顺序high | 0.2413 | 465 | moe RENNER ETSI IEEE OEE AER TT. ALIN Em CHORAL 9.255.AR CE a ME EC C... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 210 | 平均置信度偏低、版面顺序high | 0.2415 | 845 | ons设备的选择 2831 mee RAD STE MMH ACAD ANCHE OL MSE LAR SSO LARA 5 I LI H... |
| 航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AEROD... | 88 | 平均置信度偏低、版面顺序high | 0.2426 | 405 | ARH Ae SADA AEs MH A EA A ser Far, snd ek I ZI ST OAR 2 A WERE HG CLU... |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library... | 255 | 平均置信度偏低、版面顺序high | 0.247 | 507 | ULTRAM PRR rect 些seein cer v 网[ITD sem yim\|Hem maninnnesitesety me TM... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 182 | 平均置信度偏低、版面顺序high | 0.2472 | 572 | aU, Fe eae NEAT MN FA RAR SEER FORTE, 05.22 AKROS ea ADL KA AEH RETA ... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 120 | 平均置信度偏低、版面顺序high | 0.2477 | 487 | mr 1)ES SIH RII 2)RVR PHU teas PATER, 3)IACMR RI A a I ABC A feynTein... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 114 | 平均置信度偏低、版面顺序high | 0.2486 | 794 | >)ale ROLE.COTA RARE ee EI A FAR A AN AE TE AC PA TARE YOR CAR A ARSE... |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著... | 451 | 平均置信度偏低、版面顺序high | 0.2497 | 2184 | Gy RNS.HOE LAA RR I SRA EERO mimcteaeR. CLI RRR re eel rererrr iy. AG... |

## 交付时建议说法

> OCR 已完成全量处理，并生成了带坐标和版面风险标记的 layout-aware 版本。工程完整性通过，但 OCR 不等于精校文本；高版面风险页、低置信页、表格公式页需要人工复核后才能用于论文结论或知识图谱三元组抽取。
