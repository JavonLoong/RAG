from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.fmea_review_contracts import ReviewDecisionBody  # noqa: E402
from fmea_review_fixtures import valid_accept_body  # noqa: E402


def test_request_models_forbid_actor_status_model_and_unknown_fields() -> None:
    for forbidden in ("actor_id", "actor_type", "roles", "review_status", "publication_status", "model"):
        with pytest.raises(ValidationError):
            ReviewDecisionBody.model_validate({**valid_accept_body(), forbidden: "attacker"})
