"""Operational CLI for M3 lifecycle, indexing, retrieval, and recovery."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from knowledge_base import (  # noqa: E402
    DocumentInput,
    KnowledgeBaseQueryService,
    KnowledgeBaseStore,
    M2HandoffService,
    ReviewDecision,
    SearchMode,
    document_from_payload,
    m2_handoff_from_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Versioned normative knowledge-base operations")
    parser.add_argument("--db", type=Path, required=True, help="SQLite knowledge-base path")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init")

    candidate = commands.add_parser("create-candidate")
    candidate.add_argument("--input", type=Path, required=True, help="Normalized M2 JSON document")
    candidate.add_argument("--actor", required=True)
    candidate.add_argument("--chunk-size", type=int, default=800)
    candidate.add_argument("--overlap", type=int, default=100)

    accept_m2 = commands.add_parser("accept-m2")
    accept_m2.add_argument("--input", type=Path, required=True, help="power-rag.m2-document.v1 JSON hand-off")
    accept_m2.add_argument("--actor", required=True)
    accept_m2.add_argument("--chunk-size", type=int, default=800)
    accept_m2.add_argument("--overlap", type=int, default=100)

    submit = commands.add_parser("submit-review")
    submit.add_argument("--revision", required=True)
    submit.add_argument("--actor", required=True)

    review = commands.add_parser("review")
    review.add_argument("--revision", required=True)
    review.add_argument("--decision", choices=[item.value for item in ReviewDecision], required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--comment", default="")

    embed = commands.add_parser("index-embeddings")
    embed_target = embed.add_mutually_exclusive_group(required=True)
    embed_target.add_argument("--revision", action="append")
    embed_target.add_argument("--version", type=int)
    embed.add_argument("--model", required=True)
    embed.add_argument("--backend", choices=["openai", "sentence-transformer", "hashing-test-only"], required=True)
    embed.add_argument("--batch-size", type=int, default=64)
    embed.add_argument("--force", action="store_true", help="Rebuild vectors even when content hashes match")

    publish = commands.add_parser("publish")
    publish.add_argument("--revision", action="append", required=True)
    publish.add_argument("--actor", required=True)
    publish.add_argument("--note", default="")
    publish.add_argument("--expected-base-version", type=int)
    publish.add_argument("--require-embeddings", action="store_true")
    publish.add_argument("--embedding-model")

    verify = commands.add_parser("verify")
    verify.add_argument("--version", type=int)
    verify.add_argument("--require-embeddings", action="store_true")
    verify.add_argument("--embedding-model")

    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--mode", choices=[item.value for item in SearchMode], default=SearchMode.KEYWORD.value)
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--version", type=int)
    search.add_argument("--model")
    search.add_argument("--backend", choices=["openai", "sentence-transformer", "hashing-test-only"])

    compare = commands.add_parser("compare")
    compare.add_argument("--from-version", type=int, required=True)
    compare.add_argument("--to-version", type=int, required=True)

    export_snapshot = commands.add_parser("export-snapshot")
    export_snapshot.add_argument("--version", type=int)
    export_snapshot.add_argument("--output", type=Path, help="Write the M3→M4 JSON snapshot to this path")

    deprecate = commands.add_parser("deprecate")
    deprecate.add_argument("--document", required=True)
    deprecate.add_argument("--actor", required=True)
    deprecate.add_argument("--note", default="")
    deprecate.add_argument("--expected-base-version", type=int)

    rollback = commands.add_parser("rollback")
    rollback.add_argument("--target-version", type=int, required=True)
    rollback.add_argument("--actor", required=True)
    rollback.add_argument("--note", default="")
    rollback.add_argument("--expected-base-version", type=int)

    backup = commands.add_parser("backup")
    backup.add_argument("--output-dir", type=Path, required=True)
    backup.add_argument("--name")

    restore = commands.add_parser("restore")
    restore.add_argument("--backup-db", type=Path, required=True)
    restore.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:  # noqa: C901
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    store = KnowledgeBaseStore(args.db)
    command = args.command
    if command == "init":
        store.initialize()
        result: Any = {"status": "ok", "database": str(args.db), "current_version": store.current_version()}
    elif command == "create-candidate":
        result = store.create_candidate(
            _load_document(args.input),
            created_by=args.actor,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
    elif command == "accept-m2":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = M2HandoffService(store).accept(
            m2_handoff_from_payload(payload),
            actor=args.actor,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
    elif command == "submit-review":
        result = store.submit_for_review(args.revision, actor=args.actor)
    elif command == "review":
        result = store.record_review(
            args.revision,
            decision=ReviewDecision(args.decision),
            reviewer=args.reviewer,
            comment=args.comment,
        )
    elif command == "index-embeddings":
        result = store.index_embeddings(
            revision_ids=args.revision,
            version=args.version,
            embedding_model=args.model,
            embedder=_build_embedder(args.backend, args.model),
            batch_size=args.batch_size,
            force=args.force,
        )
    elif command == "publish":
        result = store.publish(
            args.revision,
            actor=args.actor,
            note=args.note,
            expected_base_version=args.expected_base_version,
            require_embeddings=args.require_embeddings,
            embedding_model=args.embedding_model,
        )
    elif command == "verify":
        result = store.verify_version(
            args.version,
            require_embeddings=args.require_embeddings,
            embedding_model=args.embedding_model,
        )
    elif command == "search":
        mode = SearchMode(args.mode)
        if mode is not SearchMode.KEYWORD and (not args.backend or not args.model):
            raise SystemExit("semantic/hybrid search requires --backend and --model")
        result = KnowledgeBaseQueryService(store).search(
            args.query,
            mode=mode,
            top_k=args.top_k,
            version=args.version,
            embedder=None if mode is SearchMode.KEYWORD else _build_embedder(args.backend, args.model),
            embedding_model=args.model,
        )
    elif command == "compare":
        result = store.compare_versions(args.from_version, args.to_version)
    elif command == "export-snapshot":
        snapshot = store.export_snapshot(args.version)
        if args.output is None:
            result = snapshot
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(_serializable(snapshot), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            result = {
                "schema_version": snapshot.schema_version,
                "knowledge_base_version": snapshot.release.version,
                "manifest_sha256": snapshot.release.manifest_sha256,
                "document_count": len(snapshot.documents),
                "chunk_count": sum(len(document.chunks) for document in snapshot.documents),
                "output": str(args.output),
            }
    elif command == "deprecate":
        result = store.deprecate_document(
            args.document,
            actor=args.actor,
            note=args.note,
            expected_base_version=args.expected_base_version,
        )
    elif command == "rollback":
        result = store.rollback(
            args.target_version,
            actor=args.actor,
            note=args.note,
            expected_base_version=args.expected_base_version,
        )
    elif command == "backup":
        result = store.create_backup(args.output_dir, name=args.name)
    elif command == "restore":
        result = store.restore_backup(args.backup_db, args.manifest)
    else:  # pragma: no cover - argparse guarantees a known command.
        raise AssertionError(command)
    print(json.dumps(_serializable(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _load_document(path: Path) -> DocumentInput:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return document_from_payload(payload)


def _build_embedder(backend: str, model: str) -> Any:
    from model_adapters.embedding import (
        HashingEmbeddingAdapter,
        OpenAIEmbeddingAdapter,
        SentenceTransformerAdapter,
    )

    if backend == "hashing-test-only":
        return HashingEmbeddingAdapter()
    if backend == "sentence-transformer":
        return SentenceTransformerAdapter(model_name=model)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for the openai backend")
    return OpenAIEmbeddingAdapter(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=model,
    )


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return _serializable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
