"""Evidence-oriented comparison of local OCR output and Baidu Cloud OCR."""

# ruff: noqa: RUF001, TRY003

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from data_pipeline.baidu_ocr import BaiduOCRClient, BaiduOCRConfig

OCRProvider = Callable[[bytes, int, str], dict[str, Any]]


class OCRBenchmarkError(RuntimeError):
    """Raised when the benchmark manifest or an OCR result is invalid."""


def run_ocr_benchmark(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    include_cloud: bool = False,
    cloud_provider: OCRProvider | None = None,
    local_provider: OCRProvider | None = None,
    price_per_cloud_call: float | None = None,
) -> dict[str, Any]:
    manifest_file = Path(manifest_path).resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    samples = manifest.get("samples") if isinstance(manifest, dict) else None
    if not isinstance(samples, list) or not samples:
        raise OCRBenchmarkError("Benchmark manifest must contain a non-empty samples list")

    if include_cloud and cloud_provider is None:
        cloud_provider = BaiduOCRClient(BaiduOCRConfig.from_env())

    records: list[dict[str, Any]] = []
    for index, raw_sample in enumerate(samples, start=1):
        if not isinstance(raw_sample, Mapping):
            raise OCRBenchmarkError(f"Sample {index} must be a JSON object")
        records.append(
            _run_sample(
                dict(raw_sample),
                manifest_dir=manifest_file.parent,
                include_cloud=include_cloud,
                cloud_provider=cloud_provider,
                local_provider=local_provider,
            )
        )

    cloud_calls = sum(1 for item in records if item["cloud"]["status"] == "completed")
    report = {
        "schema_version": "ocr-benchmark-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": manifest_file.name,
        "dataset_name": str(manifest.get("dataset_name") or manifest_file.stem),
        "policy": {
            "cloud_enabled": include_cloud,
            "cloud_upload_requires_external_allowed": True,
            "credentials_persisted": False,
        },
        "summary": _summarize(records, cloud_calls, price_per_cloud_call),
        "category_summary": _summarize_categories(records),
        "samples": records,
        "recommendations": _recommendations(records),
    }
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "ocr_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "ocr_benchmark.md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def compare_ocr_texts(local_text: str, cloud_text: str, gold_text: str = "") -> dict[str, Any]:
    local = normalize_ocr_text(local_text)
    cloud = normalize_ocr_text(cloud_text)
    gold = normalize_ocr_text(gold_text)
    disagreement_distance = levenshtein_distance(local, cloud)
    result: dict[str, Any] = {
        "local_chars": len(local),
        "cloud_chars": len(cloud),
        "pair_edit_distance": disagreement_distance,
        "pair_disagreement_rate": round(disagreement_distance / max(len(local), len(cloud), 1), 4),
        "numeric_token_overlap": round(_token_overlap(_numeric_tokens(local), _numeric_tokens(cloud)), 4),
        "latin_token_overlap": round(_token_overlap(_latin_tokens(local), _latin_tokens(cloud)), 4),
        "gold_available": bool(gold),
    }
    if gold:
        local_distance = levenshtein_distance(gold, local)
        cloud_distance = levenshtein_distance(gold, cloud)
        local_cer = local_distance / max(len(gold), 1)
        cloud_cer = cloud_distance / max(len(gold), 1)
        result.update({
            "gold_chars": len(gold),
            "local_edit_distance": local_distance,
            "cloud_edit_distance": cloud_distance,
            "local_cer": round(local_cer, 4),
            "cloud_cer": round(cloud_cer, 4),
            "cer_improvement_cloud_vs_local": round(local_cer - cloud_cer, 4),
            "winner": "cloud" if cloud_cer < local_cer else "local" if local_cer < cloud_cer else "tie",
        })
    return result


def normalize_ocr_text(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", str(text or "")).split()).lower()


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def load_local_result(path: str | Path, *, page: int) -> dict[str, Any]:
    result_path = Path(path)
    if not result_path.is_file():
        raise OCRBenchmarkError(f"Local OCR result does not exist: {result_path}")
    if result_path.suffix.lower() == ".jsonl":
        with result_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                payload_page = int(payload.get("page") or payload.get("page_num") or 0)
                if payload_page == page:
                    return _normalize_existing_payload(payload, page=page)
        raise OCRBenchmarkError(f"Page {page} is missing from local OCR result: {result_path.name}")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
        match = next(
            (item for item in payload["pages"] if int(item.get("page") or item.get("page_num") or 0) == page),
            None,
        )
        if match is None:
            raise OCRBenchmarkError(f"Page {page} is missing from local OCR result: {result_path.name}")
        payload = match
    if not isinstance(payload, dict):
        raise OCRBenchmarkError(f"Local OCR result must be a JSON object: {result_path.name}")
    return _normalize_existing_payload(payload, page=page)


def render_source_page(source_path: str | Path, page: int) -> bytes:
    path = Path(source_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - dependency gate
            raise OCRBenchmarkError("PyMuPDF is required to render benchmark PDF pages") from exc
        document = fitz.open(path)
        if not 1 <= page <= document.page_count:
            raise OCRBenchmarkError(f"Page {page} is outside PDF range 1..{document.page_count}: {path.name}")
        pixmap = document.load_page(page - 1).get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        return pixmap.tobytes("png")
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        if page != 1:
            raise OCRBenchmarkError(f"Image samples only support page 1: {path.name}")
        return path.read_bytes()
    raise OCRBenchmarkError(f"Unsupported benchmark source type: {suffix or 'unknown'}")


def _run_sample(
    sample: dict[str, Any],
    *,
    manifest_dir: Path,
    include_cloud: bool,
    cloud_provider: OCRProvider | None,
    local_provider: OCRProvider | None,
) -> dict[str, Any]:
    sample_id = str(sample.get("sample_id") or "").strip()
    if not sample_id:
        raise OCRBenchmarkError("Every sample needs a sample_id")
    source_path = _resolve_path(manifest_dir, sample.get("source_path"))
    if not source_path.is_file():
        raise OCRBenchmarkError(f"Benchmark source does not exist for {sample_id}: {source_path}")
    page = int(sample.get("page") or 1)
    image_bytes = render_source_page(source_path, page)

    local_status = "not_configured"
    local_payload: dict[str, Any] = {}
    local_result_value = sample.get("local_result_path")
    if local_result_value:
        local_result_path = _resolve_path(manifest_dir, local_result_value)
        local_payload = load_local_result(local_result_path, page=page)
        local_status = "completed"
    elif local_provider is not None:
        local_payload = local_provider(image_bytes, page, source_path.name)
        local_status = "completed"

    external_allowed = sample.get("external_allowed") is True
    cloud_status = "disabled"
    cloud_payload: dict[str, Any] = {}
    if include_cloud and not external_allowed:
        cloud_status = "blocked_by_policy"
    elif include_cloud:
        if cloud_provider is None:
            raise OCRBenchmarkError("Cloud OCR was enabled without a provider")
        cloud_payload = cloud_provider(image_bytes, page, source_path.name)
        cloud_status = "completed"

    local_text = str(local_payload.get("text") or "")
    cloud_text = str(cloud_payload.get("text") or "")
    gold_text = str(sample.get("gold_text") or "")
    metrics = (
        compare_ocr_texts(local_text, cloud_text, gold_text)
        if local_status == cloud_status == "completed"
        else _single_provider_metrics(local_text, gold_text, provider="local")
        if local_status == "completed"
        else {}
    )
    metrics.update({
        "local_confidence": _payload_float(local_payload, "confidence", "avg_confidence"),
        "cloud_confidence": _payload_float(cloud_payload, "confidence", "avg_confidence"),
        "local_elapsed_seconds": _payload_float(local_payload, "elapsed_seconds", "elapsed_s"),
        "cloud_elapsed_seconds": _payload_float(cloud_payload, "elapsed_seconds", "elapsed_s"),
        "local_line_count": _payload_line_count(local_payload),
        "cloud_line_count": _payload_line_count(cloud_payload),
        "local_table_count": len(local_payload.get("tables") or []),
        "cloud_table_count": len(cloud_payload.get("tables") or []),
    })
    category = str(sample.get("category") or "body_text")
    if category == "two_column" and local_payload.get("layout_reordered_text"):
        optimized = _single_provider_metrics(
            str(local_payload["layout_reordered_text"]),
            gold_text,
            provider="local_layout",
        )
        metrics.update(optimized)
        if metrics.get("local_cer") is not None and metrics.get("local_layout_cer") is not None:
            metrics["local_layout_cer_improvement"] = round(
                float(metrics["local_cer"]) - float(metrics["local_layout_cer"]),
                4,
            )
    layout_risk = str((local_payload.get("layout") or {}).get("reading_order_risk") or "")
    return {
        "sample_id": sample_id,
        "source_file": source_path.name,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "page": page,
        "category": category,
        "external_allowed": external_allowed,
        "notes": str(sample.get("notes") or ""),
        "gold_text": gold_text,
        "local": {
            **_safe_payload(local_payload),
            "provider_status": local_payload.get("status"),
            "status": local_status,
        },
        "cloud": {
            **_safe_payload(cloud_payload),
            "provider_status": cloud_payload.get("status"),
            "status": cloud_status,
        },
        "metrics": metrics,
        "needs_human_review": (
            not gold_text
            or cloud_status == "blocked_by_policy"
            or float(metrics.get("pair_disagreement_rate") or 0.0) >= 0.08
            or float(metrics.get("local_cer") or 0.0) >= 0.05
            or float(metrics.get("cloud_cer") or 0.0) >= 0.05
            or (category == "table" and int(metrics.get("local_table_count") or 0) == 0)
            or (category == "two_column" and layout_risk in {"medium", "high"})
        ),
    }


def _single_provider_metrics(text: str, gold_text: str, *, provider: str) -> dict[str, Any]:
    normalized = normalize_ocr_text(text)
    gold = normalize_ocr_text(gold_text)
    metrics: dict[str, Any] = {f"{provider}_chars": len(normalized), "gold_available": bool(gold)}
    if gold:
        distance = levenshtein_distance(gold, normalized)
        metrics[f"{provider}_edit_distance"] = distance
        metrics[f"{provider}_cer"] = round(distance / max(len(gold), 1), 4)
    return metrics


def _summarize(
    records: list[dict[str, Any]],
    cloud_calls: int,
    price_per_cloud_call: float | None,
) -> dict[str, Any]:
    winners = Counter(str(item["metrics"].get("winner")) for item in records if item["metrics"].get("winner"))
    gold_records = [item for item in records if item["metrics"].get("gold_available")]
    paired = [item for item in records if item["cloud"]["status"] == item["local"]["status"] == "completed"]
    return {
        "sample_count": len(records),
        "paired_sample_count": len(paired),
        "gold_sample_count": len(gold_records),
        "cloud_call_count": cloud_calls,
        "cloud_blocked_by_policy": sum(1 for item in records if item["cloud"]["status"] == "blocked_by_policy"),
        "needs_human_review": sum(1 for item in records if item["needs_human_review"]),
        "winner_counts": dict(winners),
        "mean_pair_disagreement_rate": round(
            sum(float(item["metrics"].get("pair_disagreement_rate") or 0.0) for item in paired) / max(len(paired), 1),
            4,
        ),
        "mean_local_cer": _mean_metric(gold_records, "local_cer"),
        "mean_cloud_cer": _mean_metric(gold_records, "cloud_cer"),
        "price_per_cloud_call": price_per_cloud_call,
        "estimated_cloud_cost": (
            round(cloud_calls * price_per_cloud_call, 4) if price_per_cloud_call is not None else None
        ),
    }


def _recommendations(records: list[dict[str, Any]]) -> list[str]:
    recommendations = [
        "只对 external_allowed=true 的样本调用云端 OCR，内部资料默认留在本地。",
        "没有人工金标时，两套 OCR 的差异只能用于定位风险，不能据此宣布哪套更准确。",
    ]
    gold = [item for item in records if item["metrics"].get("winner")]
    cloud_wins = sum(1 for item in gold if item["metrics"].get("winner") == "cloud")
    local_wins = sum(1 for item in gold if item["metrics"].get("winner") == "local")
    if cloud_wins > local_wins:
        recommendations.append("金标样本中百度 OCR 更优：可将低置信度、复杂版面页路由到云端复核，而非全量上传。")
    elif local_wins > cloud_wins:
        recommendations.append("金标样本中本地 OCR 更优：保留本地主路径，只把高风险页送人工或云端二次核验。")
    else:
        recommendations.append("当前金标不足或两者接近：先扩充按正文、表格、公式、双栏分层的人工金标。")
    if any(item["category"] in {"table", "formula", "two_column"} for item in records):
        recommendations.append("表格、公式和双栏页面必须分层统计，不能只看全体平均字符错误率。")
    if any(float(item["metrics"].get("local_layout_cer_improvement") or 0.0) > 0 for item in records):
        recommendations.append("分栏重排候选明显降低 CER：保留原始框顺序，同时把重排结果送人工审核后再进入图谱抽取。")
    if any(item["category"] == "table" and int(item["metrics"].get("local_table_count") or 0) == 0 for item in records):
        recommendations.append(
            "表格文字已识别但没有行列结构：应路由到表格/办公文档识别，不能把换行文本当成结构化表格。"
        )
    return recommendations


def _summarize_categories(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        categories.setdefault(str(item["category"]), []).append(item)
    return [
        {
            "category": category,
            "sample_count": len(items),
            "gold_sample_count": sum(1 for item in items if item["metrics"].get("gold_available")),
            "mean_pair_disagreement_rate": _mean_metric(items, "pair_disagreement_rate"),
            "mean_local_cer": _mean_metric(items, "local_cer"),
            "mean_local_layout_cer": _mean_metric(items, "local_layout_cer"),
            "mean_cloud_cer": _mean_metric(items, "cloud_cer"),
            "mean_local_elapsed_seconds": _mean_metric(items, "local_elapsed_seconds"),
            "mean_cloud_elapsed_seconds": _mean_metric(items, "cloud_elapsed_seconds"),
        }
        for category, items in sorted(categories.items())
    ]


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 百度云 OCR 与本地 OCR 对比报告",
        "",
        f"> 数据集：`{report['dataset_name']}`<br>",
        f"> 生成时间：`{report['generated_at']}`",
        "",
        "## 结论边界",
        "",
        "只有带人工金标的样本才能判断准确率高低；没有金标的页面只报告两套结果的差异。",
        "",
        "## 汇总",
        "",
        f"- 样本数：{summary['sample_count']}",
        f"- 云/本地成对样本：{summary['paired_sample_count']}",
        f"- 人工金标样本：{summary['gold_sample_count']}",
        f"- 百度云成功调用：{summary['cloud_call_count']}",
        f"- 因外发策略阻断：{summary['cloud_blocked_by_policy']}",
        f"- 需人工复核：{summary['needs_human_review']}",
        f"- 本地平均 CER：{_display_metric(summary['mean_local_cer'])}",
        f"- 百度平均 CER：{_display_metric(summary['mean_cloud_cer'])}",
        f"- 估算云端费用：{_display_cost(summary['estimated_cloud_cost'])}",
        "",
        "## 分层结果",
        "",
        "| 类别 | 样本 | 金标 | 差异率 | 本地 CER | 本地分栏 CER | 百度 CER | 本地耗时 | 百度耗时 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["category_summary"]:
        lines.append(
            f"| {item['category']} | {item['sample_count']} | {item['gold_sample_count']} | "
            f"{_display_metric(item['mean_pair_disagreement_rate'])} | "
            f"{_display_metric(item['mean_local_cer'])} | {_display_metric(item['mean_local_layout_cer'])} | "
            f"{_display_metric(item['mean_cloud_cer'])} | "
            f"{_display_metric(item['mean_local_elapsed_seconds'])} | "
            f"{_display_metric(item['mean_cloud_elapsed_seconds'])} |"
        )
    lines.extend([
        "",
        "## 样本明细",
        "",
        "| 样本 | 类别 | 页 | 本地 | 百度 | 差异率 | 本地 CER | 百度 CER | 胜出 | 复核 |",
        "|---|---|---:|---|---|---:|---:|---:|---|---|",
    ])
    for item in report["samples"]:
        metrics = item["metrics"]
        lines.append(
            f"| {item['sample_id']} | {item['category']} | {item['page']} | {item['local']['status']} | "
            f"{item['cloud']['status']} | {_display_metric(metrics.get('pair_disagreement_rate'))} | "
            f"{_display_metric(metrics.get('local_cer'))} | {_display_metric(metrics.get('cloud_cer'))} | "
            f"{metrics.get('winner', '-')} | {'是' if item['needs_human_review'] else '否'} |"
        )
    lines.extend(["", "## 优化建议", ""])
    lines.extend(f"- {item}" for item in report["recommendations"])
    lines.extend([
        "",
        "## 安全说明",
        "",
        "- 百度 API Key、Secret Key 和 access token 均不写入报告或仓库。",
        "- 报告只保存文件名与 SHA-256，不保存源文件绝对路径。",
        "- `external_allowed` 不是 `true` 时，工具不会向百度上传页面。",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    return {key: value for key, value in payload.items() if key not in {"access_token", "api_key", "secret_key"}}


def _normalize_existing_payload(payload: dict[str, Any], *, page: int) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["page"] = page
    normalized["text"] = str(normalized.get("text") or "")
    normalized["provider"] = str(normalized.get("provider") or normalized.get("engine") or "local")
    return normalized


def _resolve_path(base: Path, value: Any) -> Path:
    text = str(value or "").strip()
    if not text:
        raise OCRBenchmarkError("source_path/local_result_path must not be empty")
    path = Path(text)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _numeric_tokens(text: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", text)


def _latin_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+(?:[-_][a-z0-9]+)*", text)


def _token_overlap(left: list[str], right: list[str]) -> float:
    left_counter = Counter(left)
    right_counter = Counter(right)
    denominator = sum((left_counter | right_counter).values())
    return sum((left_counter & right_counter).values()) / max(denominator, 1)


def _mean_metric(records: list[dict[str, Any]], key: str) -> float | None:
    values = [float(item["metrics"][key]) for item in records if item["metrics"].get(key) is not None]
    return round(sum(values) / len(values), 4) if values else None


def _payload_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return round(float(value), 4)
    return None


def _payload_line_count(payload: dict[str, Any]) -> int | None:
    if not payload:
        return None
    if payload.get("line_count") is not None:
        return int(payload["line_count"])
    blocks = payload.get("blocks") or payload.get("lines")
    if isinstance(blocks, list):
        return len(blocks)
    text = str(payload.get("text") or "")
    return len(text.splitlines()) if text else 0


def _display_metric(value: Any) -> str:
    return "-" if value is None else f"{float(value):.4f}"


def _display_cost(value: Any) -> str:
    return "未配置账号实际单价" if value is None else f"约 ¥{float(value):.4f}"
