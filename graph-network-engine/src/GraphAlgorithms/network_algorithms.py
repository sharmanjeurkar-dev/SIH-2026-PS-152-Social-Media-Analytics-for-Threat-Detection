from __future__ import annotations

import logging
from typing import Any

import networkx as nx
from networkx.algorithms import community


class NetworkAnalyticsEngine:
    """
    Computes mathematical network algorithms on top of the extracted NetworkX graph:
    - Louvain Modularity (Community / Echo Chamber Partitioning)
    - Weighted PageRank (Super Spreader Identification)[cite: 1]
    - Betweenness Centrality (Boundary Spanner / Bridge Node Isolation)[cite: 1]
    """

    @staticmethod
    def compute_communities(G: nx.DiGraph) -> dict[str, str]:
        """
        Transforms directed graph to undirected and applies Louvain Community Detection.
        Returns a mapping of user_id -> COMMUNITY_ID.
        """
        if len(G) == 0:
            return {}

        undirected_G = G.to_undirected()
        communities = community.louvain_communities(
            undirected_G, weight="weight", resolution=1.0
        )

        node_community_map = {}
        for c_id, comm in enumerate(communities):
            for node in comm:
                node_community_map[node] = f"COMMUNITY_{c_id}"

        logging.info(f"Louvain detected {len(communities)} modular communities.")
        return node_community_map

    @staticmethod
    def compute_centrality_metrics(
        G: nx.DiGraph, sample_k: int = 100
    ) -> dict[str, dict[str, Any]]:
        """
        Calculates Weighted PageRank and Approx Betweenness Centrality.
        Uses k-node sampling to prevent O(V*E) execution hangs on large graphs.
        """
        if len(G) == 0:
            return {}

        logging.info("Computing PageRank...")
        pagerank_scores = nx.pagerank(G, weight="weight", alpha=0.85)

        logging.info(f"Computing Betweenness Centrality (sampled k={sample_k})...")
        # Sample k random pivot nodes instead of computing all 86,000 shortest paths
        k_val = min(sample_k, len(G))
        betweenness_scores = nx.betweenness_centrality(G, k=k_val, weight="weight")

        metrics = {}
        for node in G.nodes():
            pr = pagerank_scores.get(node, 0.0)
            bc = betweenness_scores.get(node, 0.0)

            # Deterministic structural threshold classification
            role = "ORGANIC_USER"
            if pr > 0.08:
                role = "SUPER_SPREADER"
            elif bc > 0.05:
                role = "BOUNDARY_SPANNER"

            metrics[node] = {
                "pagerank": round(pr, 6),
                "betweenness": round(bc, 6),
                "role_label": role,
            }

        logging.info("Centrality metrics and topological roles computed successfully.")
        return metrics
