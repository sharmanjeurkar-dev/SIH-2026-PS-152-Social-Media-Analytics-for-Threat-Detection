import os
import sys

# Ensure root of graph-network-engine is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from collections import Counter

from src.GraphAlgorithms.graph_extraction import SubGraphExtraction
from src.GraphAlgorithms.network_algorithms import NetworkAnalyticsEngine
from src.GraphDB.connection import Neo4jConnection
from src.model.gnn_pipeline import GNNPIPELINE


def test_full_analytics_pipeline():
    Neo4jConnection.init_schema()

    print("\n--- 1. PART A: EXTRACTION & DETERMINISTIC ALGORITHMS ---")
    loader = SubGraphExtraction()
    G, metadata = loader.load_subgraphs_into_networkx()

    if G.number_of_edges() == 0:
        print(
            "[WARN] Graph has no edges. Ensure you ran the training_data_ingestion.py on the dataset."
        )
        Neo4jConnection.close()
        return

    analytics = NetworkAnalyticsEngine()
    communities = analytics.compute_communities(G)

    print("\n--- 2. PART B: GRAPHSAGE INDUCTIVE CLASSIFICATION ---")
    gnn = GNNPIPELINE(hidden_dim=32)
    pyg_data, reverse_mapping = gnn.networkx_to_pyg(G, metadata)

    # Train model and get predictions
    probabilities = gnn.train_and_predict(pyg_data, epochs=40)
    predictions = probabilities.argmax(dim=1)

    print("\n--- 3. FULL GRAPH THREAT SUMMARY ---")
    class_map = {0: "ORGANIC_USER", 1: "BOT", 2: "MALICIOUS_ACTOR"}
    pred_counts = Counter([class_map[p.item()] for p in predictions])
    for label, count in pred_counts.items():
        pct = (count / len(predictions)) * 100 if len(predictions) > 0 else 0
        print(f"  {label:<16}: {count:>6} users ({pct:.2f}%)")

    print("\n--- 4. SAMPLE THREAT INTELLIGENCE OUTPUT BY CLASS ---")
    # Collect sample nodes per predicted class
    samples_per_class = {0: [], 1: [], 2: []}
    for i, node_id in enumerate(reverse_mapping):
        cls = predictions[i].item()
        if len(samples_per_class[cls]) < 3:
            conf = probabilities[i][cls].item()
            samples_per_class[cls].append((node_id, conf))

    for cls, samples in samples_per_class.items():
        print(f"\n>> Category: {class_map[cls]} (Samples: {len(samples)})")
        for node_id, conf in samples:
            meta = metadata.get(node_id, {})
            print(f"  User: {node_id} (@{meta.get('handle', 'unknown')})")
            print(f"    - Prediction: {class_map[cls]} (Confidence: {conf:.2f})")
            print(
                f"    - Followers: {meta.get('followers_count', 0)} | Following: {meta.get('following_count', 0)}"
            )
            print(
                f"    - Toxicity: {meta.get('avg_toxicity', 0.0):.3f} | Echo Chamber: {communities.get(node_id, 'UNKNOWN')}"
            )

    Neo4jConnection.close()


if __name__ == "__main__":
    test_full_analytics_pipeline()
