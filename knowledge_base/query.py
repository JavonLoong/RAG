"""Version-bound keyword, semantic, hybrid, and evidence-only RAG queries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .models import Citation, EvidenceConflict, KnowledgeBaseError, RagAnswer, SearchHit, SearchMode
from .store import KnowledgeBaseStore


class KnowledgeBaseQueryService:
    def __init__(self, store: KnowledgeBaseStore) -> None:
        self.store = store

    def search(
        self,
        query: str,
        *,
        mode: SearchMode = SearchMode.HYBRID,
        top_k: int = 5,
        version: int | None = None,
        embedder: Any | None = None,
        embedding_model: str | None = None,
        candidate_multiplier: int = 4,
        allowed_access_labels: set[str] | None = None,
    ) -> list[SearchHit]:
        if not query.strip() or top_k <= 0:
            return []
        candidate_k = max(top_k, top_k * candidate_multiplier)
        keyword: list[SearchHit] = []
        semantic: list[SearchHit] = []
        if mode in {SearchMode.KEYWORD, SearchMode.HYBRID}:
            keyword = self.store.keyword_search(query, version=version, top_k=candidate_k)
        if mode in {SearchMode.SEMANTIC, SearchMode.HYBRID}:
            if embedder is None or not embedding_model:
                if mode is SearchMode.SEMANTIC:
                    raise KnowledgeBaseError(
                        "SEMANTIC_BACKEND_REQUIRED",
                        "Semantic search requires an embedder and embedding_model.",
                    )
            else:
                query_vector = (
                    embedder.embed_query(query)
                    if callable(getattr(embedder, "embed_query", None))
                    else embedder.embed([query])[0]
                )
                semantic = self.store.semantic_search(
                    query_vector,
                    embedding_model=embedding_model,
                    version=version,
                    top_k=candidate_k,
                )
        keyword = [hit for hit in keyword if _is_authorized(hit, allowed_access_labels)]
        semantic = [hit for hit in semantic if _is_authorized(hit, allowed_access_labels)]
        if mode is SearchMode.KEYWORD:
            return keyword[:top_k]
        if mode is SearchMode.SEMANTIC:
            return semantic[:top_k]
        if not semantic:
            return keyword[:top_k]
        return _reciprocal_rank_fusion(keyword, semantic, top_k=top_k)

    def answer(
        self,
        query: str,
        *,
        responder: Callable[[str], str] | Any | None = None,
        mode: SearchMode = SearchMode.HYBRID,
        top_k: int = 5,
        version: int | None = None,
        embedder: Any | None = None,
        embedding_model: str | None = None,
        allowed_access_labels: set[str] | None = None,
    ) -> RagAnswer:
        release = self.store.get_release(version)
        hits = self.search(
            query,
            mode=mode,
            top_k=top_k,
            version=release.version,
            embedder=embedder,
            embedding_model=embedding_model,
            allowed_access_labels=allowed_access_labels,
        )
        if not hits:
            return RagAnswer(
                query=query,
                version=release.version,
                answer="未在当前已发布资料库中找到足够证据。",
                citations=(),
                no_answer=True,
                search_mode=mode,
            )
        citations = tuple(_citation(hit, index + 1) for index, hit in enumerate(hits))
        conflicts = _detect_conflicts(hits)
        if responder is None:
            answer_text = "\n\n".join(f"[{citation.citation_id}] {citation.quote}" for citation in citations)
        else:
            prompt = _grounded_prompt(query, hits)
            if callable(responder):
                answer_text = str(responder(prompt)).strip()
            elif callable(getattr(responder, "generate", None)):
                answer_text = str(responder.generate(prompt)).strip()
            else:
                raise TypeError("responder must be callable or expose generate(prompt)")
            if not answer_text:
                return RagAnswer(
                    query=query,
                    version=release.version,
                    answer="证据已检索到，但回答生成器未返回有效内容。",
                    citations=citations,
                    no_answer=True,
                    search_mode=mode,
                    conflicts=conflicts,
                )
        return RagAnswer(
            query=query,
            version=release.version,
            answer=answer_text,
            citations=citations,
            no_answer=False,
            search_mode=mode,
            conflicts=conflicts,
        )


def _reciprocal_rank_fusion(
    keyword: list[SearchHit],
    semantic: list[SearchHit],
    *,
    top_k: int,
    constant: int = 60,
) -> list[SearchHit]:
    source: dict[str, SearchHit] = {}
    scores: dict[str, float] = {}
    components: dict[str, dict[str, float]] = {}
    for name, ranking in (("keyword", keyword), ("semantic", semantic)):
        for rank, hit in enumerate(ranking, start=1):
            source.setdefault(hit.chunk_id, hit)
            contribution = 1.0 / (constant + rank)
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + contribution
            components.setdefault(hit.chunk_id, {})[name] = contribution
    ranked = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_k]
    return [
        replace(source[chunk_id], score=scores[chunk_id], component_scores=components[chunk_id]) for chunk_id in ranked
    ]


def _citation(hit: SearchHit, index: int) -> Citation:
    pages = tuple(sorted({item.page_number for item in hit.evidence}))
    quote = hit.text if len(hit.text) <= 320 else hit.text[:317].rstrip() + "..."
    return Citation(
        citation_id=f"C{index}",
        document_id=hit.document_id,
        revision_id=hit.revision_id,
        chunk_id=hit.chunk_id,
        source_uri=hit.source_uri,
        title=hit.title,
        pages=pages,
        quote=quote,
    )


def _grounded_prompt(query: str, hits: list[SearchHit]) -> str:
    contexts = []
    for index, hit in enumerate(hits, start=1):
        pages = ",".join(str(item) for item in sorted({locator.page_number for locator in hit.evidence}))
        contexts.append(f"[C{index}] {hit.title}，页 {pages}\n{hit.text}")
    return (
        "你是证据约束的科研问答助手。只能使用下列已发布证据回答；每个事实后标注 [C编号]。"
        "证据不足时明确回答不知道，不得补造事实；不同来源存在冲突时并列陈述，不得擅自裁决。\n\n"
        f"问题：{query}\n\n证据：\n" + "\n\n".join(contexts)
    )


def _is_authorized(hit: SearchHit, allowed_access_labels: set[str] | None) -> bool:
    if allowed_access_labels is None:
        return True
    required = hit.metadata.get("required_access_labels", [])
    if isinstance(required, str):
        required_labels = {required}
    elif isinstance(required, list):
        required_labels = {str(value) for value in required}
    else:
        return False
    return required_labels.issubset(allowed_access_labels)


def _detect_conflicts(hits: list[SearchHit]) -> tuple[EvidenceConflict, ...]:
    groups: dict[str, set[str]] = {}
    for hit in hits:
        group = hit.metadata.get("conflict_group")
        if group:
            groups.setdefault(str(group), set()).add(hit.document_id)
    return tuple(
        EvidenceConflict(
            conflict_group=group,
            document_ids=tuple(sorted(document_ids)),
            message="检索结果包含人工标记为相互冲突的已发布来源，请保留并列证据并交由领域人员裁决。",
        )
        for group, document_ids in sorted(groups.items())
        if len(document_ids) > 1
    )
