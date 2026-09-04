import json
import logging
import math
import os
import signal
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure root of graph-network-engine is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import numpy as np
import torch
from pydantic import ValidationError
from torch_geometric.data import Data
from torch_geometric.utils import to_undirected

try:
    from kafka import KafkaConsumer
except ImportError:
    KafkaConsumer = None

from src.GraphAlgorithms.trend_topic_engine import TrendAndTopicEngine
from src.GraphDB.connection import Neo4jConnection
from src.GraphDB.ingestion import EnrichedSocialEvent, GraphInjestor
from src.model.gnnmodel import ThreatGraphSAGE

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


# =========================================================================
# 1. Real-Time Inductive GNN Threat Inference Engine
# =========================================================================
class LiveThreatInferenceEngine:
    """
    Executes real-time inductive threat classification using ThreatGraphSAGE.
    Queries the local multi-hop neighborhood for newly ingested users,
    computes graph and NLP features, runs GNN forward inference, writes predictions
    back to Neo4j, and emits security alerts for detected Bots and Malicious Actors.
    """

    def __init__(self, model_path: Optional[str] = None):
        if model_path is None:
            model_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "../../models/threat_graphsage.pt"
                )
            )
        self.model_path = model_path
        self.num_features = 8
        self.target_classifiers = 3
        self.class_map = {0: "ORGANIC_USER", 1: "BOT", 2: "MALICIOUS_ACTOR"}
        self.driver = Neo4jConnection.get_driver()

        self.model = ThreatGraphSAGE(
            in_channels=self.num_features,
            hidden_channels=32,
            out_channels=self.target_classifiers,
            dropout=0.0,
        )

        if os.path.exists(self.model_path):
            try:
                state_dict = torch.load(self.model_path, map_location="cpu")
                self.model.load_state_dict(state_dict)
                self.model.eval()
                logging.info(
                    f"[GNN INFERENCE] Loaded trained model checkpoint from: {self.model_path}"
                )
            except Exception as e:
                logging.error(f"[GNN INFERENCE] Failed to load model weights: {e}")
        else:
            logging.warning(
                f"[GNN INFERENCE] Checkpoint not found at: {self.model_path}. "
                "Ensure training_gnn_model.py has been run."
            )

    LOCAL_SUBGRAPH_QUERY = """
    MATCH (u:User)
    WHERE u.user_id IN $user_ids
    OPTIONAL MATCH (u)-[r_out:INTERACTED_WITH]->(out_n:User)
    OPTIONAL MATCH (in_n:User)-[r_in:INTERACTED_WITH]->(u)
    OPTIONAL MATCH (u)-[:POSTED]->(p:Post)
    RETURN 
        u.user_id AS user_id,
        u.handle AS handle,
        coalesce(u.followers_count, 0) AS followers,
        coalesce(u.following_count, 0) AS following,
        count(DISTINCT in_n) AS in_degree,
        count(DISTINCT out_n) AS out_degree,
        avg(coalesce(p.toxicity_score, 0.0)) AS avg_toxicity,
        avg(coalesce(p.sentiment_score, 0.0)) AS avg_sentiment,
        count(DISTINCT p) AS post_count,
        collect(DISTINCT out_n.user_id) + collect(DISTINCT in_n.user_id) AS neighbor_ids
    """

    LOCAL_EDGES_QUERY = """
    MATCH (s:User)-[r:INTERACTED_WITH]->(t:User)
    WHERE s.user_id IN $node_ids AND t.user_id IN $node_ids
    RETURN s.user_id AS source, t.user_id AS target
    """

    UPDATE_USER_PREDICTION_CYPHER = """
    UNWIND $predictions AS pred
    MATCH (u:User {user_id: pred.user_id})
    SET u.threat_label = pred.threat_label,
        u.threat_confidence = pred.threat_confidence,
        u.last_classified_at = timestamp()
    """

    def infer_users(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Runs inductive inference on a batch of target user IDs.
        Returns prediction dictionaries and persists results to Neo4j.
        """
        if not user_ids:
            return []

        clean_user_ids = list(set([u for u in user_ids if u and u != "None"]))
        if not clean_user_ids:
            return []

        # 1. Fetch user metrics and neighbors from Neo4j
        nodes_data = {}
        all_node_ids = set(clean_user_ids)

        with self.driver.session() as session:
            result = session.run(self.LOCAL_SUBGRAPH_QUERY, user_ids=clean_user_ids)
            for row in result:
                uid = row["user_id"]
                neighbors = [n for n in (row["neighbor_ids"] or []) if n]
                all_node_ids.update(neighbors)
                nodes_data[uid] = {
                    "user_id": uid,
                    "handle": row["handle"] or uid,
                    "followers": float(row["followers"] or 0),
                    "following": float(row["following"] or 0),
                    "in_degree": float(row["in_degree"] or 0),
                    "out_degree": float(row["out_degree"] or 0),
                    "toxicity": float(row["avg_toxicity"] or 0.0),
                    "sentiment": float(row["avg_sentiment"] or 0.0),
                    "post_count": int(row["post_count"] or 0),
                }

            if not nodes_data:
                return []

            # 2. Fetch edges among target nodes and their neighbors
            edges_result = session.run(
                self.LOCAL_EDGES_QUERY, node_ids=list(all_node_ids)
            )
            raw_edges = [(r["source"], r["target"]) for r in edges_result]

        # 3. Construct PyG feature tensor
        ordered_nodes = list(nodes_data.keys())
        node_to_idx = {uid: idx for idx, uid in enumerate(ordered_nodes)}

        feature_matrix = []
        for uid in ordered_nodes:
            d = nodes_data[uid]
            in_deg = d["in_degree"]
            out_deg = d["out_degree"]
            amp_ratio = (in_deg + 1.0) / (out_deg + 1.0)
            followers = d["followers"]
            following = d["following"]
            follower_ratio = (followers + 1.0) / (followers + following + 2.0)
            toxicity = d["toxicity"]

            # Approximate PageRank scaled to match global social graph scale
            pr_approx = (in_deg + 1.0) / 50000.0

            feat = [
                min(math.log1p(in_deg) / 5.0, 1.0),
                min(math.log1p(out_deg) / 5.0, 1.0),
                min(amp_ratio / 5.0, 1.0),
                min(pr_approx * 10000.0, 1.0),
                min(math.log1p(followers) / 10.0, 1.0),
                min(math.log1p(following) / 10.0, 1.0),
                min(follower_ratio, 1.0),
                min(toxicity, 1.0),
            ]
            feature_matrix.append(feat)

        x_tensor = torch.tensor(feature_matrix, dtype=torch.float)

        # 4. Construct edge index
        mapped_edges = [
            (node_to_idx[s], node_to_idx[t])
            for s, t in raw_edges
            if s in node_to_idx and t in node_to_idx
        ]

        if mapped_edges:
            directed_edges = (
                torch.tensor(mapped_edges, dtype=torch.long).t().contiguous()
            )
            edge_index = to_undirected(directed_edges, num_nodes=len(ordered_nodes))
        else:
            edge_index = torch.empty((2, 0), dtype=torch.long)

        # 5. Model forward pass
        self.model.eval()
        with torch.no_grad():
            logits = self.model(x_tensor, edge_index)
            probabilities = torch.exp(logits)
            predictions = logits.argmax(dim=1)

        # 6. Parse and format results
        results = []
        for idx, uid in enumerate(ordered_nodes):
            pred_class_idx = predictions[idx].item()
            pred_class_label = self.class_map[pred_class_idx]
            confidence = probabilities[idx][pred_class_idx].item()
            d = nodes_data[uid]

            pred_dict = {
                "user_id": uid,
                "handle": d["handle"],
                "threat_label": pred_class_label,
                "threat_confidence": round(confidence, 3),
                "bot_probability": round(probabilities[idx][1].item(), 4),
                "malicious_user_probability": round(probabilities[idx][2].item(), 4),
                "ordinary_user_probability": round(probabilities[idx][0].item(), 4),
                "followers": int(d["followers"]),
                "following": int(d["following"]),
                "avg_toxicity": round(d["toxicity"], 3),
            }
            results.append(pred_dict)

            # Emit real-time security alert for flagged threats
            if pred_class_label in ["BOT", "MALICIOUS_ACTOR"] and confidence >= 0.35:
                icon = (
                    "🤖 [BOT ALERT]"
                    if pred_class_label == "BOT"
                    else "🚨 [MALICIOUS ACTOR ALERT]"
                )
                logging.warning(
                    f"{icon} Flagged @{d['handle']} ({uid}) as {pred_class_label} "
                    f"with {confidence * 100:.1f}% confidence | "
                    f"Followers: {int(d['followers'])}, Following: {int(d['following'])}, "
                    f"Toxicity: {d['toxicity']:.2f}"
                )

        # 7. Compute batch-level Network Feedback Payload
        density = 0.0
        pr_max = 0.0
        cluster_cnt = 1
        if len(ordered_nodes) > 1 and mapped_edges:
            import networkx as nx
            from networkx.algorithms import community

            G_sub = nx.DiGraph()
            for s, t in mapped_edges:
                G_sub.add_edge(s, t)
            density = round(float(nx.density(G_sub)), 6)
            try:
                pr_scores = nx.pagerank(G_sub, alpha=0.85)
                pr_max = round(float(max(pr_scores.values())), 6)
            except Exception:
                pr_max = 0.0
            try:
                comm_list = list(community.louvain_communities(G_sub.to_undirected()))
                cluster_cnt = len(comm_list)
            except Exception:
                cluster_cnt = 1

        self.last_network_payload = {
            "graph_density": density,
            "super_spreader_pagerank_max": pr_max,
            "bot_probability": round(float(probabilities[:, 1].mean().item()), 4),
            "malicious_user_probability": round(
                float(probabilities[:, 2].mean().item()), 4
            ),
            "ordinary_user_probability": round(
                float(probabilities[:, 0].mean().item()), 4
            ),
            "louvain_cluster_count": cluster_cnt,
        }
        logging.info(f"[NETWORK FEEDBACK PAYLOAD] {self.last_network_payload}")

        # 8. Persist classification to Neo4j
        with self.driver.session() as session:
            try:
                session.run(self.UPDATE_USER_PREDICTION_CYPHER, predictions=results)
            except Exception as e:
                logging.error(
                    f"[GNN INFERENCE] Failed to persist predictions to Neo4j: {e}"
                )

        return results


# =========================================================================
# 2. Live Graph Stream Consumer with Integrated Inference
# =========================================================================
class LiveGraphStreamConsumer:
    """
    Consumes enriched threat events from Member 2 via Kafka,
    validates payloads with Pydantic, writes micro-batches into Neo4j,
    and executes real-time inductive GNN threat classification.
    """

    def __init__(
        self,
        topic: str = "enriched-threat-stream",
        bootstrap_servers: str = "localhost:9092",
        batch_size: int = 20,
        flush_interval_secs: float = 3.0,
    ):
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.batch_size = batch_size
        self.flush_interval_secs = flush_interval_secs

        self.ingestor = GraphInjestor()
        self.inference_engine = LiveThreatInferenceEngine()
        self.trend_engine = TrendAndTopicEngine(baseline_window_count=5)
        self.sliding_window_events: List[dict] = []
        Neo4jConnection.init_schema()

        self.buffer: List[dict] = []
        self.last_flush_time = time.time()
        self.is_running = True

        # Handle graceful shutdown on Ctrl+C
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame):
        logging.info("Shutdown signal received. Flushing remaining buffer to Neo4j...")
        self.is_running = False

    def _flush_buffer(self):
        """Flushes the current micro-batch to Neo4j, triggers live GNN inference, and runs trend detection."""
        if not self.buffer:
            return

        batch_count = len(self.buffer)
        users_to_classify = set()

        # Collect user IDs from the batch for live inference
        for event in self.buffer:
            author = event.get("author", {})
            if author.get("user_id"):
                users_to_classify.add(author["user_id"])
            interactions = event.get("interactions", {})
            if interactions.get("target_user_id"):
                users_to_classify.add(interactions["target_user_id"])
            for m_id in interactions.get("mentioned_user_ids", []):
                if m_id:
                    users_to_classify.add(m_id)

        try:
            self.ingestor.ingest_batch(self.buffer)
            logging.info(
                f"[NEO4J LIVE FLUSH] Successfully ingested batch of {batch_count} events."
            )

            # Trigger live GNN threat classification on ingested users
            if users_to_classify:
                predictions = self.inference_engine.infer_users(list(users_to_classify))
                logging.info(
                    f"[GNN LIVE INFERENCE] Classified {len(predictions)} active users in batch."
                )

            # Trigger real-time Trend & Topic Detection across sliding window (up to 2000 events)
            self.sliding_window_events.extend(self.buffer)
            if len(self.sliding_window_events) > 2000:
                self.sliding_window_events = self.sliding_window_events[-2000:]

            if len(self.sliding_window_events) >= 3:
                trend_report = self.trend_engine.analyze_window(
                    self.sliding_window_events,
                    dt_hours=0.25,
                    top_n=200,
                    sync_to_manager=True,
                )
                top_200 = trend_report.get("top_200_trends", [])
                rising = trend_report.get("rising_trends", [])
                if rising:
                    top_trend = rising[0]
                    logging.warning(
                        f"📈 [RISING TREND ALERT] #{top_trend['tag']} surging! "
                        f"Velocity: +{top_trend['velocity']:.1f}/h | Accel: +{top_trend['acceleration']:.1f} | "
                        f"Surge Score: {top_trend['surge_score']:.1f} | Toxicity: {top_trend['avg_toxicity']:.2f}"
                    )
                if top_200:
                    logging.info(
                        f"[TREND RADAR] Dynamically maintaining {len(top_200)} trending hashtags. "
                        f"Top 3: {', '.join(['#' + t['tag'] for t in top_200[:3]])}"
                    )
                shifts = trend_report.get("shifting_discussions", [])
                for shift in shifts:
                    if shift.get("type") in [
                        "NEW_EMERGING_TOPIC",
                        "ESCALATING_HOSTILITY",
                    ]:
                        logging.warning(
                            f"⚡ [THEMATIC SHIFT] [{shift['type']}] #{shift['topic']} | {shift.get('note', '')}"
                        )

        except Exception as e:
            logging.error(f"Failed during live batch processing: {e}")
        finally:
            self.buffer.clear()
            self.last_flush_time = time.time()

    def process_incoming_event(self, raw_payload: dict):
        """Validates a single payload and appends to micro-batch buffer."""
        try:
            validated_event = EnrichedSocialEvent.model_validate(raw_payload)
            self.buffer.append(validated_event.model_dump())
            if len(self.buffer) >= self.batch_size:
                self._flush_buffer()
        except ValidationError as val_err:
            logging.warning(
                f"Skipping malformed event {raw_payload.get('post_id')}: {val_err}"
            )

    def start_listening(self):
        """Initializes Kafka consumer and begins continuous stream processing loop."""
        logging.info(
            f"Connecting to Kafka broker at {self.bootstrap_servers} on topic '{self.topic}'..."
        )

        try:
            consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=[self.bootstrap_servers],
                auto_offset_reset="latest",
                enable_auto_commit=True,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                consumer_timeout_ms=1000,
            )
            logging.info("Connected to Kafka! Awaiting live events from Member 2...")
        except Exception as e:
            logging.error(f"Could not connect to Kafka broker: {e}")
            return

        while self.is_running:
            try:
                message_pack = consumer.poll(timeout_ms=1000)
                for tp, messages in message_pack.items():
                    for message in messages:
                        self.process_incoming_event(message.value)

                if (time.time() - self.last_flush_time) >= self.flush_interval_secs:
                    self._flush_buffer()

            except Exception as loop_err:
                logging.error(f"Error during consumption loop: {loop_err}")
                time.sleep(1.0)

        # Final cleanup on exit
        self._flush_buffer()
        consumer.close()
        Neo4jConnection.close()
        logging.info("Live Graph Consumer stopped cleanly.")


# =========================================================================
# 3. Simulation & Standalone Verification Helper
# =========================================================================
def run_live_simulation():
    """Simulates live incoming events to verify real-time ingestion & GNN inference."""
    print("\n--- RUNNING LIVE GNN INFERENCE SIMULATION ---")
    consumer = LiveGraphStreamConsumer(batch_size=3, flush_interval_secs=1.0)

    # 1. Simulate an Organic Post
    event_organic = {
        "post_id": "sim_tweet_101",
        "timestamp": "2026-09-04T12:00:00Z",
        "platform": "Twitter/X",
        "author": {
            "user_id": "usr_organic_citizen_01",
            "handle": "organic_citizen_01",
            "followers_count": 850,
            "following_count": 620,
        },
        "interactions": {
            "interaction_type": "ORIGINAL_POST",
            "mentioned_user_ids": ["usr_friend_node_02"],
        },
        "entities": {"hashtags": ["#CommunityNews"]},
        "nlp_enrichment": {
            "threat_category": "BENIGN",
            "toxicity_score": 0.02,
            "sentiment_score": 0.35,
        },
    }

    # 2. Simulate a Suspicious Bot Amplifier (zero followers, spamming mentions)
    event_bot = {
        "post_id": "sim_tweet_102",
        "timestamp": "2026-09-04T12:01:00Z",
        "platform": "Twitter/X",
        "author": {
            "user_id": "usr_amplification_bot_99",
            "handle": "amplification_bot_99",
            "followers_count": 2,
            "following_count": 1800,
        },
        "interactions": {
            "interaction_type": "RETWEET",
            "target_user_id": "usr_target_influencer_01",
            "mentioned_user_ids": [
                "usr_target_influencer_01",
                "usr_organic_citizen_01",
            ],
        },
        "entities": {"hashtags": ["#SurgeHashtag", "#UrgentAction"]},
        "nlp_enrichment": {
            "threat_category": "BENIGN",
            "toxicity_score": 0.05,
            "sentiment_score": 0.0,
        },
    }

    # 3. Simulate a Malicious Hostile Actor (high toxicity, aggressive targets)
    event_malicious = {
        "post_id": "sim_tweet_103",
        "timestamp": "2026-09-04T12:02:00Z",
        "platform": "Twitter/X",
        "author": {
            "user_id": "usr_radical_agitator_07",
            "handle": "radical_agitator_07",
            "followers_count": 2400,
            "following_count": 400,
        },
        "interactions": {
            "interaction_type": "REPLY",
            "target_user_id": "usr_organic_citizen_01",
            "mentioned_user_ids": ["usr_organic_citizen_01"],
        },
        "entities": {"hashtags": ["#RiotNow", "#Attack"]},
        "nlp_enrichment": {
            "threat_category": "CALL_TO_VIOLENCE",
            "toxicity_score": 0.92,
            "sentiment_score": -0.85,
        },
    }

    print("Feeding simulated micro-batch events to LiveGraphStreamConsumer...")
    consumer.process_incoming_event(event_organic)
    consumer.process_incoming_event(event_bot)
    consumer.process_incoming_event(event_malicious)

    # Force flush to trigger GNN inference
    consumer._flush_buffer()

    print("\n--- VERIFYING PREDICTIONS WRITTEN TO NEO4J ---")
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        check_query = """
        MATCH (u:User)
        WHERE u.user_id IN ['usr_organic_citizen_01', 'usr_amplification_bot_99', 'usr_radical_agitator_07']
        RETURN u.user_id AS user_id, u.handle AS handle, u.threat_label AS label, u.threat_confidence AS confidence
        """
        records = session.run(check_query)
        for r in records:
            print(
                f"  User: {r['user_id']} (@{r['handle']}) -> Stored Threat Label: {r['label']} (Confidence: {r['confidence']})"
            )

    Neo4jConnection.close()

    print("\n--- GENERATED REAL-TIME NETWORK FEEDBACK PAYLOAD ---")
    payload = consumer.inference_engine.last_network_payload
    print(json.dumps(payload, indent=2))

    print(
        "\nLive simulation, network payload generation, and GNN inference completed successfully."
    )


if __name__ == "__main__":
    # If '--simulate' flag passed, run live simulation; otherwise start continuous Kafka listener
    if "--simulate" in sys.argv or len(sys.argv) == 1:
        run_live_simulation()
    else:
        live_consumer = LiveGraphStreamConsumer()
        live_consumer.start_listening()
