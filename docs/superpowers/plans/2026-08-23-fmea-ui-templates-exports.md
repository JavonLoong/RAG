# FMEA UI, Templates, and Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成第四阶段的 FMEA normalized export DTO、JSON/XLSX/Word 安全导出、声明式模板与 Excel 导入、独立原生 ES Modules 工作台、Playwright 主链、20 条非认证燃烧/燃料夹具和最终一致性验收。

**Architecture:** 前三阶段提供的 `FmeaService` 读取不可变 revision，并通过 `fmea_application/ports.py` 生成一个唯一的 `NormalizedFmeaSnapshot`；JSON 是规范序列化，XLSX 和 Word 只能把同一 snapshot 映射为展示文件。模板服务使用 JSON Schema 2020-12 加受限 DSL，Excel 导入只产生草案，LLM 只产生带 diff 和 ledger 的 patch candidate。`frontend_app/current_console/fmea.html` 是独立薄壳，所有数据经 `graphrag.fmea.v1` API 和 SSE 进入状态 store，证据、传播、审核、发布和导出界面均不直接访问 SQLite。

**Tech Stack:** Python 3.11+, Pydantic 2, `orjson`, `jsonschema` Draft 2020-12, `openpyxl`, `python-docx`, FastAPI/TestClient, vanilla JavaScript ES Modules, Playwright Chromium, pytest, ruff, mypy, `tomllib` fixtures。

**Spec:** `docs/superpowers/specs/2026-08-23-graphrag-fmea-system-design.md`

## Global Constraints

- 只实现规格中的 `OWN` 项；`INTEGRATE` 只能实现合同、适配器、mock、fixture 和接入测试；`DEPEND` 只能写前置条件、可验证输入和失败行为；规格中的 `OUT` 项不生成任务。
- 接前三计划的可用实现：`SqliteFmeaRepository`、`FmeaService`、`FmeaCandidatePipeline` 和稳定的审核/发布状态机；缺任一实现时测试必须返回明确的 `DEPENDENCY_NOT_READY`，不得在本阶段重写其业务。
- 共享类型名保持逐字一致：`ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `ActorType`, `RunStatus`, `VersionSet`, `EvidenceRef`, `EvidencePack`, `EvidenceSupportStatus`, `FmeaAnalysis`, `FmeaRow`, `RiskAssessment`, `PropagationEdge`, `ScoringRulePack`。
- 所有应用端口只定义在 `fmea_application/ports.py`；持久化实现只使用 `SqliteFmeaRepository`；应用入口只使用 `FmeaService`；候选入口只使用 `FmeaCandidatePipeline`。
- 所有 HTTP、CLI、浏览器 fixtures 和导出 manifest 使用接口 schema 标识 `graphrag.fmea.v1`；不新增 `QueryMode.FMEA`，不创建顶级 `graphrag` Python 包。
- 规范输出只允许来自不可变 published revision，或显式标记为 `draft_preview` 的快照；浏览器当前未保存状态不能进入导出。
- 三条状态轴独立保存：`known | unknown | insufficient_evidence | conflict | not_applicable`、`draft | suggested | in_review | accepted | rejected | superseded`、`unpublished | published | withdrawn`；`published` 不显示成 `certified`。
- 未通过 EvidencePack 的 workspace、ACL、document/version/hash、quote/span/cell 校验的证据不能成为 `known`；冲突来源全部保留，不能静默选边。
- unknown、conflict 或缺失评分不能转换为 0 或有效 RPN；措施缺少有效性证据时不能生成 `verified_residual_risk`。
- 模板生命周期严格为 `draft -> validating -> published -> deprecated`；已发布模板和评分版本不可原地修改，发布 FMEA 永久绑定其 `VersionSet`。
- 模板只允许 JSON Schema 2020-12、字段配置和有限 DSL；禁止任意 JavaScript、网络请求、任意公式、循环、跨表查询、模板决定权限/审批和用户上传服务端插件。
- Excel 文本以 `=`, `+`, `-`, `@` 开头时必须前置单引号；XLSX 禁止宏和外部链接；Word 只写纯文本或安全 XML，不拼接用户 HTML。
- 文件名、下载路径和 `Content-Disposition` 由服务端生成；导出下载先检查项目权限，长导出走 run 和临时产物；客户端不接受任意数据库路径、模型地址或 API Key。
- `frontend_app/current_console/index.html` 不得修改；新增页面只使用 `frontend_app/current_console/fmea.html` 和 `frontend_app/current_console/fmea/`。
- 20 条 fixture 是内部、非认证、非工业金标样本；每条保存 fixture ID、版本、预期不变量、证据来源、编写者、评审者、争议、许可证和变更历史。
- 每个任务结束都要执行该任务的精确测试命令并提交本任务文件；提交只包含任务列出的路径。实现者不得提交运行时 SQLite、上传文件、浏览器缓存、模型原始响应或导出二进制。

## Dependency Gate Before Task 1

前三计划必须先提供以下可验证合同；这些是 `DEPEND` 前置，不是本计划任务，也不要求本阶段建设上游模块。

1. `core_domain.fmea.contracts` 可导入全部共享类型，`fmea_application/ports.py` 已有前三计划的 `ActorContext`、`FmeaRepository`、`EvidenceProvider` 和 `CandidateGenerator`；本计划新增的 export/template 端口必须继续放在该文件。
2. `SqliteFmeaRepository.get_revision(revision_id)` 能返回不可变的 `RevisionSnapshot`，其中包含 `FmeaAnalysis`、`FmeaRow`、`RiskAssessment`、`PropagationEdge`、`EvidencePack` 和 `VersionSet`；published revision 的修改返回 `FMEA_REVISION_IMMUTABLE`。
3. `FmeaService` 已提供前三计划的 actor、权限、revision、review、approve、publish、withdraw 和 audit 行为；本计划 Task 2 在其上增加 `read_export_snapshot(revision_id, actor: ActorContext, draft_preview: bool) -> NormalizedFmeaSnapshot` 和 `export_revision(...)` 委托，服务缺少 EvidencePack 时返回 `insufficient_evidence`，不返回 `known`。
4. `FmeaCandidatePipeline` 能用固定 EvidencePack、固定模型 mock 和固定 budget 产生可审核 candidate；本计划不实现候选生成、LLM provider、GraphStore、OCR、Chroma、M1-M4 资料流程或 M6 编排器。
5. 阶段 F 已提供下列稳定 API 资源和命令合同供浏览器调用：`/api/v1/fmea/projects`、`/api/v1/fmea/analyses`、`/api/v1/fmea/revisions`、`/api/v1/fmea/rows`、`/api/v1/fmea/evidence-packs`、`/api/v1/fmea/propagation-edges`、`/api/v1/fmea/templates`、`/api/v1/fmea/template-versions`、`/api/v1/fmea/runs`、`/api/v1/fmea/exports`；写请求支持 `Idempotency-Key`，可变资源支持 `If-Match`，长任务返回 `run_id`、状态 URL、事件 URL 和取消 URL。

若依赖 gate 失败，执行：

```powershell
uv run python -c "from core_domain.fmea.contracts import EvidencePack, EvidenceRef, FmeaAnalysis, FmeaRow, PropagationEdge, RiskAssessment, ScoringRulePack, VersionSet; from fmea_application.ports import ActorContext, CandidateGenerator, EvidenceProvider, FmeaRepository; from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository; from fmea_application.services import FmeaService; from fmea_application.candidate_pipeline import FmeaCandidatePipeline; print('FMEA_DEPENDENCIES_READY')"
```

Expected failure contract: `DEPENDENCY_NOT_READY`；停止本计划实现，记录缺少的模块名和 import error，不新增替代 repository、替代 service 或替代 candidate pipeline。

## File and Interface Map

| Path | Responsibility in this plan |
| --- | --- |
| `fmea_application/ports.py` | 新增 snapshot/export/template/LLM-patch 端口；不移动既有端口。 |
| `fmea_application/export_dto.py` | `NormalizedFmeaSnapshot`、manifest 和导出 artifact 的不可变 DTO。 |
| `fmea_application/export_service.py` | 只从 service/repository 读取快照，选择导出 adapter，执行权限、状态、ETag 和文件名策略。 |
| `fmea_infrastructure/exporters/json_exporter.py` | `NormalizedFmeaSnapshot -> graphrag.fmea.v1 JSON`。 |
| `fmea_infrastructure/exporters/xlsx_exporter.py` | `NormalizedFmeaSnapshot -> .xlsx`，公式注入和外链/宏安全。 |
| `fmea_infrastructure/exporters/word_exporter.py` | `NormalizedFmeaSnapshot -> .docx`，纯文本安全写入。 |
| `fmea_infrastructure/templates/schemas/template-v1.schema.json` | 服务端唯一的 JSON Schema 2020-12 模板合同。 |
| `fmea_infrastructure/templates/schema_loader.py` | schema hash、Draft 2020-12 validation 和受限规则解析。 |
| `fmea_application/template_service.py` | 模板 draft/validate/publish/deprecate 生命周期和版本绑定。 |
| `fmea_infrastructure/templates/excel_import.py` | Excel hash、工作表/行列/cell/merge、未知列和歧义表头提取。 |
| `fmea_application/template_import_service.py` | Excel 草案保存、LLM patch ledger、人工接受/拒绝。 |
| `frontend_app/current_console/fmea.html` | 独立工作台入口；不改现有 `index.html`。 |
| `frontend_app/current_console/fmea/` | 原生 ES Modules、状态、API/SSE、证据/传播/审核/发布/模板/导出视图。 |
| `tests/fixtures/fmea/non_certified_cases.toml` | 10 条燃烧系统、10 条燃料系统内部 fixture。 |
| `tests/fixtures/fmea/security_fault_cases.toml` | prompt injection、证据、版本、provider、幂等和重连故障 fixture。 |
| `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/acceptance/` | 红绿单元、合同、Playwright 主链和最终一致性门。 |

---

### Task 1: Freeze the Normalized Export Snapshot Boundary

**Responsibility:** `OWN` — JSON/XLSX/Word normalized snapshot 和导出合同；只消费前三计划的 `FmeaService`/`SqliteFmeaRepository`。

**Files:**
- Modify: `fmea_application/ports.py`
- Create: `fmea_application/export_dto.py`
- Modify: `.gitignore` (仅增加已审查的 schema/config 例外，不放宽运行时 JSON)
- Create: `tests/unit/test_fmea_export_dto.py`

**Interfaces:**
- Consumes: `FmeaAnalysis`, `FmeaRow`, `RiskAssessment`, `PropagationEdge`, `EvidencePack`, `EvidenceRef`, `VersionSet`, `ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `ActorType` from前三计划。
- Produces: `SnapshotReader.read_snapshot(revision_id: str, *, actor: ActorContext, draft_preview: bool = False) -> NormalizedFmeaSnapshot`; `ExportArtifact` with `revision_id`, `snapshot_hash`, `format`, `content_type`, `filename`, `sha256`, `path`。

- [ ] **Step 1: Write the failing DTO and port test**

Add `tests/unit/test_fmea_export_dto.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmea_application.export_dto import NormalizedFmeaSnapshot


def test_snapshot_rejects_wrong_schema_and_is_immutable(snapshot_factory):
    snapshot = snapshot_factory(schema_version="graphrag.fmea.v1")
    assert snapshot.schema_version == "graphrag.fmea.v1"
    with pytest.raises(TypeError):
        snapshot.revision_id = "rev-mutated"


def test_snapshot_requires_same_revision_in_manifest(snapshot_factory):
    payload = snapshot_factory(revision_id="rev-1").model_dump(mode="python")
    payload["manifest"]["revision_id"] = "rev-2"
    with pytest.raises(ValueError, match="revision_id"):
        NormalizedFmeaSnapshot.model_validate(payload)


def test_snapshot_hash_is_deterministic(snapshot_factory):
    left = snapshot_factory(created_at=datetime(2026, 8, 23, tzinfo=timezone.utc))
    right = snapshot_factory(created_at=datetime(2026, 8, 23, tzinfo=timezone.utc))
    assert left.canonical_hash() == right.canonical_hash()
```

The fixture factory must construct real shared types, not dictionaries that bypass validation; it must include one `FmeaRow`, one `EvidenceRef`, one `RiskAssessment`, one `PropagationEdge` and one `EvidencePack`.

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
uv run pytest tests/unit/test_fmea_export_dto.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'fmea_application.export_dto'`.

- [ ] **Step 3: Add the minimal immutable DTO and port**

Add these exact contracts. The existing `ports.py` declarations remain in place:

```python
# fmea_application/export_dto.py
from __future__ import annotations

from hashlib import sha256
from typing import Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core_domain.fmea.contracts import (
    EvidencePack,
    EvidenceRef,
    FmeaAnalysis,
    FmeaRow,
    PropagationEdge,
    VersionSet,
)


class ExportManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    analysis_id: str
    revision_id: str
    parent_revision_id: str | None
    schema_version: Literal["graphrag.fmea.v1"]
    version_set: VersionSet
    snapshot_hash: str
    evidence_manifest: tuple[EvidenceRef, ...]
    unresolved_item_ids: tuple[str, ...]
    disclaimer: str = "非认证、非安全批准、需专业人员负责。"


class NormalizedFmeaSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["graphrag.fmea.v1"]
    revision_id: str
    analysis: FmeaAnalysis
    version_set: VersionSet
    evidence_pack: EvidencePack
    rows: tuple[FmeaRow, ...]
    propagation_edges: tuple[PropagationEdge, ...]
    snapshot_hash: str
    manifest: ExportManifest
    source_revision_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_manifest_identity(self) -> NormalizedFmeaSnapshot:
        if self.manifest.revision_id != self.revision_id:
            raise ValueError("manifest.revision_id must equal snapshot.revision_id")
        if self.manifest.analysis_id != self.analysis.analysis_id:
            raise ValueError("manifest.analysis_id must equal analysis.analysis_id")
        if self.manifest.version_set != self.version_set:
            raise ValueError("manifest.version_set must equal snapshot.version_set")
        if self.manifest.snapshot_hash != self.snapshot_hash:
            raise ValueError("manifest.snapshot_hash must equal snapshot.snapshot_hash")
        return self

    def canonical_bytes(self) -> bytes:
        payload = self.model_dump(mode="json", exclude={"manifest": {"snapshot_hash"}})
        return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)

    def canonical_hash(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


class ExportArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision_id: str
    snapshot_hash: str
    format: Literal["json", "xlsx", "docx"]
    content_type: str
    filename: str
    sha256: str
    path: str
```

Add to `fmea_application/ports.py`:

```python
class SnapshotReader(Protocol):
    def read_snapshot(
        self, revision_id: str, *, actor: ActorContext, draft_preview: bool = False
    ) -> NormalizedFmeaSnapshot: ...


class ExportWriter(Protocol):
    format: Literal["json", "xlsx", "docx"]

    def write(self, snapshot: NormalizedFmeaSnapshot, destination: Path) -> ExportArtifact: ...
```

Use the existing `ActorContext`/`ActorType` from `fmea_application/ports.py` and import the DTO with a local type-checking import if needed; do not introduce a second `ActorType` or a second repository protocol.

Add these `.gitignore` exceptions after the existing broad `*.json` rule so committed schemas remain trackable while runtime JSON remains ignored:

```gitignore
!fmea_infrastructure/templates/schemas/*.json
!frontend_app/current_console/fmea/schemas/*.json
```

- [ ] **Step 4: Run the DTO tests to verify they pass**

Run:

```powershell
uv run pytest tests/unit/test_fmea_export_dto.py -q
```

Expected: PASS with all three tests passing and no mutable snapshot assignment accepted.

- [ ] **Step 5: Commit the snapshot boundary**

```powershell
git add fmea_application/ports.py fmea_application/export_dto.py tests/unit/test_fmea_export_dto.py .gitignore
git commit -m "feat: freeze FMEA normalized export snapshot"
```

### Task 2: Implement the Canonical JSON Export and Service Boundary

**Responsibility:** `OWN` —规范 JSON、manifest hash、draft/published 读取策略；不实现 REST 路由或 CLI。

**Files:**
- Modify: `fmea_application/services.py`
- Create: `fmea_application/export_service.py`
- Create: `fmea_infrastructure/exporters/json_exporter.py`
- Create: `tests/unit/test_fmea_json_export.py`
- Create: `tests/integration/test_fmea_export_service.py`

**Interfaces:**
- Consumes: `SnapshotReader`, `ExportWriter`, `NormalizedFmeaSnapshot`, `ActorContext`, `FmeaService` and `SqliteFmeaRepository` through the existing service assembly。
- Produces: `FmeaService.read_export_snapshot(revision_id: str, *, actor: ActorContext, draft_preview: bool = False) -> NormalizedFmeaSnapshot`; `FmeaService.export_revision(revision_id: str, *, format: Literal["json", "xlsx", "docx"], actor: ActorContext, draft_preview: bool = False) -> ExportArtifact`; JSON body contains one `schema_version` and the same `revision_id`/`snapshot_hash` as the snapshot。

- [ ] **Step 1: Write the red unit and integration tests**

Add `tests/unit/test_fmea_json_export.py`:

```python
import orjson
import pytest

from fmea_application.export_service import ExportService


def test_json_export_uses_snapshot_hash_and_never_serializes_browser_state(tmp_path, snapshot_reader, json_writer, human_actor):
    service = ExportService(reader=snapshot_reader, writers={"json": json_writer}, output_root=tmp_path)
    artifact = service.export_revision("rev-42", format="json", actor=human_actor)
    body = orjson.loads((tmp_path / artifact.filename).read_bytes())
    assert body["schema_version"] == "graphrag.fmea.v1"
    assert body["revision_id"] == "rev-42"
    assert body["snapshot_hash"] == artifact.snapshot_hash
    assert "unsaved_browser_state" not in body
    assert artifact.filename == "fmea-rev-42-graphrag-v1.json"


def test_json_export_blocks_model_from_publishing_snapshot(tmp_path, snapshot_reader, json_writer, model_actor):
    snapshot_reader.reject_actor("model", code="FMEA_ACTOR_FORBIDDEN")
    service = ExportService(reader=snapshot_reader, writers={"json": json_writer}, output_root=tmp_path)
    with pytest.raises(PermissionError, match="FMEA_ACTOR_FORBIDDEN"):
        service.export_revision("rev-42", format="json", actor=model_actor)
```

Add `tests/integration/test_fmea_export_service.py` with a `SqliteFmeaRepository` fixture and assert that a published revision is readable twice with the same hash, while a mutable revision with stale `record_version` returns `FMEA_VERSION_CONFLICT` and does not create a file.

- [ ] **Step 2: Run the red tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_json_export.py tests/integration/test_fmea_export_service.py -q
```

Expected: FAIL because `ExportService` and `json_exporter` do not exist.

- [ ] **Step 3: Implement the minimal service and JSON writer**

Implement the service with a fixed writer map and a server-generated destination:

```python
class ExportService:
    def __init__(self, *, reader: SnapshotReader, writers: Mapping[str, ExportWriter], output_root: Path) -> None:
        self._reader = reader
        self._writers = dict(writers)
        self._output_root = output_root.resolve()

    def export_revision(self, revision_id: str, *, format: str, actor: ActorContext, draft_preview: bool = False) -> ExportArtifact:
        if format not in {"json", "xlsx", "docx"}:
            raise ValueError("FMEA_EXPORT_FORMAT_UNSUPPORTED")
        snapshot = self._reader.read_snapshot(revision_id, actor=actor, draft_preview=draft_preview)
        if not draft_preview and snapshot.manifest.schema_version != "graphrag.fmea.v1":
            raise ValueError("FMEA_SCHEMA_VERSION_UNSUPPORTED")
        destination = self._output_root / f"fmea-{revision_id}-graphrag-v1.{format}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        return self._writers[format].write(snapshot, destination)
```

The JSON writer must dump `snapshot.model_dump(mode="json")` with `orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS`, set both top-level `snapshot_hash` and `manifest.snapshot_hash` to the already validated `snapshot.canonical_hash()`, and return the SHA-256 of the bytes written. It must never accept a client filename, path or body object as input.

Extend the existing `FmeaService` rather than adding a parallel application entry:

```python
def read_export_snapshot(self, revision_id: str, *, actor: ActorContext, draft_preview: bool = False) -> NormalizedFmeaSnapshot:
    revision = self.repository.get_revision(revision_id)
    self.policy.require_project_read(actor, revision.project_id)
    if revision.publication_status.value != "published" and not draft_preview:
        raise PermissionError("FMEA_EXPORT_REQUIRES_PUBLISHED_REVISION")
    return build_normalized_snapshot(revision, draft_preview=draft_preview)


def export_revision(self, revision_id: str, *, format: str, actor: ActorContext, draft_preview: bool = False) -> ExportArtifact:
    snapshot = self.read_export_snapshot(revision_id, actor=actor, draft_preview=draft_preview)
    return self.export_service.export_snapshot(snapshot, format=format)
```

`build_normalized_snapshot` must re-run EvidencePack/ACL/version/hash validation before constructing the DTO; it may not serialize a request body or browser store. The service must append the existing audit event for a successful export request and a failure event with a stable code for a denied request.

- [ ] **Step 4: Run the green tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_json_export.py tests/integration/test_fmea_export_service.py -q
```

Expected: PASS; the output directory contains only the server-generated JSON file and no runtime database artifact.

- [ ] **Step 5: Commit the JSON export boundary**

```powershell
git add fmea_application/export_service.py fmea_infrastructure/exporters/json_exporter.py tests/unit/test_fmea_json_export.py tests/integration/test_fmea_export_service.py
git commit -m "feat: add canonical FMEA JSON export"
```

### Task 3: Add Safe XLSX and Word Adapters

**Responsibility:** `OWN` —同一 normalized DTO 的安全展示适配；不建设通用办公文档平台。

**Files:**
- Modify: `pyproject.toml`
- Create: `fmea_infrastructure/exporters/xlsx_exporter.py`
- Create: `fmea_infrastructure/exporters/word_exporter.py`
- Create: `tests/unit/test_fmea_xlsx_export.py`
- Create: `tests/unit/test_fmea_word_export.py`
- Create: `tests/integration/test_fmea_export_consistency.py`

**Interfaces:**
- Consumes: `NormalizedFmeaSnapshot` and `ExportWriter` from Tasks 1-2; `openpyxl` and existing `python-docx`.
- Produces: `XlsxExporter.write(snapshot, destination) -> ExportArtifact`, `WordExporter.write(snapshot, destination) -> ExportArtifact`; both preserve `revision_id`, `snapshot_hash`, row IDs, evidence counts, state axes and risk fields from JSON.

- [ ] **Step 1: Write red security and consistency tests**

Add `tests/unit/test_fmea_xlsx_export.py`:

```python
from zipfile import ZipFile

from openpyxl import load_workbook

from fmea_infrastructure.exporters.xlsx_exporter import XlsxExporter


def test_xlsx_escapes_formula_prefix_and_has_no_macro_or_external_link(tmp_path, snapshot_factory):
    snapshot = snapshot_factory(row_text="=HYPERLINK(\"https://evil.example\",\"open\")")
    artifact = XlsxExporter().write(snapshot, tmp_path / "safe.xlsx")
    workbook = load_workbook(artifact.path, data_only=False, keep_links=False)
    assert workbook.active["D2"].value.startswith("'=HYPERLINK")
    assert workbook.vba_archive is None
    with ZipFile(artifact.path) as archive:
        assert not any(name.startswith("xl/externalLinks/") for name in archive.namelist())
```

Add `tests/unit/test_fmea_word_export.py`:

```python
from zipfile import ZipFile

from fmea_infrastructure.exporters.word_exporter import WordExporter


def test_word_writes_untrusted_text_as_text(tmp_path, snapshot_factory):
    artifact = WordExporter().write(snapshot_factory(row_text="<script>alert(1)</script>"), tmp_path / "safe.docx")
    with ZipFile(artifact.path) as archive:
        xml = archive.read("word/document.xml")
    assert b"<script>" not in xml
    assert b"&lt;script&gt;" in xml
    assert b"w:hyperlink" not in xml
```

`tests/integration/test_fmea_export_consistency.py` must call the same `ExportService` three times and assert:

```python
assert {(item.revision_id, item.snapshot_hash) for item in artifacts} == {("rev-42", expected_hash)}
assert json_payload["rows"][0]["row_id"] == xlsx_sheet["A2"].value == word_row_id
assert json_payload["manifest"]["evidence_manifest"]
```

- [ ] **Step 2: Run the red tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_xlsx_export.py tests/unit/test_fmea_word_export.py tests/integration/test_fmea_export_consistency.py -q
```

Expected: FAIL because the two exporters and explicit XLSX dependency are absent.

- [ ] **Step 3: Add dependencies and minimal safe writers**

Run:

```powershell
uv add "openpyxl>=3.1.5"
```

In `xlsx_exporter.py`, use `Workbook()` with no macros, no formulas, no hyperlinks and `keep_links=False`; write the first row as fixed semantic headers and the second row from `FmeaRow`. Every text cell must pass:

```python
def safe_excel_text(value: object) -> object:
    text = str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text
```

The exporter must write manifest metadata in a dedicated `Manifest` worksheet, set `workbook.properties.title`, never call `cell.hyperlink`, and verify after save that no `xl/externalLinks/` entry exists. It must place `row_id` in column A and the exact fields `failure_mode`, `claim_status`, `review_status`, `publication_status`, `rpn`, `evidence_count`, `revision_id`, `snapshot_hash` in fixed columns.

In `word_exporter.py`, use `Document()`, `add_heading`, `add_table`, `cell.text = str(value)`, and `add_paragraph` only. Do not pass strings to an HTML/XML parser; `python-docx` performs XML escaping for plain text. Include the same manifest values and disclaimer as JSON.

- [ ] **Step 4: Run the green tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_xlsx_export.py tests/unit/test_fmea_word_export.py tests/integration/test_fmea_export_consistency.py -q
```

Expected: PASS with identical revision/snapshot identity and zero macro/external-link findings.

- [ ] **Step 5: Commit the office exporters**

```powershell
git add pyproject.toml uv.lock fmea_infrastructure/exporters/xlsx_exporter.py fmea_infrastructure/exporters/word_exporter.py tests/unit/test_fmea_xlsx_export.py tests/unit/test_fmea_word_export.py tests/integration/test_fmea_export_consistency.py
git commit -m "feat: add safe FMEA XLSX and Word exports"
```

### Task 4: Build the Declarative Template Schema and Lifecycle

**Responsibility:** `OWN` —声明式 JSON Schema、受限规则、版本生命周期；不建设低代码画布、插件平台或任意执行器。

**Files:**
- Create: `fmea_infrastructure/templates/schemas/template-v1.schema.json`
- Create: `fmea_infrastructure/templates/schema_loader.py`
- Create: `fmea_application/template_service.py`
- Create: `tests/unit/test_fmea_template_schema.py`
- Create: `tests/integration/test_fmea_template_lifecycle.py`

**Interfaces:**
- Consumes: `VersionSet`, `ActorType`, `SqliteFmeaRepository`/template store port from前三计划。
- Produces: `TemplateService.validate_draft(payload: Mapping[str, object]) -> TemplateValidationReport`; `TemplateService.transition(template_id: str, target: Literal["validating", "published", "deprecated"], *, actor: ActorContext, record_version: int) -> TemplateVersion`; `TemplateVersion.state` is exactly `draft | validating | published | deprecated`。

- [ ] **Step 1: Write red schema and lifecycle tests**

Add `tests/unit/test_fmea_template_schema.py`:

```python
import pytest

from fmea_infrastructure.templates.schema_loader import TemplateSchemaError, validate_template_payload


def test_template_accepts_namespaced_extension_and_rejects_executable_keys():
    payload = {
        "schema_version": "graphrag.fmea.v1",
        "template_id": "gas-turbine-fmea",
        "version": "1.0.0",
        "fields": [{"name": "gas_turbine.fuel.wobbe_index", "type": "number", "required": False}],
        "rules": [{"kind": "required_if", "when": {"field": "analysis_type", "equals": "fuel_system"}, "field": "fuel_type"}],
    }
    assert validate_template_payload(payload).errors == []
    payload["rules"][0]["script"] = "fetch('https://evil.example')"
    with pytest.raises(TemplateSchemaError, match="script"):
        validate_template_payload(payload)


@pytest.mark.parametrize("key", ["network", "formula", "loop", "cross_table_query", "permission", "approval"])
def test_template_rejects_non_declarative_keys(key):
    payload = {"schema_version": "graphrag.fmea.v1", "template_id": "t", "version": "1.0.0", "fields": [], "rules": [], key: True}
    with pytest.raises(TemplateSchemaError, match=key):
        validate_template_payload(payload)
```

Add `tests/integration/test_fmea_template_lifecycle.py`:

```python
def test_published_template_is_immutable_and_only_human_can_publish(template_service, human_template_admin, model_template_admin):
    draft = template_service.create_draft(valid_payload())
    assert template_service.transition(draft.template_id, "validating", actor=human_template_admin, record_version=1).state == "validating"
    with pytest.raises(PermissionError, match="FMEA_ACTOR_FORBIDDEN"):
        template_service.transition(draft.template_id, "published", actor=model_template_admin, record_version=2)
    published = template_service.transition(draft.template_id, "published", actor=human_template_admin, record_version=2)
    with pytest.raises(ValueError, match="FMEA_TEMPLATE_IMMUTABLE"):
        template_service.update_draft(draft.template_id, valid_payload(), record_version=published.record_version)
```

- [ ] **Step 2: Run the red tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_template_schema.py tests/integration/test_fmea_template_lifecycle.py -q
```

Expected: FAIL because the schema loader and template service do not exist.

- [ ] **Step 3: Add the JSON Schema and whitelist-only validator**

Create `template-v1.schema.json` with `$schema` `https://json-schema.org/draft/2020-12/schema`, `additionalProperties: false`, and these exact top-level properties: `schema_version`, `template_id`, `version`, `fields`, `rules`, `scoring_rule_pack_id`, `export_mappings`. `fields[].name` must match `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$` for custom namespaces; `fields[].type` is one of `string`, `integer`, `number`, `boolean`, `enum`, `evidence_ref`; `rules[].kind` is one of `required_if`, `visible_if`, `enum`, `min_length`, `max_length`; `export_mappings` values are fixed semantic field names or namespaced extension names.

The loader must call `Draft202012Validator.check_schema`, reject unknown executable-looking keys before validation, calculate a schema hash with SHA-256, and evaluate rules without `eval`, imports, HTTP clients, database handles, or function calls. The only conditional expression is `{field, equals}`; only `required_if`, `visible_if`, `enum`, `min_length`, and `max_length` are accepted.

Implement lifecycle guards:

```python
ALLOWED_TRANSITIONS = {
    "draft": {"validating"},
    "validating": {"published"},
    "published": {"deprecated"},
    "deprecated": set(),
}

def assert_template_transition(current: str, target: str, actor: ActorContext) -> None:
    if actor.actor_type.value != "human" or "template_admin" not in actor.roles:
        raise PermissionError("FMEA_ACTOR_FORBIDDEN")
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError("FMEA_TEMPLATE_TRANSITION_INVALID")
```

Use the exact enum member spelling already defined by前三计划; if that enum serializes to `human`, keep the wire value `human` and do not create a second actor enum.

- [ ] **Step 4: Run the green tests and schema hash check**

Run:

```powershell
uv run pytest tests/unit/test_fmea_template_schema.py tests/integration/test_fmea_template_lifecycle.py -q
uv run python -c "from pathlib import Path; from fmea_infrastructure.templates.schema_loader import schema_hash; print(schema_hash(Path('fmea_infrastructure/templates/schemas/template-v1.schema.json')))"
```

Expected: PASS; the second command prints one 64-character lowercase SHA-256 hash.

- [ ] **Step 5: Commit the declarative template lifecycle**

```powershell
git add fmea_infrastructure/templates/schemas/template-v1.schema.json fmea_infrastructure/templates/schema_loader.py fmea_application/template_service.py tests/unit/test_fmea_template_schema.py tests/integration/test_fmea_template_lifecycle.py
git commit -m "feat: add declarative FMEA template lifecycle"
```

### Task 5: Import Excel Templates and Record LLM Patch Candidates

**Responsibility:** `OWN` for import, draft and patch ledger; `INTEGRATE` for the LLM suggester mock only. No model provider or enterprise DLP is built here.

**Files:**
- Modify: `fmea_application/ports.py`
- Modify: `fmea_infrastructure/repository_sqlite.py`
- Create: `fmea_infrastructure/templates/excel_import.py`
- Create: `fmea_application/template_import_service.py`
- Create: `tests/unit/test_fmea_excel_import.py`
- Create: `tests/unit/test_fmea_template_patch.py`
- Create: `tests/integration/test_fmea_excel_import_persistence.py`

**Interfaces:**
- Consumes: `SqliteFmeaRepository`, `ActorType`, `VersionSet`, `TemplateService` and a mock-only `TemplatePatchSuggester`.
- Produces: `ExcelTemplateDraft(source_sha256: str, sheets: tuple[...], unknown_columns: tuple[str, ...], ambiguous_headers: tuple[str, ...], merged_ranges: tuple[str, ...], state="draft")`; `TemplatePatchCandidate(patch_id, base_template_version, model_id, prompt_hash, diff, status="suggested")`; `TemplateImportService.import_excel(raw_bytes: bytes, filename: str, ...) -> ExcelTemplateDraft` and `suggest_patch(..., actor: ActorContext) -> TemplatePatchCandidate`。

- [ ] **Step 1: Write red import and patch tests**

Add `tests/unit/test_fmea_excel_import.py`:

```python
from io import BytesIO

import pytest
from openpyxl import Workbook

from fmea_infrastructure.templates.excel_import import ExcelTemplateError, inspect_excel_template


def workbook_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "FMEA"
    sheet.append(["Row ID", "Failure Mode", "未知列"])
    sheet.append(["fuel-001", "阀卡滞", "保留原文"])
    sheet.merge_cells("A3:B3")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_import_records_hash_cells_unknown_header_and_merge():
    draft = inspect_excel_template(workbook_bytes(), filename="input.xlsx")
    assert len(draft.source_sha256) == 64
    assert draft.sheets[0].name == "FMEA"
    assert draft.sheets[0].cells["A2"].value == "fuel-001"
    assert draft.unknown_columns == ("未知列",)
    assert "A3:B3" in draft.merged_ranges
    assert draft.state == "draft"


@pytest.mark.parametrize("filename", ["input.xlsm", "input.xlsx"])
def test_import_rejects_macro_or_external_link_payload(filename):
    raw = b"PK\x03\x04" if filename.endswith("xlsm") else b"not-an-excel-file"
    with pytest.raises(ExcelTemplateError):
        inspect_excel_template(raw, filename=filename)
```

Add `tests/unit/test_fmea_template_patch.py`:

```python
def test_model_patch_is_suggestion_and_human_decision_is_audit_event(template_import_service, model_actor, human_actor):
    candidate = template_import_service.suggest_patch("template-1@1.0.0", actor=model_actor)
    assert candidate.status == "suggested"
    assert candidate.diff[0]["op"] in {"add", "replace"}
    with pytest.raises(PermissionError, match="FMEA_MODEL_CANNOT_PUBLISH"):
        template_import_service.accept_patch(candidate.patch_id, actor=model_actor, record_version=1)
    accepted = template_import_service.accept_patch(candidate.patch_id, actor=human_actor, record_version=1)
    assert accepted.status == "accepted"
    assert accepted.audit_event_id
```

- [ ] **Step 2: Run the red tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_excel_import.py tests/unit/test_fmea_template_patch.py tests/integration/test_fmea_excel_import_persistence.py -q
```

Expected: FAIL because the importer, patch service and repository methods do not exist.

- [ ] **Step 3: Implement deterministic Excel inspection and the patch ledger**

Read raw bytes first and calculate SHA-256. Load with `openpyxl.load_workbook(BytesIO(raw_bytes), read_only=False, data_only=False, keep_links=False)`. Reject a `.xlsm` suffix, a non-zip workbook, `workbook.vba_archive is not None`, and any non-empty `workbook._external_links`. For each worksheet save name, `max_row`, `max_column`, every non-empty cell address/value/data type, and every merged range. Normalize headers with Unicode trim and `casefold`; preserve unknown headers and mark duplicate aliases as `ambiguous_headers` instead of guessing.

The imported object must always be `state="draft"`, carry `source_sha256`, filename, sheet/cell coordinates and the original unknown header text. It must never invoke the template publisher.

Add these ports in `fmea_application/ports.py`:

```python
class TemplatePatchSuggester(Protocol):
    def suggest(self, *, template_version: str, import_summary: Mapping[str, object], actor: ActorContext) -> tuple[dict, ...]: ...


class TemplateDraftStore(Protocol):
    def save_excel_draft(self, draft: ExcelTemplateDraft) -> str: ...
    def save_patch_candidate(self, candidate: TemplatePatchCandidate) -> str: ...
    def decide_patch(self, patch_id: str, *, actor: ActorContext, record_version: int, decision: str) -> TemplatePatchCandidate: ...
```

`SqliteFmeaRepository` implements those methods transactionally with unique `(source_sha256, template_id)` and `(patch_id, record_version)` constraints. A patch is accepted only when `actor.actor_type.value == "human"`; the candidate stores input template version, model ID, prompt hash, exact JSON diff, created time, and accept/reject actor/reason. The mock suggester is the only model implementation in this task and returns a bounded JSON Patch tuple; it cannot call filesystem, network or repository methods.

- [ ] **Step 4: Run the green tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_excel_import.py tests/unit/test_fmea_template_patch.py tests/integration/test_fmea_excel_import_persistence.py -q
```

Expected: PASS; unknown and ambiguous columns remain visible, imported content is draft-only, and model actors cannot accept a patch.

- [ ] **Step 5: Commit Excel import and patch candidates**

```powershell
git add fmea_application/ports.py fmea_infrastructure/repository_sqlite.py fmea_infrastructure/templates/excel_import.py fmea_application/template_import_service.py tests/unit/test_fmea_excel_import.py tests/unit/test_fmea_template_patch.py tests/integration/test_fmea_excel_import_persistence.py
git commit -m "feat: import Excel templates and ledger LLM patches"
```

### Task 6: Create the Independent FMEA ES Module Workbench Shell

**Responsibility:** `OWN` —独立 FMEA 页面、状态、API/SSE client；`INTEGRATE` only consumes the stage F API contract. `index.html` remains untouched.

**Files:**
- Create: `frontend_app/current_console/fmea.html`
- Create: `frontend_app/current_console/fmea/bootstrap.js`
- Create: `frontend_app/current_console/fmea/config.js`
- Create: `frontend_app/current_console/fmea/state/store.js`
- Create: `frontend_app/current_console/fmea/api/client.js`
- Create: `frontend_app/current_console/fmea/api/runs.js`
- Create: `frontend_app/current_console/fmea/api/sse.js`
- Create: `frontend_app/current_console/fmea/domain/fmea.js`
- Create: `frontend_app/current_console/fmea/schemas/ui-state.schema.json`
- Create: `frontend_app/current_console/fmea/fmea.css`
- Create: `tests/unit/test_fmea_ui_structure.py`

**Interfaces:**
- Consumes: stage F endpoints under `/api/v1/fmea`, response `schema_version="graphrag.fmea.v1"`, `application/problem+json`, `ETag`, `If-Match`, `Idempotency-Key`, `run_id`, `Location`, SSE monotonic event ID and `Last-Event-ID`。
- Produces: `createFmeaStore(initialState, reducer)`, `fmeaApi.request(path, options)`, `connectRunEvents(runId, handlers)`, and DOM test IDs `fmea-project`, `fmea-analysis`, `project-select`, `analysis-save`, `fmea-run-start`, `fmea-run-status`, `fmea-event-count`, `fmea-row-table`, `fmea-row-id-{row_id}`, `fmea-evidence-sidebar`, `fmea-propagation`, `propagation-review-{row_id}`, `fmea-review`, `review-accept-row-{row_id}`, `conflict-panel`, `fmea-publication`, `publish-button`, `approve-revision`, `publish-revision`, `publication-status`, `fmea-template`, `fmea-export`, `export-json`, `export-xlsx`, `export-docx`, `export-identity`。

- [ ] **Step 1: Write the red static-shell tests**

Add `tests/unit/test_fmea_ui_structure.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_fmea_page_is_independent_and_does_not_modify_existing_console():
    page = (ROOT / "frontend_app/current_console/fmea.html").read_text(encoding="utf-8")
    old_index = (ROOT / "frontend_app/current_console/index.html").read_text(encoding="utf-8")
    assert '<script type="module" src="./fmea/bootstrap.js"></script>' in page
    assert "fmea-run-start" in page
    assert "frontend_app/current_console/index.html" not in page
    assert "innerHTML =" not in page
    assert len(old_index) > 300_000


def test_fmea_modules_use_text_content_and_schema_version_guard():
    client = (ROOT / "frontend_app/current_console/fmea/api/client.js").read_text(encoding="utf-8")
    sse = (ROOT / "frontend_app/current_console/fmea/api/sse.js").read_text(encoding="utf-8")
    assert "graphrag.fmea.v1" in client
    assert "Last-Event-ID" in sse
    assert "textContent" in client or "textContent" in sse
    assert "eval(" not in client
```

- [ ] **Step 2: Run the red tests**

Run:

```powershell
uv run pytest tests/unit/test_fmea_ui_structure.py -q
```

Expected: FAIL because `fmea.html` and its modules do not exist.

- [ ] **Step 3: Implement the minimal shell and protocol-aware clients**

`fmea.html` must contain semantic landmarks and no inline business logic:

```html
<main id="fmea-app" data-read-only="false">
  <header><h1>FMEA 工作台</h1><span id="fmea-schema-version">graphrag.fmea.v1</span></header>
  <section id="fmea-project" data-testid="fmea-project"></section>
  <button id="fmea-run-start" data-testid="fmea-run-start" type="button">生成候选</button>
  <output id="fmea-run-status" data-testid="fmea-run-status">queued</output>
  <output id="fmea-event-count" data-testid="fmea-event-count">0</output>
  <section id="fmea-row-table" data-testid="fmea-row-table"></section>
  <aside id="fmea-evidence-sidebar" data-testid="fmea-evidence-sidebar"></aside>
  <section id="fmea-propagation" data-testid="fmea-propagation"></section>
  <section id="fmea-review" data-testid="fmea-review"></section>
  <section id="fmea-publication" data-testid="fmea-publication"></section>
  <section id="fmea-template" data-testid="fmea-template"></section>
  <section id="fmea-export" data-testid="fmea-export"></section>
</main>
<script type="module" src="./fmea/bootstrap.js"></script>
```

`client.js` must accept only relative server paths, add `schema_version` checks to successful JSON, map `application/problem+json` to `{code, status, retryable, errors}` without exposing stack/path/key/provider text, and pass `If-Match`/`Idempotency-Key` only from service-generated values. `store.js` uses reducer actions and freezes snapshots. `sse.js` uses `EventSource` or the injected transport, tracks the greatest numeric event ID, sends `Last-Event-ID` on reconnect, ignores duplicate IDs, and never calls the cancel endpoint merely because the browser disconnects. `config.js` marks `file:` and GitHub Pages demo mode as read-only and disables approve/publish/withdraw/real persistence.

Create `ui-state.schema.json` with `additionalProperties: false` for the client state projection only; it must not replace the server semantic schema.

- [ ] **Step 4: Run the green static tests and a module syntax check**

Run:

```powershell
uv run pytest tests/unit/test_fmea_ui_structure.py -q
node --check frontend_app/current_console/fmea/bootstrap.js
node --check frontend_app/current_console/fmea/api/client.js
node --check frontend_app/current_console/fmea/api/sse.js
```

Expected: PASS; all three JavaScript checks exit 0 and `index.html` is byte-for-byte unchanged.

- [ ] **Step 5: Commit the independent shell**

```powershell
git add frontend_app/current_console/fmea.html frontend_app/current_console/fmea tests/unit/test_fmea_ui_structure.py
git commit -m "feat: add independent FMEA ES module shell"
```

### Task 7: Implement Evidence, Propagation, Review, Publication, Template, and Export Views

**Responsibility:** `OWN` —FMEA workbench interaction and readable state expression；`INTEGRATE` —只读取已有 API/SSE/`FmeaService` contracts，不直接访问 GraphRAG 或 SQLite。

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `frontend_app/current_console/fmea/views/project-list.js`
- Create: `frontend_app/current_console/fmea/views/configuration.js`
- Create: `frontend_app/current_console/fmea/views/workbench.js`
- Create: `frontend_app/current_console/fmea/views/evidence-panel.js`
- Create: `frontend_app/current_console/fmea/views/propagation.js`
- Create: `frontend_app/current_console/fmea/views/review.js`
- Create: `frontend_app/current_console/fmea/views/publication.js`
- Create: `frontend_app/current_console/fmea/views/template-editor.js`
- Modify: `frontend_app/current_console/fmea/bootstrap.js`
- Modify: `frontend_app/current_console/fmea/domain/fmea.js`
- Modify: `frontend_app/current_console/fmea/fmea.css`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_fmea_views.py`

**Interfaces:**
- Consumes: `FmeaAnalysis`, `FmeaRow`, `RiskAssessment`, `EvidenceRef`, `EvidencePack`, `EvidenceSupportStatus`, `PropagationEdge`, `ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `RunStatus`, API `ETag` and review/publish/export commands。
- Produces: DOM behavior for fixed row IDs, evidence side panel, forward/backward propagation table, review diff actions, human-only publication checklist, template draft/preview and server-generated export download.

- [ ] **Step 1: Write the red Playwright view tests**

Add `tests/e2e/test_fmea_views.py`:

```python
from playwright.sync_api import expect


def test_workbench_exposes_evidence_status_and_review_diff(page, fmea_fixture_url):
    page.goto(f"{fmea_fixture_url}/fmea.html?fixture=views")
    expect(page.get_by_test_id("fmea-row-table")).to_contain_text("fuel-row-001")
    expect(page.get_by_test_id("fmea-evidence-sidebar")).to_contain_text("supported")
    expect(page.get_by_test_id("fmea-evidence-sidebar")).to_contain_text("页码")
    expect(page.get_by_test_id("fmea-review")).to_contain_text("模型建议")
    expect(page.get_by_test_id("fmea-review")).to_contain_text("工程师确认值")
    expect(page.get_by_test_id("fmea-propagation")).to_contain_text("前向影响")
    expect(page.get_by_test_id("fmea-propagation")).to_contain_text("后向贡献者")


def test_publication_is_disabled_for_model_and_shows_non_certification_disclaimer(page, fmea_fixture_url):
    page.goto(f"{fmea_fixture_url}/fmea.html?fixture=views&actor=model")
    expect(page.get_by_test_id("publish-button")).to_be_disabled()
    expect(page.get_by_test_id("fmea-publication")).to_contain_text("需要 human actor")
    expect(page.get_by_test_id("fmea-publication")).to_contain_text("非认证")
```

- [ ] **Step 2: Run the red view tests**

Install the browser test dependencies before the first Playwright run:

```powershell
uv add --dev "playwright>=1.50.0" "pytest-playwright>=0.7.0"
uv run playwright install chromium
```

Run:

```powershell
uv run pytest tests/e2e/test_fmea_views.py -q
```

Expected: FAIL because the view modules and test fixture route do not exist.

- [ ] **Step 3: Implement the views with explicit state and text-safe rendering**

`workbench.js` renders only key fields in the main table: `row_id`, item path, failure mode, claim/review/publication status, decision severity, RPN and evidence coverage. It uses fixed `data-row-id` values, stable sort, column preset, width, wrap, density, horizontal scrolling and keyboard focus. Complete row content is rendered in the right inspector, not hidden in an editable grid cell.

`evidence-panel.js` renders source type, document ID, data version, page/chunk/span/cell locator, quote, normalized quote, evidence hash, ACL status, expiry and `EvidenceSupportStatus`. It uses `textContent`, never `innerHTML`, and displays `supported`, `partially_supported`, `contradicted`, `not_supported`, `unknown`, `conflict` and `insufficient_evidence` as text plus icon/label, not color alone.

The minimum text-safe renderer is:

```javascript
export function renderEvidencePanel(root, evidence) {
  root.replaceChildren();
  for (const [label, value] of [
    ["来源", evidence.source_type],
    ["版本", evidence.data_version],
    ["定位", evidence.locator],
    ["支持状态", evidence.support_status],
    ["quote", evidence.quote],
  ]) {
    const row = document.createElement("p");
    const name = document.createElement("strong");
    name.textContent = `${label}: `;
    const text = document.createElement("span");
    text.textContent = String(value ?? "unknown");
    row.append(name, text);
    root.append(row);
  }
}
```

`propagation.js` renders a relation table and read-only forward/backward view. It shows source, interface variable/unit/direction, threshold/range, operating mode, delay, response time, tolerance time, target, barrier, evidence support, max hops, `cycle`, `inferred`, `unprocessed`, `external`, and `terminal`. The client never offers free-drag graph editing; more than two hops is visibly `inferred` and awaiting human confirmation.

`review.js` renders model suggestion and engineer-confirmed value in separate columns with `Accept`, `Reject`, `Edit`, `Resolve conflict` and `Diff` actions. Each write includes the current `ETag` and an `Idempotency-Key`; 409/412 leaves unsaved edits in a visible conflict panel and offers reload from the old revision.

`publication.js` computes a checklist from server data: evidence coverage, unresolved items, conflict count, high-risk unsupported edges, version set and disclaimer. Approve/publish/withdraw buttons are disabled unless the actor is a human with the required role. A model or system response can never trigger those actions. A published revision is read-only; editing creates a child revision through the API.

`template-editor.js` exposes field label/order/group/type/required/enum/static hint, registered scoring package selection, limited conditions, API/Excel/Word mapping and namespaced extension fields. It calls server validation; it does not execute rules in the browser. Excel import displays original hash, sheet/row/column/cell/merge, unknown columns and ambiguous headers. Patch candidates display input version, model, prompt hash, diff and human accept/reject state.

`bootstrap.js` mounts all views, subscribes to store actions and ensures a `file:`/Pages demo has `data-read-only="true"`; the UI must never construct a database path or provider URL.

Create `tests/e2e/conftest.py` in this task with a loopback `http.server` fixture named `fmea_fixture_url`; it serves `frontend_app/current_console` and fulfills `/api/v1/fmea/**` with deterministic in-memory JSON/SSE responses. Task 9 modifies this same fixture to start the real FastAPI app; the static fixture is only the view-rendering boundary.

- [ ] **Step 4: Run the green view tests and source safety checks**

Run:

```powershell
uv run pytest tests/e2e/test_fmea_views.py -q
rg -n "innerHTML|eval\(|new Function|fetch\(.*https?://|indexedDB|sqlite|approve|publish|withdraw" frontend_app/current_console/fmea
```

Expected: Playwright view tests PASS. The source scan may find visible button labels containing `approve`, `publish` or `withdraw`, but it must find no direct database access, `eval`, `new Function`, arbitrary remote URL construction or unsafe HTML assignment; document any intentional action-label matches in the test output rather than removing the safety check.

- [ ] **Step 5: Commit the FMEA views**

```powershell
git add pyproject.toml uv.lock frontend_app/current_console/fmea/views frontend_app/current_console/fmea/bootstrap.js frontend_app/current_console/fmea/domain/fmea.js frontend_app/current_console/fmea/fmea.css tests/e2e/conftest.py tests/e2e/test_fmea_views.py
git commit -m "feat: add FMEA evidence review and publication views"
```

### Task 8: Add the 20 Non-Certified Domain Fixtures and Security/Fault Matrix

**Responsibility:** `OWN` —fixture schema、测试夹具、回归指标和硬零检查；fixture 是内部非认证样本，不代表真实设备安全结论。

**Files:**
- Create: `tests/fixtures/fmea/non_certified_cases.toml`
- Create: `tests/fixtures/fmea/security_fault_cases.toml`
- Create: `tests/fixtures/fmea/loader.py`
- Create: `tests/regression/test_fmea_security_faults.py`
- Create: `tests/acceptance/test_fmea_fixture_matrix.py`

**Interfaces:**
- Consumes: `FmeaService`, `FmeaCandidatePipeline`, `SqliteFmeaRepository`, deterministic EvidencePack/model/clock ports from前三计划；GraphRAG and external model are `INTEGRATE` mocks only。
- Produces: exactly 20 fixture cases, 10 `combustion_system` and 10 `fuel_system`, each with metadata and expected invariants; security/fault regression counts; P0 hard-zero report。

- [ ] **Step 1: Write the red fixture-count and hard-zero tests**

Add `tests/acceptance/test_fmea_fixture_matrix.py`:

```python
from tests.fixtures.fmea.loader import load_cases


def test_fixture_matrix_has_exactly_ten_combustion_and_ten_fuel_cases():
    cases = load_cases("tests/fixtures/fmea/non_certified_cases.toml")
    assert len(cases) == 20
    assert sum(case["domain"] == "combustion_system" for case in cases) == 10
    assert sum(case["domain"] == "fuel_system" for case in cases) == 10
    assert all(case["non_certified"] is True for case in cases)
    assert all({"fixture_id", "version", "expected_invariants", "evidence_sources", "author", "reviewer", "disputes", "license", "change_history"} <= case.keys() for case in cases)


def test_p0_hard_zero_invariants(fmea_fixture_runner):
    report = fmea_fixture_runner.run_all()
    assert report.accepted_unauthorized_evidence_ids == 0
    assert report.accepted_mismatched_quotes == 0
    assert report.known_without_evidence == 0
    assert report.silent_conflicts == 0
    assert report.model_state_transitions == 0
    assert report.duplicate_state_transitions == 0
    assert report.prompt_injection_escapes == 0
    assert report.missing_audit_trails == 0
    assert report.export_identity_mismatches == 0
```

Add `tests/regression/test_fmea_security_faults.py`:

```python
import pytest

from tests.fixtures.fmea.loader import load_fault_cases


@pytest.mark.parametrize("case", load_fault_cases("tests/fixtures/fmea/security_fault_cases.toml"), ids=lambda case: case["case_id"])
def test_security_and_fault_case_fails_closed(case, fmea_fixture_runner):
    result = fmea_fixture_runner.run_fault_case(case)
    assert result.status == case["expected_status"]
    assert result.outbound_urls == []
    assert result.database_paths == []
    assert result.secret_values == []
    assert result.state_transitions <= case["max_state_transitions"]
```

- [ ] **Step 2: Run the red matrix tests**

Run:

```powershell
uv run pytest tests/acceptance/test_fmea_fixture_matrix.py tests/regression/test_fmea_security_faults.py -q
```

Expected: FAIL because the fixture files, loader and runner do not exist.

- [ ] **Step 3: Add the exact 20 fixture entries**

Create one TOML array `[[fixture]]` per entry in `tests/fixtures/fmea/non_certified_cases.toml` with `non_certified = true` and the following exact IDs and invariant coverage:

| # | `fixture_id` | `domain` | Required invariants |
| ---: | --- | --- | --- |
| 1 | `combustion.complete_row` | `combustion_system` | complete row, supported evidence, accepted-but-unpublished |
| 2 | `combustion.hierarchy_boundary` | `combustion_system` | system/subsystem/component boundary, stable row ID |
| 3 | `combustion.cause_mechanism_effect_symptom` | `combustion_system` | cause/mechanism/effect/symptom remain separate |
| 4 | `combustion.unknown_missing_evidence` | `combustion_system` | missing EvidenceRef becomes `unknown`, never `known` |
| 5 | `combustion.insufficient_evidence` | `combustion_system` | partial support becomes `insufficient_evidence` |
| 6 | `combustion.conflicting_sources` | `combustion_system` | all sources retained, claim becomes `conflict` |
| 7 | `combustion.version_mismatch` | `combustion_system` | data/graph/EvidencePack mismatch blocks acceptance |
| 8 | `combustion.rpn_collision` | `combustion_system` | equal RPN uses decision priority and does not overwrite rows |
| 9 | `combustion.action_risk_transition` | `combustion_system` | inherent/current/target/verified residual risk and missing effectiveness evidence |
| 10 | `combustion.export_template_extension` | `combustion_system` | normalized JSON/XLSX/Word identity and `gas_turbine.*` field |
| 11 | `fuel.complete_row` | `fuel_system` | complete row, supported evidence, accepted-but-unpublished |
| 12 | `fuel.hierarchy_boundary` | `fuel_system` | system/subsystem/component boundary, stable row ID |
| 13 | `fuel.cause_mechanism_effect_symptom` | `fuel_system` | cause/mechanism/effect/symptom remain separate |
| 14 | `fuel.unknown_missing_evidence` | `fuel_system` | missing EvidenceRef becomes `unknown`, never `known` |
| 15 | `fuel.insufficient_evidence` | `fuel_system` | partial support becomes `insufficient_evidence` |
| 16 | `fuel.conflicting_sources` | `fuel_system` | all sources retained, claim becomes `conflict` |
| 17 | `fuel.version_mismatch` | `fuel_system` | data/graph/EvidencePack mismatch blocks acceptance |
| 18 | `fuel.public_cause_cycle` | `fuel_system` | fuel-to-combustion public cause, reverse edge, cycle marker, no auto-accept |
| 19 | `fuel.unprocessed_long_chain` | `fuel_system` | second cross-system chain exceeds two hops and is `inferred/unprocessed` |
| 20 | `fuel.llm_permission_boundary` | `fuel_system` | direct/indirect instruction injection cannot read, send, publish or change score |

Every TOML entry must include `fixture_id`, `version = "1.0.0"`, `expected_invariants`, `evidence_sources`, `author = "fmea-test-suite"`, `reviewer = "fmea-test-review"`, `disputes = []` or an explicit dispute string, `license = "internal-test-fixture"`, and `change_history = ["1.0.0: initial non-certified fixture"]`. The 18th and 19th entries must contain at least one fuel-to-combustion and one combustion-to-fuel `PropagationEdge`; they must not claim dynamic simulation or certification.

Create `security_fault_cases.toml` with exactly these case IDs and expected behavior: `direct_prompt_injection_01` through `_05` -> `needs_review`; `indirect_document_injection_01` through `_05` -> `needs_review`; `evidence_missing_or_ocr_01` through `_04` -> `insufficient_evidence`; `multi_source_conflict_01` through `_04` -> `conflict`; `version_mismatch_01` through `_04` -> `failed`; `provider_429_timeout_5xx_malformed_01` through `_04` -> `fallback`; `duplicate_cache_fallback_reconnect_01` through `_04` -> `idempotent`.

`loader.py` uses `tomllib`, checks exact counts and required metadata, and returns immutable mappings. The test runner builds a real `EvidencePack` fixture and a fixed model mock through ports; it never calls an external URL, never reads arbitrary paths and never treats these fixtures as industrial evidence.

The loader's minimum implementation is:

```python
import tomllib
from pathlib import Path


def load_cases(path: str) -> tuple[dict[str, object], ...]:
    with Path(path).open("rb") as handle:
        rows = tuple(tomllib.load(handle)["fixture"])
    assert len(rows) == 20
    assert sum(row["domain"] == "combustion_system" for row in rows) == 10
    assert sum(row["domain"] == "fuel_system" for row in rows) == 10
    return rows
```

- [ ] **Step 4: Run the green fixture and regression tests**

Run:

```powershell
uv run pytest tests/acceptance/test_fmea_fixture_matrix.py tests/regression/test_fmea_security_faults.py -q
```

Expected: PASS with 20 domain fixtures, 30 security/fault cases, and all P0 counters equal to zero. Report content metrics separately: state-aware F1 `>= 0.85`, evidence-support precision `>= 0.95`, non-unknown evidence coverage `>= 0.90`, unknown/conflict recall `>= 0.90`, propagation precision `>= 0.90`, high-risk unsupported propagation `== 0`, RPN arithmetic `== 1.0`; these are internal regression metrics and not certification evidence.

- [ ] **Step 5: Commit the fixture and regression matrix**

```powershell
git add tests/fixtures/fmea/non_certified_cases.toml tests/fixtures/fmea/security_fault_cases.toml tests/fixtures/fmea/loader.py tests/regression/test_fmea_security_faults.py tests/acceptance/test_fmea_fixture_matrix.py
git commit -m "test: add FMEA non-certified fixtures and hard-zero regressions"
```

### Task 9: Exercise the Playwright Main Chain and Final Export Consistency Gate

**Responsibility:** `OWN` for browser/fixture acceptance; `INTEGRATE` for stage F API and existing CLI/Skill replay. This task does not implement M6, enterprise OIDC, enterprise DLP or a second API.

**Files:**
- Modify: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_fmea_main_chain.py`
- Create: `tests/acceptance/test_fmea_final_acceptance.py`
- Create: `tests/acceptance/test_fmea_cli_replay_contract.py`

**Interfaces:**
- Consumes: `fmea.html`, stage F REST/SSE contract, `FmeaService`, `SqliteFmeaRepository`, `ExportService`, existing `scripts/fmea_skill.py` contract and the 20 fixture runner。
- Produces: browser proof of project configuration -> run -> SSE reconnect -> evidence/propagation review -> stale-write conflict -> human approve/publish -> JSON/XLSX/Word export; final assertion that every artifact uses one `revision_id` and `snapshot_hash`。

- [ ] **Step 1: Write the red Playwright and final consistency tests**

Modify `tests/e2e/conftest.py` so its fixture starts the real FastAPI app on a loopback ephemeral port, injects deterministic repository/evidence/model ports, waits for `GET /api/health`, yields `base_url`, and terminates the process in `finally`. The app must serve `fmea.html` through a dedicated route or static mount; it must not replace `index.html`.

Add `tests/e2e/test_fmea_main_chain.py`:

```python
from playwright.sync_api import expect


def test_fmea_main_chain_survives_sse_reconnect_and_exports_one_snapshot(page, fmea_server):
    page.goto(f"{fmea_server.base_url}/fmea.html?fixture=main-chain")
    page.get_by_test_id("project-select").select_option("fixture-project")
    page.get_by_test_id("analysis-save").click()
    page.get_by_test_id("fmea-run-start").click()
    expect(page.get_by_test_id("fmea-run-status")).to_have_text("running")
    page.context.set_offline(True)
    page.wait_for_timeout(250)
    page.context.set_offline(False)
    expect(page.get_by_test_id("fmea-run-status")).to_have_text("succeeded")
    expect(page.get_by_test_id("fmea-event-count")).to_have_text("4")
    page.get_by_test_id("fmea-row-id-fuel-row-001").click()
    expect(page.get_by_test_id("fmea-evidence-sidebar")).to_contain_text("supported")
    page.get_by_test_id("propagation-review-fuel-row-001").click()
    page.get_by_test_id("review-accept-row-fuel-row-001").click()
    expect(page.get_by_test_id("conflict-panel")).to_be_hidden()
    page.get_by_test_id("approve-revision").click()
    page.get_by_test_id("publish-revision").click()
    expect(page.get_by_test_id("publication-status")).to_have_text("published")
    page.get_by_test_id("export-json").click()
    page.get_by_test_id("export-xlsx").click()
    page.get_by_test_id("export-docx").click()
    expect(page.get_by_test_id("export-identity")).to_contain_text("same snapshot_hash")
```

Add `tests/acceptance/test_fmea_final_acceptance.py`:

```python
def test_json_xlsx_word_share_immutable_revision_and_snapshot(fmea_acceptance):
    artifacts = fmea_acceptance.export_published_revision("rev-42", formats=("json", "xlsx", "docx"))
    identities = {(artifact.revision_id, artifact.snapshot_hash) for artifact in artifacts}
    assert identities == {("rev-42", fmea_acceptance.expected_snapshot_hash)}
    assert fmea_acceptance.compare_rows(artifacts) == {
        "row_ids": True,
        "fields": True,
        "risk_scores": True,
        "evidence_counts": True,
        "state_axes": True,
        "revision_id": True,
        "snapshot_hash": True,
    }
```

Add `tests/acceptance/test_fmea_cli_replay_contract.py` as an integration-only check: invoke the existing `scripts/fmea_skill.py` with a fixture project using `subprocess.run`, assert stdout parses as exactly one JSON document, stderr contains logs only, exit code is stable, and the returned manifest has `schema_version="graphrag.fmea.v1"`. If the CLI is not present from the previous plan, the test must fail with `DEPENDENCY_NOT_READY`; do not add a second CLI in this task.

- [ ] **Step 2: Run the red browser and acceptance tests**

Run:

```powershell
uv run pytest tests/e2e/test_fmea_main_chain.py tests/acceptance/test_fmea_final_acceptance.py tests/acceptance/test_fmea_cli_replay_contract.py -q
```

Expected: FAIL because the real FastAPI harness, server-backed route and full main-chain selectors are not yet connected.

- [ ] **Step 3: Implement the deterministic real-server main-chain harness**

The server fixture from Task 7 must be replaced in-place with a real FastAPI process using a loopback host only, a temporary allowed root, the deterministic 20-fixture provider and a fixed model mock. It must seed one unpublished candidate revision and one evidence-supported propagation edge. The SSE stream must emit exactly four monotonic events (`run.queued`, `run.running`, `run.candidate_ready`, `run.succeeded`); after a disconnect, the reconnect request must include `Last-Event-ID`, and duplicate events must not increase `fmea-event-count` beyond four. A disconnected browser must not call `/cancel`.

The process fixture must use a real subprocess and a bounded readiness loop:

```python
process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "chroma_rag_poc.api:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)],
    env={**os.environ, "PYTHONPATH": str(package_src), "FMEA_TEST_MODE": "1"},
)
try:
    wait_for_http(f"http://127.0.0.1:{port}/api/health", timeout_seconds=10)
    yield FmeaServer(base_url=f"http://127.0.0.1:{port}")
finally:
    process.terminate()
    process.wait(timeout=5)
```

The fixture must pass temporary paths through the supported service factory/configuration seam; it must not add a database path to a browser request.

The stale-write subtest must open two pages, edit the same row, let page A commit with `If-Match: "row-v1"`, then assert page B receives 412 with `FMEA_VERSION_CONFLICT`, retains its unsaved edit, and can reload the new revision. The publish path must use a human actor fixture; a model actor attempt must return `FMEA_ACTOR_FORBIDDEN` and leave the revision unpublished.

The final acceptance fixture must parse JSON with `orjson`, read XLSX with `openpyxl`, read Word tables with `python-docx`, and compare the fixed semantic set: row ID, failure mode, all three state axes, S/O/D/RPN and risk stages, evidence count, propagation edge count, revision ID and snapshot hash. It must also assert the disclaimer is present in all three outputs and that no export file includes macro/external-link findings.

- [ ] **Step 4: Run the green main chain, final gate and complete regression suite**

Run:

```powershell
uv run pytest tests/e2e/test_fmea_main_chain.py tests/acceptance/test_fmea_final_acceptance.py tests/acceptance/test_fmea_cli_replay_contract.py -q
uv run pytest tests/unit tests/integration tests/regression tests/acceptance -q
uv run ruff check fmea_application fmea_infrastructure tests frontend_app/current_console/fmea
uv run mypy fmea_application/export_dto.py fmea_application/export_service.py fmea_application/template_service.py fmea_application/template_import_service.py fmea_infrastructure/exporters fmea_infrastructure/templates
```

Expected: Playwright main chain PASS; JSON/XLSX/Word identity is one revision/hash; full pytest has zero failures; ruff has zero errors; targeted mypy has zero errors. Record any pre-existing unrelated failures separately and do not label the phase complete while a required command fails.

- [ ] **Step 5: Commit the final acceptance harness**

```powershell
git add tests/e2e/conftest.py tests/e2e/test_fmea_main_chain.py tests/acceptance/test_fmea_final_acceptance.py tests/acceptance/test_fmea_cli_replay_contract.py
git commit -m "test: verify FMEA browser chain and export consistency"
```

## Self-Review Checklist Before Handoff

- [ ] **Spec coverage:** Tasks 1-3 cover normalized DTO plus JSON/XLSX/Word, same immutable snapshot, formula injection, macro/external-link blocking, Word plain text, server filenames and manifest identity from sections 10, 15, 17 and 19.
- [ ] **Template coverage:** Tasks 4-5 cover JSON Schema 2020-12, constrained rules, four-layer version binding, `draft -> validating -> published -> deprecated`, Excel hash/sheet/row/column/cell/merge capture, unknown/ambiguous headers and LLM patch candidates with human decision ledger.
- [ ] **UI coverage:** Tasks 6-7 cover independent `fmea.html`, native ES Modules, evidence sidebar, fixed row IDs, field status, propagation table/read-only direction views, review diff, publication checklist, conflict recovery, read-only file/Pages mode and template/export controls.
- [ ] **Acceptance coverage:** Tasks 8-9 cover 10 combustion plus 10 fuel fixtures, two cross-system propagation chains, 5 direct injection, 5 indirect injection, 4 evidence/OCR, 4 conflict, 4 version, 4 provider, 4 duplicate/cache/fallback/reconnect cases, P0 hard-zero metrics, Playwright SSE reconnection and final JSON/XLSX/Word identity.
- [ ] **Responsibility matrix:** No OUT capability is a task; GraphRAG, external model and M6 appear only as INTEGRATE ports/mocks/fixtures or DEPEND failure contracts; no QMS, plugin platform, enterprise OIDC/DLP or full M6 work is included.
- [ ] **Type consistency:** Every task uses the exact shared names `ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `ActorType`, `RunStatus`, `VersionSet`, `EvidenceRef`, `EvidencePack`, `EvidenceSupportStatus`, `FmeaAnalysis`, `FmeaRow`, `RiskAssessment`, `PropagationEdge`, `ScoringRulePack`; ports stay in `fmea_application/ports.py`, repository is `SqliteFmeaRepository`, application entry is `FmeaService`, candidate entry is `FmeaCandidatePipeline`, schema is `graphrag.fmea.v1`.
- [ ] **Placeholder scan:** Run `$forbidden = @('T'+'B'+'D', 'T'+'O'+'D'+'O', '类'+'似'+'前'+'文', '添'+'加'+'适'+'当'+'处'+'理', 'implement '+'later', 'fill '+'in '+'details', 'write '+'tests '+'for '+'the '+'above', 'similar '+'to '+'task'); Select-String -Path docs/superpowers/plans/2026-08-23-fmea-ui-templates-exports.md -Pattern $forbidden -SimpleMatch`; expected no matches.
- [ ] **Scope scan:** Run `rg -n "QMS|OIDC|SSO|DLP|plugin platform|M1-M6.*CI|full.*M6|QueryMode\.FMEA" docs/superpowers/plans/2026-08-23-fmea-ui-templates-exports.md`; every match must be a global exclusion or dependency boundary, never a Files entry or implementation step.

Plan complete and saved to `docs/superpowers/plans/2026-08-23-fmea-ui-templates-exports.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task and review between tasks。
2. **Inline Execution** — execute tasks in this session with checkpoints。
