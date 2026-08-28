"""Application-facing immutable propagation validation contracts.

The application layer imports these types without adding persistence,
retrieval, or model-provider behavior.  Domain validation remains the single
source of truth for topology-constrained propagation graphs.
"""

from core_domain.fmea.propagation import (
    PropagationEvidenceResolution,
    PropagationGraphRevision,
    PropagationPath,
    PropagationRulePack,
    TopologyInterface,
    TopologyNode,
    TopologySnapshot,
    validate_graph_revision,
    validate_path,
    validate_propagation_rule_pack,
    validate_topology_snapshot,
)
from core_domain.fmea.states import PropagationStatus

__all__ = [
    "PropagationEvidenceResolution",
    "PropagationGraphRevision",
    "PropagationPath",
    "PropagationRulePack",
    "PropagationStatus",
    "TopologyInterface",
    "TopologyNode",
    "TopologySnapshot",
    "validate_graph_revision",
    "validate_path",
    "validate_propagation_rule_pack",
    "validate_topology_snapshot",
]
