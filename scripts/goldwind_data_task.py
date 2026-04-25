from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sqlite3
import sys
import zipfile
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any


MISSING_MARKERS = {"", "na", "n/a", "nan", "none", "null", "-"}


@dataclass
class ColumnStats:
    name: str
    declared_type: str = ""
    total_count: int = 0
    missing_count: int = 0
    numeric_count: int = 0
    non_numeric_count: int = 0
    numeric_min: float | None = None
    numeric_max: float | None = None
    non_numeric_examples: list[str] = field(default_factory=list)

    @property
    def non_missing_count(self) -> int:
        return self.total_count - self.missing_count

    @property
    def numeric_convertible(self) -> bool:
        return self.non_missing_count > 0 and self.non_numeric_count == 0

    @property
    def missing_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.missing_count / self.total_count


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING_MARKERS


def numeric_value(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def safe_column_filename(index: int, column: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9-]+", "_", column).strip("_")
    if not normalized:
        normalized = "column"
    return f"{index:03d}_{normalized[:80]}.csv"


def decode_goldwind(source_path: Path, output_dir: Path) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {source_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    with source_path.open("rb") as file:
        signature = file.read(16)

    if signature.startswith(b"SQLite format 3"):
        target_path = output_dir / source_path.name
        if source_path.resolve() != target_path.resolve():
            shutil.copyfile(source_path, target_path)
        return target_path

    if not signature.startswith(b"PK"):
        raise ValueError(f"Unsupported input format: {source_path}")

    with zipfile.ZipFile(source_path) as archive:
        db_entries = [entry for entry in archive.infolist() if entry.filename.lower().endswith(".db")]
        if not db_entries:
            raise ValueError(f"No SQLite .db file found inside: {source_path}")

        entry = max(db_entries, key=lambda item: item.file_size)
        safe_name = PurePosixPath(entry.filename.replace("\\", "/")).name
        target_path = output_dir / safe_name
        with archive.open(entry) as source, target_path.open("wb") as target:
            shutil.copyfileobj(source, target)

    return target_path


def get_tables(connection: sqlite3.Connection) -> list[str]:
    cursor = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def choose_table(connection: sqlite3.Connection, requested_table: str | None) -> str:
    tables = get_tables(connection)
    if not tables:
        raise ValueError("No user tables found in decoded SQLite database.")

    if requested_table:
        if requested_table not in tables:
            raise ValueError(f"Requested table not found: {requested_table}. Available tables: {', '.join(tables)}")
        return requested_table

    if "RUNDATA" in tables:
        return "RUNDATA"

    return max(tables, key=lambda table: connection.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0])


def get_declared_types(connection: sqlite3.Connection, table_name: str) -> dict[str, str]:
    cursor = connection.execute(f"PRAGMA table_info({quote_ident(table_name)})")
    return {row[1]: row[2] for row in cursor.fetchall()}


def export_table_to_csv(connection: sqlite3.Connection, table_name: str, csv_path: Path) -> tuple[int, list[str]]:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    cursor = connection.execute(f"SELECT * FROM {quote_ident(table_name)}")
    headers = [description[0] for description in cursor.description]

    row_count = 0
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            writer.writerows(rows)
            row_count += len(rows)

    return row_count, headers


def update_column_stats(stats: ColumnStats, value: str) -> None:
    stats.total_count += 1
    stripped = value.strip()

    if is_missing(stripped):
        stats.missing_count += 1
        return

    converted = numeric_value(stripped)
    if converted is None:
        stats.non_numeric_count += 1
        if len(stats.non_numeric_examples) < 5 and stripped not in stats.non_numeric_examples:
            stats.non_numeric_examples.append(stripped)
        return

    stats.numeric_count += 1
    stats.numeric_min = converted if stats.numeric_min is None else min(stats.numeric_min, converted)
    stats.numeric_max = converted if stats.numeric_max is None else max(stats.numeric_max, converted)


def missing_value_plan(stats: ColumnStats) -> str:
    if stats.missing_count == 0:
        return "No missing values detected."

    if stats.numeric_convertible:
        if stats.missing_rate <= 0.05:
            return "Use median fill or time-series interpolation, and keep an imputation flag column."
        if stats.missing_rate <= 0.30:
            return "Prefer timestamp-aware interpolation or rolling-window fill; validate against sensor behavior."
        return "Missing rate is high; recover source data or exclude the column from modeling after review."

    if "time" in stats.name.lower() or stats.declared_type.lower() in {"datetime", "date", "timestamp"}:
        return "Do not impute key time fields blindly; recover source records or drop affected rows."

    return "Use mode or forward-fill for categorical/version fields, and keep an imputation flag column."


def split_columns_and_analyze(
    csv_path: Path, output_dir: Path, declared_types: dict[str, str] | None = None
) -> tuple[list[ColumnStats], list[dict[str, Any]]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Required CSV file does not exist: {csv_path}")

    declared_types = declared_types or {}
    columns_dir = output_dir / "columns"
    columns_dir.mkdir(parents=True, exist_ok=True)

    with csv_path.open("r", newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header row: {csv_path}")

        headers = list(reader.fieldnames)
        stats_by_column = {
            column: ColumnStats(name=column, declared_type=declared_types.get(column, "")) for column in headers
        }

        manifest: list[dict[str, Any]] = []
        with ExitStack() as stack:
            writers: dict[str, csv.writer] = {}
            for index, column in enumerate(headers, start=1):
                filename = safe_column_filename(index, column)
                column_path = columns_dir / filename
                column_file = stack.enter_context(column_path.open("w", newline="", encoding="utf-8-sig"))
                writer = csv.writer(column_file)
                writer.writerow(["row_index", column])
                writers[column] = writer
                manifest.append(
                    {
                        "index": index,
                        "column": column,
                        "declared_type": declared_types.get(column, ""),
                        "file": str(column_path),
                    }
                )

            for row_index, row in enumerate(reader, start=1):
                for column in headers:
                    value = row.get(column, "")
                    writers[column].writerow([row_index, value])
                    update_column_stats(stats_by_column[column], value)

    for item in manifest:
        column_stats = stats_by_column[item["column"]]
        item.update(
            {
                "numeric_convertible": column_stats.numeric_convertible,
                "missing_count": column_stats.missing_count,
                "non_numeric_count": column_stats.non_numeric_count,
            }
        )

    manifest_path = output_dir / "column_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "index",
                "column",
                "declared_type",
                "file",
                "numeric_convertible",
                "missing_count",
                "non_numeric_count",
            ],
        )
        writer.writeheader()
        writer.writerows(manifest)

    return [stats_by_column[column] for column in headers], manifest


def write_reports(
    output_dir: Path,
    source_path: Path,
    db_path: Path,
    csv_path: Path,
    table_name: str,
    row_count: int,
    column_stats: list[ColumnStats],
) -> dict[str, Any]:
    numeric_columns = [stats.name for stats in column_stats if stats.numeric_convertible]
    non_numeric_columns = [stats for stats in column_stats if not stats.numeric_convertible]
    missing_columns = [stats for stats in column_stats if stats.missing_count > 0]

    report = {
        "source_file": str(source_path.resolve()),
        "decoded_database": str(db_path.resolve()),
        "parsed_csv": str(csv_path.resolve()),
        "table": table_name,
        "row_count": row_count,
        "column_count": len(column_stats),
        "numeric_convertible_column_count": len(numeric_columns),
        "non_numeric_column_count": len(non_numeric_columns),
        "missing_column_count": len(missing_columns),
        "non_numeric_columns": [
            {
                "name": stats.name,
                "declared_type": stats.declared_type,
                "non_numeric_count": stats.non_numeric_count,
                "examples": stats.non_numeric_examples,
            }
            for stats in non_numeric_columns
        ],
        "missing_columns": [
            {
                "name": stats.name,
                "declared_type": stats.declared_type,
                "missing_count": stats.missing_count,
                "missing_rate": round(stats.missing_rate, 6),
                "handling_plan": missing_value_plan(stats),
            }
            for stats in missing_columns
        ],
        "columns": [
            {
                **asdict(stats),
                "numeric_convertible": stats.numeric_convertible,
                "missing_rate": round(stats.missing_rate, 6),
                "handling_plan": missing_value_plan(stats),
            }
            for stats in column_stats
        ],
    }

    json_path = output_dir / "analysis_report.json"
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    markdown_path = output_dir / "analysis_report.md"
    with markdown_path.open("w", encoding="utf-8") as file:
        file.write("# Goldwind Decoding And Data Quality Report\n\n")
        file.write("## Outputs\n\n")
        file.write(f"- Decoded database: `{db_path}`\n")
        file.write(f"- Parsed CSV: `{csv_path}`\n")
        file.write(f"- Split column files: `{output_dir / 'columns'}`\n")
        file.write(f"- Column manifest: `{output_dir / 'column_manifest.csv'}`\n")
        file.write(f"- JSON report: `{json_path}`\n\n")

        file.write("## Required Checks\n\n")
        file.write(f"- File existence: PASS, `{csv_path.name}` exists.\n")
        file.write(f"- Data shape: {row_count} rows x {len(column_stats)} columns from table `{table_name}`.\n")
        file.write(
            f"- Numeric conversion: {len(numeric_columns)} columns can be converted to numeric values; "
            f"{len(non_numeric_columns)} columns contain non-numeric values.\n"
        )
        if missing_columns:
            file.write(f"- Missing values: {len(missing_columns)} columns contain missing values.\n\n")
            file.write("## Missing Value Handling Plan\n\n")
            for stats in missing_columns:
                file.write(
                    f"- `{stats.name}`: {stats.missing_count} missing "
                    f"({stats.missing_rate:.2%}). {missing_value_plan(stats)}\n"
                )
        else:
            file.write("- Missing values: PASS, no missing values detected.\n\n")
            file.write("## Missing Value Handling Plan\n\n")
            file.write(
                "No missing values were found in the current file. If future files contain missing values, "
                "use median or timestamp-aware interpolation for numeric sensor data, mode or forward-fill "
                "for categorical/version data, and avoid blind imputation for timestamp/key fields.\n"
            )

        if non_numeric_columns:
            file.write("\n## Non-Numeric Columns\n\n")
            for stats in non_numeric_columns:
                examples = ", ".join(repr(value) for value in stats.non_numeric_examples[:3])
                file.write(
                    f"- `{stats.name}` ({stats.declared_type or 'unknown'}): "
                    f"{stats.non_numeric_count} non-numeric values"
                )
                if examples:
                    file.write(f"; examples: {examples}")
                file.write("\n")

    return report


def run(source_path: Path, output_dir: Path, table_name: str | None) -> dict[str, Any]:
    db_path = decode_goldwind(source_path, output_dir)

    with sqlite3.connect(db_path) as connection:
        selected_table = choose_table(connection, table_name)
        declared_types = get_declared_types(connection, selected_table)
        csv_path = output_dir / "parsed_data.csv"
        row_count, _headers = export_table_to_csv(connection, selected_table, csv_path)

    column_stats, _manifest = split_columns_and_analyze(csv_path, output_dir, declared_types)
    return write_reports(output_dir, source_path, db_path, csv_path, selected_table, row_count, column_stats)


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_source = Path.cwd().parent / "GW15000120180104.goldwind"
    parser = argparse.ArgumentParser(description="Decode a Goldwind archive and prepare parsed CSV column data.")
    parser.add_argument("--source", type=Path, default=default_source, help="Path to the .goldwind or .db input file.")
    parser.add_argument("--output-dir", type=Path, default=Path("goldwind_decoded"), help="Directory for generated files.")
    parser.add_argument("--table", default=None, help="SQLite table to export. Defaults to RUNDATA when present.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = run(args.source, args.output_dir, args.table)
    except (FileNotFoundError, ValueError, sqlite3.Error, csv.Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Goldwind decoding and data task completed.")
    print(f"Rows: {report['row_count']}")
    print(f"Columns: {report['column_count']}")
    print(f"Numeric-convertible columns: {report['numeric_convertible_column_count']}")
    print(f"Columns with missing values: {report['missing_column_count']}")
    print(f"Parsed CSV: {report['parsed_csv']}")
    print(f"Report: {Path(args.output_dir) / 'analysis_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
