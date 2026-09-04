"""
Real-Time Trend & Topic Detection Engine for Social Threat Intelligence
SIH 2026 PS:152 - National Technical Research Organisation (NTRO)

Computes:
- Velocity (rate of change in volume)
- Acceleration (rate of change in velocity / momentum predictor)
- Kleinberg Burst Z-score (deviation against historical window baselines)
- Threat-Weighted Surge Scores (fusing acceleration, content toxicity, and co-occurrence degree)
- Louvain Community Topic Detection on Hashtag Co-occurrence Graphs
- Chronological Narrative Drift & Shifting Discourse (Jaccard similarity overlap)
- Unified Top 200 Trending Hashtags Ranking & Synchronization
"""

import itertools
import logging
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from networkx.algorithms import community

# Ensure current and project root are in sys.path for trending_hashtag_manager
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)
_PROJECT_ROOT = (
    os.path.dirname(_CURRENT_DIR)
    if os.path.basename(_CURRENT_DIR) == "trend-analytics-engine"
    else _CURRENT_DIR
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from trending_hashtag_manager import get_trending_hashtag_manager
except ImportError:
    try:
        from trend_analytics_engine.trending_hashtag_manager import (
            get_trending_hashtag_manager,
        )
    except ImportError:
        get_trending_hashtag_manager = None

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


class TrendAndTopicEngine:
    """
    Real-Time Trend & Topic Detection Engine for Social Threat Intelligence:
    - Analyzes chronological streams of social events & hashtags.
    - Computes mathematical trend dynamics: Velocity, Acceleration, and Kleinberg Z-score bursts.
    - Generates Threat-Weighted Surge Scores combining volume acceleration and toxicity.
    - Constructs Hashtag Co-occurrence Graphs and performs Louvain Community Detection to track topic clusters.
    - Identifies Shifting Discussions & Thematic Drift between chronological time windows.
    - Ranks and synchronizes the dynamic Top 200 Trending Hashtags radar.
    """

    def __init__(self, baseline_window_count: int = 4):
        self.baseline_window_count = baseline_window_count
        # Historical frequency tracking: hashtag -> list of frequencies per historical window
        self.history_frequencies: Dict[str, List[int]] = defaultdict(list)
        self.previous_window_freq: Dict[str, int] = defaultdict(int)
        self.previous_window_velocities: Dict[str, float] = defaultdict(float)
        self.previous_clusters: List[Dict[str, Any]] = []

    @staticmethod
    def parse_iso_timestamp(ts_str: str) -> Optional[datetime]:
        """Safely parses multiple ISO/SQL datetime formats into UTC datetime."""
        if not ts_str:
            return None
        ts_clean = str(ts_str).strip()
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(ts_clean, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        try:
            from dateutil import parser

            dt = parser.parse(ts_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def build_cooccurrence_graph(self, events: List[Dict[str, Any]]) -> nx.Graph:
        """
        Constructs an undirected weighted graph of co-occurring hashtags
        from a batch or window of events.
        """
        G = nx.Graph()
        tag_stats = defaultdict(
            lambda: {"count": 0, "total_toxicity": 0.0, "total_sentiment": 0.0}
        )

        for event in events:
            raw_tags = event.get("hashtags", [])
            if not raw_tags and "entities" in event:
                raw_tags = event["entities"].get("hashtags", [])

            clean_tags = sorted(list({t.lower().lstrip("#") for t in raw_tags if t}))
            if not clean_tags:
                continue

            nlp = event.get("nlp_enrichment", {})
            toxicity = float(
                event.get("toxicity_score", nlp.get("toxicity_score", 0.0)) or 0.0
            )
            sentiment = float(
                event.get("sentiment_score", nlp.get("sentiment_score", 0.0)) or 0.0
            )

            for tag in clean_tags:
                tag_stats[tag]["count"] += 1
                tag_stats[tag]["total_toxicity"] += toxicity
                tag_stats[tag]["total_sentiment"] += sentiment

            # Connect pairwise co-occurrences
            for h1, h2 in itertools.combinations(clean_tags, 2):
                if G.has_edge(h1, h2):
                    G[h1][h2]["weight"] += 1.0
                else:
                    G.add_edge(h1, h2, weight=1.0)

        # Set node attributes
        for tag, stats in tag_stats.items():
            avg_tox = stats["total_toxicity"] / max(stats["count"], 1)
            avg_sent = stats["total_sentiment"] / max(stats["count"], 1)
            G.add_node(
                tag,
                frequency=stats["count"],
                avg_toxicity=round(avg_tox, 3),
                avg_sentiment=round(avg_sent, 3),
            )

        return G

    def detect_topic_clusters(self, G_cooccur: nx.Graph) -> List[Dict[str, Any]]:
        """
        Executes Louvain Community Detection on the hashtag co-occurrence graph
        to group related keywords into semantic discussion topics.
        """
        if len(G_cooccur) == 0:
            return []

        try:
            communities = list(
                community.louvain_communities(
                    G_cooccur, weight="weight", resolution=1.0
                )
            )
        except Exception:
            communities = list(nx.connected_components(G_cooccur))

        topic_clusters = []
        for c_idx, comm in enumerate(communities):
            if not comm:
                continue
            ranked_tags = sorted(
                comm,
                key=lambda t: (
                    G_cooccur.nodes[t].get("frequency", 1)
                    * (G_cooccur.degree(t, weight="weight") + 1)
                ),
                reverse=True,
            )

            primary_theme = ranked_tags[0]
            cluster_freq = sum(G_cooccur.nodes[t].get("frequency", 1) for t in comm)
            avg_tox = sum(
                G_cooccur.nodes[t].get("avg_toxicity", 0.0) for t in comm
            ) / len(comm)

            topic_clusters.append(
                {
                    "cluster_id": f"TOPIC_{c_idx + 1:02d}",
                    "primary_tag": primary_theme,
                    "top_keywords": ranked_tags[:6],
                    "all_tags": set(comm),
                    "cluster_size": len(comm),
                    "total_volume": cluster_freq,
                    "avg_toxicity": round(avg_tox, 3),
                    "is_high_threat": avg_tox >= 0.25,
                }
            )

        topic_clusters.sort(key=lambda c: c["total_volume"], reverse=True)
        return topic_clusters

    def compute_trending_metrics(
        self,
        current_events: List[Dict[str, Any]],
        dt_hours: float = 1.0,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculates Velocity, Acceleration, Z-Score, and Threat-Weighted Surge Scores
        for all hashtags in the current temporal window.
        """
        curr_freq: Dict[str, int] = Counter()
        curr_tox: Dict[str, float] = defaultdict(float)

        for event in current_events:
            raw_tags = event.get("hashtags", [])
            if not raw_tags and "entities" in event:
                raw_tags = event["entities"].get("hashtags", [])

            clean_tags = {t.lower().lstrip("#") for t in raw_tags if t}
            nlp = event.get("nlp_enrichment", {})
            tox = float(
                event.get("toxicity_score", nlp.get("toxicity_score", 0.0)) or 0.0
            )

            for tag in clean_tags:
                curr_freq[tag] += 1
                curr_tox[tag] += tox

        G_cooccur = self.build_cooccurrence_graph(current_events)

        metrics = {}
        all_tags = set(curr_freq.keys()) | set(self.previous_window_freq.keys())

        for tag in all_tags:
            f_curr = curr_freq.get(tag, 0)
            f_prev = self.previous_window_freq.get(tag, 0)
            v_prev = self.previous_window_velocities.get(tag, 0.0)

            # 1. Velocity: rate of change in mentions per unit time
            velocity = (f_curr - f_prev) / max(dt_hours, 0.1)

            # 2. Acceleration: rate of change in velocity (rising momentum predictor)
            acceleration = (velocity - v_prev) / max(dt_hours, 0.1)

            # 3. Kleinberg Burst Z-Score: comparison against historical baseline
            history = self.history_frequencies.get(tag, [])
            if len(history) >= 2:
                mu = sum(history) / len(history)
                variance = sum((x - mu) ** 2 for x in history) / len(history)
                sigma = math.sqrt(variance)
                z_score = (f_curr - mu) / (sigma + 1.0)
            else:
                z_score = float(f_curr - f_prev)

            avg_toxicity = (curr_tox[tag] / max(f_curr, 1)) if f_curr > 0 else 0.0
            degree = G_cooccur.degree(tag, weight="weight") if tag in G_cooccur else 0

            # 4. Threat-Weighted Surge Index:
            growth_factor = max(0.0, velocity)
            threat_mult = 1.0 + (avg_toxicity * 2.5)
            network_reach = math.log2(2.0 + degree)
            surge_score = growth_factor * threat_mult * network_reach

            is_rising = (acceleration > 0.0) and (velocity > 0.0) and (f_curr >= 2)

            metrics[tag] = {
                "tag": tag,
                "current_volume": f_curr,
                "previous_volume": f_prev,
                "velocity": round(velocity, 2),
                "acceleration": round(acceleration, 2),
                "z_score": round(z_score, 2),
                "degree": degree,
                "avg_toxicity": round(avg_toxicity, 3),
                "surge_score": round(surge_score, 2),
                "is_rising": is_rising,
            }

        # Update historical state
        for tag in set(curr_freq.keys()):
            self.history_frequencies[tag].append(curr_freq[tag])
            if len(self.history_frequencies[tag]) > self.baseline_window_count:
                self.history_frequencies[tag].pop(0)

        self.previous_window_freq = curr_freq
        self.previous_window_velocities = {t: m["velocity"] for t, m in metrics.items()}

        return metrics

    def detect_shifting_discussions(
        self, current_clusters: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Compares current topic clusters with previous window clusters using Jaccard similarity.
        Detects newly emerging topics, drifting narratives, and escalating hostility.
        """
        shifts = []
        if not self.previous_clusters:
            self.previous_clusters = current_clusters
            for c in current_clusters:
                shifts.append(
                    {
                        "type": "INITIAL_TOPIC",
                        "topic": c["primary_tag"],
                        "keywords": c["top_keywords"],
                        "volume": c["total_volume"],
                        "toxicity": c["avg_toxicity"],
                        "note": "Initial baseline discussion cluster established.",
                    }
                )
            return shifts

        for curr_c in current_clusters:
            curr_tags = curr_c["all_tags"]
            best_match = None
            max_jaccard = 0.0

            for prev_c in self.previous_clusters:
                prev_tags = prev_c["all_tags"]
                intersection = curr_tags & prev_tags
                union = curr_tags | prev_tags
                jaccard = len(intersection) / len(union) if union else 0.0

                if jaccard > max_jaccard:
                    max_jaccard = jaccard
                    best_match = prev_c

            if max_jaccard < 0.20:
                shifts.append(
                    {
                        "type": "NEW_EMERGING_TOPIC",
                        "topic": curr_c["primary_tag"],
                        "keywords": curr_c["top_keywords"],
                        "volume": curr_c["total_volume"],
                        "toxicity": curr_c["avg_toxicity"],
                        "jaccard_continuity": round(max_jaccard, 2),
                        "note": "Sudden thematic shift: brand new discussion cluster emerged.",
                    }
                )
            elif best_match and (
                curr_c["avg_toxicity"] - best_match["avg_toxicity"] >= 0.15
            ):
                shifts.append(
                    {
                        "type": "ESCALATING_HOSTILITY",
                        "topic": curr_c["primary_tag"],
                        "keywords": curr_c["top_keywords"],
                        "volume": curr_c["total_volume"],
                        "prev_toxicity": best_match["avg_toxicity"],
                        "toxicity": curr_c["avg_toxicity"],
                        "jaccard_continuity": round(max_jaccard, 2),
                        "note": "Hostility escalation: discourse became significantly more toxic.",
                    }
                )
            elif max_jaccard < 0.50:
                shifts.append(
                    {
                        "type": "DRIFTING_NARRATIVE",
                        "topic": curr_c["primary_tag"],
                        "keywords": curr_c["top_keywords"],
                        "volume": curr_c["total_volume"],
                        "toxicity": curr_c["avg_toxicity"],
                        "jaccard_continuity": round(max_jaccard, 2),
                        "note": f"Discussion drifting from '{best_match['primary_tag']}' into new sub-topics.",
                    }
                )

        self.previous_clusters = current_clusters
        return shifts

    def get_top_trending_hashtags(
        self, metrics: Dict[str, Dict[str, Any]], top_n: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Computes the Unified Trend Score across all active and historical hashtags:
        Score = Surge_Score * 0.40 + Volume * 0.25 + max(0, Acceleration) * 0.20 + Z_Score * 0.15
        Returns the ranked list of top_n trending hashtags.
        """
        ranked = []
        for tag, m in metrics.items():
            curr_vol = m.get("current_volume", 0)
            surge = m.get("surge_score", 0.0)
            accel = m.get("acceleration", 0.0)
            z = m.get("z_score", 0.0)
            tox = m.get("avg_toxicity", 0.0)
            vel = m.get("velocity", 0.0)

            unified_score = (
                surge * 0.40
                + min(curr_vol, 500) * 0.25
                + max(0.0, accel) * 0.20
                + max(0.0, z) * 0.15
            )

            ranked.append(
                {
                    "rank": 0,
                    "tag": tag,
                    "hashtag": f"#{tag}",
                    "unified_score": round(unified_score, 2),
                    "volume": curr_vol,
                    "velocity": vel,
                    "acceleration": accel,
                    "surge_score": surge,
                    "z_score": z,
                    "avg_toxicity": tox,
                    "is_rising": m.get("is_rising", False),
                    "degree": m.get("degree", 0),
                    "tier": 1,
                }
            )

        ranked.sort(key=lambda x: x["unified_score"], reverse=True)
        for idx, item in enumerate(ranked[:top_n], start=1):
            item["rank"] = idx
            item["tier"] = 1 if idx <= 25 else 2

        return ranked[:top_n]

    def analyze_window(
        self,
        events: List[Dict[str, Any]],
        dt_hours: float = 1.0,
        top_n: int = 200,
        sync_to_manager: bool = True,
    ) -> Dict[str, Any]:
        """
        End-to-end window analysis returning:
        1. Ranked Top 200 Trending Hashtags (Unified Trend Score)
        2. Ranked Rising Trends (Highest Acceleration & Surge Index)
        3. Ranked Viral Keywords (Highest Current Volume & Reach)
        4. Topic Clusters (Louvain Communities)
        5. Shifting Discussions (Narrative Drift & Hostility Escalation)
        6. Synchronizes active metrics with the central TrendingHashtagManager.
        """
        G_cooccur = self.build_cooccurrence_graph(events)
        metrics = self.compute_trending_metrics(events, dt_hours=dt_hours)
        clusters = self.detect_topic_clusters(G_cooccur)
        shifts = self.detect_shifting_discussions(clusters)

        # 1. Top Trending Hashtags (Unified Trend Ranking)
        top_trends = self.get_top_trending_hashtags(metrics, top_n=top_n)

        # 2. Rising Trends: Positive acceleration + surge score (predictive)
        rising_trends = sorted(
            [m for m in metrics.values() if m["is_rising"]],
            key=lambda m: (m["acceleration"], m["surge_score"]),
            reverse=True,
        )

        # 3. Viral Keywords: Top by raw volume and network connectivity
        viral_keywords = sorted(
            [m for m in metrics.values() if m["current_volume"] > 0],
            key=lambda m: (m["current_volume"], m["degree"]),
            reverse=True,
        )

        # Synchronize with TrendingHashtagManager for scraper consumption
        if sync_to_manager and get_trending_hashtag_manager is not None:
            try:
                mgr = get_trending_hashtag_manager()
                mgr.update_from_trend_metrics(metrics, topic_clusters=clusters)
            except Exception as e:
                logging.warning(f"Failed to sync trend metrics to manager: {e}")

        return {
            "top_200_trends": top_trends,
            "rising_trends": rising_trends[:top_n],
            "viral_keywords": viral_keywords[:top_n],
            "topic_clusters": clusters[:10],
            "shifting_discussions": shifts,
            "total_hashtags_analyzed": len(metrics),
            "cooccurrence_graph_edges": G_cooccur.number_of_edges(),
        }

    def generate_trend_payload(
        self,
        analysis: Dict[str, Any],
        lookback_hours: float = 4.0,
        cycle_index: int = 0,
        events_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Formats the standardized output intelligence payload for the Trend Analytics Engine.
        Directly consumable by dashboards, security analysts, downstream Kafka topics, and live scrapers.
        """
        top_200 = analysis.get("top_200_trends", [])
        rising = analysis.get("rising_trends", [])
        viral = analysis.get("viral_keywords", [])
        clusters = analysis.get("topic_clusters", [])
        shifts = analysis.get("shifting_discussions", [])

        top_surging = rising[0] if rising else (top_200[0] if top_200 else None)

        scraper_directives = {}
        if get_trending_hashtag_manager is not None:
            try:
                mgr = get_trending_hashtag_manager()
                scraper_directives = {
                    "tier1_critical_targets": mgr.get_tier1_hashtags()[:10],
                    "query_batches_count": len(
                        mgr.get_search_query_batches(cycle_index=cycle_index)
                    ),
                    "sample_query_batch": mgr.get_search_query_batches(
                        cycle_index=cycle_index
                    )[0]
                    if mgr.trending_pool
                    else "",
                }
            except Exception:
                pass

        serializable_clusters = []
        for c in clusters[:6]:
            c_dict = dict(c)
            if isinstance(c_dict.get("all_tags"), set):
                c_dict["all_tags"] = sorted(list(c_dict["all_tags"]))
            serializable_clusters.append(c_dict)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "window_summary": {
                "lookback_hours": lookback_hours,
                "events_processed": events_count,
                "total_unique_hashtags": analysis.get("total_hashtags_analyzed", 0),
                "cooccurrence_graph_edges": analysis.get("cooccurrence_graph_edges", 0),
            },
            "top_surging_threat_trend": top_surging,
            "top_200_trending_radar": top_200,
            "rising_trends": rising[:10],
            "viral_keywords": viral[:10],
            "topic_clusters": serializable_clusters,
            "shifting_discussions": shifts,
            "scraper_directives": scraper_directives,
        }
