# ruff: noqa: RUF001
from __future__ import annotations

import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest
import uvicorn
from playwright.sync_api import Page, expect

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.api import create_app  # noqa: E402
from chroma_rag_poc.fmea_review_contracts import (  # noqa: E402
    FmeaEnvelope,
    ReviewContextData,
    ReviewDecisionResultData,
)

from core_domain.fmea.states import (  # noqa: E402
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile  # noqa: E402
from fmea_application.review_contracts import ActorContext  # noqa: E402
from fmea_application.review_errors import ReviewError  # noqa: E402

TOKEN = "a" * 32
VALID_ACCEPT_BODY = {
    "action": "accept",
    "suggestion_id": "suggestion-001",
    "reason_code": "ACCEPT_AS_IS",
    "reason": "人工审核确认该条目。",
    "edits": [],
    "evidence_requests": [],
    "unresolved_acknowledgements": [],
}


def _context_json(record_version: int = 7) -> dict[str, Any]:
    return {
        "identity": {
            "row_id": "row-001",
            "item_id": "item-001",
            "function_id": "function-001",
            "item_label": "燃烧室",
            "function_label": "保持稳定燃烧",
        },
        "row": {
            "row_id": "row-001",
            "analysis_id": "analysis-001",
            "evidence_pack_id": "evidence-pack-001",
            "item_id": "item-001",
            "function_id": "function-001",
            "failure_mode": "燃烧不稳定",
            "causes": ["供给扰动"],
            "mechanisms": ["局部混合变化"],
            "effects": ["输出波动"],
            "symptoms": ["压力波动"],
            "controls": ["在线监测"],
            "barriers": ["联锁保护"],
            "actions": ["复核供给参数"],
            "risk_assessment": None,
            "claim_status": "known",
            "review_status": "draft",
            "publication_status": "unpublished",
            "record_version": record_version,
        },
        "reviewability": True,
        "field_reviews": [
            {
                "target_field": "failure_mode",
                "value": "燃烧不稳定",
                "claim_status": "known",
                "support_status": "supported",
                "evidence_ids": ["evidence-001"],
                "last_decision_id": None,
            }
        ],
        "evidence": {
            "pack_id": "evidence-pack-001",
            "pack_hash": "sha256:" + "a" * 64,
            "expires_at": None,
            "refs": [
                {
                    "evidence_id": "evidence-001",
                    "source_type": "manual",
                    "source_trust": "verified",
                    "is_primary": True,
                    "locator": "manual://combustion/001",
                    "quote": "供给扰动会造成局部混合变化。",
                },
                {
                    "evidence_id": "evidence-002",
                    "source_type": "test-report",
                    "source_trust": "reviewed",
                    "is_primary": False,
                    "locator": "report://combustion/002",
                    "quote": "压力波动记录见第 4 节。",
                },
            ],
        },
        "retrieval": {
            "requested_profile": "rag_only",
            "resolved_profile": "rag_only",
            "evidence_types": ["text"],
            "trace_id": "retrieval-trace-001",
            "warnings": [],
            "incomplete": False,
        },
        "latest_suggestion": {
            "suggestion_id": "suggestion-001",
            "run_id": "run-001",
            "row_id": "row-001",
            "source_record_version": record_version,
            "recommended_action": "accept",
            "field_findings": [
                {
                    "target_field": "failure_mode",
                    "judgement": "supported",
                    "recommended_claim_status": "known",
                    "evidence_ids": ["evidence-001"],
                    "rationale": "引用证据支持该字段。",
                }
            ],
            "proposed_edits": [],
            "evidence_requests": [],
            "missing_evidence": [],
            "conflicts": [],
            "rationale": "该建议仅供人工审核。",
            "model_manifest": {
                "provider": "local",
                "model": "fixture-model",
                "template_id": "review-template",
                "template_version": "1",
            },
            "applied": False,
            "stale": False,
            "created_at": "2026-09-04T00:00:00Z",
        },
        "decision_history": [
            {
                "decision_id": "decision-001",
                "row_id": "row-001",
                "previous_record_version": 6,
                "record_version": 7,
                "actor_id": "human-reviewer-001",
                "action": "request_evidence",
                "suggestion_id": None,
                "reason_code": "EVIDENCE_REQUIRED",
                "reason": "已要求补充试验报告。",
                "edits": [],
                "evidence_requests": [],
                "unresolved_acknowledgements": [],
                "created_at": "2026-09-04T00:00:00Z",
            }
        ],
        "warnings": [],
    }


def _validated_context_envelope(record_version: int = 7) -> dict[str, Any]:
    data = ReviewContextData.model_validate(_context_json(record_version))
    envelope = FmeaEnvelope[ReviewContextData](
        resource_type="review_context",
        request_id="request-core-001",
        trace_id="trace-core-001",
        data=data,
    )
    return envelope.model_dump(mode="json")


def _context_namespace(record_version: int = 7) -> SimpleNamespace:
    raw = _context_json(record_version)
    row = raw["row"]
    context = SimpleNamespace(
        item_label=raw["identity"]["item_label"],
        function_label=raw["identity"]["function_label"],
        row=SimpleNamespace(
            **{
                **row,
                "causes": tuple(row["causes"]),
                "mechanisms": tuple(row["mechanisms"]),
                "effects": tuple(row["effects"]),
                "symptoms": tuple(row["symptoms"]),
                "controls": tuple(row["controls"]),
                "barriers": tuple(row["barriers"]),
                "actions": tuple(row["actions"]),
                "claim_status": ClaimStatus(row["claim_status"]),
                "review_status": ReviewStatus(row["review_status"]),
                "publication_status": PublicationStatus(row["publication_status"]),
            }
        ),
        reviewability=raw["reviewability"],
        field_reviews=(
            SimpleNamespace(
                target_field="failure_mode",
                value="燃烧不稳定",
                claim_status=ClaimStatus.KNOWN,
                support_status=EvidenceSupportStatus.SUPPORTED,
                evidence_ids=("evidence-001",),
                last_decision_id=None,
            ),
        ),
        evidence=SimpleNamespace(
            pack_id="evidence-pack-001",
            pack_hash="sha256:" + "a" * 64,
            expires_at=None,
            refs=(
                SimpleNamespace(
                    evidence_id="evidence-001",
                    source_type="manual",
                    source_trust="verified",
                    is_primary=True,
                    locator="manual://combustion/001",
                    quote="供给扰动会造成局部混合变化。",
                ),
                SimpleNamespace(
                    evidence_id="evidence-002",
                    source_type="test-report",
                    source_trust="reviewed",
                    is_primary=False,
                    locator="report://combustion/002",
                    quote="压力波动记录见第 4 节。",
                ),
            ),
        ),
        retrieval=SimpleNamespace(
            requested_profile=EvidenceSelectionProfile.RAG_ONLY,
            resolved_profile=EvidenceSelectionProfile.RAG_ONLY,
            evidence_types=(CitationType.TEXT,),
            trace_id="retrieval-trace-001",
            warnings=(),
            incomplete=False,
        ),
        latest_suggestion=SimpleNamespace(
            suggestion_id="suggestion-001",
            run_id="run-001",
            row_id="row-001",
            source_record_version=record_version,
            recommended_action="accept",
            field_findings=(
                SimpleNamespace(
                    target_field="failure_mode",
                    judgement="supported",
                    recommended_claim_status=ClaimStatus.KNOWN,
                    evidence_ids=("evidence-001",),
                    rationale="引用证据支持该字段。",
                ),
            ),
            proposed_edits=(),
            evidence_requests=(),
            missing_evidence=(),
            conflicts=(),
            rationale="该建议仅供人工审核。",
            model_manifest=SimpleNamespace(
                provider="local",
                model="fixture-model",
                template_id="review-template",
                template_version="1",
            ),
            applied=False,
            stale=False,
            created_at="2026-09-04T00:00:00Z",
        ),
        decision_history=(
            SimpleNamespace(
                decision_id="decision-001",
                row_id="row-001",
                previous_record_version=6,
                record_version=7,
                actor_id="human-reviewer-001",
                action="request_evidence",
                suggestion_id=None,
                reason_code="EVIDENCE_REQUIRED",
                reason="已要求补充试验报告。",
                edits=(),
                evidence_requests=(),
                unresolved_acknowledgements=(),
                created_at="2026-09-04T00:00:00Z",
            ),
        ),
        warnings=(),
    )
    return context


def _suggestion_run() -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-002",
        row_id="row-001",
        source_record_version=7,
        status=RunStatus.SUCCEEDED,
        suggestion_id="suggestion-001",
        error_code=None,
        retryable=False,
        request_id="request-core-002",
        trace_id="trace-core-002",
        created_at="2026-09-04T00:00:00Z",
        started_at="2026-09-04T00:00:00Z",
        finished_at="2026-09-04T00:00:01Z",
    )


@dataclass
class FakeAuth:
    workspace_id: str = "ws-1"

    def authenticate(self, bearer_token: str, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        assert remote_host in {"127.0.0.1", "testclient"}
        return ActorContext("human-reviewer-001", ActorType.HUMAN, frozenset({"reviewer"}), self.workspace_id)


@dataclass
class FakeReviewService:
    context: SimpleNamespace = field(default_factory=_context_namespace)
    suggestion_run: SimpleNamespace = field(default_factory=_suggestion_run)
    calls: list[tuple[str, Any]] = field(default_factory=list)
    conflict_once: bool = True
    hold_decision: bool = False
    decision_started: threading.Event = field(default_factory=threading.Event)
    decision_release: threading.Event = field(default_factory=threading.Event)
    decision_finished: threading.Event = field(default_factory=threading.Event)
    fail_refresh_after_success: bool = False
    context_failures_remaining: int = 0

    def get_context(self, row_id: str, actor: ActorContext) -> SimpleNamespace:
        assert row_id == "row-001"
        assert actor.workspace_id == "ws-1"
        self.calls.append(("get_context", row_id))
        if self.context_failures_remaining:
            self.context_failures_remaining -= 1
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "bounded context refresh failure", retryable=True)
        return self.context

    def start_suggestion(self, command: Any, actor: ActorContext) -> SimpleNamespace:
        assert command.row_id == "row-001"
        assert command.expected_record_version == 7
        assert actor.actor_type is ActorType.HUMAN
        self.calls.append(("start_suggestion", command))
        return self.suggestion_run

    def submit_decision(self, command: Any, actor: ActorContext) -> SimpleNamespace:
        assert actor.actor_type is ActorType.HUMAN
        assert command.row_id == "row-001"
        assert command.expected_record_version == 7
        self.calls.append(("submit_decision", command))
        self.decision_started.set()
        try:
            if self.hold_decision:
                assert self.decision_release.wait(timeout=15), "test must release the bounded decision"
            if self.conflict_once:
                self.conflict_once = False
                self.context = _context_namespace(record_version=8)
                raise ReviewError("FMEA_VERSION_CONFLICT", "the review row changed")
            self.context = _context_namespace(record_version=8)
            self.context.row.review_status = ReviewStatus.ACCEPTED
            self.context_failures_remaining = int(self.fail_refresh_after_success)
            return SimpleNamespace(
                decision_id="decision-002",
                row=self.context.row,
                previous_record_version=7,
                record_version=8,
                review_status=ReviewStatus.ACCEPTED,
                publication_status=PublicationStatus.UNPUBLISHED,
                audit_event_id="audit-002",
                suggestion_id="suggestion-001",
                evidence_requests=(),
                persisted=True,
                request_id="request-decision-002",
                trace_id="trace-decision-002",
            )
        finally:
            self.decision_finished.set()

    def get_retrieval_trace(self, row_id: str, actor: ActorContext) -> str:
        assert row_id == "row-001"
        assert actor.actor_type is ActorType.HUMAN
        return "retrieval-trace-001"

    def page_decisions(
        self,
        row_id: str,
        actor: ActorContext,
        *,
        after: tuple[str, str] | None = None,
        limit: int = 50,
    ) -> tuple[SimpleNamespace, ...]:
        assert row_id == "row-001"
        assert actor.workspace_id == "ws-1"
        assert limit == 50
        template = self.context.decision_history[0]
        decisions = tuple(
            SimpleNamespace(
                **{
                    **vars(template),
                    "decision_id": f"decision-{index:03d}",
                    "created_at": "2026-09-04T00:00:00Z",
                }
            )
            for index in range(1, 52)
        )
        self.calls.append(("page_decisions", (after, limit)))
        if after is None:
            return decisions
        assert after == (decisions[49].created_at, decisions[49].decision_id)
        return decisions[50:]


class _FakeExecutor:
    def close(self) -> None:
        return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def fmea_server(tmp_path: Path) -> tuple[str, FakeReviewService]:
    _validated_context_envelope()
    service = FakeReviewService()
    runtime = SimpleNamespace(
        service=service,
        repository=object(),
        executor=_FakeExecutor(),
        template_registry_root=tmp_path,
    )
    app = create_app(review_runtime_factory=lambda _workspace: runtime, review_auth_provider=FakeAuth())
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", ws="none"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/openapi.json", timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("real create_app server did not become ready")  # noqa: TRY003
    try:
        yield base_url, service
    finally:
        service.decision_release.set()
        server.should_exit = True
        thread.join(timeout=8)
        assert not thread.is_alive(), "real create_app server must shut down cleanly"


def _load_workbench(page: Page, base_url: str) -> None:
    response = page.goto(f"{base_url}/static/fmea.html")
    assert response is not None and response.status == 200
    page.get_by_label("访问令牌（仅当前页面内存）").fill(TOKEN)
    page.get_by_label("分析 ID").fill("analysis-001")
    page.get_by_label("行 ID").fill("row-001")
    page.get_by_label("修订 ID").fill("revision-001")
    page.get_by_role("button", name="载入工作台").click()
    expect(page.get_by_role("heading", name="分析总览")).to_be_visible()


def test_real_create_app_setup_and_evidence_panel(page: Page, fmea_server: tuple[str, FakeReviewService]) -> None:
    base_url, _service = fmea_server
    responses: list[Any] = []
    page.on("response", lambda response: responses.append(response))
    _load_workbench(page, base_url)

    page.get_by_role("link", name="证据").click()
    expect(page.get_by_role("heading", name="证据", exact=True)).to_be_visible()
    expect(page.get_by_role("table")).to_be_visible()
    expect(page.get_by_role("cell", name="供给扰动会造成局部混合变化。", exact=True)).to_be_visible()
    page.get_by_role("button", name="查看证据 evidence-002").click()
    expect(page.get_by_role("complementary", name="证据详情")).to_contain_text("压力波动记录见第 4 节。")
    context_response = next(
        response for response in responses if response.url.endswith("/api/v1/fmea/rows/row-001/review-context")
    )
    assert context_response.headers["etag"] == '"7"'


def test_review_decision_dialog_names_resources_requires_confirmation_and_refreshes_conflict(
    page: Page, fmea_server: tuple[str, FakeReviewService]
) -> None:
    base_url, service = fmea_server
    requests: list[Any] = []
    page.on("request", lambda request: requests.append(request))
    _load_workbench(page, base_url)
    page.get_by_role("link", name="字段复核").click()
    page.get_by_label("复核理由").fill("人工审核确认该条目。")
    page.get_by_role("button", name="复核并确认").click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("提交人工复核")
    expect(dialog).to_contain_text("行 row-001")
    expect(dialog).to_contain_text("修订 revision-001")
    expect(dialog.get_by_role("checkbox", name="我已核对资源与内容，明确确认此操作")).not_to_be_checked()
    expect(dialog.get_by_role("button", name="确认提交")).to_be_disabled()
    assert not any(request.url.endswith("/review-decisions") for request in requests)

    dialog.get_by_role("checkbox", name="我已核对资源与内容，明确确认此操作").check()
    with page.expect_response(
        lambda response: response.url.endswith("/api/v1/fmea/rows/row-001/review-decisions")
    ) as decision_response_info:
        dialog.get_by_role("button", name="确认提交").click()
    decision_response = decision_response_info.value
    decision_request = decision_response.request
    assert decision_request.headers["if-match"] == '"7"'
    assert decision_request.post_data_json == VALID_ACCEPT_BODY
    expect(page.get_by_role("alert")).to_contain_text("版本或状态冲突，已刷新资源")
    expect(page.get_by_text("资源版本：8", exact=True)).to_be_visible()
    assert [name for name, _ in service.calls].count("get_context") == 2


def test_review_history_paginates_with_server_cursor(page: Page, fmea_server: tuple[str, FakeReviewService]) -> None:
    base_url, service = fmea_server
    history_path = "/api/v1/fmea/rows/row-001/review-decisions"
    _load_workbench(page, base_url)
    page.get_by_role("link", name="字段复核").click()

    with page.expect_response(
        lambda response: response.request.method == "GET" and response.url.split("?", 1)[0].endswith(history_path)
    ) as first_response_info:
        page.get_by_role("button", name="载入复核记录").click()
    first_response = first_response_info.value
    first_request = first_response.request
    first_query = parse_qs(urlparse(first_request.url).query)
    first_page = first_response.json()["data"]
    assert first_query == {"limit": ["50"]}
    assert first_page["limit"] == 50
    assert len(first_page["items"]) == 50
    assert first_page["next_cursor"]
    expect(page.get_by_role("button", name="下一页复核记录")).to_be_visible()

    server_cursor = first_page["next_cursor"]
    with page.expect_response(
        lambda response: response.request.method == "GET" and response.url.split("?", 1)[0].endswith(history_path)
    ) as second_response_info:
        page.get_by_role("button", name="下一页复核记录").click()
    second_response = second_response_info.value
    second_request = second_response.request
    second_query = parse_qs(urlparse(second_request.url).query)
    second_page = second_response.json()["data"]
    assert second_query["limit"] == ["50"]
    assert second_query["cursor"] == [server_cursor]
    assert len(second_page["items"]) == 1
    assert second_page["next_cursor"] is None
    page_calls = [payload for name, payload in service.calls if name == "page_decisions"]
    assert page_calls == [
        (None, 50),
        (("2026-09-04T00:00:00Z", "decision-050"), 50),
    ]


def test_review_suggestion_uses_context_etag_and_keeps_token_in_memory_only(
    page: Page, fmea_server: tuple[str, FakeReviewService]
) -> None:
    base_url, _service = fmea_server
    requests: list[Any] = []
    page.on("request", lambda request: requests.append(request))
    response = page.goto(f"{base_url}/static/fmea.html?analysis_id=analysis-001&row_id=row-001&token=secret")
    assert response is not None and response.status == 200
    expect(page.get_by_label("访问令牌（仅当前页面内存）")).to_have_value("")
    page.get_by_label("访问令牌（仅当前页面内存）").fill(TOKEN)
    page.get_by_label("分析 ID").fill("analysis-001")
    page.get_by_label("行 ID").fill("row-001")
    page.get_by_label("修订 ID").fill("revision-001")
    page.get_by_role("button", name="载入工作台").click()
    page.get_by_role("link", name="字段复核").click()
    page.get_by_role("button", name="请求模型建议").click()

    expect(page.get_by_text("模型建议请求已提交", exact=True)).to_be_visible()
    suggestion_request = next(
        request for request in requests if request.url.endswith("/api/v1/fmea/rows/row-001/review-suggestion-runs")
    )
    assert suggestion_request.headers["if-match"] == '"7"'
    assert suggestion_request.headers["idempotency-key"]
    assert suggestion_request.post_data_json == {"review_policy": "default", "focus_fields": []}
    assert "record_version" not in suggestion_request.post_data_json
    assert page.evaluate("Object.keys(localStorage).length") == 0


def test_core_screenshots_cover_desktop_and_mobile(page: Page, fmea_server: tuple[str, FakeReviewService]) -> None:
    base_url, _service = fmea_server
    _load_workbench(page, base_url)
    expect(page.locator("details.connection")).not_to_have_attribute("open")
    assert page.evaluate("document.activeElement === document.getElementById('workbench-main')") is True
    page.get_by_role("link", name="证据").click()
    expect(page.get_by_role("cell", name="供给扰动会造成局部混合变化。", exact=True)).to_be_visible()
    screenshot_root = (
        REPO_ROOT
        / ".superpowers"
        / "sdd"
        / "2026-08-27-fmea-migration-delivery-closure"
        / "task-7-core-screenshots"
    )
    screenshot_root.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_root / "fmea-core-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(screenshot_root / "fmea-core-mobile.png"), full_page=True)
    assert (screenshot_root / "fmea-core-desktop.png").is_file()
    assert (screenshot_root / "fmea-core-mobile.png").is_file()


def test_all_navigation_views_render_without_page_errors_or_mutations(
    page: Page, fmea_server: tuple[str, FakeReviewService]
) -> None:
    base_url, _service = fmea_server
    page_errors: list[str] = []
    mutating_requests: list[tuple[str, str]] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "request",
        lambda request: mutating_requests.append((request.method, request.url))
        if request.method not in {"GET", "HEAD", "OPTIONS"}
        else None,
    )
    _load_workbench(page, base_url)
    mutating_requests.clear()

    navigation_headings = (
        ("分析", "分析总览"),
        ("证据", "证据"),
        ("字段复核", "字段复核"),
        ("风险评分", "风险评分"),
        ("传播分析", "传播分析"),
        ("批准发布", "治理与发布"),
        ("模板与迁移", "模板与迁移交付"),
        ("成果导出", "导出与叙事交付"),
    )
    for link_name, heading_name in navigation_headings:
        page.get_by_role("link", name=link_name, exact=True).click()
        expect(page.get_by_role("heading", name=heading_name, exact=True)).to_be_visible()

    assert page_errors == []
    assert mutating_requests == []


def _open_review_confirmation(page: Page) -> None:
    page.get_by_role("link", name="字段复核", exact=True).click()
    page.get_by_label("复核理由").fill(VALID_ACCEPT_BODY["reason"])
    page.get_by_role("button", name="复核并确认").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("行 row-001")
    dialog.get_by_role("checkbox", name="我已核对资源与内容，明确确认此操作").check()


def test_unresolved_post_locks_connection_and_preserves_context(
    page: Page, fmea_server: tuple[str, FakeReviewService]
) -> None:
    base_url, service = fmea_server
    service.hold_decision = True
    service.conflict_once = False
    decision_url = f"{base_url}/api/v1/fmea/rows/row-001/review-decisions"
    posts: list[Any] = []
    page.on("request", lambda request: posts.append(request) if request.method == "POST" else None)
    _load_workbench(page, base_url)
    _open_review_confirmation(page)

    try:
        with page.expect_request(
            lambda request: request.method == "POST" and request.url == decision_url, timeout=5000
        ) as request_info:
            page.get_by_role("dialog").get_by_role("button", name="确认提交").click()
        assert service.decision_started.wait(timeout=3)
        assert not service.decision_finished.is_set()
        page.locator("details.connection > summary").click()
        expect(page.get_by_role("button", name="载入工作台")).to_be_disabled()
        expect(page.locator("#disconnect")).to_be_disabled()
        expect(page.get_by_label("分析 ID")).to_have_value("analysis-001")
        expect(page.get_by_label("行 ID")).to_have_value("row-001")
        expect(page.get_by_label("修订 ID")).to_have_value("revision-001")
        expect(page.get_by_text("资源版本：7", exact=True)).to_be_visible()
        expect(page.get_by_role("cell", name="燃烧不稳定", exact=True)).to_be_visible()

        # Stopping the HTTP wait leaves the server's write unresolved.
        page.locator("#cancel-request").click()
        expect(page.locator("#retry-request")).to_be_visible()
        expect(page.locator("#workbench-main")).to_have_attribute("aria-busy", "false")
        expect(page.get_by_role("button", name="载入工作台")).to_be_disabled()
        expect(page.locator("#disconnect")).to_be_disabled()
        expect(page.get_by_text("资源版本：7", exact=True)).to_be_visible()
        page.get_by_role("link", name="证据", exact=True).click()
        expect(page.get_by_role("cell", name="供给扰动会造成局部混合变化。", exact=True)).to_be_visible()
        assert not service.decision_finished.is_set()
        assert request_info.value.headers["if-match"] == '"7"'
        assert request_info.value.post_data_json == VALID_ACCEPT_BODY
        assert len(posts) == 1
    finally:
        service.decision_release.set()
        assert service.decision_finished.wait(timeout=5), "held service work must be released"

    assert service.context.row.record_version == 8
    page.get_by_role("link", name="字段复核", exact=True).click()
    expect(page.get_by_text("资源版本：7", exact=True)).to_be_visible()
    expect(page.locator("#disconnect")).to_be_disabled()
    assert [name for name, _ in service.calls].count("get_context") == 1


def test_successful_post_failed_refresh_retries_get_without_repeating_post(
    page: Page, fmea_server: tuple[str, FakeReviewService]
) -> None:
    base_url, service = fmea_server
    service.conflict_once = False
    service.fail_refresh_after_success = True
    decision_url = f"{base_url}/api/v1/fmea/rows/row-001/review-decisions"
    context_url = f"{base_url}/api/v1/fmea/rows/row-001/review-context"
    requests: list[tuple[str, str]] = []
    page.on("request", lambda request: requests.append((request.method, request.url)))
    _load_workbench(page, base_url)
    _open_review_confirmation(page)

    with (
        page.expect_response(lambda response: response.url == decision_url, timeout=5000) as post_info,
        page.expect_response(lambda response: response.url == context_url, timeout=5000) as refresh_info,
    ):
        page.get_by_role("dialog").get_by_role("button", name="确认提交").click()
    assert post_info.value.status == 200
    receipt = FmeaEnvelope[ReviewDecisionResultData].model_validate(post_info.value.json())
    assert receipt.data.persisted is True
    assert receipt.data.decision_id == "decision-002"
    assert receipt.data.record_version == 8
    assert post_info.value.headers["etag"] == '"8"'
    assert post_info.value.request.post_data_json == VALID_ACCEPT_BODY
    assert refresh_info.value.status == 503
    assert refresh_info.value.json()["code"] == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
    expect(page.get_by_role("alert")).to_contain_text("已收到成功回执，但刷新状态失败")
    expect(page.locator("#request-status")).to_contain_text("服务端已返回成功回执")
    expect(page.locator("#retry-refresh")).to_be_visible()
    expect(page.locator("#retry-refresh")).to_be_enabled()
    expect(page.locator("#retry-request")).to_be_hidden()
    expect(page.get_by_text("资源版本：7", exact=True)).to_be_visible()

    request_mark = len(requests)
    with page.expect_response(lambda response: response.url == context_url, timeout=5000) as retry_info:
        page.locator("#retry-refresh").click()
    assert retry_info.value.status == 200
    assert retry_info.value.headers["etag"] == '"8"'
    expect(page.get_by_text("资源版本：8", exact=True)).to_be_visible()
    expect(page.locator("#request-status")).to_contain_text("没有重新提交写入")
    expect(page.locator("#retry-refresh")).to_be_hidden()
    expect(page.locator("#retry-request")).to_be_hidden()
    expect(page.get_by_role("alert")).to_be_hidden()
    assert requests[request_mark:] == [("GET", context_url)]
    assert requests.count(("POST", decision_url)) == 1
    assert requests.count(("GET", context_url)) == 3
    assert [name for name, _ in service.calls].count("submit_decision") == 1
