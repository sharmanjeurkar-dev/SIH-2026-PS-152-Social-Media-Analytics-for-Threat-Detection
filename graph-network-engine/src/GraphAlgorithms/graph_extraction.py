import logging
from typing import Any

import networkx as nx

from src.GraphDB.connection import Neo4jConnection


class SubGraphExtraction:
    def __init__(self) -> None:
        self.driver = Neo4jConnection.get_driver()

    EXTRACT_GRAPH_QUERY = """
    // 1. Match direct interactions (Retweets, Mentions, Replies, Quotes)
    MATCH (source:User)-[r:INTERACTED_WITH]->(target:User)
    RETURN 
        source.user_id AS source_id,
        source.handle AS source_handle,
        coalesce(source.followers_count, 0) AS source_followers,
        coalesce(source.following_count, 0) AS source_following,
        target.user_id AS target_id,
        target.handle AS target_handle,
        coalesce(target.followers_count, 0) AS target_followers,
        coalesce(target.following_count, 0) AS target_following,
        r.type AS interaction_type,
        coalesce(r.weight, 1.0) AS weight

    UNION

    // 2. Match Telegram forward chains
    MATCH (source:User)-[rf:FORWARDED_FROM]->(target:User)
    RETURN 
        source.user_id AS source_id,
        source.handle AS source_handle,
        coalesce(source.followers_count, 0) AS source_followers,
        coalesce(source.following_count, 0) AS source_following,
        target.user_id AS target_id,
        target.handle AS target_handle,
        coalesce(target.followers_count, 0) AS target_followers,
        coalesce(target.following_count, 0) AS target_following,
        'FORWARD' AS interaction_type,
        1.5 AS weight
    """

    EXTRACT_USER_NLP_QUERY = """
    MATCH (u:User)-[:POSTED]->(p:Post)
    RETURN 
        u.user_id AS user_id,
        avg(p.toxicity_score) AS avg_toxicity,
        avg(p.sentiment_score) AS avg_sentiment,
        count(p) AS post_count
    """

    def load_subgraphs_into_networkx(
        self,
    ) -> tuple[nx.DiGraph, dict[str, dict[str, Any]]]:
        G = nx.DiGraph()
        node_metadata: dict[str, dict[str, Any]] = {}

        with self.driver.session() as session:
            nlp_records = session.run(self.EXTRACT_USER_NLP_QUERY)
            for record in nlp_records:
                uid = record["user_id"]
                node_metadata[uid] = {
                    "avg_toxicity": float(record["avg_toxicity"] or 0.0),
                    "avg_sentiment": float(record["avg_sentiment"] or 0.0),
                    "post_count": int(record["post_count"] or 0),
                }

            interaction_records = session.run(self.EXTRACT_GRAPH_QUERY)
            edge_count = 0
            for row in interaction_records:
                s_id = row["source_id"]
                t_id = row["target_id"]
                weight = float(row["weight"])
                itype = row["interaction_type"]

                # Ensure source metadata
                # Ensure source metadata
                if s_id not in node_metadata:
                    node_metadata[s_id] = {
                        "avg_toxicity": 0.0,
                        "avg_sentiment": 0.0,
                        "post_count": 0,
                    }
                node_metadata[s_id].update(
                    {
                        "handle": row["source_handle"],
                        "followers_count": row["source_followers"],
                        "following_count": row["source_following"],
                    }
                )

                # Ensure target metadata
                if t_id not in node_metadata:
                    node_metadata[t_id] = {
                        "avg_toxicity": 0.0,
                        "avg_sentiment": 0.0,
                        "post_count": 0,
                    }
                node_metadata[t_id].update(
                    {
                        "handle": row["target_handle"],
                        "followers_count": row["target_followers"],
                        "following_count": row["target_following"],
                    }
                )

                # Add nodes with basic features
                G.add_node(s_id, **node_metadata[s_id])
                G.add_node(t_id, **node_metadata[t_id])

                # Add directed weighted edge (aggregating if multi-edges exist)
                if G.has_edge(s_id, t_id):
                    G[s_id][t_id]["weight"] += weight
                else:
                    G.add_edge(s_id, t_id, weight=weight, interaction_type=itype)
        edge_count += 1

        logging.info(
            f"Successfully extracted subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges from {edge_count} raw relations."
        )
        return G, node_metadata
