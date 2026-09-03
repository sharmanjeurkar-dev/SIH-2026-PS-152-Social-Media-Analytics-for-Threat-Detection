"""
Stream Buffer and Storage Routing for Member 1
Implements:
1. Resilient buffering (in-memory queue with thread-safe micro-batch flush).
2. Cold Storage Archive (Partitioned JSONL storage under data/ingested/YYYY-MM-DD/).
3. Member 2 Handoff Buffer (data/member2_nlp_queue/).
4. Member 3 Handoff Buffer (data/member3_graph_queue/).
5. Member 5 Search & Storage Buffer (data/member5_storage_buffer/).
6. Real-time metrics tracking for new posts and updated post metrics.
"""

import os
import json
import time
import queue
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from models import IngestionEvent


class StreamBuffer:
    def __init__(self, base_data_dir: str = "data", batch_size: int = 10, flush_interval_secs: float = 2.0):
        self.base_data_dir = base_data_dir
        self.batch_size = batch_size
        self.flush_interval_secs = flush_interval_secs

        self.dir_ingested = os.path.join(base_data_dir, "ingested")
        self.dir_member2 = os.path.join(base_data_dir, "member2_nlp_queue")
        self.dir_member3 = os.path.join(base_data_dir, "member3_graph_queue")
        self.dir_member5 = os.path.join(base_data_dir, "member5_storage_buffer")

        self._init_directories()

        self.queue: queue.Queue[IngestionEvent] = queue.Queue()
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None

        self.metrics = {
            "total_ingested": 0,
            "new_posts_count": 0,
            "metric_updates_count": 0,
            "high_signal_count": 0,
            "spam_filtered_count": 0,
            "languages": {},
            "start_time": time.time(),
            "last_flush_time": time.time()
        }
        self._lock = threading.Lock()

    def _init_directories(self):
        for d in [self.dir_ingested, self.dir_member2, self.dir_member3, self.dir_member5]:
            os.makedirs(d, exist_ok=True)

    def push(self, event: IngestionEvent):
        self.queue.put(event)

    def push_many(self, events: List[IngestionEvent]):
        for ev in events:
            self.push(ev)

    def start_background_flusher(self):
        self._is_running = True
        self._worker_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._worker_thread.start()

    def stop_background_flusher(self):
        self._is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
        self.flush_now()

    def _flush_loop(self):
        while self._is_running:
            time.sleep(self.flush_interval_secs)
            if not self.queue.empty():
                self.flush_now()

    def flush_now(self, max_items: Optional[int] = None) -> int:
        items: List[IngestionEvent] = []
        limit = max_items or self.queue.qsize()

        while not self.queue.empty() and len(items) < limit:
            try:
                items.append(self.queue.get_nowait())
            except queue.Empty:
                break

        if not items:
            return 0

        grouped_by_date_hour: Dict[str, List[IngestionEvent]] = {}
        for item in items:
            try:
                ts_clean = item.timestamp.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_clean)
                date_key = dt.strftime("%Y-%m-%d")
                hour_key = dt.strftime("%H")
            except Exception:
                now = datetime.now(timezone.utc)
                date_key = now.strftime("%Y-%m-%d")
                hour_key = now.strftime("%H")

            key = f"{date_key}/{hour_key}"
            grouped_by_date_hour.setdefault(key, []).append(item)

        for key, event_list in grouped_by_date_hour.items():
            date_part, hour_part = key.split("/")
            cold_storage_dir = os.path.join(self.dir_ingested, date_part)
            os.makedirs(cold_storage_dir, exist_ok=True)
            cold_storage_path = os.path.join(cold_storage_dir, f"raw_stream_{hour_part}.jsonl")

            member2_path = os.path.join(self.dir_member2, f"stream_member2_{date_part}.jsonl")
            member3_path = os.path.join(self.dir_member3, f"stream_member3_{date_part}.jsonl")
            member5_path = os.path.join(self.dir_member5, f"stream_member5_{date_part}.jsonl")

            with open(cold_storage_path, "a", encoding="utf-8") as f_raw, \
                 open(member2_path, "a", encoding="utf-8") as f_m2, \
                 open(member3_path, "a", encoding="utf-8") as f_m3, \
                 open(member5_path, "a", encoding="utf-8") as f_m5:

                for item in event_list:
                    f_raw.write(item.to_json() + "\n")
                    f_m2.write(json.dumps(item.to_member2_nlp_packet(), ensure_ascii=False) + "\n")
                    f_m3.write(json.dumps(item.to_member3_graph_packet(), ensure_ascii=False) + "\n")
                    f_m5.write(json.dumps(item.to_member5_storage_record(), ensure_ascii=False) + "\n")

                    with self._lock:
                        self.metrics["total_ingested"] += 1
                        if item.event_type == "METRIC_UPDATE":
                            self.metrics["metric_updates_count"] += 1
                        else:
                            self.metrics["new_posts_count"] += 1

                        if item.triage.is_high_signal:
                            self.metrics["high_signal_count"] += 1
                        if item.triage.is_spam:
                            self.metrics["spam_filtered_count"] += 1

                        lang = item.triage.language
                        self.metrics["languages"][lang] = self.metrics["languages"].get(lang, 0) + 1

        with self._lock:
            self.metrics["last_flush_time"] = time.time()

        return len(items)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            uptime = max(1.0, time.time() - self.metrics["start_time"])
            rate = self.metrics["total_ingested"] / uptime
            return {
                "total_ingested": self.metrics["total_ingested"],
                "new_posts_count": self.metrics["new_posts_count"],
                "metric_updates_count": self.metrics["metric_updates_count"],
                "buffered_in_queue": self.queue.qsize(),
                "high_signal_count": self.metrics["high_signal_count"],
                "spam_filtered_count": self.metrics["spam_filtered_count"],
                "languages_distribution": dict(self.metrics["languages"]),
                "throughput_posts_per_sec": round(rate, 2),
                "uptime_seconds": round(uptime, 1)
            }