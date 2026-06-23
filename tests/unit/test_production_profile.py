from __future__ import annotations

from pathlib import Path

from rag_orchestrator.production_profile import (
    REQUIRED_ADOPTION_AREAS,
    build_default_profile,
)


def test_default_profile_covers_requested_adoption_areas() -> None:
    profile = build_default_profile()

    assert {stage.area for stage in profile.stages} == set(REQUIRED_ADOPTION_AREAS)
    assert profile.ready_stage_count < profile.total_stage_count
    assert profile.overall_status in {"prototype", "partial"}


def test_each_stage_has_external_pattern_and_local_component() -> None:
    profile = build_default_profile()

    for stage in profile.stages:
        assert stage.external_patterns
        assert stage.local_components
        assert stage.direct_use_steps
        assert stage.gaps
        assert stage.next_actions


def test_profile_renders_actionable_markdown() -> None:
    profile = build_default_profile()
    markdown = profile.to_markdown()

    assert "# RAG Mature Project Adoption Profile" in markdown
    assert "document_parsing_product" in markdown
    assert "retrieval_quality" in markdown
    assert "graphrag" in markdown
    assert "evaluation" in markdown


def test_document_parsing_stage_points_to_intake_entrypoint() -> None:
    profile = build_default_profile()
    stage = profile.stage("document_parsing_product")

    assert "data_pipeline/document_intake.py" in stage.local_components
    assert "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/pipeline.py" in stage.local_components
    assert any("run_document_intake" in step for step in stage.direct_use_steps)
    assert any("/api/process" in step for step in stage.direct_use_steps)
    assert stage.status in {"partial", "ready"}


def test_retrieval_quality_stage_points_to_pipeline_upgrades() -> None:
    profile = build_default_profile()
    stage = profile.stage("retrieval_quality")

    assert "retrieval_engine/hybrid.py" in stage.local_components
    assert any("fusion_mode=\"rrf\"" in step for step in stage.direct_use_steps)
    assert any("metadata filter" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/search" in step and "retrieval_diagnostics" in step for step in stage.direct_use_steps)
    assert any("Retrieval Diagnostics" in step for step in stage.direct_use_steps)
    assert any("/api/search" in step and "HybridRetriever" in step for step in stage.direct_use_steps)
    assert any("query_rewrite" in step and "reranker" in step for step in stage.direct_use_steps)
    assert any("graph_db_path" in step and "graph" in step for step in stage.direct_use_steps)
    assert any("/api/search" in step and "filters" in step for step in stage.direct_use_steps)
    assert any("no_answer_min_score" in step and "/api/search" in step for step in stage.direct_use_steps)
    assert any("source type" in step.lower() and "natural-language" in step.lower() for step in stage.direct_use_steps)
    assert any("filename" in step.lower() and "year" in step.lower() for step in stage.direct_use_steps)
    assert any("author" in step.lower() and "date-range" in step.lower() for step in stage.direct_use_steps)
    assert any("metadata_field_aliases" in step and "meta.source_date" in step for step in stage.direct_use_steps)
    assert any("retrieval_default_policy" in step for step in stage.direct_use_steps)
    assert any("retrieval_policies.json" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/roles/upsert" in step and "role_registry" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/promote" in step and "audit" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/propose" in step and "pending" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/propose" in step and "assigned_to" in step and "due_at" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/approve" in step and "role_registry" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/reject" in step and "role_registry" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/history" in step and "diff" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/notifications" in step and "pending" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/notifications/dispatch" in step and "outbox" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/notifications/dispatch" in step and "webhook" in step.lower() for step in stage.direct_use_steps)
    assert any("pagerduty_event_v2" in step and "webhook_routing_key_env" in step for step in stage.direct_use_steps)
    assert any("opsgenie_alert" in step and "webhook_auth_token_env" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/directory/sync" in step and "SCIM" in step for step in stage.direct_use_steps)
    assert any("active=false" in step and "role_registry" in step for step in stage.direct_use_steps)
    assert any("RAG_POLICY_OIDC_REQUIRED" in step and "JWKS" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/upsert" in step and "jwks_url" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider" in step and "client_secret" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/login-url" in step and "PKCE" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/token" in step and "client_secret_env" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/callback" in step and "state" in step for step in stage.direct_use_steps)
    assert any("retrieval_policy_oidc_states.json" in step and "code_verifier" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/session" in step and "HttpOnly" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/session/refresh" in step and "refresh_token" in step for step in stage.direct_use_steps)
    assert any("RAG_POLICY_SESSION_SECRET_KEYS" in step and "AESGCM" in step for step in stage.direct_use_steps)
    assert any("refresh_token_encrypted" in step and "key rotation" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/sessions" in step and "admin" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/sessions/{session_id}" in step and "revoke" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/sessions/rotate-key" in step and "active" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/sessions/key-status" in step and "rotation_due_reasons" in step for step in stage.direct_use_steps)
    assert any("RAG_POLICY_SESSION_KEY_MAX_AGE_SECONDS" in step and "rotation" in step.lower() for step in stage.direct_use_steps)
    assert any("identity_provider_session_revoke" in step and "audit" in step.lower() for step in stage.direct_use_steps)
    assert any("identity_provider_session_key_rotate" in step and "audit" in step.lower() for step in stage.direct_use_steps)
    assert any("session inventory table" in step.lower() and "secret_storage" in step for step in stage.direct_use_steps)
    assert any("session admin audit" in step.lower() and "identity_provider_session_revoke" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/identity-provider/logout" in step and "cookie" in step.lower() for step in stage.direct_use_steps)
    assert any("sessionStorage" in step and "Authorization: Bearer" in step for step in stage.direct_use_steps)
    assert any("Authorization: Bearer" in step and "approve" in step for step in stage.direct_use_steps)
    assert any("/api/retrieval/policies/rollback" in step and "previous audited" in step.lower() for step in stage.direct_use_steps)
    assert any("Retrieval Policy Review" in step for step in stage.direct_use_steps)
    assert any("notification outbox" in gap.lower() for gap in stage.gaps)
    assert not any("API layer still needs to expose retrieval diagnostics" in gap for gap in stage.gaps)
    assert not any("Chroma-only adapter" in gap for gap in stage.gaps)
    assert not any("GraphRAG retriever participation" in gap for gap in stage.gaps)
    assert not any("Metadata filter extraction from natural-language queries is not automatic yet." in gap for gap in stage.gaps)
    assert not any("return last_diagnostics" in action for action in stage.next_actions)
    assert not any("Route /api/search through HybridRetriever" in action for action in stage.next_actions)
    assert not any("Add GraphRAG retriever participation" in action for action in stage.next_actions)
    assert stage.status in {"partial", "ready"}


def test_graphrag_stage_points_to_lightrag_mode_engine() -> None:
    profile = build_default_profile()
    stage = profile.stage("graphrag")

    assert "rag_orchestrator/lightrag.py" in stage.local_components
    assert "rag_orchestrator/graph_quality.py" in stage.local_components
    assert "rag_orchestrator/triage.py" in stage.local_components
    assert "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py" in stage.local_components
    assert "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_graphrag.py" in stage.local_components
    assert "frontend_app/current_console/index.html" in stage.local_components
    assert any("LightRagQueryEngine" in step for step in stage.direct_use_steps)
    assert any("evaluate_graph_quality" in step for step in stage.direct_use_steps)
    assert any("/api/query" in step and "graph quality gate" in step for step in stage.direct_use_steps)
    assert any("Graph Quality Gate" in step for step in stage.direct_use_steps)
    assert any("allow_unsafe_graph" in step for step in stage.direct_use_steps)
    assert any('mode="mix"' in step for step in stage.direct_use_steps)
    assert any("sentence_evidence" in step for step in stage.direct_use_steps)
    assert any("source_evidence" in step for step in stage.direct_use_steps)
    assert any("graph_community_source" in step for step in stage.direct_use_steps)
    assert any("/api/graphrag/triage" in step for step in stage.direct_use_steps)
    assert any("/api/graphrag/triage/export" in step for step in stage.direct_use_steps)
    assert any("/api/graphrag/triage/analytics" in step for step in stage.direct_use_steps)
    assert any("/api/graphrag/triage/{triage_id}/promote" in step for step in stage.direct_use_steps)
    assert any("LightRagDiagnostics" in step and "/api/query" in step for step in stage.direct_use_steps)
    assert any("console answer panel" in step and "LightRAG Diagnostics" in step for step in stage.direct_use_steps)
    assert any("GraphRAG Triage History" in step for step in stage.direct_use_steps)
    assert any("reviewer dashboard" in step for step in stage.direct_use_steps)
    assert any("source evidence coverage" in step for step in stage.direct_use_steps)
    assert any("promoted_case_count" in step for step in stage.direct_use_steps)
    assert any("failure trend" in step for step in stage.direct_use_steps)
    assert any("route-level drilldown" in step for step in stage.direct_use_steps)
    assert any("source_evidence" in gap for gap in stage.gaps)
    assert not any("reviewer dashboard" in action for action in stage.next_actions)
    assert not any("failure trend" in action for action in stage.next_actions)
    assert not any("route-level drilldown" in action for action in stage.next_actions)
    assert not any("exposed in the answer citation UI" in gap for gap in stage.gaps)
    assert not any("dedicated historical triage view" in gap for gap in stage.gaps)
    assert not any("failure trend visualization" in gap for gap in stage.gaps)
    assert not any("still need filters, export" in gap for gap in stage.gaps)
    assert not any("LightRagDiagnostics" in action for action in stage.next_actions)
    assert stage.status in {"partial", "ready"}


def test_evaluation_stage_points_to_rag_evaluation_harness() -> None:
    profile = build_default_profile()
    stage = profile.stage("evaluation")

    assert "evaluation/harness.py" in stage.local_components
    assert "evaluation/triage_regression.py" in stage.local_components
    assert "scripts/run_graphrag_triage_regression.py" in stage.local_components
    assert any("RAGEvaluationHarness" in step for step in stage.direct_use_steps)
    assert any("LocalChromaRegressionRag" in step for step in stage.direct_use_steps)
    assert any("run_graphrag_triage_regression.py" in step for step in stage.direct_use_steps)
    assert any("quality gates" in step.lower() for step in stage.direct_use_steps)
    assert stage.status in {"partial", "ready"}


def test_operating_steps_stage_points_to_smoke_command() -> None:
    profile = build_default_profile()
    stage = profile.stage("operating_steps")

    assert "scripts/run_rag_smoke_evaluation.py" in stage.local_components
    assert any("run_rag_smoke_evaluation.py" in step for step in stage.direct_use_steps)
    assert any("ingest-search-evaluation" in step.lower() for step in stage.direct_use_steps)
    assert any("/api/query" in step for step in stage.direct_use_steps)
    assert any("global answer" in step.lower() for step in stage.direct_use_steps)
    assert any("rag-smoke-job" in step for step in stage.direct_use_steps)


def test_adoption_guide_exists_and_mentions_source_projects() -> None:
    guide = Path("docs/RAG成熟项目最佳实践接入.md")

    assert guide.exists()
    text = guide.read_text(encoding="utf-8")
    for name in ("RAGFlow", "Dify", "Haystack", "LlamaIndex", "LightRAG", "RAGAS"):
        assert name in text
    assert "run_document_intake" in text
    assert "opencv-python" in text
    assert "parser_backend" in text
    assert "PPTX" in text
    assert "Spreadsheet" in text
    assert "Image" in text
    assert "RAGEvaluationHarness" in text
    assert "run_rag_smoke_evaluation.py" in text
    assert "rag-smoke-job" in text
    assert "graphrag_global=pass" in text
    assert "evaluate_graph_quality" in text
    assert "Graph Quality Gate" in text
    assert "sentence_evidence" in text
    assert "source_evidence" in text
    assert "graph_community_source" in text
    assert "/api/graphrag/triage" in text
    assert "/api/graphrag/triage/export" in text
    assert "/api/graphrag/triage/analytics" in text
    assert "/api/graphrag/triage/{triage_id}/promote" in text
    assert "graphrag_triage_regression" in text
    assert "LocalChromaRegressionRag" in text
    assert "--persist-dir" in text
    assert "run_graphrag_triage_regression.py" in text
    assert "GraphRAG Triage History" in text
    assert "reviewer dashboard" in text
    assert "source evidence coverage" in text
    assert "promoted_case_count" in text
    assert "kgTriageAnalytics" in text
    assert "failure trend" in text
    assert "route-level drilldown" in text
    assert "failure_trend" in text
    assert "route_drilldown" in text
    assert "allow_unsafe_graph" in text
    assert 'fusion_mode="rrf"' in text
    assert "retrieval_diagnostics" in text
    assert "Retrieval Diagnostics" in text
    assert "rewritten_queries" in text
    assert "reranker_error" in text
    assert "no_answer_reason" in text
    assert "/api/retrieval/policies/notifications" in text
    assert "/api/retrieval/policies/notifications/dispatch" in text
    assert "/api/retrieval/policies/notification-recipients" in text
    assert "/api/retrieval/policies/notification-recipients/upsert" in text
    assert "/api/retrieval/policies/directory/sync" in text
    assert "SCIM" in text
    assert "role_group_mappings" in text
    assert "active=false" in text
    assert "RAG_POLICY_OIDC_REQUIRED" in text
    assert "RAG_POLICY_OIDC_JWKS_URL" in text
    assert "/api/retrieval/policies/identity-provider/upsert" in text
    assert "/api/retrieval/policies/identity-provider" in text
    assert "jwks_url" in text
    assert "client_secret" in text
    assert "identity_provider" in text
    assert "/api/retrieval/policies/identity-provider/login-url" in text
    assert "/api/retrieval/policies/identity-provider/token" in text
    assert "/api/retrieval/policies/identity-provider/callback" in text
    assert "/api/retrieval/policies/identity-provider/session" in text
    assert "/api/retrieval/policies/identity-provider/session/refresh" in text
    assert "/api/retrieval/policies/identity-provider/sessions" in text
    assert "/api/retrieval/policies/identity-provider/sessions/{session_id}" in text
    assert "/api/retrieval/policies/identity-provider/sessions/rotate-key" in text
    assert "/api/retrieval/policies/identity-provider/sessions/key-status" in text
    assert "/api/retrieval/policies/identity-provider/logout" in text
    assert "refresh_token" in text
    assert "refresh_token_encrypted" in text
    assert "RAG_POLICY_SESSION_SECRET_KEYS" in text
    assert "AESGCM" in text
    assert "identity_provider_session_key_rotate" in text
    assert "identity_provider_session_revoke" in text
    assert "rotation_due_reasons" in text
    assert "RAG_POLICY_SESSION_KEY_MAX_AGE_SECONDS" in text
    assert "OIDC session inventory" in text
    assert "Session admin audit" in text
    assert "secret_storage" in text
    assert "rag_policy_oidc_state" in text
    assert "retrieval_policy_oidc_states.json" in text
    assert "HttpOnly" in text
    assert "PKCE" in text
    assert "client_secret_env" in text
    assert "sessionStorage" in text
    assert "Use Token" in text
    assert "Authorization: Bearer" in text
    assert "PyJWT" in text
    assert "notification_recipient_registry" in text
    assert "recipient_source" in text
    assert "outbox_file" in text
    assert "delivery_mode=\"webhook\"" in text
    assert "webhook_url" in text
    assert "webhook_template" in text
    assert "lark_text" in text
    assert "dingtalk_text" in text
    assert "wecom_text" in text
    assert "pagerduty_event_v2" in text
    assert "webhook_routing_key_env" in text
    assert "opsgenie_alert" in text
    assert "webhook_auth_header_name" in text
    assert "webhook_auth_token_env" in text
    assert "webhook_auth_scheme" in text
    assert "webhook_signing_secret_env" in text
    assert "hmac-sha256" in text
    assert "delivery_mode=\"smtp\"" in text
    assert "smtp_host" in text
    assert "smtp_username_env" in text
    assert "smtp_password_env" in text
    assert "attempted_count" in text
    assert "failed_count" in text
    assert "failed delivery" in text
    assert "assigned_to" in text
    assert "due_at" in text
    assert "notification outbox" in text
    assert "LightRagQueryEngine" in text
    assert "LightRagDiagnostics" in text
    assert "lightrag_diagnostics" in text
    assert "LightRAG Diagnostics" in text
    assert "控制台回答面板" in text


def test_tsinghua_gas_turbine_top_tier_rubric_exists() -> None:
    guide = Path("docs/清华燃气轮机知识库顶尖对标与验收标准.md")

    assert guide.exists()
    text = guide.read_text(encoding="utf-8")
    assert "清华" in text
    assert "燃气轮机" in text
    assert "开源头部不等于行业顶尖" in text
    for name in (
        "RAGFlow",
        "Dify",
        "Microsoft GraphRAG",
        "Glean",
        "Hebbia",
        "Palantir AIP",
        "Azure AI Search",
        "Gemini Enterprise Agent Platform",
        "Amazon Bedrock Knowledge Bases",
        "Vectara",
    ):
        assert name in text
    for requirement in (
        "文档解析",
        "权限与审计",
        "工程可靠性",
        "检索质量",
        "GraphRAG",
        "评测门禁",
        "领域知识",
        "验收指标",
    ):
        assert requirement in text
