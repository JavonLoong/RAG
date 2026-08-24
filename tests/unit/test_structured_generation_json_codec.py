from __future__ import annotations

import json

import pytest

from core_domain.structured_generation import CriticVerdict, SemanticSupport, StructuredGenerationError
from core_domain.structured_output import ClaimState
from structured_generation_infrastructure.json_codec import (
    StrictCandidateBatchCodec,
    StrictCriticReportCodec,
)

VALID_BATCH_OBJECT = {
    "template_id": "maintenance-checklist",
    "template_version": "1.0.0",
    "template_hash": "a" * 64,
    "evidence_pack_id": "pack-1",
    "candidates": [
        {
            "candidate_id": "candidate-1",
            "payload": {"failure_mode": "pressure loss"},
            "claims": [
                {
                    "target": "/failure_mode",
                    "state": "known",
                    "evidence_ids": ["ev-1"],
                }
            ],
        }
    ],
}
VALID_BATCH_JSON = json.dumps(VALID_BATCH_OBJECT)

VALID_CRITIC_OBJECT = {
    "verdict": "accept",
    "findings": [
        {
            "candidate_id": "candidate-1",
            "target": "/failure_mode",
            "support": "supported",
            "code": "EVIDENCE_SUPPORTS_CLAIM",
            "evidence_ids": ["ev-1"],
            "explanation": "The cited quote directly states the failure mode.",
        }
    ],
    "summary": "All evidence-bearing claims are supported.",
}
VALID_CRITIC_JSON = json.dumps(VALID_CRITIC_OBJECT)


def _invalid_batch(mutation: str, secret: str) -> str:
    value = json.loads(VALID_BATCH_JSON)
    if mutation == "unknown_root":
        value["raw_prompt"] = secret
    elif mutation == "unknown_candidate":
        value["candidates"][0]["provider_payload"] = secret
    elif mutation == "unknown_claim":
        value["candidates"][0]["claims"][0]["reasoning_content"] = secret
    elif mutation == "bad_hash":
        value["template_hash"] = secret
    elif mutation == "duplicate_claim":
        value["candidates"][0]["claims"].append(value["candidates"][0]["claims"][0])
    elif mutation == "trailing_json":
        return json.dumps(value) + json.dumps({"secret": secret})
    else:  # pragma: no cover - keeps the test helper honest
        raise AssertionError(mutation)
    return json.dumps(value)


def test_batch_codec_decodes_one_exact_object() -> None:
    batch = StrictCandidateBatchCodec().decode_batch(VALID_BATCH_JSON)

    assert batch.template_id == "maintenance-checklist"
    assert batch.candidates[0].payload == {"failure_mode": "pressure loss"}
    assert batch.candidates[0].claims[0].target == "/failure_mode"
    assert batch.candidates[0].claims[0].state is ClaimState.KNOWN
    assert batch.candidates[0].claims[0].evidence_ids == ("ev-1",)


@pytest.mark.parametrize(
    "mutation",
    ["unknown_root", "unknown_candidate", "unknown_claim", "bad_hash", "duplicate_claim", "trailing_json"],
)
def test_batch_codec_fails_closed_without_echoing_content(mutation: str) -> None:
    sensitive_marker = "sk-private-codec-marker"

    with pytest.raises(StructuredGenerationError) as caught:
        StrictCandidateBatchCodec().decode_batch(_invalid_batch(mutation, sensitive_marker))

    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert str(caught.value) == "Model output is not a valid structured-generation object."
    assert sensitive_marker not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "value",
    [
        [],
        {**VALID_BATCH_OBJECT, "candidates": {}},
        {
            **VALID_BATCH_OBJECT,
            "candidates": [
                {
                    **VALID_BATCH_OBJECT["candidates"][0],
                    "claims": [
                        {
                            **VALID_BATCH_OBJECT["candidates"][0]["claims"][0],
                            "evidence_ids": "ev-1",
                        }
                    ],
                }
            ],
        },
        {
            **VALID_BATCH_OBJECT,
            "candidates": [
                {
                    **VALID_BATCH_OBJECT["candidates"][0],
                    "candidate_id": "x" * 257,
                }
            ],
        },
    ],
)
def test_batch_codec_rejects_wrong_json_shapes_and_overlong_identity(value: object) -> None:
    with pytest.raises(StructuredGenerationError, match="valid structured-generation object"):
        StrictCandidateBatchCodec().decode_batch(json.dumps(value))


def test_batch_codec_checks_character_limit_before_json_parse() -> None:
    sensitive_marker = "sk-limit-marker"
    codec = StrictCandidateBatchCodec(max_response_chars=16)

    with pytest.raises(StructuredGenerationError) as caught:
        codec.decode_batch("{" + sensitive_marker * 100)

    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert sensitive_marker not in str(caught.value)


def test_critic_codec_decodes_one_exact_object() -> None:
    report = StrictCriticReportCodec().decode_critic(VALID_CRITIC_JSON)

    assert report.verdict is CriticVerdict.ACCEPT
    assert report.findings[0].support is SemanticSupport.SUPPORTED
    assert report.findings[0].evidence_ids == ("ev-1",)


@pytest.mark.parametrize(
    "mutation",
    ["unknown_root", "unknown_finding", "invalid_support", "non_array_evidence", "overlong_summary"],
)
def test_critic_codec_rejects_unknown_fields_and_invalid_values(mutation: str) -> None:
    sensitive_marker = "sk-private-critic-marker"
    value = json.loads(VALID_CRITIC_JSON)
    if mutation == "unknown_root":
        value["raw"] = sensitive_marker
    elif mutation == "unknown_finding":
        value["findings"][0]["reasoning_content"] = sensitive_marker
    elif mutation == "invalid_support":
        value["findings"][0]["support"] = sensitive_marker
    elif mutation == "non_array_evidence":
        value["findings"][0]["evidence_ids"] = sensitive_marker
    elif mutation == "overlong_summary":
        value["summary"] = sensitive_marker * 100

    with pytest.raises(StructuredGenerationError) as caught:
        StrictCriticReportCodec().decode_critic(json.dumps(value))

    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert sensitive_marker not in str(caught.value)


def test_critic_codec_rejects_trailing_json_and_duplicate_findings() -> None:
    duplicate = json.loads(VALID_CRITIC_JSON)
    duplicate["findings"].append(duplicate["findings"][0])

    for content in (VALID_CRITIC_JSON + "{}", json.dumps(duplicate)):
        with pytest.raises(StructuredGenerationError) as caught:
            StrictCriticReportCodec().decode_critic(content)
        assert caught.value.code == "MODEL_OUTPUT_INVALID"
