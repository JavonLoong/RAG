import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256

from .errors import FmeaDomainError
from .states import FMEA_SCHEMA_ID

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_LINEAGE_SCHEMA = "graphrag.fmea.evidence-lineage.v1"


@dataclass(frozen=True, slots=True)
class VersionSet:
    schema_id: str
    data_version: str
    graph_version: str
    evidence_pack_version: str
    profile_version: str
    template_version: str
    scoring_version: str
    prompt_version: str
    model_version: str
    input_snapshot_hash: str

    def __post_init__(self) -> None:
        if self.schema_id != FMEA_SCHEMA_ID:
            raise FmeaDomainError(f"schema_id must be {FMEA_SCHEMA_ID}")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    workspace_id: str
    document_id: str
    document_version: str
    content_hash: str
    locator: str
    quote: str
    normalized_quote: str
    evidence_hash: str
    acl_scope: tuple[str, ...]
    source_type: str
    source_trust: str
    is_primary: bool
    created_at: str
    expires_at: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "workspace_id",
            "document_id",
            "document_version",
            "content_hash",
            "evidence_hash",
            "quote",
            "normalized_quote",
        ):
            if not getattr(self, field_name):
                raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
        object.__setattr__(self, "acl_scope", tuple(self.acl_scope))


@dataclass(frozen=True, slots=True)
class EvidencePack:
    pack_id: str
    workspace_id: str
    acl_scope: tuple[str, ...]
    versions: VersionSet
    refs: tuple[EvidenceRef, ...]
    pack_hash: str
    created_at: str
    expires_at: str | None
    parent_pack_refs: tuple[tuple[str, str], ...] = ()
    lineage_reason: str | None = None
    lineage_schema_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "acl_scope", tuple(self.acl_scope))
        object.__setattr__(self, "refs", tuple(self.refs))
        parent_refs = tuple(self.parent_pack_refs)
        normalized: list[tuple[str, str]] = []
        for item in parent_refs:
            if not isinstance(item, tuple | list) or len(item) != 2:
                raise FmeaDomainError("parent_pack_refs must contain pack ID/hash pairs")  # noqa: TRY003
            parent_id, parent_hash = item
            if not isinstance(parent_id, str) or not parent_id.strip():
                raise FmeaDomainError("parent pack ID must not be empty")  # noqa: TRY003
            if not isinstance(parent_hash, str) or _SHA256.fullmatch(parent_hash) is None:
                raise FmeaDomainError("parent pack hash must be lowercase SHA-256")  # noqa: TRY003
            normalized.append((parent_id.strip(), parent_hash))
        normalized_refs = tuple(sorted(normalized))
        if len({parent_id for parent_id, _ in normalized_refs}) != len(normalized_refs):
            raise FmeaDomainError("duplicate parent pack reference")  # noqa: TRY003
        if self.pack_id in {parent_id for parent_id, _ in normalized_refs}:
            raise FmeaDomainError("EvidencePack lineage cannot self-reference")  # noqa: TRY003
        object.__setattr__(self, "parent_pack_refs", normalized_refs)

        if normalized_refs:
            if not isinstance(self.lineage_reason, str) or not self.lineage_reason.strip():
                raise FmeaDomainError("lineage reason is required for supplemental EvidencePack")  # noqa: TRY003
            if self.lineage_schema_version != EVIDENCE_LINEAGE_SCHEMA:
                raise FmeaDomainError("lineage schema version is invalid")  # noqa: TRY003
            object.__setattr__(self, "lineage_reason", self.lineage_reason.strip())
        elif self.lineage_reason is not None or self.lineage_schema_version is not None:
            raise FmeaDomainError("lineage fields must be supplied all-or-none")  # noqa: TRY003

    @classmethod
    def build(
        cls,
        *,
        pack_id: str,
        workspace_id: str,
        acl_scope: tuple[str, ...],
        versions: VersionSet,
        refs: tuple[EvidenceRef, ...],
        created_at: str,
        expires_at: str | None,
        parent_pack_refs: tuple[tuple[str, str], ...] = (),
        lineage_reason: str | None = None,
        lineage_schema_version: str | None = None,
    ) -> "EvidencePack":
        ids = [ref.evidence_id for ref in refs]
        if len(ids) != len(set(ids)):
            raise FmeaDomainError("duplicate evidence_id")  # noqa: TRY003
        for ref in refs:
            if ref.workspace_id != workspace_id:
                raise FmeaDomainError("evidence workspace_id does not match pack workspace_id")  # noqa: TRY003
            if not set(ref.acl_scope).issubset(acl_scope):
                raise FmeaDomainError("evidence acl_scope is not compatible with pack acl_scope")  # noqa: TRY003
        evidence_payload = [
            {"evidence_id": ref.evidence_id, "evidence_hash": ref.evidence_hash, "locator": ref.locator}
            for ref in sorted(refs, key=lambda item: item.evidence_id)
        ]
        normalized_parent_refs = tuple(sorted(tuple(item) for item in parent_pack_refs))
        if normalized_parent_refs:
            hash_payload: object = {
                "evidence_refs": evidence_payload,
                "lineage": {
                    "lineage_reason": lineage_reason,
                    "lineage_schema_version": lineage_schema_version,
                    "parent_pack_refs": [
                        {"pack_id": pack_id, "pack_hash": pack_hash}
                        for pack_id, pack_hash in normalized_parent_refs
                    ],
                },
            }
        else:
            # Keep the original bytes for legacy packs. Empty lineage is not a
            # new version of the identity algorithm.
            hash_payload = evidence_payload
        payload = json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return cls(
            pack_id=pack_id,
            workspace_id=workspace_id,
            acl_scope=tuple(acl_scope),
            versions=versions,
            refs=tuple(refs),
            pack_hash=sha256(payload).hexdigest(),
            created_at=created_at,
            expires_at=expires_at,
            parent_pack_refs=normalized_parent_refs,
            lineage_reason=lineage_reason,
            lineage_schema_version=lineage_schema_version,
        )

    def ref_by_id(self, evidence_id: str) -> EvidenceRef | None:
        return next((ref for ref in self.refs if ref.evidence_id == evidence_id), None)


def _resolved_parent_map(
    parent_packs: Mapping[str, EvidencePack] | Iterable[EvidencePack],
) -> dict[str, EvidencePack]:
    if isinstance(parent_packs, Mapping):
        items = tuple(parent_packs.items())
        if any(key != pack.pack_id for key, pack in items):
            raise FmeaDomainError("resolved parent map key does not match pack ID")  # noqa: TRY003
        values = tuple(pack for _, pack in items)
    else:
        values = tuple(parent_packs)
    result: dict[str, EvidencePack] = {}
    for pack in values:
        if not isinstance(pack, EvidencePack):
            raise FmeaDomainError("resolved parent packs contain an invalid value")  # noqa: TRY003
        if pack.pack_id in result and result[pack.pack_id] != pack:
            raise FmeaDomainError("silent parent pack replacement is not allowed")  # noqa: TRY003
        result[pack.pack_id] = pack
    return result


def validate_evidence_lineage(
    candidate: EvidencePack,
    parent_packs: Mapping[str, EvidencePack] | Iterable[EvidencePack],
) -> None:
    """Validate a candidate's explicit lineage against already-resolved parents."""

    if not isinstance(candidate, EvidencePack):
        raise FmeaDomainError("candidate must be an EvidencePack")  # noqa: TRY003
    resolved = _resolved_parent_map(parent_packs)
    if candidate.pack_id in resolved and resolved[candidate.pack_id] != candidate:
        raise FmeaDomainError("silent parent pack replacement is not allowed")  # noqa: TRY003
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(pack: EvidencePack) -> None:
        if pack.pack_id in visiting:
            raise FmeaDomainError("EvidencePack lineage contains a cycle")  # noqa: TRY003
        if pack.pack_id in visited:
            return
        visiting.add(pack.pack_id)
        for parent_id, parent_hash in pack.parent_pack_refs:
            if parent_id == candidate.pack_id and pack is not candidate:
                # The target is checked before the hash so an actual cycle is
                # reported as a cycle even when its fixture hash is stale.
                if candidate.pack_id in visiting:
                    raise FmeaDomainError("EvidencePack lineage contains a cycle")  # noqa: TRY003
            parent = candidate if parent_id == candidate.pack_id else resolved.get(parent_id)
            if parent is None:
                raise FmeaDomainError(f"unknown parent pack: {parent_id}")  # noqa: TRY003
            if parent.pack_id in visiting:
                raise FmeaDomainError("EvidencePack lineage contains a cycle")  # noqa: TRY003
            if parent.workspace_id != candidate.workspace_id:
                raise FmeaDomainError("parent pack workspace does not match candidate workspace")  # noqa: TRY003
            if parent_hash != parent.pack_hash:
                raise FmeaDomainError(f"parent pack hash mismatch: {parent_id}")  # noqa: TRY003
            visit(parent)
        visiting.remove(pack.pack_id)
        visited.add(pack.pack_id)

    visit(candidate)
