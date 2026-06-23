from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AdoptionStatus = Literal["missing", "prototype", "partial", "ready"]

REQUIRED_ADOPTION_AREAS: tuple[str, ...] = (
    "document_parsing_product",
    "engineering_boundary",
    "retrieval_quality",
    "graphrag",
    "evaluation",
    "operating_steps",
)

_STATUS_ORDER: dict[AdoptionStatus, int] = {
    "missing": 0,
    "prototype": 1,
    "partial": 2,
    "ready": 3,
}


@dataclass(frozen=True, slots=True)
class AdoptionStage:
    area: str
    label: str
    status: AdoptionStatus
    external_patterns: tuple[str, ...]
    local_components: tuple[str, ...]
    direct_use_steps: tuple[str, ...]
    gaps: tuple[str, ...]
    next_actions: tuple[str, ...]

    @property
    def maturity_score(self) -> int:
        return _STATUS_ORDER[self.status]


@dataclass(frozen=True, slots=True)
class ProductionRagProfile:
    stages: tuple[AdoptionStage, ...]

    @property
    def total_stage_count(self) -> int:
        return len(self.stages)

    @property
    def ready_stage_count(self) -> int:
        return sum(1 for stage in self.stages if stage.status == "ready")

    @property
    def overall_status(self) -> AdoptionStatus:
        if not self.stages:
            return "missing"
        min_score = min(stage.maturity_score for stage in self.stages)
        if min_score >= _STATUS_ORDER["ready"]:
            return "ready"
        if min_score >= _STATUS_ORDER["partial"]:
            return "partial"
        if any(stage.status in {"partial", "ready"} for stage in self.stages):
            return "partial"
        if any(stage.status == "prototype" for stage in self.stages):
            return "prototype"
        return "missing"

    def stage(self, area: str) -> AdoptionStage:
        for stage in self.stages:
            if stage.area == area:
                return stage
        raise KeyError(area)

    def to_markdown(self) -> str:
        lines = [
            "# RAG Mature Project Adoption Profile",
            "",
            f"Overall status: `{self.overall_status}`",
            f"Ready stages: `{self.ready_stage_count}/{self.total_stage_count}`",
            "",
        ]
        for stage in self.stages:
            lines.extend(
                [
                    f"## {stage.area}",
                    "",
                    f"- Label: {stage.label}",
                    f"- Status: `{stage.status}`",
                    f"- External patterns: {', '.join(stage.external_patterns)}",
                    f"- Local components: {', '.join(stage.local_components)}",
                    "- Direct use steps:",
                    *[f"  - {step}" for step in stage.direct_use_steps],
                    "- Current gaps:",
                    *[f"  - {gap}" for gap in stage.gaps],
                    "- Next actions:",
                    *[f"  - {action}" for action in stage.next_actions],
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"


def build_default_profile() -> ProductionRagProfile:
    return ProductionRagProfile(
        stages=(
            AdoptionStage(
                area="document_parsing_product",
                label="RAGFlow-style document understanding and citation-ready chunks",
                status="partial",
                external_patterns=(
                    "RAGFlow/DeepDoc: visual document parsing, OCR, layout, and grounded chunks",
                    "Docling: reading-order, table, formula, and OCR-aware document conversion",
                    "Unstructured: partition raw documents into typed elements before chunking",
                    "LlamaIndex: readers/loaders plus node metadata",
                    "Haystack: explicit document conversion pipeline",
                ),
                local_components=(
                    "data_pipeline/document_intake.py",
                    "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/parsing.py",
                    "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/cleaning.py",
                    "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/chunking.py",
                    "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/pipeline.py",
                    "scripts/ocr_scanned_pdfs.py",
                    "data_pipeline/ocr_processing_stages",
                ),
                direct_use_steps=(
                    "Call data_pipeline.document_intake.run_document_intake(source_name, raw_bytes) before indexing.",
                    "Use /api/process or /api/ingest to run the current Chroma ingestion path through document_intake.",
                    "Use the returned status: parsed documents can be indexed, needs_ocr documents go to OCR/layout/table recognition first.",
                    "Require source_file, record_id, page_nums, source_kind, char_count, and estimated_tokens metadata for every chunk.",
                    "Expose the returned profile, quality, errors, warnings, records, and chunks in upload/process API responses.",
                ),
                gaps=(
                    "OCR/layout/table recognition is classified as a first-class route, but external OCR output is not yet automatically re-fed into intake.",
                    "Chunk preview and citation inspection are not yet surfaced as a polished frontend workflow.",
                    "DeepDoc/MinerU/Docling are represented as parser backends and queues, but their heavy visual model runtimes are not vendored into this repo.",
                ),
                next_actions=(
                    "Expose DocumentIntakeResult.to_dict() more directly in the upload/process UI.",
                    "Add a small sample-file smoke test for PDF, DOCX, TXT, CSV, JSON, JSONL, and scanned-PDF failure.",
                    "Make chunk preview and failed-file triage visible in the console UI.",
                ),
            ),
            AdoptionStage(
                area="engineering_boundary",
                label="Dify/FastGPT-style product boundary with a single runtime contract",
                status="prototype",
                external_patterns=(
                    "Dify: app/workflow/model/provider boundaries",
                    "FastGPT/MaxKB: knowledge base plus workflow product shell",
                    "AnythingLLM/Open WebUI: low-friction local deployment",
                ),
                local_components=(
                    "api_server/current_console/server.py",
                    "api_server/current_console/chroma_rag_poc/pyproject.toml",
                    "pyproject.toml",
                    "frontend_app/current_console/index.html",
                ),
                direct_use_steps=(
                    "Use api_server/current_console/server.py as the current runtime entrypoint.",
                    "Use /api/health, /api/upload, /api/process, /api/search, and /api/query as the public API contract.",
                    "Keep runtime data under POWER_RAG_RUNTIME_DIR or the resolved local app data path.",
                ),
                gaps=(
                    "Root and console packages have conflicting dependency constraints.",
                    "Several modules insert repo paths into sys.path instead of relying on one installable package.",
                    "The frontend is a large single HTML file, which makes API contract drift easy.",
                ),
                next_actions=(
                    "Consolidate root and console pyproject files into one dependency source of truth.",
                    "Split the frontend into state, API client, RAG, GraphRAG, and UI modules.",
                    "Add one Docker Compose path that runs health, ingest, search, and GraphRAG smoke checks.",
                ),
            ),
            AdoptionStage(
                area="retrieval_quality",
                label="Haystack/LlamaIndex-style retriever pipeline with rerank and gates",
                status="partial",
                external_patterns=(
                    "Haystack: explicit retriever/ranker/generator pipeline nodes",
                    "Haystack: retriever-level metadata filters and visible ranker components",
                    "LlamaIndex: query engine with metadata-rich nodes",
                    "LlamaIndex: query transformations, reciprocal rank fusion, and post-retrieval rerank",
                    "RAGFlow: hybrid retrieval plus reranking and citation grounding",
                ),
                local_components=(
                    "retrieval_engine/hybrid.py",
                    "retrieval_engine/chroma.py",
                    "retrieval_engine/keyword.py",
                    "model_adapters/reranker.py",
                    "evaluation/system_eval_questions.jsonl",
                ),
                direct_use_steps=(
                    "Combine ChromaRetriever, KeywordRetriever, and SQLiteGraphRetriever behind HybridRetriever.",
                    "Use HybridRetriever(..., fusion_mode=\"rrf\") for LlamaIndex-style reciprocal rank fusion.",
                    "Pass filters={...} to retrieve(...) for Haystack-style metadata filter scoping.",
                    "Pass query_rewriter=... to run original and rewritten queries through the same fusion path.",
                    "Attach CrossEncoderReranker or LLMReranker; inspect last_diagnostics.reranker_error when it fails.",
                    "Set no_answer_min_score or no_answer_min_results to block weak evidence instead of forcing an answer.",
                    "Use /api/search as the local HybridRetriever entrypoint: Chroma vector and keyword retrievers are fused with fusion_mode=\"rrf\" and returned through retrieval_diagnostics.",
                    "Pass /api/search query_rewrite=true and reranker=noop or reranker=cross_encoder to exercise template query expansion and optional reranker diagnostics.",
                    "Pass /api/search graph_db_path=... to add SQLiteGraphRetriever as the graph path in the same HybridRetriever RRF adapter.",
                    "Pass POST /api/search filters={...} for Haystack-style metadata filtering through the same HybridRetriever adapter.",
                    "Use /api/search natural-language source type hints such as markdown/pdf/txt to auto-build source_ext metadata filters.",
                    "Use /api/search natural-language filename and year hints to auto-build source_file contains filters.",
                    "Use /api/search natural-language author, department, product, and date-range hints to auto-build business metadata filters.",
                    "Set retrieval_policies.json metadata_field_aliases to map canonical filters such as meta.source_date or meta.author to real-corpus fields such as meta.document_date or meta.owner.",
                    "Pass POST /api/search no_answer_min_score or no_answer_min_results to block weak evidence instead of forcing an answer.",
                    "Use /api/search retrieval_diagnostics to inspect original_query, rewritten_queries, fusion_mode, candidate counts, reranker_error, and no_answer_reason from the console.",
                    "Use evaluation report retrieval_default_policy to decide whether query_rewrite, reranker, graph, and no-answer gates should become defaults.",
                    "Place collection defaults in retrieval_policies.json so /api/search applies query_rewrite, reranker, filters, and no-answer thresholds automatically.",
                    "POST /api/retrieval/policies/roles/upsert to register service-side reviewer/approver/admin/owner roles and assigned collections in role_registry.",
                    "POST /api/retrieval/policies/promote to write reviewed collection defaults into retrieval_policies.json with an audit entry.",
                    "POST /api/retrieval/policies/propose to create a pending policy proposal without applying it; include assigned_to and due_at to create a local assignment notification.",
                    "POST /api/retrieval/policies/approve to apply a pending proposal using role_registry roles when present, falling back to request roles only for compatibility, while blocking self-approval.",
                    "POST /api/retrieval/policies/reject to close unsafe proposals without applying them, using the same role_registry gate.",
                    "GET /api/retrieval/policies/history to inspect current policy, audit history, and the latest added/removed/changed settings diff.",
                    "GET /api/retrieval/policies/notifications?recipient=...&status=pending to load local reviewer assignment notifications before approval.",
                    "POST /api/retrieval/policies/notification-recipients/upsert to store local notification_recipient_registry entries with email, webhook_url, webhook_template, webhook_signing_secret_env, webhook_routing_key_env, webhook_auth_header_name, webhook_auth_token_env, webhook_auth_scheme, and preferred_delivery_mode; GET /api/retrieval/policies/notification-recipients to inspect those mappings.",
                    "POST /api/retrieval/policies/directory/sync with SCIM-style users, groups, role_group_mappings, and recipient_defaults to bulk-sync role_registry and notification_recipient_registry from an external directory export.",
                    "Directory sync marks disabled users active=false in role_registry and notification_recipient_registry, clearing roles so inactive IdP accounts cannot approve policy changes through request-supplied roles.",
                    "Set RAG_POLICY_OIDC_REQUIRED=1 with RAG_POLICY_OIDC_ISSUER, RAG_POLICY_OIDC_AUDIENCE, and RAG_POLICY_OIDC_JWKS_URL to require signed OIDC/JWKS bearer-token identity on policy propose, approve, and reject endpoints.",
                    "POST /api/retrieval/policies/identity-provider/upsert with provider=oidc, enabled, issuer, audience, jwks_url, authorization_endpoint, token_endpoint, client_id, client_secret_env, redirect_uri, scopes, subject_claim, groups_claim, and algorithms to persist managed OIDC/JWKS enforcement config in retrieval_policies.json.",
                    "GET /api/retrieval/policies/identity-provider to inspect the managed OIDC config; request fields such as client_secret are ignored and never stored in retrieval_policies.json.",
                    "POST /api/retrieval/policies/identity-provider/login-url to generate an OIDC authorization URL with PKCE state, nonce, code_challenge, and a tab-local code_verifier for browser login.",
                    "POST /api/retrieval/policies/identity-provider/token with code, code_verifier, and redirect_uri to exchange an authorization code; client_secret_env resolves the confidential client secret from environment variables without storing the secret.",
                    "GET /api/retrieval/policies/identity-provider/callback?code=...&state=... consumes rag_policy_oidc_state plus retrieval_policy_oidc_states.json state/code_verifier, exchanges the code, validates the returned token, and creates the HttpOnly policy session.",
                    "POST /api/retrieval/policies/identity-provider/session with Authorization: Bearer <OIDC JWT> to create a server-side policy session and HttpOnly cookie for policy propose/approve/reject endpoints.",
                    "POST /api/retrieval/policies/identity-provider/session/refresh to use the server-side OIDC refresh_token from retrieval_policy_sessions.json, call the IdP refresh_token grant, validate the returned token, rotate refresh_token when supplied, and renew the HttpOnly policy session cookie.",
                    "Set RAG_POLICY_SESSION_SECRET_KEYS=activeKid:base64urlKey,oldKid:base64urlKey to store refresh_token_encrypted with AESGCM; the first key encrypts new tokens while older keys remain available for key rotation and decrypting existing sessions.",
                    "GET /api/retrieval/policies/identity-provider/sessions with an OIDC admin or owner in role_registry to list active tenant policy sessions without returning refresh tokens or encrypted ciphertext.",
                    "POST /api/retrieval/policies/identity-provider/sessions/rotate-key with an OIDC admin or owner in role_registry to re-encrypt existing session refresh_token_encrypted values with the active RAG_POLICY_SESSION_SECRET_KEYS key and append an identity_provider_session_key_rotate audit entry.",
                    "GET /api/retrieval/policies/identity-provider/sessions/key-status with an OIDC admin or owner in role_registry to inspect active_key_id, key_source, stale_encrypted_session_count, plain_refresh_session_count, rotation_due, and rotation_due_reasons without returning key material; set RAG_POLICY_SESSION_KEY_MAX_AGE_SECONDS to make stale rotation age visible.",
                    "DELETE /api/retrieval/policies/identity-provider/sessions/{session_id} with an OIDC admin or owner in role_registry to revoke a server-side policy session immediately and append an identity_provider_session_revoke audit entry.",
                    "Use the console Retrieval Policy Review session inventory table to scan sanitized OIDC sessions, select session ids for revocation, inspect secret_storage and has_refresh_token metadata, and read the latest session admin audit for identity_provider_session_revoke or identity_provider_session_key_rotate.",
                    "POST /api/retrieval/policies/identity-provider/logout to delete the stored policy session and clear the session cookie.",
                    "Use the console Retrieval Policy Review panel Use Token action to keep a reviewer OIDC JWT in browser sessionStorage for the current tab and automatically attach Authorization: Bearer headers to /api/retrieval/policies requests.",
                    "Call /api/retrieval/policies/approve with Authorization: Bearer <OIDC JWT>; the token subject replaces request-body approver/approver_role, and role_registry remains the authorization source.",
                    "POST /api/retrieval/policies/notifications/dispatch with delivery_mode=outbox_file to deliver pending reviewer notifications into a JSONL outbox under the persist directory.",
                    "POST /api/retrieval/policies/notifications/dispatch with delivery_mode=webhook and webhook_url=https://... to send pending reviewer notifications to external webhook receivers; http is allowed only for loopback local testing.",
                    "Set webhook_template=lark_text, dingtalk_text, or wecom_text for Lark/Feishu, DingTalk, or WeCom text bot payloads, and set webhook_signing_secret_env to add hmac-sha256 verification headers without storing the secret in retrieval_policies.json.",
                    "Set webhook_template=pagerduty_event_v2 and webhook_routing_key_env=RAG_PAGERDUTY_ROUTING_KEY to send PagerDuty Events API v2 trigger payloads without storing the routing key in retrieval_policies.json.",
                    "Set webhook_template=opsgenie_alert with webhook_auth_header_name=Authorization, webhook_auth_scheme=GenieKey, and webhook_auth_token_env=RAG_OPSGENIE_API_KEY to send Opsgenie alert payloads without storing the API key in retrieval_policies.json.",
                    "POST /api/retrieval/policies/notifications/dispatch with delivery_mode=smtp, smtp_host, smtp_port, smtp_from, smtp_to, smtp_subject, smtp_use_tls, smtp_username_env, and smtp_password_env to send reviewer notifications by email while keeping SMTP credentials in environment variables.",
                    "Inspect attempted_count, dispatched_count, failed_count, and notification.delivery.response.failed after webhook dispatches; failed delivery attempts keep response/error metadata and mark notifications as failed for audit and retry.",
                    "POST /api/retrieval/policies/rollback to restore the previous audited collection policy when a promoted default regresses.",
                    "Use the Retrieval Policy Review panel in the console to propose, assign, load pending notifications, dispatch notifications, approve, reject, promote, inspect latest diff/history, or roll back the collection policy.",
                    "Read the Retrieval Diagnostics card in the standard search results panel before trusting weak or empty retrieval output.",
                    "Run scripts/run_system_evaluation.py after retrieval changes.",
                ),
                gaps=(
                    "Evaluation reports now produce retrieval_default_policy recommendations; /api/search applies retrieval_policies.json defaults and metadata_field_aliases; /api/retrieval/policies/roles/upsert stores service-side role_registry entries; /api/retrieval/policies/directory/sync bulk-syncs SCIM-style directory exports into role_registry and notification_recipient_registry, including active=false deprovisioning; RAG_POLICY_OIDC_REQUIRED and /api/retrieval/policies/identity-provider/upsert enable PyJWT-backed OIDC/JWKS bearer-token validation so policy propose/approve/reject use signed IdP identity instead of request-body identity, while client_secret-style inputs are ignored and not stored; /api/retrieval/policies/identity-provider/login-url and /api/retrieval/policies/identity-provider/token add PKCE browser login URL generation and authorization-code exchange with client_secret_env-only confidential client support; /api/retrieval/policies/identity-provider/callback consumes stored PKCE state/code_verifier from retrieval_policy_oidc_states.json, validates the rag_policy_oidc_state cookie, exchanges the code, and creates the HttpOnly policy session; /api/retrieval/policies/identity-provider/session creates HttpOnly cookie-backed policy sessions, /api/retrieval/policies/identity-provider/session/refresh uses the server-side refresh_token to renew and rotate the session, RAG_POLICY_SESSION_SECRET_KEYS stores refresh_token_encrypted with AESGCM and supports key rotation through active plus old keys, /api/retrieval/policies/identity-provider/sessions lets role_registry admin/owner identities list sanitized active tenant sessions, /api/retrieval/policies/identity-provider/sessions/rotate-key re-encrypts existing session refresh tokens with the active key and writes identity_provider_session_key_rotate audit, /api/retrieval/policies/identity-provider/sessions/{session_id} revokes sessions with identity_provider_session_revoke audit, and /api/retrieval/policies/identity-provider/logout clears the current session, while the console can still keep a reviewer JWT in sessionStorage and attach Authorization: Bearer headers to policy requests; /api/retrieval/policies/propose, /api/retrieval/policies/approve, and /api/retrieval/policies/reject provide a lightweight audited approval flow with role registry, collection assignment gate, self-approval blocking, assigned_to/due_at metadata, and a local assignment notification outbox; /api/retrieval/policies/notification-recipients/upsert stores local notification_recipient_registry mappings, including incident webhook template env fields, and dispatch records recipient_source when smtp_to or webhook_url is resolved from that registry; /api/retrieval/policies/notifications exposes pending reviewer notifications; /api/retrieval/policies/notifications/dispatch can deliver pending notifications into a guarded outbox_file JSONL under the persist directory, POST them to delivery_mode=webhook receivers through webhook_url with https enforcement and loopback-only http for local tests, or send them by delivery_mode=smtp with smtp_host/smtp_username_env/smtp_password_env while keeping SMTP secrets in environment variables; webhook_template=lark_text emits Lark/Feishu-style text payloads, webhook_template=dingtalk_text and webhook_template=wecom_text emit DingTalk/WeCom text bot payloads, webhook_template=pagerduty_event_v2 emits PagerDuty Events API v2 trigger payloads with webhook_routing_key_env, webhook_template=opsgenie_alert emits Opsgenie alert payloads with webhook_auth_header_name/webhook_auth_scheme/webhook_auth_token_env, webhook_signing_secret_env adds hmac-sha256 signature headers while keeping secrets in environment variables, and failed webhook or SMTP attempts return failed_count plus failed delivery metadata instead of aborting the whole dispatch; /api/retrieval/policies/promote remains a direct compatibility path; /api/retrieval/policies/history exposes audit diffs; /api/retrieval/policies/rollback restores the previous audited policy; the console Retrieval Policy Review panel supports managed IdP config, PKCE login URL, hosted callback, authorization-code exchange, HttpOnly policy session, session refresh, tenant session list/revoke, session key rotation, tab-scoped token session, directory sync, role upsert, recipient upsert/list, propose, assignment, notification loading, notification dispatch, approve, reject, promote, history/diff, and rollback. The remaining gap is deeper tenant admin UI, IdP key rotation runbooks, stronger governance, and broader threshold calibration.",
                    "Natural-language source type, filename, year, author, department, product, and structured date range filters are automatic, and metadata_field_aliases can map them to real-corpus fields; the remaining work is calibrating those aliases against the real corpus.",
                    "RRF/rerank/no-answer thresholds can be passed per request, but still need evaluation-backed defaults for the real corpus.",
                ),
                next_actions=(
                    "Add tenant admin flows, IdP key rotation runbooks, and stronger governance on top of the OIDC/JWKS enforcement path.",
                    "Promote query rewrite and reranker switches into evaluation-backed defaults for selected collections.",
                    "Calibrate retrieval quality gates for recall@k, citation coverage, no-answer precision, and latency on the real corpus.",
                ),
            ),
            AdoptionStage(
                area="graphrag",
                label="LightRAG/Microsoft GraphRAG-style local/global graph retrieval",
                status="partial",
                external_patterns=(
                    "LightRAG: naive/local/global/hybrid/mix query modes",
                    "LightRAG: lightweight dual-level graph plus vector retrieval",
                    "Microsoft GraphRAG: community summaries and global map-reduce search",
                    "GraphRAG papers: local entity neighborhoods plus global community summaries",
                ),
                local_components=(
                    "kg_pipeline/community_detection.py",
                    "kg_pipeline/community_summary.py",
                    "storage_layer/graph_store.py",
                    "retrieval_engine/graph.py",
                    "rag_orchestrator/lightrag.py",
                    "rag_orchestrator/graph_quality.py",
                    "rag_orchestrator/triage.py",
                    "rag_orchestrator/global_search.py",
                    "rag_orchestrator/graphrag_qa.py",
                    "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py",
                    "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_graphrag.py",
                    "frontend_app/current_console/index.html",
                ),
                direct_use_steps=(
                    "Import triples into GraphStore, run Leiden community detection, then summarize communities.",
                    "Run rag_orchestrator.evaluate_graph_quality(graph_store) before using graph answers in production.",
                    "Use /api/query with mode=local/global/aggregation to enforce the graph quality gate before answer generation.",
                    "Read the Graph Quality Gate block in the console answer panel to inspect pass/fail metrics and blocked graph failures.",
                    "Use /api/graphrag/triage to list persisted GraphRAG pass/fail triage records.",
                    "Use /api/graphrag/triage/{triage_id}/review to persist accepted/rejected human review status.",
                    "Use /api/graphrag/triage/export to export filtered triage records as JSONL.",
                    "Use /api/graphrag/triage/analytics to summarize graph quality, review status, route strategy, failure metrics, and source evidence coverage.",
                    "Use /api/graphrag/triage/{triage_id}/promote to append a rejected case into the GraphRAG regression dataset.",
                    "Use the GraphRAG Triage History panel to filter by graph quality/review status, edit reviewer notes, export records, and promote bad cases.",
                    "Use the GraphRAG Triage History reviewer dashboard (kgTriageAnalytics) to inspect source evidence coverage, promoted_case_count, failure trend, route-level drilldown, review status, and failure metric counts before promotion.",
                    "Read /api/query lightrag_diagnostics to inspect LightRagDiagnostics counts for naive text, local graph, global community evidence, active paths, and route strategy; the same payload is persisted into triage records.",
                    "Read the LightRAG Diagnostics block in the console answer panel to inspect lightrag_diagnostics without opening raw JSON.",
                    "Inspect community summary metadata for evidence_triple_ids, sentence_evidence, and source_evidence before trusting global summaries.",
                    "Read /api/query citations with source_type=graph_community_source to inspect community-level source_evidence spans in the answer panel.",
                    "Pass allow_unsafe_graph=true only for debugging failed graphs; production requests should leave it false.",
                    "Use SQLiteGraphRetriever for local entity-neighborhood retrieval.",
                    "Use GlobalSearchOrchestrator for broad thematic questions.",
                    "Use LightRagQueryEngine(text_retriever=..., graph_retriever=..., global_searcher=...) for LightRAG-style modes.",
                    "Use LightRagQueryEngine.query(question, mode=\"mix\") as the default graph-plus-text retrieval path.",
                    "Use mode=\"naive\" for text-only, mode=\"local\" for graph-neighborhood, mode=\"global\" for community-only, and mode=\"hybrid\" for local+global.",
                ),
                gaps=(
                    "Graph quality gates now have historical triage, filters, export, review notes, regression promotion, analytics, and a reviewer dashboard with failure trend and route-level drilldown; they still need reviewer assignment and alerting for repeated failures.",
                    "Community source_evidence spans are exposed in answer citations and rejected query-level cases can be promoted into regression datasets, but sentence-level span decisions are not scored as first-class eval labels yet.",
                ),
                next_actions=(
                    "Add reviewer assignment and alerting for repeated GraphRAG quality failures.",
                    "Upgrade the console LightRAG Diagnostics block from markdown metrics into clickable retrieval-path breakdowns.",
                    "Extend /api/query GraphRAG smoke from fake-LLM global answer generation to a real configured LLM smoke profile.",
                ),
            ),
            AdoptionStage(
                area="evaluation",
                label="RAGAS-style continuous quality evaluation and regression gates",
                status="partial",
                external_patterns=(
                    "RAGAS: faithfulness, answer relevance, context recall",
                    "Dify/RAGFlow product telemetry: query logs and feedback loops",
                    "Haystack evaluation: pipeline-level regression checks",
                ),
                local_components=(
                    "evaluation/harness.py",
                    "evaluation/triage_regression.py",
                    "evaluation/metrics.py",
                    "evaluation/runner.py",
                    "evaluation/system_eval_questions.jsonl",
                    "scripts/run_system_evaluation.py",
                    "scripts/run_graphrag_triage_regression.py",
                ),
                direct_use_steps=(
                    "Use evaluation.RAGEvaluationHarness(rag_system, thresholds=...) to run live questions against a local RAG object.",
                    "Use evaluation.LocalChromaRegressionRag(persist_dir=..., collection_name=...) when promoted triage cases should run against the current persisted Chroma index.",
                    "Use EvaluationThresholds to enforce quality gates for keyword recall, answer completeness, citation coverage, no-result rate, and hallucination risk.",
                    "Generate or capture system outputs as JSONL.",
                    "Run scripts/run_system_evaluation.py with evaluation/system_eval_questions.jsonl.",
                    "Run scripts/run_graphrag_triage_regression.py --persist-dir <chroma_dir> --collection <collection> against promoted GraphRAG triage cases; GitLab CI runs the same gate with --allow-empty.",
                    "Compare recall, evidence coverage, citation missing rate, and hallucination risk between runs.",
                ),
                gaps=(
                    "CI runs the one-command smoke gate, but the full 60-question evaluation set is not yet a required pipeline gate.",
                    "GraphRAG triage has a promoted-case regression gate backed by the local Chroma adapter, but broader human feedback across ordinary RAG answers is not a first-class dataset yet.",
                    "Library harness quality gates exist, but only the tiny smoke subset is enforced by CI and none are visible in the console UI yet.",
                ),
                next_actions=(
                    "Promote the 60-question evaluation set into a scheduled or required CI gate.",
                    "Store failure cases as regression tests with expected evidence keywords.",
                    "Expose RAGEvaluationReport failure cases in the console for triage.",
                ),
            ),
            AdoptionStage(
                area="operating_steps",
                label="Direct-use runbook from upload to evaluated answer",
                status="prototype",
                external_patterns=(
                    "AnythingLLM/Open WebUI: low-friction local run path",
                    "MaxKB/FastGPT: visible knowledge-base lifecycle",
                    "Dify: workflow-oriented operating model",
                ),
                local_components=(
                    "Dockerfile",
                    ".gitlab-ci.yml",
                    "scripts/run_rag_smoke_evaluation.py",
                    "api_server/current_console/start_local.bat",
                    "README.md",
                ),
                direct_use_steps=(
                    "Start the console with api_server/current_console/start_local.bat or python server.py.",
                    "Upload documents, process them into a collection, then run /api/search or /api/query.",
                    "For GraphRAG, import graph data, detect communities, summarize, pass graph quality, then run global or local search.",
                    "Run scripts/run_rag_smoke_evaluation.py for a one-command ingest-search-evaluation-graph-quality-/api/query global answer smoke gate.",
                    "In GitLab CI, rag-smoke-job runs the same smoke command inside the built Docker image before deployment.",
                    "Run the evaluation script after every retrieval or graph pipeline change.",
                ),
                gaps=(
                    "The deployment smoke check still only verifies /api/health after the earlier RAG smoke gate passes.",
                    "The one-command smoke path covers fake-LLM /api/query global GraphRAG answer generation, but not a real configured model profile yet.",
                    "Runtime configuration is spread across environment variables, defaults, and docs.",
                ),
                next_actions=(
                    "Extend the smoke command to optionally cover a tiny /api/query GraphRAG global answer with a real configured LLM.",
                    "Document one recommended local path and one Docker path.",
                    "Expose the production profile in docs and API diagnostics.",
                ),
            ),
        )
    )
