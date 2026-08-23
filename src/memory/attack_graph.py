"""Attack Path Knowledge Graph using NetworkX.

This module provides a directed property graph abstraction over NetworkX for
mapping assets, vulnerabilities, and exploitation paths during a pentest engagement.
"""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


class AttackGraph:
    """A directed property graph representing an attack surface and exploitation paths."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Initialize the graph, optionally from a serialized dict."""
        if data:
            self._graph = nx.node_link_graph(data, directed=True)
        else:
            self._graph = nx.DiGraph()

    def add_node(
        self, node_id: str, label: str, properties: dict[str, Any] | None = None
    ) -> None:
        """Add or update a node in the graph."""
        props = properties or {}
        props["label"] = label
        self._graph.add_node(node_id, **props)

    def add_edge(
        self,
        source: str,
        target: str,
        relationship: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Add a directed edge between two nodes."""
        props = properties or {}
        props["relationship"] = relationship
        self._graph.add_edge(source, target, **props)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Retrieve a node by ID, including its properties."""
        if self._graph.has_node(node_id):
            return dict(self._graph.nodes[node_id])
        return None

    def find_nodes_by_label(self, label: str) -> list[dict[str, Any]]:
        """Find all nodes matching a specific label."""
        return [
            {"id": n, **attr}
            for n, attr in self._graph.nodes(data=True)
            if attr.get("label") == label
        ]

    def shortest_path(self, source: str, target: str) -> list[str] | None:
        """Find the shortest path (node IDs) between source and target, if it exists."""
        try:
            return nx.shortest_path(self._graph, source=source, target=target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a dictionary (node-link format)."""
        return nx.node_link_data(self._graph)

    def get_statistics(self) -> dict[str, int]:
        """Return basic statistics about the graph size."""
        return {
            "num_nodes": self._graph.number_of_nodes(),
            "num_edges": self._graph.number_of_edges(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttackGraph:
        """Deserialize a graph from a dictionary."""
        return cls(data)
