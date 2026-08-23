import json
from dataclasses import dataclass
from hashlib import sha256

from .errors import FmeaDomainError
from .states import FMEA_SCHEMA_ID


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
    ) -> "EvidencePack":
        ids = [ref.evidence_id for ref in refs]
        if len(ids) != len(set(ids)):
            raise FmeaDomainError("duplicate evidence_id")  # noqa: TRY003
        for ref in refs:
            if ref.workspace_id != workspace_id:
                raise FmeaDomainError("evidence workspace_id does not match pack workspace_id")  # noqa: TRY003
            if not set(ref.acl_scope).issubset(acl_scope):
                raise FmeaDomainError("evidence acl_scope is not compatible with pack acl_scope")  # noqa: TRY003
        payload = json.dumps(
            [
                {"evidence_id": ref.evidence_id, "evidence_hash": ref.evidence_hash, "locator": ref.locator}
                for ref in sorted(refs, key=lambda item: item.evidence_id)
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            pack_id=pack_id,
            workspace_id=workspace_id,
            acl_scope=tuple(acl_scope),
            versions=versions,
            refs=tuple(refs),
            pack_hash=sha256(payload).hexdigest(),
            created_at=created_at,
            expires_at=expires_at,
        )

    def ref_by_id(self, evidence_id: str) -> EvidenceRef | None:
        return next((ref for ref in self.refs if ref.evidence_id == evidence_id), None)
