from __future__ import annotations

import json
from pathlib import Path

import pytest

from core_domain.fmea.errors import FmeaDomainError
from fmea_infrastructure.profile_loader import load_fmea_template_profile
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

ROOT = Path(__file__).parents[2]
FULL_FMEA_TEMPLATE = ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
PROFILE = ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"


def _compiler() -> TemplateCompiler:
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    )


def test_full_fmea_template_compiles_and_requires_no_risk_or_workflow_fields() -> None:
    template = _compiler().compile_path(FULL_FMEA_TEMPLATE)

    assert template.metadata.template_id == "fuel-combustion-fmea-full"
    assert set(template.output_schema["required"]) == {
        "item",
        "function",
        "failure_mode",
        "causes",
        "mechanisms",
        "effects",
        "symptoms",
        "controls",
        "barriers",
        "actions",
    }
    serialized = template.canonical_json.lower()
    for forbidden in ("severity", "occurrence", "detection", "rpn", "propagation", "publication"):
        assert forbidden not in serialized


def test_profile_loader_accepts_only_literal_complete_field_map() -> None:
    profile = load_fmea_template_profile(PROFILE)

    assert profile.profile_id == "fuel-combustion-fmea-row"
    assert profile.fields[0] == ("item_id", "/item")
    assert profile.fields[-1] == ("actions", "/actions")
    assert len(profile.fields) == 10


@pytest.mark.parametrize(
    "mutation",
    ["root_extra", "field_extra", "bad_pointer", "bad_version", "missing_field"],
)
def test_profile_loader_rejects_unknown_or_executable_shapes(
    tmp_path: Path,
    mutation: str,
) -> None:
    value = json.loads(PROFILE.read_text(encoding="utf-8"))
    if mutation == "root_extra":
        value["expression"] = "$.item"
    elif mutation == "field_extra":
        value["fields"]["row_id"] = "/row_id"
    elif mutation == "bad_pointer":
        value["fields"]["item_id"] = "$.item"
    elif mutation == "bad_version":
        value["version"] = "latest"
    elif mutation == "missing_field":
        del value["fields"]["actions"]
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(FmeaDomainError, match="profile"):
        load_fmea_template_profile(path)
