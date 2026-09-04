"""
Trending Hashtag Manager: Centralized Dynamic 200-Hashtag Radar
Shared between Data Ingestion Scraper & Graph Network Trend Engine
SIH 2026 PS:152 - Social Media Analytics for Threat Detection
"""

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# Resolve Project Root Directory
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_CURRENT_DIR) == "trend-analytics-engine":
    PROJECT_ROOT = os.path.dirname(_CURRENT_DIR)
else:
    PROJECT_ROOT = _CURRENT_DIR

DEFAULT_REGISTRY_PATH = os.path.join(PROJECT_ROOT, "data", "trending_200_hashtags.json")

# Baseline Core Domain Threat & Protest Seed Keywords
CORE_THREAT_SEEDS = [
    "farmersprotest",
    "delhipolice",
    "nationalsecurity",
    "flashprotest",
    "section144",
    "bharatbandh",
    "civilunrest",
    "paperleak",
    "kisanandolan",
    "emergencyalert",
    "chakkajam",
    "shutdowncity",
    "cyberalert",
    "protestmarch",
    "desh_samachar_live",
    "dharna",
    "curfew",
    "jamiamillia",
    "shaheenbagh",
    "redfort",
    "parliamentmarch",
    "tractorrally",
    "modigovernment",
    "msp_guarantee",
    "anti_farmer_laws",
    "notobjp",
    "boycottbjp",
    "justiceforstudents",
    "railroko",
    "lathicharge",
    "tear_gas",
    "barricades",
    "internetshutdown",
    "delhiborder",
    "singhuborder",
    "tikriborder",
    "ghazipurborder",
    "kisanektazindabad",
    "bku",
    "standwithfarmers",
    "fakeencounter",
    "cyberwarfare",
    "propagandaalert",
    "doxxing",
    "disinformation",
    "botnetwork",
    "evmhacking",
    "deepfakealert",
    "blackday",
    "humanrightsviolation",
    "stateemergency",
    "pressfreedom",
]


class TrendingHashtagManager:
    """
    Manages the dynamic pool of the Top 200 Trending & Threat Hashtags:
    1. Bootstraps from tweets.csv dataset + high-priority threat seed taxonomy.
    2. Persists real-time state (rank, volume, velocity, acceleration, surge_score, cluster).
    3. Provides synchronized updates from Graph Trend & Topic Engine.
    4. Generates prioritized, rate-limit safe search query batches for live scraping.
    """

    def __init__(
        self, registry_path: str = DEFAULT_REGISTRY_PATH, target_count: int = 200
    ):
        self.registry_path = registry_path
        self.target_count = target_count
        self.trending_pool: List[Dict[str, Any]] = []
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        self.load_or_initialize()

    def load_or_initialize(self):
        """Loads existing 200 trending hashtags from JSON, or bootstraps initial pool."""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.trending_pool = data.get("trending_hashtags", [])
                    if len(self.trending_pool) >= self.target_count:
                        logging.info(
                            f"[HASHTAG MANAGER] Loaded {len(self.trending_pool)} trending hashtags from {self.registry_path}"
                        )
                        return
            except Exception as e:
                logging.warning(
                    f"[HASHTAG MANAGER] Failed loading existing registry ({e}). Re-initializing..."
                )

        self.bootstrap_initial_pool()

    def bootstrap_initial_pool(self):
        """Extracts top hashtags from tweets.csv combined with CORE_THREAT_SEEDS to build initial 200 pool."""
        logging.info("[HASHTAG MANAGER] Initializing dynamic 200-hashtag radar...")
        candidates = Counter()

        # 1. High-weight priority seeds
        for seed in CORE_THREAT_SEEDS:
            candidates[seed.lower()] += 1000

        # 2. Extract from tweets.csv if available
        possible_csv_paths = [
            os.path.join(PROJECT_ROOT, "graph-network-engine", "data", "tweets.csv"),
            os.path.join(PROJECT_ROOT, "data", "tweets.csv"),
        ]

        csv_found = False
        for csv_path in possible_csv_paths:
            if os.path.exists(csv_path):
                logging.info(
                    f"[HASHTAG MANAGER] Extracting top candidate hashtags from {csv_path}..."
                )
                try:
                    import pandas as pd

                    df = pd.read_csv(
                        csv_path,
                        nrows=30000,
                        usecols=lambda col: col in ["renderedContent", "text"],
                    )
                    col_name = (
                        "renderedContent" if "renderedContent" in df.columns else "text"
                    )
                    for text in df[col_name].dropna():
                        tags = re.findall(r"#(\w+)", str(text))
                        for t in tags:
                            cleaned = t.strip().lower()
                            if len(cleaned) >= 3:
                                candidates[cleaned] += 1
                    csv_found = True
                    break
                except Exception as e:
                    logging.warning(f"[HASHTAG MANAGER] Error reading tweets.csv: {e}")

        # Top 200 most frequent candidates
        most_common = candidates.most_common(self.target_count)

        # Fallback if candidates < target_count
        tag_set = {item[0] for item in most_common}
        idx = 1
        while len(tag_set) < self.target_count:
            synthetic_tag = f"threat_monitor_{idx:03d}"
            if synthetic_tag not in tag_set:
                tag_set.add(synthetic_tag)
                most_common.append((synthetic_tag, 10))
            idx += 1

        now_iso = datetime.now(timezone.utc).isoformat()
        self.trending_pool = []

        for rank, (tag, vol) in enumerate(most_common[: self.target_count], start=1):
            is_threat = any(
                s in tag
                for s in [
                    "police",
                    "alert",
                    "protest",
                    "bandh",
                    "strike",
                    "leak",
                    "morcha",
                    "jam",
                    "cyber",
                    "emergency",
                ]
            )
            self.trending_pool.append(
                {
                    "rank": rank,
                    "tag": tag,
                    "hashtag": f"#{tag}",
                    "volume": vol,
                    "velocity": 0.0,
                    "acceleration": 0.0,
                    "surge_score": round(vol * 0.1, 2),
                    "z_score": 0.0,
                    "avg_toxicity": 0.35 if is_threat else 0.05,
                    "is_threat": is_threat,
                    "tier": 1 if rank <= 25 else 2,
                    "last_updated": now_iso,
                }
            )

        self.save_registry()
        logging.info(
            f"[HASHTAG MANAGER] Initialized and saved {len(self.trending_pool)} hashtags to {self.registry_path}"
        )

    def save_registry(self):
        """Persists the 200 trending hashtags to disk."""
        data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_count": len(self.trending_pool),
            "tier1_critical_count": len(
                [h for h in self.trending_pool if h.get("tier") == 1]
            ),
            "trending_hashtags": self.trending_pool,
        }
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def update_from_trend_metrics(
        self,
        trend_metrics: Dict[str, Dict[str, Any]],
        topic_clusters: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Dynamically updates and re-ranks the 200 trending hashtags using live metrics
        computed by the Graph Trend & Topic Engine.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Cluster lookup for semantic topic attribution
        cluster_map = {}
        if topic_clusters:
            for c in topic_clusters:
                cid = c.get("cluster_id", "GENERAL")
                for t in c.get("all_tags", []):
                    cluster_map[t.lower().lstrip("#")] = cid

        # Update existing and incorporate new rising tags
        all_candidates: Dict[str, Dict[str, Any]] = {}

        # 1. Incorporate existing pool
        for item in self.trending_pool:
            all_candidates[item["tag"]] = dict(item)

        # 2. Update with live engine metrics
        for tag, m in trend_metrics.items():
            clean_tag = tag.lower().lstrip("#")
            curr_vol = m.get("current_volume", 0)
            velocity = m.get("velocity", 0.0)
            acceleration = m.get("acceleration", 0.0)
            surge_score = m.get("surge_score", 0.0)
            z_score = m.get("z_score", 0.0)
            avg_tox = m.get("avg_toxicity", 0.0)

            if clean_tag in all_candidates:
                entry = all_candidates[clean_tag]
                entry["volume"] = max(entry.get("volume", 0), curr_vol)
                entry["velocity"] = velocity
                entry["acceleration"] = acceleration
                entry["surge_score"] = surge_score
                entry["z_score"] = z_score
                entry["avg_toxicity"] = avg_tox
                entry["cluster_id"] = cluster_map.get(
                    clean_tag, entry.get("cluster_id", "GENERAL")
                )
                entry["last_updated"] = now_iso
            else:
                # Newly discovered emerging tag from live stream
                all_candidates[clean_tag] = {
                    "tag": clean_tag,
                    "hashtag": f"#{clean_tag}",
                    "volume": curr_vol,
                    "velocity": velocity,
                    "acceleration": acceleration,
                    "surge_score": surge_score,
                    "z_score": z_score,
                    "avg_toxicity": avg_tox,
                    "is_threat": avg_tox >= 0.25,
                    "cluster_id": cluster_map.get(clean_tag, "EMERGENT"),
                    "last_updated": now_iso,
                }

        # Compute Unified Trend Score for re-ranking:
        # Score = Surge_Score * 0.40 + Volume * 0.25 + max(0, Acceleration) * 0.20 + Z_Score * 0.15
        for tag, item in all_candidates.items():
            score = (
                item.get("surge_score", 0.0) * 0.40
                + min(item.get("volume", 0), 500) * 0.25
                + max(0.0, item.get("acceleration", 0.0)) * 0.20
                + max(0.0, item.get("z_score", 0.0)) * 0.15
            )
            item["unified_score"] = round(score, 2)

        # Sort candidate tags descending by unified trend score
        sorted_tags = sorted(
            all_candidates.values(), key=lambda x: x["unified_score"], reverse=True
        )

        # Retain Top 200
        new_pool = []
        for rank, item in enumerate(sorted_tags[: self.target_count], start=1):
            item["rank"] = rank
            item["tier"] = 1 if rank <= 25 else 2
            new_pool.append(item)

        self.trending_pool = new_pool
        self.save_registry()
        logging.info(
            f"[HASHTAG MANAGER] Re-ranked Top {len(self.trending_pool)} trending hashtags (Top Surge: #{self.trending_pool[0]['tag']})"
        )

    def get_all_hashtags(self) -> List[str]:
        """Returns all 200 hashtags with leading '#'."""
        return [item["hashtag"] for item in self.trending_pool]

    def get_tier1_hashtags(self) -> List[str]:
        """Returns the top 25 highest priority surging hashtags."""
        return [item["hashtag"] for item in self.trending_pool if item.get("tier") == 1]

    def get_search_query_batches(
        self, cycle_index: int = 0, batch_size: int = 5
    ) -> List[str]:
        """
        Generates rate-limit safe, prioritized search queries for scraping:
        - Tier 1 (Top 25 critical): Polled every cycle.
        - Tier 2 (Ranks 26-200): Rotated in slices of ~35 tags per cycle, combined using OR operators.
        Example query: "(#farmersprotest OR #delhipolice OR #flashprotest)"
        """
        tier1 = self.get_tier1_hashtags()
        tier2 = [
            item["hashtag"] for item in self.trending_pool if item.get("tier") == 2
        ]

        queries = []

        # 1. Tier 1 queries: Individual or paired queries for precise extraction
        for i in range(0, len(tier1), 3):
            chunk = tier1[i : i + 3]
            queries.append("(" + " OR ".join(chunk) + ")")

        # 2. Tier 2 rotation slice (rotate 35 tags per cycle across the 175 tier-2 tags)
        slice_size = 35
        total_tier2 = len(tier2)
        if total_tier2 > 0:
            start_idx = (cycle_index * slice_size) % total_tier2
            rotated_slice = tier2[start_idx : start_idx + slice_size]
            if len(rotated_slice) < slice_size:
                rotated_slice.extend(tier2[: slice_size - len(rotated_slice)])

            # Group rotated slice into OR batches of size `batch_size`
            for i in range(0, len(rotated_slice), batch_size):
                chunk = rotated_slice[i : i + batch_size]
                queries.append("(" + " OR ".join(chunk) + ")")

        return queries


# Global Singleton accessor
_manager_instance: Optional[TrendingHashtagManager] = None


def get_trending_hashtag_manager(
    registry_path: Optional[str] = None,
) -> TrendingHashtagManager:
    global _manager_instance
    if _manager_instance is None:
        path = registry_path or DEFAULT_REGISTRY_PATH
        _manager_instance = TrendingHashtagManager(registry_path=path)
    return _manager_instance


if __name__ == "__main__":
    mgr = get_trending_hashtag_manager()
    print(f"\n[✓] Loaded {len(mgr.trending_pool)} Trending Hashtags!")
    print(f"Top 10 Hashtags:")
    for h in mgr.trending_pool[:10]:
        print(
            f"  #{h['rank']:02d}: {h['hashtag']} (Vol: {h['volume']}, Surge: {h['surge_score']}, Tier: {h['tier']})"
        )

    batches = mgr.get_search_query_batches(cycle_index=0)
    print(f"\nGenerated {len(batches)} Batched Scraper Queries for Cycle 0:")
    for b in batches[:5]:
        print(f"  Query: {b}")
