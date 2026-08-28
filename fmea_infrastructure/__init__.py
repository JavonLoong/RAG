"""Infrastructure adapters for the FMEA application boundary."""

from .composition import (
    PropagationRuntime,
    ReviewRuntime,
    build_workspace_propagation_runtime,
    build_workspace_review_runtime,
    new_prefixed_uuid,
    utc_now,
)
from .evidence_provider import QueryPort, QueryServiceEvidenceProvider
from .local_auth import LocalReviewAuthProvider
from .profile_loader import load_fmea_template_profile
from .propagation_generator import EnvironmentPropagationSuggestionGenerator
from .propagation_repository_sqlite import SqlitePropagationRepository
from .repository_sqlite import SqliteFmeaRepository
from .review_executor import ThreadPoolReviewRunExecutor
from .review_generator import EnvironmentReviewSuggestionGenerator

__all__ = [
    "EnvironmentPropagationSuggestionGenerator",
    "EnvironmentReviewSuggestionGenerator",
    "LocalReviewAuthProvider",
    "PropagationRuntime",
    "QueryPort",
    "QueryServiceEvidenceProvider",
    "ReviewRuntime",
    "SqliteFmeaRepository",
    "SqlitePropagationRepository",
    "ThreadPoolReviewRunExecutor",
    "build_workspace_propagation_runtime",
    "build_workspace_review_runtime",
    "load_fmea_template_profile",
    "new_prefixed_uuid",
    "utc_now",
]
