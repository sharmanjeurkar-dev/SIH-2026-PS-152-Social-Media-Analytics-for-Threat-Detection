import json
import logging
import signal
import sys
import time
from typing import List

from kafka import KafkaConsumer
from pydantic import ValidationError
from src.GraphDB.connection import Neo4jConnection
from src.GraphDB.ingestion import EnrichedSocialEvent, GraphInjestor

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


class LiveGraphStreamConsumer:
    """
    Consumes enriched threat events from Member 2 via Kafka,
    validates payloads with Pydantic, and writes batches into Neo4j.
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
        """Flushes the current in-memory micro-batch directly to Neo4j."""
        if not self.buffer:
            return

        batch_count = len(self.buffer)
        try:
            self.ingestor.ingest_batch(self.buffer)
            logging.info(
                f"[NEO4J LIVE FLUSH] Successfully ingested batch of {batch_count} events into graph."
            )
        except Exception as e:
            logging.error(f"Failed to ingest live batch to Neo4j: {e}")
        finally:
            self.buffer.clear()
            self.last_flush_time = time.time()

    def start_listening(self):
        """Initializes Kafka consumer and begins continuous stream processing loop."""
        logging.info(
            f"Connecting to Kafka broker at {self.bootstrap_servers} on topic '{self.topic}'..."
        )

        try:
            consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=[self.bootstrap_servers],
                auto_offset_reset="latest",  # Listen for live incoming posts
                enable_auto_commit=True,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                consumer_timeout_ms=1000,  # Non-blocking poll ticks
            )
            logging.info("Connected to Kafka! Awaiting live events from Member 2...")
        except Exception as e:
            logging.error(f"Could not connect to Kafka broker: {e}")
            return

        while self.is_running:
            try:
                # Poll message batches from Kafka
                message_pack = consumer.poll(timeout_ms=1000)

                for tp, messages in message_pack.items():
                    for message in messages:
                        raw_payload = message.value

                        # Validate and normalize payload (handles Member 2 nested schema)
                        try:
                            validated_event = EnrichedSocialEvent.model_validate(
                                raw_payload
                            )
                            self.buffer.append(validated_event.model_dump())
                        except ValidationError as val_err:
                            logging.warning(
                                f"Skipping malformed event {raw_payload.get('post_id')}: {val_err}"
                            )
                            continue

                        # Flush if micro-batch threshold reached
                        if len(self.buffer) >= self.batch_size:
                            self._flush_buffer()

                # Time-based flush trigger (ensures low-latency updates)
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


if __name__ == "__main__":
    live_consumer = LiveGraphStreamConsumer()
    live_consumer.start_listening()
