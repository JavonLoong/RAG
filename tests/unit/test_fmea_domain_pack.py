from __future__ import annotations

from types import SimpleNamespace

import pytest

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.entities import FieldValue, validate_extension_values
from core_domain.fmea.errors import FmeaDomainError


def _manifest(**overrides: object) -> DomainPackManifest:
    values: dict[str, object] = {
        "pack_id": "fuel-combustion",
        "version": "1.0.0",
        "content_hash": "a" * 64,
        "compatible_schema_ids": ("graphrag.fmea.v1",),
        "analysis_types": ("design_fmea",),
        "template_identities": (("fuel-fmea", "1.0.0"),),
        "scoring_rule_identities": (("fuel-sod-rpn", "1.0.0"),),
        "propagation_rule_identities": (),
        "extension_fields": (),
    }
    values.update(overrides)
    return DomainPackManifest(**values)


def test_domain_pack_rejects_duplicate_template_identity() -> None:
    with pytest.raises(FmeaDomainError, match="duplicate template identity"):
        _manifest(template_identities=(("fuel-fmea", "1.0.0"), ("fuel-fmea", "1.0.0")))


def test_domain_pack_has_compatibility_preserving_kernel_default() -> None:
    manifest = _manifest()
    assert manifest.kernel_compatibility_range == ">=1.0.0,<2.0.0"


def test_domain_pack_rejects_invalid_hash_and_version() -> None:
    with pytest.raises(FmeaDomainError, match="content_hash"):
        _manifest(content_hash="A" * 64)
    with pytest.raises(FmeaDomainError, match="semantic version"):
        _manifest(version="1")


def test_extension_values_use_structural_template_contract() -> None:
    row = SimpleNamespace(
        extension_values=(FieldValue("gas_turbine.fuel.wobbe_index", "decimal", "48.2"),),
    )
    template = SimpleNamespace(extension_fields={"gas_turbine.fuel.wobbe_index": "decimal"})
    assert validate_extension_values(row, template) is None

    with pytest.raises(FmeaDomainError, match="extension field"):
        validate_extension_values(
            SimpleNamespace(
                extension_values=(FieldValue("gas_turbine.fuel.wobbe_index", "integer", "48"),),
            ),
            template,
        )
