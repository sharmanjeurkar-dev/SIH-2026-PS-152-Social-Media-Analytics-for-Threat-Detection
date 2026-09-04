"""
Chronological Trend & Topic Detector Runner
SIH 2026 PS:152 - National Technical Research Organisation (NTRO)

Evaluates chronological sliding windows on historical datasets (tweets.csv),
tracking hashtag velocity, acceleration, Kleinberg burst Z-scores, Louvain community clusters,
narrative shifts, and ranking the Top 200 Trending Hashtags radar.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

# Ensure current and project root are in sys.path
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

from trend_topic_engine import TrendAndTopicEngine

FAST_TOXIC_KEYWORDS = {
    "hate",
    "kill",
    "threat",
    "attack",
    "death",
    "traitor",
    "gaddar",
    "scam",
    "riot",
    "burn",
    "shame",
    "boycott",
    "protest",
    "clash",
    "corrupt",
    "violence",
    "curfew",
    "extremist",
    "terror",
}


def compute_fast_toxicity(text: str) -> float:
    """Computes a deterministic keyword-based toxicity score in [0.0, 1.0]."""
    if not text:
        return 0.0
    words = set(re.findall(r"\w+", text.lower()))
    matches = words & FAST_TOXIC_KEYWORDS
    if not matches:
        return 0.0
    return min(round(0.12 * len(matches), 3), 1.0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Chronological Trend & Topic Detection Simulation"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=25000,
        help="Number of rows to sample from tweets.csv (default: 25000)",
    )
    parser.add_argument(
        "--window_hours",
        type=float,
        default=4.0,
        help="Sliding window duration in hours (default: 4.0)",
    )
    parser.add_argument(
        "--csv_path",
        type=str,
        default=None,
        help="Optional explicit path to tweets.csv",
    )
    return parser.parse_args()


def run_chronological_trend_detection(
    sample_size: int = 25000, window_hours: float = 4.0, csv_path: str = None
):
    possible_paths = [
        csv_path,
        os.path.join(_PROJECT_ROOT, "graph-network-engine", "data", "tweets.csv"),
        os.path.join(_PROJECT_ROOT, "data", "tweets.csv"),
    ]
    actual_path = next((p for p in possible_paths if p and os.path.exists(p)), None)

    if not actual_path:
        print(f"[ERROR] Could not find tweets.csv in candidate paths.")
        return

    print("=" * 70)
    print("NTRO SOCIAL MEDIA THREAT INTELLIGENCE: REAL-TIME TREND & TOPIC DETECTOR")
    print(f"Loading {sample_size} tweets chronologically from: {actual_path}")
    print(f"Sliding Window Size: {window_hours} hours")
    print("=" * 70)

    use_cols = ["date", "renderedContent", "retweetCount", "likeCount"]
    try:
        df = pd.read_csv(actual_path, nrows=sample_size, usecols=use_cols)
    except Exception:
        df = pd.read_csv(actual_path, nrows=sample_size)

    # Convert dates to UTC datetime and sort chronologically
    df["dt"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    df = df.dropna(subset=["dt", "renderedContent"])
    df = df.sort_values(by="dt").reset_index(drop=True)

    min_time = df["dt"].min()
    max_time = df["dt"].max()
    print(f"Chronological Range: {min_time} -> {max_time} (Total rows: {len(df)})\n")

    hashtag_regex = re.compile(r"#(\w+)")
    events: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        text = str(row["renderedContent"])
        tags = [t.lower().strip() for t in hashtag_regex.findall(text) if t]
        tox = compute_fast_toxicity(text)
        events.append(
            {
                "post_id": f"tweet_{idx}",
                "timestamp": row["dt"],
                "hashtags": tags,
                "toxicity_score": tox,
                "retweet_count": int(row.get("retweetCount") or 0),
            }
        )

    # Initialize Trend & Topic Engine
    engine = TrendAndTopicEngine(baseline_window_count=5)

    # Chronological sliding window grouping
    window_delta = pd.Timedelta(hours=window_hours)
    current_start = min_time
    window_index = 1

    while current_start < max_time:
        current_end = current_start + window_delta
        window_events = [
            e for e in events if current_start <= e["timestamp"] < current_end
        ]

        if len(window_events) >= 10:
            print("-" * 70)
            print(
                f"[WINDOW {window_index:02d}] {current_start.strftime('%Y-%m-%d %H:%M')} -> "
                f"{current_end.strftime('%Y-%m-%d %H:%M')} (Events: {len(window_events)})"
            )
            print("-" * 70)

            # Analyze window dynamics
            analysis = engine.analyze_window(
                window_events, dt_hours=window_hours, top_n=200
            )

            # 1. Top 200 Trending Hashtags Radar
            top_200 = analysis.get("top_200_trends", [])
            print(
                f"\n🎯 DYNAMIC TOP 200 TRENDING RADAR (Active Tracked: {len(top_200)} hashtags):"
            )
            for t in top_200[:5]:
                print(
                    f"  #{t['rank']:02d} #{t['tag']:<22} | Score: {t['unified_score']:>6.1f} | "
                    f"Vol: {t['volume']:>4} | Accel: {t['acceleration']:>+5.1f} | Surge: {t['surge_score']:>5.1f} | Tier: {t['tier']}"
                )
            if len(top_200) > 25:
                print(f"  ... [Ranks 06-25 Tier-1 Critical Monitored] ...")
                print(f"  ... [Ranks 26-200 Tier-2 Rotational Radar Tracked] ...")

            # 2. Rising Trends
            print("\n📈 TOP RISING TRENDS (Predicted Growth & Acceleration):")
            if analysis["rising_trends"]:
                for r in analysis["rising_trends"][:5]:
                    print(
                        f"  #{r['tag']:<24} | Velocity: +{r['velocity']:>5.1f}/h | "
                        f"Accel: +{r['acceleration']:>5.1f} | Surge: {r['surge_score']:>6.1f} | "
                        f"Tox: {r['avg_toxicity']:.2f}"
                    )
            else:
                print("  No accelerating surges detected in this window.")

            # 3. Viral Keywords
            print("\n🔥 TOP VIRAL KEYWORDS (Highest Volume & Network Reach):")
            for v in analysis["viral_keywords"][:5]:
                print(
                    f"  #{v['tag']:<24} | Mentions: {v['current_volume']:>5} | "
                    f"Degree: {v['degree']:>3} | Burst Z: {v['z_score']:>5.1f}"
                )

            # 4. Topic Clusters (Louvain Communities on Hashtag Co-occurrence Graph)
            print(
                "\n🌐 ACTIVE DISCUSSION TOPIC CLUSTERS (Louvain Semantic Modularity):"
            )
            for c in analysis["topic_clusters"][:3]:
                threat_tag = " [🚨 HIGH THREAT]" if c["is_high_threat"] else ""
                print(
                    f"  [{c['cluster_id']}] Theme: #{c['primary_tag']}{threat_tag} "
                    f"(Tags: {c['cluster_size']}, Vol: {c['total_volume']}, Tox: {c['avg_toxicity']:.2f})"
                )
                print(
                    f"      Keywords: {', '.join(['#' + k for k in c['top_keywords'][:5]])}"
                )

            # 5. Shifting Discussions & Thematic Drift
            if analysis["shifting_discussions"]:
                print("\n⚡ DETECTED SHIFTING DISCUSSIONS & DRIFT:")
                for shift in analysis["shifting_discussions"][:3]:
                    stype = shift["type"]
                    icon = (
                        "🆕"
                        if stype == "NEW_EMERGING_TOPIC"
                        else "⚠️"
                        if stype == "ESCALATING_HOSTILITY"
                        else "🔄"
                    )
                    print(
                        f"  {icon} [{stype}] #{shift['topic']}: {shift.get('note', '')}"
                    )

            print()

        current_start = current_end
        window_index += 1

    print("=" * 70)
    print("CHRONOLOGICAL TREND & TOPIC SIMULATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    args = parse_args()
    run_chronological_trend_detection(
        sample_size=args.sample, window_hours=args.window_hours, csv_path=args.csv_path
    )
