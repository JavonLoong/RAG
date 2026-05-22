# PDF Text Extractability Audit

- Generated at: `2026-05-15T10:28:13`
- Raw directory: `D:\虚拟C盘\RAG\data_pipeline\raw\tsinghua_gas_turbine_books`
- Programmatic extractor: `pypdf 6.10.2`
- Sample policy: first `80` pages per PDF; text page threshold `30` chars.

## Summary

- PDFs audited: 14
- direct_text: 1
- partial_text: 0
- needs_ocr: 13
- error: 0

## Representative Build Candidates

- `燃气-蒸汽联合循环发电机组运行技术问答 燃气轮机与蒸汽轮机设备与运行 (张磊丛书主编) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (direct_text): 79/80 sampled pages have text, 81180 chars extracted, avg 1014.8 chars/page.
- Gap: Only one direct/partial PDF was found by pypdf in the sampled pages; a second representative PDF should not be selected until OCR creates usable text.

## OCR Queue

- `先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金如山，索建秦著) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳能源集团月亮湾燃机电厂，中国电机工程学会燃气轮机发电专业委员会编 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气轮机 (燃气轮机基本情况编写组编写) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气轮机与燃气-蒸汽联合循环装置 上 (清华大学热能工程系动力机械与工程研究所，深圳南山热电股份有限公司编著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研究所，深圳南山热电股份有限公司编著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著, Pdg2Pic) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.
- `航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AERODYNAMICS FOR AERO-ENGINE：FLOW ANALYSIS AND AERODYNAMICS DESIGN (邹正平，王松涛，刘火星，杨策，张... (z-library.sk, 1lib.sk, z-lib.sk).pdf` (high, needs_ocr): no_extractable_text_in_sample.

## Per-PDF Results

| File | Pages | Sampled | Text Pages | Chars | Avg chars/page | Gibberish risk | Classification | Reasons |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金如山，索建秦著) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 603 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 大型燃气-蒸汽联合循环电厂培训教材 M701F燃气轮机汽轮机分册 (深圳能源集团月亮湾燃机电厂，中国电机工程学会燃气轮机发电专业委员会编 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 410 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气-蒸汽联合循环发电机组运行技术问答 燃气轮机与蒸汽轮机设备与运行 (张磊丛书主编) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 615 | 80 | 79 | 81180 | 1014.8 | low | direct_text | - |
| 燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 442 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气蒸汽轮机动力装置热工基础 (清华大学燃气轮机教研组) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 423 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 62 | 62 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气轮机 (燃气轮机基本情况编写组编写) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 161 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气轮机与燃气-蒸汽联合循环装置 上 (清华大学热能工程系动力机械与工程研究所，深圳南山热电股份有限公司编著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 493 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气轮机与燃气-蒸汽联合循环装置 下 (清华大学热能工程系动力机械与工程研究所，深圳南山热电股份有限公司编著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 325 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 485 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气轮机原理、结构与应用 下 (沈阳黎明航空发动机（集团）有限责任公司编著, Pdg2Pic) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 478 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 燃气轮机可靠性维护理论及应用 (张会生，周登极编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 263 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 美国飞机燃气涡轮发动机发展史 (James St. Peter) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 813 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |
| 航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AERODYNAMICS FOR AERO-ENGINE：FLOW ANALYSIS AND AERODYNAMICS DESIGN (邹正平，王松涛，刘火星，杨策，张... (z-library.sk, 1lib.sk, z-lib.sk).pdf | 525 | 80 | 0 | 0 | 0.0 | low | needs_ocr | no_extractable_text_in_sample |

## Classification Rules

- `direct_text`: most sampled pages have extractable text, average text density is usable, and gibberish risk is not high.
- `partial_text`: pypdf extracts some text, but coverage, density, page errors, or gibberish risk make it unsafe as a full-book text source.
- `needs_ocr`: sampled pages have no or extremely sparse extractable text.
- `error`: pypdf could not read or sample the file; inspect the log before retrying.
