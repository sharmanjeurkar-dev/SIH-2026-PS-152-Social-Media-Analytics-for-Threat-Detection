"""
CLI and Streaming Service for Member 1: Live Scraper & Stream Ingestion
SIH 2026 PS:152 - National Technical Research Organisation (NTRO)

Live Feed Ingestion Architecture:
- 4-Hour Sliding Lookback Window executed periodically (default every 15 mins).
- Full Horizon extraction for static target threat keywords & hashtags.
- Broad Horizon extraction (500 posts) capturing emerging events outside target keywords.
- Stateful Post Tracking:
  - Blindly saves & publishes NEW posts to Kafka & Polyglot Storage.
  - Detects VALUE MUTATIONS (retweet/like/reply counts, author metrics, text changes) on existing posts and propagates updates to Kafka.
  - Silently deduplicates unchanged posts.
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

# Ensure root directory is in sys.path for TrendingHashtagManager
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from trending_hashtag_manager import get_trending_hashtag_manager
except ImportError:
    get_trending_hashtag_manager = None

from models import IngestionEvent
from producer import ThreatStreamProducer
from stream_buffer import StreamBuffer
from x_scraper import XScraper

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# 1. Fallback Static Target Keywords (used only if manager is unavailable)
FALLBACK_TARGET_HASHTAGS = [
    "#FlashProtest",
    "#DelhiPolice",
    "#NationalSecurity",
    "#cyberalert",
    "#ShutdownCity",
    "#Bandh",
    "#Section144",
    "#BharatBandh",
    "#CivilUnrest",
    "#PaperLeak",
    "#KisanAndolan",
]

# 2. Broad Horizon Query (Captures generic trending chatter outside target hashtags)
BROAD_HORIZON_QUERY = "(news OR breaking OR live OR alert OR update)"


class StatefulPostCache:
    """
    Bounded LRU Cache that tracks state signatures of posts to:
    1. Blindly ingest and save NEW posts.
    2. Detect MUTATIONS (metric changes: retweets, likes, replies, follower counts, signal score).
    3. Skip unchanged duplicates.
    """

    def __init__(self, max_size=50000):
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.max_size = max_size

    def check_and_update(self, event: IngestionEvent) -> Tuple[bool, bool, List[str]]:
        """Returns: (is_new, is_changed, changed_fields)"""
        post_id = event.post_id
        current_state = event.compute_state_signature()

        if post_id not in self.cache:
            # Case 1: BRAND NEW POST -> save blindly
            self.cache[post_id] = current_state
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
            event.event_type = "NEW_POST"
            event.changed_fields = []
            return True, False, []

        # Case 2: EXISTING POST -> inspect if any values changed
        old_state = self.cache[post_id]
        changed_fields = []
        for key, val in current_state.items():
            if old_state.get(key) != val:
                changed_fields.append(f"{key}: {old_state.get(key)} -> {val}")

        if changed_fields:
            # VALUES MUTATED -> update cache and mark as METRIC_UPDATE
            self.cache[post_id] = current_state
            self.cache.move_to_end(post_id)
            event.event_type = "METRIC_UPDATE"
            event.changed_fields = changed_fields
            return False, True, changed_fields

        # Case 3: UNCHANGED DUPLICATE -> skip
        self.cache.move_to_end(post_id)
        return False, False, []


def process_and_route_events(
    raw_events: List[IngestionEvent],
    target_name: str,
    cache: StatefulPostCache,
    producer: ThreatStreamProducer,
    buffer: StreamBuffer,
) -> Tuple[int, int]:
    """
    Handles state evaluation, Kafka publishing, and polyglot storage queueing.
    - New posts are published to Kafka and saved blindly.
    - Updated posts are re-published to Kafka with new metrics and updated in storage.
    """
    if not raw_events:
        return 0, 0

    new_events: List[IngestionEvent] = []
    updated_events: List[IngestionEvent] = []

    for ev in raw_events:
        is_new, is_changed, changed_fields = cache.check_and_update(ev)
        if is_new:
            new_events.append(ev)
            producer.publish_event(ev.to_dict())
        elif is_changed:
            updated_events.append(ev)
            producer.publish_event(ev.to_dict())

    total_routed = new_events + updated_events
    if total_routed:
        buffer.push_many(total_routed)

    if new_events or updated_events:
        logging.info(
            f"[+] {target_name:<18} | Batch: {len(raw_events):>3} | "
            f"New (Saved Blindly): {len(new_events):>3} | Metric Updates: {len(updated_events):>3}"
        )
        if updated_events:
            for u in updated_events[:2]:
                logging.info(
                    f"    ↳ [MUTATION DETECTED] {u.post_id} -> {', '.join(u.changed_fields[:3])}"
                )

    return len(new_events), len(updated_events)


def run_single_window_cycle(
    hours: int,
    broad_count: int,
    producer: ThreatStreamProducer,
    cache: StatefulPostCache,
    buffer: StreamBuffer,
    scraper: XScraper,
    cycle_index: int = 0,
) -> Dict[str, int]:
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(hours=hours)
    since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Load dynamic 200-trending hashtag radar
    if get_trending_hashtag_manager is not None:
        mgr = get_trending_hashtag_manager()
        active_pool_size = len(mgr.trending_pool)
        query_batches = mgr.get_search_query_batches(
            cycle_index=cycle_index, batch_size=5
        )
        tier1_tags = mgr.get_tier1_hashtags()
    else:
        active_pool_size = len(FALLBACK_TARGET_HASHTAGS)
        query_batches = FALLBACK_TARGET_HASHTAGS
        tier1_tags = FALLBACK_TARGET_HASHTAGS[:5]

    logging.info("=" * 75)
    logging.info(
        f"[*] EXECUTING LIVE FEED CYCLE #{cycle_index}: {hours}-Hour Lookback (Since {since_str})"
    )
    logging.info(
        f"[*] Dynamic Trending Radar: {active_pool_size} Hashtags | "
        f"Scraper Query Batches: {len(query_batches)} | Broad Horizon Cap: {broad_count} posts"
    )
    logging.info("=" * 75)

    cycle_new = 0
    cycle_updated = 0

    # 1. Targeted 200-Hashtag Extraction (Prioritized & Batched)
    logging.info(
        f"\n--- PHASE 1: Dynamic Trending Extraction ({len(query_batches)} Batched Queries Across 200-Tag Radar) ---"
    )
    for batch_target in query_batches:
        query = f"{batch_target} since:{since_dt.strftime('%Y-%m-%d_%H:%M:%S')}"
        raw_events = scraper.scrape_live(
            query, count=25, allow_simulation_fallback=True, lookback_hours=hours
        )
        n, u = process_and_route_events(
            raw_events, batch_target[:35], cache, producer, buffer
        )
        cycle_new += n
        cycle_updated += u

    # 2. Broad Horizon Extraction (Outside Keywords)
    logging.info(
        f"\n--- PHASE 2: Broad Horizon Extraction ({broad_count} Posts Outside Critical Tier-1 Tags) ---"
    )
    exclusions = " ".join(
        [f"-{tag.lstrip('#')}" for tag in tier1_tags[:10] if not " " in tag]
    )
    broad_query = f"{BROAD_HORIZON_QUERY} {exclusions} since:{since_dt.strftime('%Y-%m-%d_%H:%M:%S')}"
    raw_broad_events = scraper.scrape_live(
        broad_query,
        count=broad_count,
        allow_simulation_fallback=True,
        lookback_hours=hours,
    )
    n_broad, u_broad = process_and_route_events(
        raw_broad_events, "Broad Horizon", cache, producer, buffer
    )
    cycle_new += n_broad
    cycle_updated += u_broad

    # 3. Flush Buffer to Partitioned Storage
    flushed = buffer.flush_now()
    logging.info("\n" + "=" * 75)
    logging.info(
        f"[✓] Cycle #{cycle_index} Complete | New Posts Saved: {cycle_new} | "
        f"Updated Posts Forwarded to Kafka: {cycle_updated} | Total Flushed: {flushed}"
    )
    logging.info("=" * 75)

    return {"new": cycle_new, "updated": cycle_updated, "flushed": flushed}


def run_continuous_live_daemon(
    interval_minutes: float,
    lookback_hours: int,
    broad_count: int,
    producer: ThreatStreamProducer,
    cache: StatefulPostCache,
    buffer: StreamBuffer,
    scraper: XScraper,
    max_cycles: int = 0,
):
    logging.info("=" * 75)
    logging.info("  NTRO SOCIAL MEDIA ANALYTICS - MEMBER 1 LIVE STREAMING DAEMON")
    logging.info(
        f"  Cycle Interval: {interval_minutes} minutes | Sliding Window: {lookback_hours} hours"
    )
    logging.info(
        f"  Broad Horizon Batch: {broad_count} posts | Destination: Kafka ('raw-threat-stream')"
    )
    logging.info("=" * 75)

    buffer.start_background_flusher()
    interval_seconds = interval_minutes * 60.0
    cycle_count = 0

    try:
        while True:
            cycle_count += 1
            logging.info(f"\n[>>> STARTING LIVE EXTRACTION CYCLE #{cycle_count} <<<]")
            run_single_window_cycle(
                hours=lookback_hours,
                broad_count=broad_count,
                producer=producer,
                cache=cache,
                buffer=buffer,
                scraper=scraper,
                cycle_index=cycle_count,
            )

            stats = buffer.get_stats()
            logging.info("\n[*] Current Pipeline Stats:")
            print(json.dumps(stats, indent=2))

            if max_cycles and cycle_count >= max_cycles:
                logging.info(
                    f"[*] Reached maximum requested cycles ({max_cycles}). Stopping daemon."
                )
                break

            logging.info(
                f"[*] Sleeping {interval_minutes} minutes until next sliding window poll...\n"
            )
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logging.info("\n[*] Daemon stopped by user. Flushing remaining buffer...")
    finally:
        buffer.stop_background_flusher()
        logging.info("\n[+] Final Ingestion Stats:")
        print(json.dumps(buffer.get_stats(), indent=2))


def run_demo(hours: int = 4, broad_count: int = 10):
    logging.info("=" * 75)
    logging.info("  RUNNING LIVE FEED & DYNAMIC 200-HASHTAG ROTATION DEMONSTRATION")
    logging.info("=" * 75)

    producer = ThreatStreamProducer()
    cache = StatefulPostCache()
    buffer = StreamBuffer(base_data_dir="data", batch_size=20, flush_interval_secs=1.0)
    scraper = XScraper(timeout=8)

    logging.info("\n--- STEP 1: Initial Poll Cycle #0 (Tier-1 + Slice-1 Rotation) ---")
    run_single_window_cycle(
        hours=hours,
        broad_count=broad_count,
        producer=producer,
        cache=cache,
        buffer=buffer,
        scraper=scraper,
        cycle_index=0,
    )

    logging.info(
        "\n--- STEP 2: Subsequent Poll Cycle #1 (Tier-1 + Slice-2 Rotation & Value Mutation Check) ---"
    )
    run_single_window_cycle(
        hours=hours,
        broad_count=broad_count,
        producer=producer,
        cache=cache,
        buffer=buffer,
        scraper=scraper,
        cycle_index=1,
    )

    logging.info(
        "\n[✓] Dynamic 200-hashtag rotation demonstration completed successfully."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Member 1: Live Feed Extraction & Metric Change Ingestion (SIH PS:152)"
    )
    parser.add_argument(
        "--mode",
        choices=["live", "once", "demo"],
        default="live",
        help="Execution mode (default: live)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Polling interval in minutes (default: 15.0)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=4,
        help="Sliding lookback window in hours (default: 4)",
    )
    parser.add_argument(
        "--broad-count",
        type=int,
        default=500,
        help="Broad horizon post cap outside target hashtags (default: 500)",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Maximum daemon cycles to run (0 for infinite)",
    )

    args = parser.parse_args()

    producer = ThreatStreamProducer()
    cache = StatefulPostCache(max_size=50000)
    buffer = StreamBuffer(base_data_dir="data", batch_size=50, flush_interval_secs=2.0)
    scraper = XScraper(timeout=10)

    if args.mode == "demo":
        run_demo(hours=args.hours, broad_count=20)
    elif args.mode == "once":
        run_single_window_cycle(
            hours=args.hours,
            broad_count=args.broad_count,
            producer=producer,
            cache=cache,
            buffer=buffer,
            scraper=scraper,
        )
    else:
        run_continuous_live_daemon(
            interval_minutes=args.interval,
            lookback_hours=args.hours,
            broad_count=args.broad_count,
            producer=producer,
            cache=cache,
            buffer=buffer,
            scraper=scraper,
            max_cycles=args.max_cycles,
        )


if __name__ == "__main__":
    main()
