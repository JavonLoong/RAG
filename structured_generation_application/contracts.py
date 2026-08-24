"""Application contracts binding one template to one stable EvidencePack."""

from __future__ import annotations

from dataclasses import dataclass, field

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import GenerationBudget, StructuredGenerationError
from core_domain.structured_output import CompiledTemplate

_APPROVED_MODELS = frozenset({"deepseek-v4-flash", "deepseek-v4-pro"})


@dataclass(frozen=True, slots=True)
class GenerationRunRequest:
    run_id: str
    task: str
    template: CompiledTemplate
    evidence_pack: EvidencePack
    generator_model: str = "deepseek-v4-flash"
    critic_model: str = "deepseek-v4-pro"
    repair_model: str = "deepseek-v4-pro"
    budget: GenerationBudget = field(default_factory=GenerationBudget)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip() or len(self.run_id) > 256:
            raise StructuredGenerationError(
                "GENERATION_REQUEST_INVALID", "Structured-generation run ID is invalid."
            )
        if not isinstance(self.task, str) or not self.task.strip() or len(self.task) > 4000:
            raise StructuredGenerationError(
                "GENERATION_REQUEST_INVALID", "Structured-generation task is invalid."
            )
        if not isinstance(self.template, CompiledTemplate) or not isinstance(self.evidence_pack, EvidencePack):
            raise StructuredGenerationError(
                "GENERATION_REQUEST_INVALID", "Structured-generation inputs are invalid."
            )
        if (
            self.generator_model not in _APPROVED_MODELS
            or self.critic_model not in _APPROVED_MODELS
            or self.repair_model not in _APPROVED_MODELS
            or self.generator_model != "deepseek-v4-flash"
            or self.critic_model != "deepseek-v4-pro"
            or self.repair_model != "deepseek-v4-pro"
        ):
            raise StructuredGenerationError(
                "MODEL_CONFIGURATION_INVALID", "Structured-generation approved model configuration is invalid."
            )
        if not isinstance(self.budget, GenerationBudget):
            raise StructuredGenerationError(
                "GENERATION_REQUEST_INVALID", "Structured-generation budget is invalid."
            )


__all__ = ["GenerationRunRequest"]
