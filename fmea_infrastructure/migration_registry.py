"""Explicit, immutable registry for domain-pack migration adapters."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from core_domain.fmea.template_migration import MigrationPlan, MigrationStep
from fmea_application.ports import MigrationAdapter


class MigrationRegistryError(ValueError):
    """A deterministic registry lookup failure safe for the application boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.code}: {super().__str__()}"


def _identity(value: object, field_name: str) -> tuple[str, str]:
    if not isinstance(value, tuple | list) or len(value) != 2:
        raise MigrationRegistryError("FMEA_MIGRATION_REGISTRY_INVALID", f"{field_name} must be an id/version pair")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise MigrationRegistryError("FMEA_MIGRATION_REGISTRY_INVALID", f"{field_name} is invalid")
    return str(value[0]).strip(), str(value[1]).strip()


def _adapter_id(source: tuple[str, str], target: tuple[str, str], adapter: object) -> str:
    supplied = getattr(adapter, "adapter_id", None)
    if supplied is not None:
        if not isinstance(supplied, str) or not supplied.strip():
            raise MigrationRegistryError("FMEA_MIGRATION_REGISTRY_INVALID", "adapter_id is invalid")
        return supplied.strip()
    source_version = re.sub(r"[^a-zA-Z0-9]+", "-", source[1]).strip("-").lower()
    target_version = re.sub(r"[^a-zA-Z0-9]+", "-", target[1]).strip("-").lower()
    return f"migration-{source[0]}-{source_version}-to-{target_version}"


@dataclass(frozen=True, slots=True)
class _RegisteredAdapter:
    source: tuple[str, str]
    target: tuple[str, str]
    adapter_id: str
    adapter: MigrationAdapter


class MigrationRegistry:
    """An allowlist of Python adapter objects; no discovery is performed."""

    def __init__(self, adapters: Iterable[MigrationAdapter]) -> None:
        registered: list[_RegisteredAdapter] = []
        try:
            adapter_items = tuple(adapters)
        except Exception as exc:
            raise MigrationRegistryError(
                "FMEA_MIGRATION_REGISTRY_INVALID", "migration adapter allowlist is invalid"
            ) from exc
        if len(adapter_items) > 512:
            raise MigrationRegistryError("FMEA_MIGRATION_REGISTRY_INVALID", "migration adapter allowlist is too large")
        for adapter in adapter_items:
            try:
                source = _identity(getattr(adapter, "source_identity", None), "source_identity")
                target = _identity(getattr(adapter, "target_identity", None), "target_identity")
                adapter_id = _adapter_id(source, target, adapter)
                MigrationStep(source=source, target=target, adapter_id=adapter_id)
            except MigrationRegistryError:
                raise
            except Exception as exc:
                raise MigrationRegistryError(
                    "FMEA_MIGRATION_REGISTRY_INVALID", "migration adapter registration is invalid"
                ) from exc
            if source == target or source[0] != target[0]:
                raise MigrationRegistryError(
                    "FMEA_MIGRATION_REGISTRY_INVALID", "migration adapter identities are invalid"
                )
            if not callable(getattr(adapter, "migrate", None)):
                raise MigrationRegistryError("FMEA_MIGRATION_REGISTRY_INVALID", "migration adapter is not callable")
            if any(item.adapter_id == adapter_id for item in registered):
                raise MigrationRegistryError("FMEA_MIGRATION_REGISTRY_INVALID", "migration adapter ids must be unique")
            registered.append(_RegisteredAdapter(source, target, adapter_id, adapter))
        self._adapters = tuple(registered)

    @property
    def adapters(self) -> tuple[MigrationAdapter, ...]:
        return tuple(item.adapter for item in self._adapters)

    def _paths(
        self,
        source: tuple[str, str],
        target: tuple[str, str],
        current: tuple[str, str],
        visited: frozenset[tuple[str, str]],
    ) -> tuple[tuple[_RegisteredAdapter, ...], ...]:
        if current == target:
            return ((),)
        paths: list[tuple[_RegisteredAdapter, ...]] = []
        next_edges = sorted(
            (item for item in self._adapters if item.source == current),
            key=lambda item: (item.target, item.adapter_id),
        )
        for edge in next_edges:
            if edge.target in visited:
                raise MigrationRegistryError("FMEA_MIGRATION_EDGE_CYCLIC", "migration graph contains a cycle")
            if edge.target[0] != source[0]:
                continue
            for suffix in self._paths(source, target, edge.target, visited | {edge.target}):
                paths.append((edge, *suffix))
                if len(paths) > 1:
                    return tuple(paths)
        return tuple(paths)

    def _assert_reachable_acyclic(self, source: tuple[str, str]) -> None:
        colors: dict[tuple[str, str], int] = {}

        def visit(node: tuple[str, str]) -> None:
            color = colors.get(node, 0)
            if color == 1:
                raise MigrationRegistryError("FMEA_MIGRATION_EDGE_CYCLIC", "migration graph contains a cycle")
            if color == 2:
                return
            colors[node] = 1
            for edge in self._adapters:
                if edge.source == node and edge.target[0] == source[0]:
                    visit(edge.target)
            colors[node] = 2

        visit(source)

    def resolve(self, source: tuple[str, str], target: tuple[str, str]) -> MigrationPlan:
        source_identity = _identity(source, "migration source")
        target_identity = _identity(target, "migration target")
        if source_identity[0] != target_identity[0]:
            raise MigrationRegistryError(
                "FMEA_MIGRATION_EDGE_MISSING", "migration source and target domain packs differ"
            )
        self._assert_reachable_acyclic(source_identity)
        paths = self._paths(source_identity, target_identity, source_identity, frozenset({source_identity}))
        if not paths:
            raise MigrationRegistryError("FMEA_MIGRATION_EDGE_MISSING", "no explicit migration path is registered")
        if len(paths) > 1:
            raise MigrationRegistryError(
                "FMEA_MIGRATION_EDGE_AMBIGUOUS", "multiple explicit migration paths are registered"
            )
        try:
            steps = tuple(MigrationStep(edge.source, edge.target, edge.adapter_id) for edge in paths[0])
            return MigrationPlan(source_identity, target_identity, steps)
        except (TypeError, ValueError) as exc:
            raise MigrationRegistryError(
                "FMEA_MIGRATION_REGISTRY_INVALID", "registered migration path is invalid"
            ) from exc

    def adapter_for(self, step: MigrationStep) -> MigrationAdapter:
        for registered in self._adapters:
            if (
                registered.source == step.source
                and registered.target == step.target
                and registered.adapter_id == step.adapter_id
            ):
                return registered.adapter
        raise MigrationRegistryError("FMEA_MIGRATION_EDGE_MISSING", "migration adapter is not registered")


__all__ = ["MigrationRegistry", "MigrationRegistryError"]
