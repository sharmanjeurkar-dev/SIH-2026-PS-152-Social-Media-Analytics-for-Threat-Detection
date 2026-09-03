from src.GraphAlgorithms.graph_extraction import SubGraphExtraction
from src.GraphAlgorithms.network_algorithms import NetworkAnalyticsEngine
from src.GraphDB.connection import Neo4jConnection


def test_algorithms():
    Neo4jConnection.init_schema()

    # 1. Extract Subgraph
    loader = SubGraphExtraction()
    G, metadata = loader.load_subgraphs_into_networkx()

    print(
        f"\n[INFO] Extraction Complete: {G.number_of_nodes()} Nodes, {G.number_of_edges()} Edges."
    )

    if G.number_of_nodes() == 0:
        print("[WARN] Graph is empty. Ingest data first.")
        Neo4jConnection.close()
        return

    if G.number_of_edges() == 0:
        print(
            "[WARN] Nodes exist, but 0 interaction edges were found. Algorithms require edges to calculate centrality."
        )
        Neo4jConnection.close()
        return

    # 2. Run Analytics Engine
    analytics = NetworkAnalyticsEngine()
    communities = analytics.compute_communities(G)
    centrality = analytics.compute_centrality_metrics(G)

    print("\n--- ALGORITHMIC ANALYTICS RESULTS ---")
    for node_id in list(G.nodes)[:5]:
        print(f"Node: {node_id}")
        print(f"  -> Community: {communities.get(node_id, 'UNKNOWN')}")
        print(f"  -> Centrality: {centrality.get(node_id, {})}")

    Neo4jConnection.close()


if __name__ == "__main__":
    test_algorithms()
