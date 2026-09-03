# M3 模块交接接口 v1

本文档是发给 M2、M4、M5 同学的接口契约。跨模块传输统一使用 UTF-8 JSON；同一 Python 进程内可以使用文中列出的 dataclass / Protocol 实现。下游不得直接读写 M3 的 SQLite 表。

## 1. M2 → M3：审核资料包

### 接口类型

- 跨进程类型：JSON Object，`schema_version = power-rag.m2-document.v1`
- Python 类型：`knowledge_base.contracts.M2DocumentHandoff`
- 导入函数：`m2_handoff_from_payload(payload) -> M2DocumentHandoff`
- 接收服务：`M2HandoffService.accept(...) -> DocumentRevision`
- 完整示例：`configs/m2_to_m3.example.json`

### M2 必须提供

| 字段 | JSON 类型 | 约束 |
| --- | --- | --- |
| `schema_version` | string | 固定为 `power-rag.m2-document.v1` |
| `document.document_id` | string | 跨版本稳定，不得使用临时数组下标 |
| `document.title` | string | 非空 |
| `document.source_uri` | string | 可回看原文件的受控 URI/相对路径 |
| `document.media_type` | string | MIME type，如 `application/pdf` |
| `document.metadata` | object | 建议含来源哈希、来源版本、语言、可信度、访问标签 |
| `document.pages[]` | array | 页码必须为唯一正整数 |
| `pages[].blocks[]` | array | 至少包含 `text/block_type/ordinal`，强烈建议提供稳定 `block_id` |
| `blocks[].metadata.bbox` | number[4] | OCR/版面块建议提供，坐标系由 M2 在 metadata 中声明 |
| `document.assets[]` | array | 表格/图片使用 URI、caption、checksum，并绑定 page/block |
| `review.status` | string | M3 只接收 `approved`；另有 `pending/rejected` |
| `review.reviewer` | string | `approved` 时必须是真实人工审核者标识 |
| `quality.evidence_coverage` | number | 取值 0～1；进入 M3 必须为 1.0 |
| `quality.issues[]` | array | `severity = info/warning/blocking`，并标记 `resolved` |

M3 会拒绝未审核、证据覆盖不足或仍有未解决 blocking issue 的资料。M2 不需要切 chunk 或生成 embedding；切片、chunk ID、向量和发布版本均由 M3 负责。

### 调用示例

```python
import json

from knowledge_base import KnowledgeBaseStore, M2HandoffService, m2_handoff_from_payload

payload = json.loads(open("configs/m2_to_m3.example.json", encoding="utf-8").read())
store = KnowledgeBaseStore("storage_layer/runtime/knowledge_base.sqlite3")
revision = M2HandoffService(store).accept(
    m2_handoff_from_payload(payload),
    actor="m2-adapter",
)
```

或使用 CLI：

```powershell
python scripts/knowledge_base_cli.py --db storage_layer/runtime/knowledge_base.sqlite3 accept-m2 `
  --input configs/m2_to_m3.example.json --actor m2-adapter
```

## 2. M3 → M4：已发布资料快照

### 接口类型

- 跨进程类型：JSON Object，`schema_version = power-rag.m3-snapshot.v1`
- Python 类型：`knowledge_base.models.KnowledgeBaseSnapshot`
- 读取函数：`KnowledgeBaseStore.export_snapshot(version) -> KnowledgeBaseSnapshot`

快照是只读、不可变、绑定具体 `knowledge_base_version + manifest_sha256` 的全量构图输入，包含：

```text
release
└─ documents[]
   ├─ pages[].blocks[]
   ├─ assets[]
   └─ chunks[].evidence[]
```

`chunks[].evidence[]` 的定位类型为：

```python
EvidenceLocator(
    document_id: str,
    revision_id: str,
    page_number: int,
    block_id: str,
    char_start: int,
    char_end: int,
)
```

M4 构建的每个实体、关系和陈述至少保存：

- `knowledge_base_version`
- `manifest_sha256`
- `document_id`
- `revision_id`
- `chunk_id`
- 对应 `EvidenceLocator`
- 原资料的 `required_access_labels`

导出示例：

```powershell
python scripts/knowledge_base_cli.py --db storage_layer/runtime/knowledge_base.sqlite3 export-snapshot `
  --version 1 --output storage_layer/runtime/m3-snapshot-v1.json
```

M4 不应读取候选或待审核修订，也不应自己重新切片；增量构图通过比较相邻快照中的 document revision / chunk content hash 完成。

## 3. M3 → M5：检索与证据接口

M5 不应读取整个快照生成 FMEA，而应通过检索接口取得有限、可追溯证据。

### 仓库统一检索接口（推荐）

- 接口类型：Python `retrieval_engine.core.BaseRetriever`
- M3 实现：`retrieval_engine.knowledge_base.KnowledgeBaseRetriever`
- 方法：`retrieve(query: str, top_k: int = 5) -> list[RetrievalResult]`

每个 `RetrievalResult.metadata` 包含：

- `document_id: str`
- `revision_id: str`
- `knowledge_base_version: int`
- `source: str`
- `page: list[int]`
- `chunk_id: str`
- `evidence: list[{page_number, block_id, char_start, char_end}]`
- `document_metadata: object`

```python
from knowledge_base import KnowledgeBaseQueryService, KnowledgeBaseStore, SearchMode
from retrieval_engine import KnowledgeBaseRetriever

store = KnowledgeBaseStore("storage_layer/runtime/knowledge_base.sqlite3")
retriever = KnowledgeBaseRetriever(
    KnowledgeBaseQueryService(store),
    version=1,
    mode=SearchMode.KEYWORD,
    allowed_access_labels={"internal-research"},
)
results = retriever.retrieve("压气机积垢如何处理", top_k=5)
```

M5 当前的 `QueryServiceEvidenceProvider` 最终消费统一 `QueryResponse`。集成时应把上述 `KnowledgeBaseRetriever` 注入项目查询编排层，再由查询层生成 `QueryResponse` / `EvidencePack`；不要让 FMEA 代码直接访问 SQLite。

### M3 原生查询接口

- `KnowledgeBaseQueryService.search(...) -> list[SearchHit]`
- `KnowledgeBaseQueryService.answer(...) -> RagAnswer`

`SearchHit` 适合 M4/M5 的程序化证据消费；`RagAnswer` 适合基础 RAG 展示。语义/混合检索必须同时传入真实 `embedder` 和与索引一致的 `embedding_model`。

## 4. 版本与权限规则

1. M4、M5 每次运行必须显式固定 M3 version，不能在一次任务中使用“当前最新版本”漂移。
2. M4 graph version 和 M5 artifact version 必须记录同一个 M3 version / manifest。
3. `required_access_labels` 必须从 M2 原资料一路传播到图谱关系、检索结果和 FMEA EvidencePack。
4. 下游只保存 M3 返回的 ID 和证据定位，不复制后再自行生成另一套不可追踪 ID。
