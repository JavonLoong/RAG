from __future__ import annotations

# ruff: noqa: TRY003, S106
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from data_pipeline.baidu_ocr import (
    BaiduOCRClient,
    BaiduOCRConfig,
    BaiduOCRResponseError,
    prepare_image_for_baidu,
)
from data_pipeline.rapidocr_provider import RapidOCRProvider, reorder_two_column_blocks
from evaluation.ocr_benchmark import compare_ocr_texts, run_ocr_benchmark
from scripts.generate_ocr_benchmark_demo import generate_demo


def _png_bytes(width: int = 400, height: int = 120) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def _write_sample_files(tmp_path: Path, *, external_allowed: bool, gold: str, local: str) -> Path:
    (tmp_path / "page.png").write_bytes(_png_bytes())
    (tmp_path / "local.json").write_text(
        json.dumps({"page": 1, "text": local, "confidence": 0.72}, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest = {
        "dataset_name": "test-dataset",
        "samples": [
            {
                "sample_id": "sample-001",
                "source_path": "page.png",
                "page": 1,
                "category": "body_text",
                "external_allowed": external_allowed,
                "local_result_path": "local.json",
                "gold_text": gold,
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def test_compare_ocr_texts_uses_gold_instead_of_assuming_cloud_is_better() -> None:
    metrics = compare_ocr_texts(
        "燃气轮机过滤器者塞123",
        "燃气轮机过滤器堵塞123",
        "燃气轮机过滤器堵塞123",
    )
    assert metrics["winner"] == "cloud"
    assert metrics["cloud_cer"] == 0.0
    assert metrics["local_cer"] > 0
    assert metrics["numeric_token_overlap"] == 1.0


def test_cloud_upload_is_blocked_without_explicit_external_permission(tmp_path: Path) -> None:
    manifest = _write_sample_files(
        tmp_path,
        external_allowed=False,
        gold="燃气轮机过滤器堵塞",
        local="燃气轮机过滤器堵塞",
    )

    def forbidden_provider(_image: bytes, _page: int, _source: str) -> dict[str, Any]:
        raise AssertionError("provider must not be called for an internal sample")

    report = run_ocr_benchmark(
        manifest,
        tmp_path / "output",
        include_cloud=True,
        cloud_provider=forbidden_provider,
    )
    assert report["summary"]["cloud_call_count"] == 0
    assert report["summary"]["cloud_blocked_by_policy"] == 1
    assert report["samples"][0]["cloud"]["status"] == "blocked_by_policy"


def test_benchmark_reports_cloud_improvement_and_estimated_cost(tmp_path: Path) -> None:
    gold = "燃气轮机过滤器堵塞可能由油液污染导致"
    manifest = _write_sample_files(
        tmp_path,
        external_allowed=True,
        gold=gold,
        local="燃气轮机过滤器者塞可能由油液污染导致",
    )

    def cloud_provider(_image: bytes, page: int, source: str) -> dict[str, Any]:
        return {
            "page": page,
            "source_name": source,
            "text": gold,
            "confidence": 0.98,
            "provider": "baidu",
        }

    output_dir = tmp_path / "output"
    report = run_ocr_benchmark(
        manifest,
        output_dir,
        include_cloud=True,
        cloud_provider=cloud_provider,
        price_per_cloud_call=0.005,
    )
    assert report["summary"]["winner_counts"] == {"cloud": 1}
    assert report["summary"]["estimated_cloud_cost"] == 0.005
    assert report["samples"][0]["metrics"]["cloud_cer"] == 0.0
    assert (output_dir / "ocr_benchmark.json").is_file()
    assert (output_dir / "ocr_benchmark.md").is_file()


def test_baidu_adapter_normalizes_positions_without_persisting_credentials() -> None:
    class FakeResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return self.payload

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def post(self, url: str, **kwargs: Any) -> FakeResponse:
            self.calls.append({"url": url, **kwargs})
            if "oauth" in url:
                return FakeResponse({"access_token": "temporary-token", "expires_in": 3600})
            return FakeResponse({
                "words_result_num": 1,
                "words_result": [
                    {
                        "words": "燃气轮机",
                        "probability": {"average": 0.97},
                        "location": {"left": 10, "top": 20, "width": 100, "height": 30},
                    }
                ],
            })

    session = FakeSession()
    client = BaiduOCRClient(
        BaiduOCRConfig(api_key="test-ak", secret_key="test-sk"),
        session=session,
    )
    payload = client(_png_bytes(), 3, "allowed.png")
    assert payload["text"] == "燃气轮机"
    assert payload["blocks"][0]["bbox"] == [[10, 20], [110, 20], [110, 50], [10, 50]]
    assert payload["confidence"] == 0.97
    assert "access_token" not in payload
    assert len(session.calls) == 2


def test_baidu_preprocessing_resizes_oversized_pages() -> None:
    prepared, metadata = prepare_image_for_baidu(_png_bytes(width=5000, height=100))
    assert prepared.startswith(b"\xff\xd8")
    assert metadata["resized"] is True
    assert max(metadata["uploaded_width"], metadata["uploaded_height"]) <= 4096


def test_baidu_transport_errors_do_not_echo_credentials() -> None:
    class FailingSession:
        def post(self, _url: str, **_kwargs: Any) -> Any:
            raise RuntimeError("transport included test-sk")

    client = BaiduOCRClient(
        BaiduOCRConfig(api_key="test-ak", secret_key="test-sk"),
        session=FailingSession(),
    )
    with pytest.raises(BaiduOCRResponseError) as captured:
        client(_png_bytes(), 1, "allowed.png")
    assert "test-sk" not in str(captured.value)


def test_rapidocr_provider_normalizes_local_output() -> None:
    class FakeOutput:
        txts = ("燃气轮机", "过滤器堵塞")
        scores = (0.96, 0.91)
        boxes = (
            ((10, 10), (210, 10), (210, 50), (10, 50)),
            ((10, 70), (260, 70), (260, 110), (10, 110)),
        )
        elapse = 0.25

    provider = RapidOCRProvider(engine=lambda _image: FakeOutput())
    payload = provider(_png_bytes(), 2, "synthetic.png")
    assert payload["text"] == "燃气轮机\n过滤器堵塞"
    assert payload["confidence"] == pytest.approx(0.935)
    assert payload["blocks"][1]["block_id"] == "p2-b2"
    assert payload["reading_order_risk"] == "low"


def test_synthetic_benchmark_generator_creates_cloud_safe_manifest(tmp_path: Path) -> None:
    manifest_path = generate_demo(tmp_path / "synthetic")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(payload["samples"]) == 4
    assert all(item["external_allowed"] is True for item in payload["samples"])
    assert {item["category"] for item in payload["samples"]} == {
        "body_text",
        "low_quality",
        "table",
        "two_column",
    }
    assert all((manifest_path.parent / item["source_path"]).is_file() for item in payload["samples"])


def test_two_column_reordering_preserves_blocks_and_groups_columns() -> None:
    blocks = [
        {"block_id": "left-1", "order": 0, "text": "左一", "bbox": [[10, 10], [100, 10], [100, 30], [10, 30]]},
        {
            "block_id": "right-1",
            "order": 1,
            "text": "右一",
            "bbox": [[600, 10], [700, 10], [700, 30], [600, 30]],
        },
        {"block_id": "left-2", "order": 2, "text": "左二", "bbox": [[10, 50], [100, 50], [100, 70], [10, 70]]},
        {
            "block_id": "right-2",
            "order": 3,
            "text": "右二",
            "bbox": [[600, 50], [700, 50], [700, 70], [600, 70]],
        },
    ]
    ordered = reorder_two_column_blocks(blocks, width=1000)
    assert [item["block_id"] for item in ordered] == ["left-1", "left-2", "right-1", "right-2"]
    assert {item["block_id"] for item in ordered} == {item["block_id"] for item in blocks}
