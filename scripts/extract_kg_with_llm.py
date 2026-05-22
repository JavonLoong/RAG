from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kg_pipeline.llm_extraction.pipeline import (  # noqa: E402
    DEFAULT_SCHEMA_PATH,
    LLMExtractionError,
    MissingLLMClientError,
    OpenAICompatibleClient,
    run_extraction,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract evidence-bound KG triples from chunks by calling a configured LLM.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input chunks.jsonl or a small UTF-8 text file.",
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA_PATH),
        help="Schema JSON path. Defaults to the four-books KG construction schema.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Directory for triples_llm_candidates.json and validation_report.json. Defaults to input parent.",
    )
    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        help="Optional maximum number of chunks to send to the LLM.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI-compatible chat model name. Can also be set via OPENAI_MODEL or LLM_MODEL.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible base URL. Defaults to OPENAI_BASE_URL/LLM_BASE_URL or https://api.openai.com/v1.",
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable containing the API key. Defaults to OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="HTTP timeout for each LLM request.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM sampling temperature.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        client = OpenAICompatibleClient.from_env(
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            temperature=args.temperature,
        )
        report = run_extraction(
            args.input,
            args.schema,
            args.output_dir,
            llm_client=client,
            limit_chunks=args.limit_chunks,
        )
    except MissingLLMClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (LLMExtractionError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.input).resolve().parent
    print(f"Wrote {output_dir / 'triples_llm_candidates.json'}")
    print(f"Wrote {output_dir / 'validation_report.json'}")
    print(
        "Summary: "
        f"{report['valid_count']} valid, "
        f"{report['invalid_count']} invalid, "
        f"{report['parse_error_count']} parse errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
