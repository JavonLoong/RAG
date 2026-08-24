"""Public structured-generation application API."""

from .contracts import GenerationRunRequest
from .critic_validation import validate_critic_report
from .pipeline import StructuredGenerationPipeline
from .ports import CandidateBatchCodec, CriticReportCodec, StructuredModelGateway
from .prompts import PromptBundle, build_critic_prompt, build_generation_prompt, build_repair_prompt
from .services import StructuredGenerationService

__all__ = [
    "CandidateBatchCodec",
    "CriticReportCodec",
    "GenerationRunRequest",
    "PromptBundle",
    "StructuredGenerationPipeline",
    "StructuredGenerationService",
    "StructuredModelGateway",
    "build_critic_prompt",
    "build_generation_prompt",
    "build_repair_prompt",
    "validate_critic_report",
]
