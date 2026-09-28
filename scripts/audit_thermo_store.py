# -*- coding: utf-8 -*-
"""Inspect the persisted governance store from the 2026-09-27 literature run."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RUN = Path("build/thermo_wf_run_20260927")


def main() -> int:
    dbs = sorted(RUN.rglob("*.sqlite3"))
    print("sqlite files:")
    for path in dbs:
        print("  ", path, path.stat().st_size)
    for db in RUN.rglob("delivery.sqlite3"):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        print(f"\n=== {db}")
        counts = {
            "document_versions": "select count(*) from document_versions",
            "published": "select count(*) from document_versions where status='published'",
            "evidence_locators": "select count(*) from evidence_locators",
            "evidence_with_page": "select count(*) from evidence_locators where page is not null and page != ''",
            "evidence_with_block": "select count(*) from evidence_locators where block_id is not null and block_id != ''",
            "distinct_pages": "select count(distinct page) from evidence_locators where page is not null",
            "graph_versions": "select count(*) from graph_versions",
            "graph_statements": "select count(*) from graph_statements",
            "statements_with_evidence": (
                "select count(*) from graph_statements where evidence_ids_json not in ('[]','')"
            ),
            "reviews": "select count(*) from reviews",
            "fmea_tasks": "select count(*) from fmea_tasks",
            "feedback": "select count(*) from feedback",
            "ocr_jobs": "select count(*) from ocr_jobs",
            "source_assets": "select count(*) from source_assets",
        }
        for label, sql in counts.items():
            print(f"  {label:26} {con.execute(sql).fetchone()[0]}")

        print("  status breakdown:", [tuple(r) for r in con.execute(
            "select status, count(*) from document_versions group by status")])
        print("  sample pages:", [r[0] for r in con.execute(
            "select distinct page from evidence_locators where page is not null limit 10")])
        print("  review decisions:", [tuple(r) for r in con.execute(
            "select target_type, decision, count(*) from reviews group by target_type, decision")])
        print("  predicates:", [tuple(r) for r in con.execute(
            "select predicate, count(*) from graph_statements group by predicate")])

        # per-document evidence + page coverage
        rows = list(con.execute(
            """
            select d.document_id, d.content_hash, d.status,
                   count(e.evidence_id) as ev,
                   count(distinct e.page) as pages
            from document_versions d
            left join evidence_locators e on e.document_version_id = d.version_id
            group by d.version_id order by d.document_id
            """,
        ))
        print(f"\n  per-document ({len(rows)} rows, first 8 / last 3):")
        for row in rows[:8] + rows[-3:]:
            print(f"    {row['document_id']} ev={row['ev']:5} pages={row['pages']:4} {row['status']}")
        evidence_counts = [row["ev"] for row in rows]
        print(f"  evidence per doc: min={min(evidence_counts)} max={max(evidence_counts)} "
              f"avg={sum(evidence_counts) / len(evidence_counts):.1f}")

        fmea = list(con.execute("select task_id, status, json_extract(items_json,'$[0].fields') from fmea_tasks"))
        for task_id, status, fields in fmea:
            print(f"\n  fmea {task_id} status={status}")
            print("    first item fields:", json.dumps(json.loads(fields) if fields else None, ensure_ascii=False))
        return 0
    print("no delivery.sqlite3 found")
    return 1


if __name__ == "__main__":
    sys.exit(main())
