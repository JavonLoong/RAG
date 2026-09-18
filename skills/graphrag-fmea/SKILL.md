---
name: graphrag-fmea
description: Use when operating FMEA review, DomainPack, migration, or export delivery through the supported local CLI.
---

# GraphRAG FMEA delivery

Use the supported CLI as the only operation surface. Every operation is a single
invocation of `scripts/fmea_skill.py` and returns one JSON object on stdout.

## Quick reference

The Skill is read-only by default. Start with `domain-pack patch-status`,
`migration compatibility`, `export status`, or `export start --draft-preview`.
The server owns persistence, artifact locations, filenames, provider/model
selection, URLs, and migration adapters. Do not invent command-line switches for
those values and do not inspect application internals.

The operation states are orthogonal:

- A model suggestion is provisional and carries its run identity and EvidencePack citations.
- A human confirmation is a separate command with the exact operation flag; conversational wording never counts.
- An accepted template, confirmed migration, or published export is a durable application result.
- A narrative response is suggestion-only, has `applied: false`, and is never publication.
- A CLI error is already sanitized; surface its JSON code and detail unchanged.

## Exact human confirmation flags

Use only the matching flag when the user has explicitly authorized that operation:

`--confirm-human-assistance-decision`, `--confirm-human-review`,
`--confirm-human-risk-review`, `--confirm-human-propagation-review`,
`--confirm-human-approval`, `--confirm-publication`,
`--confirm-publication-withdrawal`, `--confirm-approval-withdrawal`,
`--confirm-supersession`, `--confirm-template-change`, and `--confirm-migration`.

The matching human role is enforced by the application. In particular,
template registration and migration confirmation require `template_admin`, and
published export requires `exporter` plus `--confirm-publication`.

## Supported operations

Use bounded source input for `domain-pack import` and bounded JSON request files
for confirmation commands. Keep server-generated IDs, output names, and output
locations out of the request. Use `export narrative-suggest` only to obtain a
provisional narrative with its evidence references.

## End-to-end example

```text
scripts/fmea_skill.py domain-pack import --source-file ./incoming-template.xlsx --idempotency-key <uuid>
scripts/fmea_skill.py domain-pack patch-suggest --draft-id <draft-id> --record-version 1 ...
scripts/fmea_skill.py domain-pack patch-status --patch-id <patch-id>
scripts/fmea_skill.py domain-pack accept --request-file ./accept-template.json --record-version 1 --idempotency-key <uuid> --confirm-template-change
scripts/fmea_skill.py migration dry-run --migration-id <migration-id> --revision-id <revision-id> --source-revision-hash <hash> ...
scripts/fmea_skill.py migration confirm --request-file ./confirm-migration.json --record-version 1 --idempotency-key <uuid> --confirm-migration
scripts/fmea_skill.py export start --revision-id <revision-id> --snapshot-id <snapshot-id> --snapshot-hash <hash> --format json --publication-id <publication-id> --record-version 1 --idempotency-key <uuid> --confirm-publication
scripts/fmea_skill.py export status --run-id <run-id>
```

Do not treat the example's placeholders as confirmation. Ask for the relevant
human authorization, pass only the exact flag, and preserve EvidencePack
citations in any user-facing explanation.
