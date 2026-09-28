# Delivery API contract

Base path: `/api/delivery`

Use the live OpenAPI schema or route source as authoritative if it differs from this reference.

## Documents

| Action | Method and path |
|---|---|
| Intake a candidate | `POST /documents/intake` |
| Get a version | `GET /documents/{version_id}` |
| Review a version | `POST /documents/{version_id}/review` |
| Publish a version | `POST /documents/{version_id}/publish` |
| Compare versions | `GET /documents/compare/{left_id}/{right_id}` |
| Roll back content | `POST /documents/{document_id}/rollback` |

Minimal intake payload:

```json
{
  "document_id": "manual-001",
  "source_name": "manual.pdf",
  "content_base64": "<base64 bytes>",
  "chunk_size": 800,
  "overlap": 100
}
```

Review payload:

```json
{
  "reviewer": "domain-expert",
  "decision": "approve",
  "comment": "Evidence and quality issues reviewed",
  "corrections": {}
}
```

## Graphs

| Action | Method and path |
|---|---|
| Create a candidate | `POST /graphs/candidates` |
| Get a version | `GET /graphs/{graph_version_id}` |
| Review a version | `POST /graphs/{graph_version_id}/review` |
| Publish a version | `POST /graphs/{graph_version_id}/publish` |
| Export triples | `GET /graphs/{graph_version_id}/export` |

Minimal graph candidate payload:

```json
{
  "source_document_version_ids": ["manual-001:v1"],
  "statements": [
    {
      "subject": "润滑油系统",
      "predicate": "故障模式",
      "object": "过滤器堵塞",
      "subject_type": "COMPONENT",
      "object_type": "FAILURE_MODE",
      "evidence_ids": ["EV-..."],
      "confidence": 0.9
    }
  ]
}
```

Supplying statements proves candidate validation, not automatic graph extraction.

## FMEA

| Action | Method and path |
|---|---|
| Create a task | `POST /fmea/tasks` |
| Get a task | `GET /fmea/tasks/{task_id}` |
| Review a task | `POST /fmea/tasks/{task_id}/review` |
| Publish a task | `POST /fmea/tasks/{task_id}/publish` |
| Export a task | `GET /fmea/tasks/{task_id}/export?format=json|csv` |
| Record feedback | `POST /fmea/tasks/{task_id}/feedback` |

Task payload:

```json
{
  "requested_by": "reviewer",
  "graph_version_id": "graph:v1",
  "document_version_ids": ["manual-001:v1"],
  "template": "gas_turbine_minimum_v1"
}
```

Human corrections should preserve or explicitly replace evidence bindings:

```json
{
  "reviewer": "fmea-expert",
  "decision": "modify",
  "corrections": {
    "FMEA-0001": {
      "cause": {
        "value": "油液污染",
        "evidence_ids": ["EV-..."]
      }
    }
  }
}
```

## Expected failures

Treat these as governed outcomes, not errors to bypass:

- input needs OCR or failed parsing;
- document lacks evidence or approval;
- graph source document is unpublished;
- graph relation or entity type is unknown;
- graph evidence is missing or outside selected versions;
- FMEA graph is unpublished;
- FMEA has unknown or conflicting fields;
- export is requested before approval and publication.
