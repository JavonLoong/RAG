# Label Studio JSON 到知识图谱的 POC 全流程报告

生成时间：2026-04-29T10:29:39.052Z

## 一句话结论

本次 POC 使用老师指定的 Label Studio 导出 JSON 作为输入，从 OCR 标注结果中重建文本块，再进行 chunk、课程知识图谱 schema 约束、候选三元组生成、证据绑定、schema 校验和展示页生成。

## 输入与输出

- 输入 JSON：`input\project-1-at-2026-04-09-07-02-f7d8cb93.json`
- schema：`course_kg_schema.json`
- 页数：4
- OCR 文本块：246
- chunk 数：14
- 候选三元组：27
- schema 校验通过：27
- 评审状态分布：{"pass":27}

## 展示边界

这次可以说已经完成了 Graph construction POC 的全流程展示：

```text
Label Studio JSON -> OCR 文本块 -> chunk -> schema -> 候选三元组 -> evidence -> review -> HTML 展示
```

但不能说已经完成完整 GraphRAG 问答，也不能说 Neo4j 已经落库。当前输出是可检查的 POC 结果，下一步才是接 LLM 自动抽取并与人工 baseline 对比。

## 候选三元组清单

| id | triple | evidence | review | schema |
| --- | --- | --- | --- | --- |
| LSKG-01 | 船舶燃气轮机控制与健康管理课程 --COURSE_DEVELOPED_BY--> 哈尔滨工程大学动力与能源工程学院 | page_1/C02 | pass | yes |
| LSKG-02 | 船舶燃气轮机控制与健康管理课程 --COURSE_DEVELOPED_BY--> 中国船舶集团有限公司第七〇三研究所 | page_1/C02 | pass | yes |
| LSKG-03 | 船舶燃气轮机控制与健康管理课程 --COURSE_USES_METHOD--> 四维构建法 | page_1/C04 | pass | yes |
| LSKG-04 | 四维构建法 --METHOD_HAS_DIMENSION--> 知识广度 | page_1/C04 | pass | yes |
| LSKG-05 | 四维构建法 --METHOD_HAS_DIMENSION--> 知识层次 | page_1/C04 | pass | yes |
| LSKG-06 | 四维构建法 --METHOD_HAS_DIMENSION--> 知识深度 | page_1/C04 | pass | yes |
| LSKG-07 | 四维构建法 --METHOD_HAS_DIMENSION--> 知识高度 | page_1/C04 | pass | yes |
| LSKG-08 | 船舶燃气轮机控制与健康管理课程 --COURSE_USES_RESOURCE--> 课程知识图谱 | page_1/C02 | pass | yes |
| LSKG-09 | 课程知识图谱 --RESOURCE_HAS_SCALE--> 12个核心模块 | page_3/C10 | pass | yes |
| LSKG-10 | 课程知识图谱 --RESOURCE_HAS_SCALE--> 162个知识点 | page_3/C10 | pass | yes |
| LSKG-11 | 动态特性分析模块 --MODULE_PROVIDES_THEORY_FOR--> 面向控制的建模模块 | page_3/C11 | pass | yes |
| LSKG-12 | 面向控制的建模模块 --MODULE_SUPPORTS--> 控制系统设计模块 | page_3/C11 | pass | yes |
| LSKG-13 | 气路故障建模模块 --MODULE_PROVIDES_METHOD_FOR--> 健康状态评估模块 | page_3/C11 | pass | yes |
| LSKG-14 | 气路故障建模模块 --MODULE_PROVIDES_METHOD_FOR--> 故障诊断模块 | page_3/C11 | pass | yes |
| LSKG-15 | 气路故障建模模块 --MODULE_PROVIDES_METHOD_FOR--> 寿命预测模块 | page_3/C11 | pass | yes |
| LSKG-16 | 发电燃气轮机控制模式设计模块 --MODULE_TECHNICALLY_COMPLEMENTS--> 推进燃气轮机并车控制模块 | page_3/C11 | pass | yes |
| LSKG-17 | 健康状态评估模块 --MODULE_APPLICATION_EXTENDS_TO--> 性能退化预测模块 | page_3/C11 | pass | yes |
| LSKG-18 | 非线性特性的线性化方法 --KNOWLEDGE_POINT_METHOD_SUPPORTS--> 小偏差建模方法 | page_3/C12 | pass | yes |
| LSKG-19 | 燃气轮机分段线性化模型 --KNOWLEDGE_POINT_TECHNICALLY_COMPLEMENTS--> 燃气轮机状态空间模型 | page_3/C12 | pass | yes |
| LSKG-20 | 压气机数学模型 --KNOWLEDGE_POINT_PARALLEL_WITH--> 燃烧室数学模型 | page_3/C12 | pass | yes |
| LSKG-21 | 课程知识图谱 --RESOURCE_USED_IN--> 备课 | page_4/C13 | pass | yes |
| LSKG-22 | 课程知识图谱 --RESOURCE_USED_IN--> 上课导航 | page_3/C09 | pass | yes |
| LSKG-23 | 课程知识图谱 --RESOURCE_USED_IN--> 自主学习 | page_4/C13 | pass | yes |
| LSKG-24 | 课程知识图谱 --RESOURCE_USED_IN--> 版本管理与专家评审 | page_4/C13 | pass | yes |
| LSKG-25 | 船舶燃气轮机控制与健康管理课程 --COURSE_HAS_OUTCOME--> 学习效果提升 | page_1/C02 | pass | yes |
| LSKG-26 | 船舶燃气轮机控制与健康管理课程 --COURSE_HAS_OUTCOME--> 工程实践能力提升 | page_1/C02 | pass | yes |
| LSKG-27 | 船舶燃气轮机控制与健康管理课程 --COURSE_HAS_OUTCOME--> 系统思维和知识迁移能力提高 | page_4/C14 | pass | yes |
