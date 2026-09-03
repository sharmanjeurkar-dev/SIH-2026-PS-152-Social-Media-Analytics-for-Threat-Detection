from src.gnn_model import GNNPipeline
from src.GraphAlgorithms.graph_extraction import SubGraphExtraction
from src.GraphAlgorithms.network_algorithms import NetworkAnalyticsEngine
from src.GraphDB.connection import Neo4jConnection


def test_full_analytics_pipeline():
    Neo4jConnection.init_schema()

    print("\n--- 1. PART A: EXTRACTION & DETERMINISTIC ALGORITHMS ---")
    loader = SubGraphExtraction()
    G, metadata = loader.load_subgraphs_into_networkx()

    if G.number_of_edges() == 0:
        print(
            "[WARN] Graph has no edges. Ensure you ran the direct_loader.py on the Kaggle dataset."
        )
        return

    analytics = NetworkAnalyticsEngine()
    communities = analytics.compute_communities(G)
    centrality = analytics.compute_centrality_metrics(G)

    print("\n--- 2. PART B: GRAPHSAGE INDUCTIVE CLASSIFICATION ---")
    gnn = GNNPipeline()
    pyg_data, reverse_mapping = gnn.networkx_to_pyg(G, centrality)

    # Train model and get predictions
    probabilities = gnn.train_and_predict(pyg_data, epochs=30)
    predictions = probabilities.argmax(dim=1)

    print("\n--- 3. SAMPLE THREAT INTELLIGENCE OUTPUT ---")
    class_map = {0: "ORGANIC_USER", 1: "BOT", 2: "MALICIOUS_ACTOR"}

    for i in range(5):
        node_id = reverse_mapping[i]
        predicted_class = class_map[predictions[i].item()]
        confidence = probabilities[i][predictions[i]].item()

        print(f"User: {node_id}")
        print(
            f"  -> Topological Role: {centrality.get(node_id, {}).get('role_label', 'UNKNOWN')}"
        )
        print(f"  -> GNN Prediction: {predicted_class} (Confidence: {confidence:.2f})")
        print(f"  -> Echo Chamber: {communities.get(node_id, 'UNKNOWN')}")

    Neo4jConnection.close()


if __name__ == "__main__":
    test_full_analytics_pipeline()
