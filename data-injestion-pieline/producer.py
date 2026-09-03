"""
Kafka Threat Stream Producer for Member 1
Publishes live deduplicated new posts and real-time metric updates to Apache Kafka.
Topic: raw-threat-stream (Default)
"""

import os
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class ThreatStreamProducer:
    """Publishes ingestion events (NEW_POST / METRIC_UPDATE) to the Kafka broker."""
    def __init__(
        self,
        bootstrap_servers: str = None,
        topic: str = "raw-threat-stream"
    ):
        self.broker = bootstrap_servers or os.getenv("KAFKA_BROKER", "localhost:9092")
        self.topic = topic
        self.producer = None

        try:
            from kafka import KafkaProducer
            self.producer = KafkaProducer(
                bootstrap_servers=[self.broker],
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                retries=3,
                request_timeout_ms=5000,
                api_version=(2, 6, 0)
            )
            logging.info(f"[KAFKA] Connected to Kafka broker at {self.broker} (Topic: '{self.topic}')")
        except ImportError:
            logging.warning("[KAFKA] 'kafka-python' library not installed. Running in local-buffer mode.")
        except Exception as e:
            logging.warning(f"[KAFKA] Kafka broker at {self.broker} unavailable ({e}). Running in local-buffer mode.")

    def publish_event(self, event_dict: dict, custom_topic: str = None):
        """Publishes a new post or metric update payload to the Kafka ingestion topic."""
        target_topic = custom_topic or self.topic
        if self.producer:
            try:
                future = self.producer.send(target_topic, event_dict)
                self.producer.flush()
                record_metadata = future.get(timeout=10)
                event_type = event_dict.get("event_type", "POST")
                post_id = event_dict.get("post_id", "unknown")
                logging.info(
                    f"[KAFKA] Published [{event_type}] '{post_id}' to topic '{record_metadata.topic}' "
                    f"[Partition: {record_metadata.partition}, Offset: {record_metadata.offset}]"
                )
                return record_metadata
            except Exception as e:
                logging.error(f"[KAFKA] Failed to publish event: {e}")
                return None
        else:
            event_type = event_dict.get("event_type", "POST")
            post_id = event_dict.get("post_id", "unknown")
            logging.debug(f"[BUFFER] Ingested [{event_type}] '{post_id}' (Kafka offline).")
            return None

    def close(self):
        if self.producer:
            try:
                self.producer.flush()
                self.producer.close()
                logging.info("[KAFKA] Producer closed cleanly.")
            except Exception as e:
                logging.error(f"[KAFKA] Error closing producer: {e}")