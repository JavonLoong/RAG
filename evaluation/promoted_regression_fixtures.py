"""Seed promoted regression fixtures that exercise non-empty GraphRAG gates."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .harness import RAGEvaluationCase
from .smoke import SMOKE_COLLECTION

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
DEFAULT_TRIAGE_REGRESSION_DATASET = (
    REPO_ROOT / "outputs" / "smoke_chroma" / "evaluation" / "graphrag_triage_regression.jsonl"
)

WECHAT_PRIVATE_CONTACT_FIXTURE_SOURCE = "wechat_private_contact_affection_gold.md"
WECHAT_PRIVATE_CONTACT_FIXTURE_TEXT = """# WeChat private-contact affection sweep gold fixture

This document is a small promoted regression fixture for 全量私聊联系人级暧昧关系分析.
It represents one-to-one private chat chunks and preserves contact partitions, dates,
speakers, message_id, chunk_id, and original text evidence.

Contact: 小琳
Remark: 小琳
username: wxid_xiaolin_gold
conversation_type: private_chat
chunk_id: contact-xiaolin-20260103
message_id: msg-xiaolin-001
2026-01-03 23:10:05 号主: 宝宝晚安，今天辛苦了，抱抱。
message_id: msg-xiaolin-002
2026-01-03 23:11:18 小琳: 晚安宝贝抱抱，明天见。
judgement: 较确定
reason: 双方互称宝宝/宝贝，并出现晚安、抱抱、明天见等双向亲密互动原文证据。

Contact: 徐明阳
Remark: 徐明阳
username: wxid_xumingyang_gold
conversation_type: private_chat
chunk_id: contact-xumingyang-20250519
message_id: msg-xumingyang-001
2025-05-19 15:24:58 徐明阳: 我们讨论一下社保制度和政治学概论的问题。
message_id: msg-xumingyang-002
2025-05-19 15:30:12 号主: 可以，这个属于学术讨论。
judgement: 不足证据
reason: 内容是学术或普通朋友交流，没有暧昧证据。

Excluded conversation: 文件传输助手
conversation_type: file_transfer
chunk_id: excluded-filehelper-001
message_id: msg-filehelper-001
2026-01-04 00:01:00 号主: 草稿里写过宝宝、宝贝、亲爱的。
judgement: 排除
reason: 文件传输助手不是一对一私聊联系人，不允许归因到任何联系人。

Expected full-contact result:
- 较确定暧昧对象人数: 1
- 疑似暧昧对象人数: 0
- 性别不确定但有暧昧证据的人数: 0
- 小琳 / wxid_xiaolin_gold / 较确定 / evidence: msg-xiaolin-001, msg-xiaolin-002
- 徐明阳 / wxid_xumingyang_gold / 不足证据
- 文件传输助手必须排除
- 不要只基于 top-k chunk; 必须做全量逐联系人扫描并解释为什么其他联系人未计入。
"""

WECHAT_PRIVATE_CONTACT_CASE = RAGEvaluationCase(
    id="wechat_private_contact_affection_sweep_gold_001",
    question=(
        "请执行全量私聊联系人级暧昧关系分析，不要只基于 top-k chunk。"
        "请按每个一对一私聊联系人逐个分析所有聊天记录，输出较确定/疑似/不足证据，"
        "必须给出日期、发送方、chunk_id 或 message_id 的原文证据，并说明为什么其他联系人未计入。"
    ),
    reference_answer=(
        "小琳因宝宝晚安、晚安宝贝抱抱等双向亲密互动判为较确定；"
        "徐明阳是学术讨论，证据不足；文件传输助手必须排除。"
    ),
    expected_evidence_keywords=[
        "全量私聊联系人级暧昧关系分析",
        "小琳",
        "晚安宝贝抱抱",
        "较确定",
        "徐明阳",
        "不足证据",
        "文件传输助手",
    ],
    task_type="private_contact_affection_sweep",
    source_scope="wechat_private_contact_affection_gold",
    grading_notes=(
        "Promoted fixture for broad private-contact analysis. Must not pass through an empty "
        "top-k-only regression gate."
    ),
    expected_modes=["global", "comprehensive"],
)


def seed_promoted_graphrag_regression_fixture(
    *,
    persist_dir: str | Path,
    dataset_path: str | Path = DEFAULT_TRIAGE_REGRESSION_DATASET,
    collection_name: str = SMOKE_COLLECTION,
    backend: str = "hashing",
) -> dict[str, Any]:
    """Ingest the private-contact fixture and upsert its promoted regression case."""
    persist_path = Path(persist_dir)
    dataset = Path(dataset_path)
    _load_console_pipeline().ingest_source_payloads(
        payloads=[(WECHAT_PRIVATE_CONTACT_FIXTURE_SOURCE, WECHAT_PRIVATE_CONTACT_FIXTURE_TEXT.encode("utf-8"))],
        persist_dir=persist_path,
        collection_name=collection_name,
        chunk_size=2400,
        overlap=120,
        backend=backend,
    )
    cases = _load_existing_cases(dataset)
    case_record = WECHAT_PRIVATE_CONTACT_CASE.to_dataset_record()
    cases = [case for case in cases if str(case.get("id")) != WECHAT_PRIVATE_CONTACT_CASE.id]
    cases.append(case_record)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    return {
        "persist_dir": str(persist_path),
        "collection_name": collection_name,
        "dataset_path": str(dataset),
        "case_count": len(cases),
        "seeded_case_id": WECHAT_PRIVATE_CONTACT_CASE.id,
        "source_file": WECHAT_PRIVATE_CONTACT_FIXTURE_SOURCE,
    }


def _load_existing_cases(dataset_path: Path) -> list[dict[str, Any]]:
    if not dataset_path.exists():
        return []
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError(f"{dataset_path}:{line_number} must contain a JSON object")
        cases.append(payload)
    return cases


def _load_console_pipeline() -> Any:
    if str(CONSOLE_SRC) not in sys.path:
        sys.path.insert(0, str(CONSOLE_SRC))
    from chroma_rag_poc import pipeline

    return pipeline
