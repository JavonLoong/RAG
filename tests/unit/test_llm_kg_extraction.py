import json

import pytest

from kg_pipeline.llm_extraction.pipeline import MissingLLMClientError, read_chunks, run_extraction


class FakeLLM:
    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def write_schema(path):
    path.write_text(
        json.dumps(
            {
                "entity_types": {
                    "Equipment": "domain equipment",
                    "Component": "equipment component",
                },
                "relation_types": {
                    "HAS_COMPONENT": "equipment contains a component",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_chunks_jsonl(path):
    path.write_text(
        json.dumps(
            {
                "id": "chunk-1",
                "text": "燃气轮机包含压气机。",
                "source_file": "book.pdf",
                "page_num": 3,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_valid_llm_json_writes_schema_bound_candidate_with_evidence(tmp_path):
    schema_path = tmp_path / "schema.json"
    chunks_path = tmp_path / "chunks.jsonl"
    output_dir = tmp_path / "out"
    write_schema(schema_path)
    write_chunks_jsonl(chunks_path)
    fake_llm = FakeLLM(
        json.dumps(
            {
                "triples": [
                    {
                        "subject": "燃气轮机",
                        "relation": "HAS_COMPONENT",
                        "object": "压气机",
                        "evidence": "燃气轮机包含压气机。",
                        "source": "book.pdf",
                        "page": 3,
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    result = run_extraction(chunks_path, schema_path, output_dir, llm_client=fake_llm)

    assert result["valid_count"] == 1
    assert result["invalid_count"] == 0
    assert "HAS_COMPONENT" in fake_llm.prompts[0]
    assert "燃气轮机包含压气机。" in fake_llm.prompts[0]

    candidates = json.loads((output_dir / "triples_llm_candidates.json").read_text(encoding="utf-8"))
    assert candidates == [
        {
            "subject": "燃气轮机",
            "relation": "HAS_COMPONENT",
            "object": "压气机",
            "evidence": "燃气轮机包含压气机。",
            "source": "book.pdf",
            "page": 3,
            "chunk_id": "chunk-1",
        }
    ]

    report = json.loads((output_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert report["valid_count"] == 1
    assert report["parse_error_count"] == 0


def test_bad_llm_json_is_reported_without_candidates(tmp_path):
    schema_path = tmp_path / "schema.json"
    chunks_path = tmp_path / "chunks.jsonl"
    output_dir = tmp_path / "out"
    write_schema(schema_path)
    write_chunks_jsonl(chunks_path)

    result = run_extraction(chunks_path, schema_path, output_dir, llm_client=FakeLLM("not json"))

    assert result["valid_count"] == 0
    assert result["parse_error_count"] == 1
    assert json.loads((output_dir / "triples_llm_candidates.json").read_text(encoding="utf-8")) == []
    report = json.loads((output_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert report["parse_errors"][0]["chunk_id"] == "chunk-1"


def test_relation_outside_schema_is_rejected(tmp_path):
    schema_path = tmp_path / "schema.json"
    chunks_path = tmp_path / "chunks.jsonl"
    output_dir = tmp_path / "out"
    write_schema(schema_path)
    write_chunks_jsonl(chunks_path)
    fake_llm = FakeLLM(
        json.dumps(
            {
                "triples": [
                    {
                        "subject": "燃气轮机",
                        "relation": "INVENTED_RELATION",
                        "object": "压气机",
                        "evidence": "燃气轮机包含压气机。",
                        "source": "book.pdf",
                        "page": 3,
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    result = run_extraction(chunks_path, schema_path, output_dir, llm_client=fake_llm)

    assert result["valid_count"] == 0
    assert result["invalid_count"] == 1
    report = json.loads((output_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert "relation" in report["invalid_triples"][0]["errors"][0]


def test_missing_evidence_is_rejected(tmp_path):
    schema_path = tmp_path / "schema.json"
    chunks_path = tmp_path / "chunks.jsonl"
    output_dir = tmp_path / "out"
    write_schema(schema_path)
    write_chunks_jsonl(chunks_path)
    fake_llm = FakeLLM(
        json.dumps(
            {
                "triples": [
                    {
                        "subject": "燃气轮机",
                        "relation": "HAS_COMPONENT",
                        "object": "压气机",
                        "evidence": "",
                        "source": "book.pdf",
                        "page": 3,
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    result = run_extraction(chunks_path, schema_path, output_dir, llm_client=fake_llm)

    assert result["valid_count"] == 0
    assert result["invalid_count"] == 1
    report = json.loads((output_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert "evidence" in report["invalid_triples"][0]["errors"]


def test_missing_llm_client_fails_clearly(tmp_path):
    schema_path = tmp_path / "schema.json"
    chunks_path = tmp_path / "chunks.jsonl"
    write_schema(schema_path)
    write_chunks_jsonl(chunks_path)

    with pytest.raises(MissingLLMClientError, match="LLM client"):
        run_extraction(chunks_path, schema_path, tmp_path / "out", llm_client=None)


def test_plain_text_input_is_chunked_with_file_metadata(tmp_path):
    input_path = tmp_path / "sample.txt"
    input_path.write_text("第一段。\n\n第二段。", encoding="utf-8")

    chunks = read_chunks(input_path)

    assert [chunk.text for chunk in chunks] == ["第一段。", "第二段。"]
    assert {chunk.source for chunk in chunks} == {"sample.txt"}
    assert {chunk.page for chunk in chunks} == {1}
