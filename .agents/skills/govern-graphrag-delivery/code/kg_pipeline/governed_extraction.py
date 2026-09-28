"""Automatic evidence-bound graph candidate extraction for governed delivery.

The deterministic rule backend is deliberately modest: it provides an offline,
auditable baseline for common gas-turbine/FMEA statements.  A callable small
model or LLM client can be injected for broader extraction, but every output is
still passed through the governance schema and evidence gates before release.
"""
# ruff: noqa: C901, RUF001, TRY003

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from core_domain.delivery import CanonicalDocumentVersion, ContentStatus, GraphDomainSchema


class GovernedExtractionError(RuntimeError):
    """Raised when automatic graph extraction cannot produce governed candidates."""


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    statements: tuple[dict[str, Any], ...]
    diagnostics: dict[str, Any]


_ZH_CORE_PATTERN = re.compile(
    r"(?:(?P<equipment>燃气轮机|燃机|燃气涡轮发动机))?"
    r"(?P<component>[A-Za-z0-9\-\u4e00-\u9fff]{2,24}?(?:系统|组件|部件|燃烧室|压气机|涡轮|轴承|过滤器|油泵|阀门))"
    r"的(?P<failure>[^，。；]{2,24}?)(?:可能|通常|主要)?(?:由|因|由于)"
    r"(?P<cause>[^，。；]{2,30}?)(?:导致|引起|造成)"
)
_ZH_FAILURE_CAUSE_PATTERN = re.compile(
    r"(?P<failure>[^，。；]{2,24}?)(?:的)?(?:原因|根因)(?:是|为|包括)?(?P<cause>[^，。；]{2,30})"
)
_ZH_EFFECT_PATTERN = re.compile(r"(?:影响|后果)(?:是|为|包括)?(?P<value>[^，。；]{2,40})")
_ZH_DETECTION_PATTERN = re.compile(r"(?:可|可以|能够)?通过(?P<value>[^，。；]{2,40}?)(?:发现|检测|识别)")
_ZH_ACTION_PATTERN = re.compile(r"(?:并|可|可以)?(?:通过|采用)(?P<value>[^，。；]{2,50}?)(?:处理|缓解|解决|预防)")
_MODEL_PATTERN = re.compile(
    r"(?P<model>M\s*7[O0]1\s*F|M\s*7[O0]I\s*F|PG\s*9351\s*F(?:A)?|LM\s*2500|STG5-4000F)",
    re.IGNORECASE,
)
_EN_CORE_PATTERN = re.compile(
    r"(?P<component>[A-Za-z][A-Za-z0-9 /_-]{2,40}?)\s+"
    r"(?P<failure>[A-Za-z][A-Za-z0-9 /_-]{2,40}?)\s+"
    r"(?:is|may be|can be)\s+caused by\s+(?P<cause>[^.;,]{2,50})",
    re.IGNORECASE,
)
_EN_EFFECT_PATTERN = re.compile(r"(?:leading to|resulting in|effect(?: is|:))\s+(?P<value>[^.;]{2,60})", re.I)
_EN_DETECTION_PATTERN = re.compile(r"(?:detected|identified|monitored)\s+(?:by|using)\s+(?P<value>[^.;]{2,60})", re.I)
_EN_ACTION_PATTERN = re.compile(r"(?:mitigated|treated|prevented)\s+(?:by|using)\s+(?P<value>[^.;]{2,60})", re.I)


def extract_governed_statements(
    documents: Sequence[CanonicalDocumentVersion],
    *,
    backend: str = "rules",
    schema: GraphDomainSchema | None = None,
    model_client: Any | None = None,
    model_name: str | None = None,
    prompt_version: str = "graph-extraction-v1",
    temperature: float = 0.0,
    timeout_seconds: float = 120.0,
    retries: int = 0,
) -> ExtractionResult:
    schema = schema or GraphDomainSchema()
    for document in documents:
        if document.status is not ContentStatus.PUBLISHED:
            raise GovernedExtractionError(f"Automatic extraction requires published material: {document.version_id}")

    normalized_backend = str(backend).strip().lower().replace("_", "-")
    if normalized_backend == "rules":
        statements, per_chunk = _extract_with_rules(documents, schema)
    elif normalized_backend in {"small-model", "llm"}:
        if model_client is None:
            raise GovernedExtractionError(
                f"{normalized_backend} extraction requires an injected callable/client; rules remains the offline fallback"
            )
        statements, per_chunk = _extract_with_model(
            documents,
            schema,
            model_client,
            prompt_version=prompt_version,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )
    else:
        raise GovernedExtractionError("backend must be rules, small-model, or llm")

    deduped: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]] = {}
    for statement in statements:
        key = (
            str(statement.get("subject") or ""),
            str(statement.get("predicate") or ""),
            str(statement.get("object") or ""),
            tuple(statement.get("evidence_ids") or ()),
        )
        deduped.setdefault(key, statement)
    result = tuple(deduped.values())
    return ExtractionResult(
        statements=result,
        diagnostics={
            "backend": normalized_backend,
            "model": model_name or ("gas-turbine-rule-baseline-v1" if normalized_backend == "rules" else "injected"),
            "prompt_version": prompt_version if normalized_backend != "rules" else None,
            "temperature": temperature if normalized_backend != "rules" else None,
            "timeout_seconds": timeout_seconds if normalized_backend != "rules" else None,
            "retries": retries if normalized_backend != "rules" else None,
            "document_versions": [item.version_id for item in documents],
            "evidence_chunks": sum(len(item.evidence) for item in documents),
            "candidate_statement_count": len(result),
            "chunks": per_chunk,
            "automatic_extraction": True,
            "requires_schema_and_human_review": True,
        },
    )


def _extract_with_rules(
    documents: Sequence[CanonicalDocumentVersion],
    schema: GraphDomainSchema,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    statements: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for document in documents:
        for evidence in document.evidence:
            extracted = _rule_statements(evidence.text, evidence.evidence_id, schema)
            statements.extend(extracted)
            diagnostics.append({
                "document_version_id": document.version_id,
                "evidence_id": evidence.evidence_id,
                "statement_count": len(extracted),
                "matched": bool(extracted),
            })
    return statements, diagnostics


def _rule_statements(text: str, evidence_id: str, schema: GraphDomainSchema) -> list[dict[str, Any]]:
    clean = " ".join(str(text).split())
    model_match = _MODEL_PATTERN.search(clean)
    model_scope = (
        (schema.normalize_model(re.sub(r"\s+", "", model_match.group("model")).upper()),)
        if model_match
        else ()
    )
    core = _ZH_CORE_PATTERN.search(clean)
    language = "zh"
    if core is None:
        core = _EN_CORE_PATTERN.search(clean)
        language = "en"
    if core is None:
        simple = _ZH_FAILURE_CAUSE_PATTERN.search(clean)
        if simple is None:
            return []
        failure = _clean_value(simple.group("failure"))
        cause = _clean_value(simple.group("cause"))
        return [
            _statement(
                failure,
                "CAUSED_BY",
                cause,
                "FAILURE_MODE",
                "CAUSE",
                evidence_id,
                0.76,
                schema=schema,
                model_scope=model_scope,
            )
        ]

    groups = core.groupdict()
    equipment = _clean_value(groups.get("equipment") or "")
    if model_scope:
        equipment = f"{model_scope[0]}燃气轮机"
    component = _clean_value(groups.get("component") or "")
    failure = _clean_value(groups.get("failure") or "")
    cause = _clean_value(groups.get("cause") or "")
    output: list[dict[str, Any]] = []
    if equipment and component:
        output.append(
            _statement(
                component,
                "PART_OF",
                equipment,
                "COMPONENT",
                "EQUIPMENT",
                evidence_id,
                0.86,
                schema=schema,
                model_scope=model_scope,
            )
        )
    if component and failure:
        output.append(
            _statement(
                component,
                "HAS_FAILURE_MODE",
                failure,
                "COMPONENT",
                "FAILURE_MODE",
                evidence_id,
                0.88,
                schema=schema,
                model_scope=model_scope,
            )
        )
    if failure and cause:
        output.append(
            _statement(
                failure,
                "CAUSED_BY",
                cause,
                "FAILURE_MODE",
                "CAUSE",
                evidence_id,
                0.84,
                schema=schema,
                model_scope=model_scope,
            )
        )

    patterns = (
        ("HAS_EFFECT", "EFFECT", _ZH_EFFECT_PATTERN if language == "zh" else _EN_EFFECT_PATTERN, 0.82),
        ("DETECTED_BY", "DETECTION_METHOD", _ZH_DETECTION_PATTERN if language == "zh" else _EN_DETECTION_PATTERN, 0.82),
        ("MITIGATED_BY", "ACTION", _ZH_ACTION_PATTERN if language == "zh" else _EN_ACTION_PATTERN, 0.80),
    )
    for predicate, object_type, pattern, confidence in patterns:
        match = pattern.search(clean)
        if match and failure:
            value = _clean_value(match.group("value"))
            if value:
                output.append(
                    _statement(
                        failure,
                        predicate,
                        value,
                        "FAILURE_MODE",
                        object_type,
                        evidence_id,
                        confidence,
                        schema=schema,
                        model_scope=model_scope,
                    )
                )
    return output


def _extract_with_model(
    documents: Sequence[CanonicalDocumentVersion],
    schema: GraphDomainSchema,
    model_client: Any,
    *,
    prompt_version: str,
    temperature: float,
    timeout_seconds: float,
    retries: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    statements: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for document in documents:
        for evidence in document.evidence:
            prompt = (
                "Extract gas-turbine knowledge graph statements as strict JSON. "
                "Return {\"statements\":[{\"subject\":...,\"predicate\":...,\"object\":...,"
                "\"subject_type\":...,\"object_type\":...,\"confidence\":0.0}]}. "
                "Use only the supplied schema, copy entity text from the evidence, and do not invent facts.\n"
                f"Entity types: {list(schema.entity_types)}\nRelation types: {list(schema.relation_types)}\n"
                f"Evidence:\n{evidence.text}"
            )
            started_at = perf_counter()
            raw, attempt_count = _invoke_model(
                model_client,
                prompt,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                retries=retries,
            )
            payload = _parse_json_payload(raw)
            chunk_statements = payload.get("statements") or payload.get("triples") or []
            if not isinstance(chunk_statements, list):
                raise GovernedExtractionError("Model output must contain a statements/triples list")
            for raw_statement in chunk_statements:
                if not isinstance(raw_statement, Mapping):
                    continue
                statement = dict(raw_statement)
                statement["predicate"] = statement.get("predicate") or statement.get("relation")
                statement["object"] = statement.get("object") or statement.get("target")
                statement["evidence_ids"] = [evidence.evidence_id]
                statement["knowledge_type"] = schema.knowledge_type_for_relation(str(statement["predicate"]))
                raw_scope = statement.get("model_scope") or []
                if isinstance(raw_scope, str):
                    raw_scope = [raw_scope]
                statement["model_scope"] = [schema.normalize_model(str(item)) for item in raw_scope if str(item)]
                statement["metadata"] = {
                    **dict(statement.get("metadata") or {}),
                    "automatic_extractor": "model",
                }
                statements.append(statement)
            diagnostics.append({
                "document_version_id": document.version_id,
                "evidence_id": evidence.evidence_id,
                "statement_count": len(chunk_statements),
                "matched": bool(chunk_statements),
                "prompt_version": prompt_version,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "temperature": temperature,
                "timeout_seconds": timeout_seconds,
                "attempt_count": attempt_count,
                "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                "raw_response_summary": {
                    "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "character_count": len(raw),
                },
            })
    return statements, diagnostics


def _invoke_model(
    client: Any,
    prompt: str,
    *,
    temperature: float,
    timeout_seconds: float,
    retries: int,
) -> tuple[str, int]:
    last_error: Exception | None = None
    for attempt in range(1, max(0, int(retries)) + 2):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="graph-extraction-model")
        future = executor.submit(_call_model, client, prompt, temperature)
        try:
            return str(future.result(timeout=max(0.001, float(timeout_seconds)))), attempt
        except FutureTimeout:
            future.cancel()
            last_error = GovernedExtractionError(
                f"Model extraction timed out after {timeout_seconds} seconds on attempt {attempt}"
            )
        except Exception as exc:  # provider failures are retried only when explicitly configured
            last_error = exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    raise GovernedExtractionError(f"Model extraction failed after {attempt} attempt(s): {last_error}") from last_error


def _call_model(client: Any, prompt: str, temperature: float) -> str:
    for method_name in ("complete", "generate", "invoke"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                return str(method(prompt, temperature=temperature))
            except TypeError:
                return str(method(prompt))
    if callable(client):
        try:
            return str(client(prompt, temperature=temperature))
        except TypeError:
            return str(client(prompt))
    raise GovernedExtractionError("Injected model client must be callable or expose complete/generate/invoke")


def _parse_json_payload(raw: str) -> dict[str, Any]:
    text = str(raw).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GovernedExtractionError(f"Model output is not valid JSON: {exc}") from exc
    if isinstance(payload, list):
        return {"statements": payload}
    if not isinstance(payload, dict):
        raise GovernedExtractionError("Model output must be a JSON object or list")
    return payload


def _statement(
    subject: str,
    predicate: str,
    object_name: str,
    subject_type: str,
    object_type: str,
    evidence_id: str,
    confidence: float,
    *,
    schema: GraphDomainSchema,
    model_scope: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "subject": subject,
        "predicate": predicate,
        "object": object_name,
        "subject_type": subject_type,
        "object_type": object_type,
        "evidence_ids": [evidence_id],
        "knowledge_type": schema.knowledge_type_for_relation(predicate),
        "model_scope": list(model_scope),
        "confidence": confidence,
        "metadata": {"automatic_extractor": "gas-turbine-rule-baseline-v1"},
    }


def _clean_value(value: str) -> str:
    return str(value).strip(" ，。；;:：、\t\r\n")
