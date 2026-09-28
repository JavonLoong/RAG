# -*- coding: utf-8 -*-
"""Copy the M2-M5 implementation into this skill's code/ folder."""

from __future__ import annotations

import shutil
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
DEST = SKILL_ROOT / "code"

FILES = (
    "core_domain/__init__.py",
    "core_domain/delivery.py",
    "core_domain/fmea/__init__.py",
    "core_domain/fmea/contracts.py",
    "core_domain/fmea/entities.py",
    "core_domain/fmea/governance.py",
    "core_domain/fmea/policies.py",
    "core_domain/fmea/states.py",
    "core_domain/fmea/value_objects.py",
    "core_domain/fmea/errors.py",
    "core_domain/fmea/codec.py",
    "data_pipeline/document_intake.py",
    "data_pipeline/external_document_parsers.py",
    "data_pipeline/m2_annotation.py",
    "storage_layer/governance_store.py",
    "storage_layer/graph_store.py",
    "storage_layer/governed_index.py",
    "storage_layer/project_workspace.py",
    "rag_orchestrator/fmea.py",
    "rag_orchestrator/fmea_templates.py",
    "rag_orchestrator/graphrag_qa.py",
    "rag_orchestrator/delivery_remediation.py",
    "rag_orchestrator/governed_graphrag.py",
    "rag_orchestrator/governed_community_summary.py",
    "rag_orchestrator/m2_delivery.py",
    "kg_pipeline/governed_extraction.py",
    "kg_pipeline/llm_extraction/__init__.py",
    "kg_pipeline/llm_extraction/pipeline.py",
    "api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_delivery.py",
    "configs/fmea/gas_turbine_minimum_v1.yaml",
    "configs/fmea/electric_motor_minimum_v1.yaml",
    "tests/unit/test_governed_delivery_workflow.py",
    "tests/unit/test_delivery_api.py",
)


def pack() -> list[Path]:
    copied: list[Path] = []
    for rel in FILES:
        src = REPO_ROOT / rel
        if not src.is_file():
            raise FileNotFoundError(src)
        dest = DEST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(dest)
    return copied


if __name__ == "__main__":
    paths = pack()
    print(DEST)
    print("files", len(paths))
