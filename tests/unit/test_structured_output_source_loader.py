from __future__ import annotations

from pathlib import Path

import pytest

from core_domain.structured_output import StructuredOutputError, TemplateLimits
from structured_output_infrastructure import load_template_source


def test_equivalent_json_and_yaml_sources_load_as_equal_objects(tmp_path: Path) -> None:
    json_source = tmp_path / "template.json"
    yaml_source = tmp_path / "template.yaml"
    json_source.write_text('{"name":"check","items":[1,true]}', encoding="utf-8")
    yaml_source.write_text("name: check\nitems:\n  - 1\n  - true\n", encoding="utf-8")

    assert load_template_source(json_source, TemplateLimits()) == load_template_source(
        yaml_source,
        TemplateLimits(),
    )


def test_yaml_alias_and_anchor_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.yaml"
    source.write_text("base: &base {type: string}\ncopy: *base\n", encoding="utf-8")

    with pytest.raises(StructuredOutputError) as error:
        load_template_source(source, TemplateLimits())

    assert error.value.code == "TEMPLATE_SOURCE_INVALID"


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (".yaml", "value: !!python/object:builtins.object {}\n"),
        (".yaml", "---\na: 1\n---\nb: 2\n"),
        (".yaml", "a scalar\n"),
        (".json", "[1, 2]\n"),
        (".txt", '{"a": 1}'),
    ],
)
def test_unsafe_or_unsupported_sources_fail_with_stable_error(
    tmp_path: Path,
    suffix: str,
    content: str,
) -> None:
    source = tmp_path / f"unsafe{suffix}"
    source.write_text(content, encoding="utf-8")

    with pytest.raises(StructuredOutputError) as raised:
        load_template_source(source, TemplateLimits())

    assert raised.value.code == "TEMPLATE_SOURCE_INVALID"
    assert content.strip() not in str(raised.value)


def test_source_size_is_checked_before_parsing(tmp_path: Path) -> None:
    source = tmp_path / "large.json"
    source.write_bytes(b'{"secret":"do-not-leak"}')

    with pytest.raises(StructuredOutputError) as raised:
        load_template_source(source, TemplateLimits(max_source_bytes=8))

    assert raised.value.code == "TEMPLATE_LIMIT_EXCEEDED"
    assert "do-not-leak" not in str(raised.value)


def test_malformed_utf8_is_rejected_without_content_leak(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_bytes(b'{"secret":"\xff"}')

    with pytest.raises(StructuredOutputError) as raised:
        load_template_source(source, TemplateLimits())

    assert raised.value.code == "TEMPLATE_SOURCE_INVALID"
    assert "secret" not in str(raised.value)


def test_yaml_constructs_that_are_not_json_are_source_errors(tmp_path: Path) -> None:
    source = tmp_path / "non-json.yaml"
    source.write_text("1: value\n", encoding="utf-8")

    with pytest.raises(StructuredOutputError) as raised:
        load_template_source(source, TemplateLimits())

    assert raised.value.code == "TEMPLATE_SOURCE_INVALID"
