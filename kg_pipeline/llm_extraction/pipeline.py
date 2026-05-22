from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_adapters import ChatMessage, OpenAICompatibleLLMClient, build_llm_from_env


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "poc" / "schema.json"


class LLMExtractionError(RuntimeError):
    """Raised when KG extraction cannot be completed."""


class MissingLLMClientError(LLMExtractionError):
    """Raised when no LLM client is supplied for extraction."""


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    id: str
    text: str
    source: str
    page: int | str | None = None


class OpenAICompatibleClient:
    """Compatibility wrapper used by scripts/extract_kg_with_llm.py."""

    def __init__(self, llm: OpenAICompatibleLLMClient, temperature: float = 0.0) -> None:
        self.llm = llm
        self.temperature = temperature

    @classmethod
    def from_env(
        cls,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        timeout_seconds: float = 60.0,
        temperature: float = 0.0,
    ) -> "OpenAICompatibleClient":
        import os

        original_model = os.environ.get("OPENAI_MODEL")
        original_base_url = os.environ.get("OPENAI_BASE_URL")
        try:
            if model:
                os.environ["OPENAI_MODEL"] = model
            if base_url:
                os.environ["OPENAI_BASE_URL"] = base_url
            return cls(
                build_llm_from_env(api_key_env=api_key_env, timeout=timeout_seconds),
                temperature=temperature,
            )
        except Exception as exc:  # noqa: BLE001 - script-facing compatibility layer.
            if "required" in str(exc):
                raise MissingLLMClientError(str(exc)) from exc
            raise
        finally:
            _restore_env("OPENAI_MODEL", original_model)
            _restore_env("OPENAI_BASE_URL", original_base_url)

    def complete(self, prompt: str) -> str:
        response = self.llm.chat(
            [ChatMessage(role="user", content=prompt)],
            temperature=self.temperature,
        )
        return response.content


def read_chunks(input_path: str | Path) -> list[ChunkRecord]:
    path = Path(input_path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        chunks = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            chunks.append(
                ChunkRecord(
                    id=str(payload.get("id") or payload.get("chunk_id") or f"chunk-{line_number}"),
                    text=str(payload.get("text") or payload.get("content") or ""),
                    source=str(payload.get("source_file") or payload.get("source") or path.name),
                    page=payload.get("page_num") or payload.get("page"),
                )
            )
        return chunks

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    return [
        ChunkRecord(id=f"{path.stem}-{index}", text=paragraph, source=path.name, page=1)
        for index, paragraph in enumerate(paragraphs, start=1)
    ]


def run_extraction(
    input_path: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    output_dir: str | Path | None = None,
    *,
    llm_client: Any | None,
    limit_chunks: int | None = None,
) -> dict[str, Any]:
    if llm_client is None:
        raise MissingLLMClientError("LLM client is required for KG extraction.")

    chunks = read_chunks(input_path)
    if limit_chunks is not None:
        chunks = chunks[:limit_chunks]
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    relation_types = _schema_relation_types(schema)

    candidates: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for chunk in chunks:
        prompt = _build_prompt(schema, chunk)
        try:
            raw_response = _call_llm(llm_client, prompt)
            triples = _parse_triples(raw_response)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            parse_errors.append({"chunk_id": chunk.id, "error": str(exc)})
            continue

        for triple in triples:
            normalized = _normalize_triple(triple, chunk)
            errors = _validate_triple(normalized, relation_types)
            if errors:
                invalid.append({"chunk_id": chunk.id, "triple": normalized, "errors": errors})
            else:
                candidates.append(normalized)

    target_dir = Path(output_dir) if output_dir is not None else Path(input_path).resolve().parent
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "triples_llm_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "input": str(input_path),
        "schema": str(schema_path),
        "chunk_count": len(chunks),
        "valid_count": len(candidates),
        "invalid_count": len(invalid),
        "parse_error_count": len(parse_errors),
        "invalid_triples": invalid,
        "parse_errors": parse_errors,
    }
    (target_dir / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _build_prompt(schema: dict[str, Any], chunk: ChunkRecord) -> str:
    return (
        "Extract evidence-bound knowledge graph triples from the chunk.\n"
        "Use only relation types from this schema. Return strict JSON: "
        '{"triples":[{"subject":"","relation":"","object":"","evidence":"","source":"","page":""}]}.\n\n'
        f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Chunk id: {chunk.id}\nSource: {chunk.source}\nPage: {chunk.page}\nText:\n{chunk.text}"
    )


def _call_llm(llm_client: Any, prompt: str) -> str:
    for method_name in ("complete", "generate", "invoke"):
        method = getattr(llm_client, method_name, None)
        if callable(method):
            return str(method(prompt))
    if callable(llm_client):
        return str(llm_client(prompt))
    raise MissingLLMClientError("LLM client must be callable or expose complete/generate/invoke.")


def _parse_triples(raw_response: str) -> list[dict[str, Any]]:
    payload = json.loads(raw_response)
    if isinstance(payload, list):
        return payload
    triples = payload.get("triples")
    if not isinstance(triples, list):
        raise ValueError("LLM JSON must contain a triples list.")
    return triples


def _normalize_triple(triple: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "subject": _coerce_text(triple.get("subject")),
        "relation": _coerce_text(triple.get("relation") or triple.get("predicate")),
        "object": _coerce_text(triple.get("object") or triple.get("target")),
        "evidence": _coerce_text(triple.get("evidence")),
        "source": _coerce_text(triple.get("source") or chunk.source),
        "page": triple.get("page") or chunk.page,
        "chunk_id": chunk.id,
    }


def _validate_triple(triple: dict[str, Any], relation_types: set[str]) -> list[str]:
    errors = []
    for field_name in ("subject", "relation", "object", "evidence"):
        if not triple.get(field_name):
            errors.append(field_name)
    if triple.get("relation") and triple["relation"] not in relation_types:
        errors.append("relation")
    return errors


def _schema_relation_types(schema: dict[str, Any]) -> set[str]:
    raw = schema.get("relation_types") or schema.get("relations") or []
    if isinstance(raw, dict):
        return {str(key) for key in raw.keys()}
    if isinstance(raw, list):
        values = set()
        for item in raw:
            if isinstance(item, dict):
                values.add(str(item.get("type") or item.get("name") or item.get("relation")))
            else:
                values.add(str(item))
        return {value for value in values if value}
    return set()


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _restore_env(key: str, original_value: str | None) -> None:
    import os

    if original_value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = original_value
