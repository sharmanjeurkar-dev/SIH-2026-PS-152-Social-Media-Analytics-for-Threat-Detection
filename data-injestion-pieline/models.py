"""
Unified Data Models for SIH 2026 PS:152 - Member 1 (Data Ingestion Layer)
Defines schemas for Raw Payloads, Metrics, In-Flight Triage, and Downstream Handoffs:
- Full Ingested Record (Cold Storage / Member 5)
- Text Intelligence Packet (Member 2 NLP Worker)
- Network Topology Packet (Member 3 Neo4j / Graph Worker)
Supports State Tracking for Metric Updates & New Post Ingestion.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import json


@dataclass
class AuthorProfile:
    user_id: str
    handle: str
    name: Optional[str] = ""
    account_created_at: Optional[str] = None
    followers_count: int = 0
    following_count: int = 0
    profile_location: Optional[str] = None
    verified: bool = False
    profile_image_url: Optional[str] = None


@dataclass
class PostInteractions:
    interaction_type: str = "ORIGINAL_POST"  # ORIGINAL_POST, RETWEET, REPLY, QUOTE
    target_user_id: Optional[str] = None
    target_handle: Optional[str] = None
    target_post_id: Optional[str] = None
    mentioned_user_ids: List[str] = field(default_factory=list)
    mentioned_handles: List[str] = field(default_factory=list)


@dataclass
class PostMetrics:
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0


@dataclass
class PostEntities:
    hashtags: List[str] = field(default_factory=list)
    shared_urls: List[str] = field(default_factory=list)
    initial_entity_markers: List[str] = field(default_factory=list)  # Dates, basic locations, orgs


@dataclass
class InFlightTriage:
    language: str = "en"                      # e.g., "Hinglish", "hi", "en", "mr", "ta"
    detected_script: str = "Latin"            # "Latin", "Devanagari", "Mixed", etc.
    is_spam: bool = False
    signal_score: float = 0.5                 # 0.0 (low-signal junk) to 1.0 (critical high-signal)
    is_high_signal: bool = True
    triage_notes: List[str] = field(default_factory=list)


@dataclass
class RawContent:
    text: str = ""
    is_code_mixed: bool = False
    media_urls: List[str] = field(default_factory=list)


@dataclass
class IngestionEvent:
    post_id: str
    timestamp: str                            # ISO 8601 UTC
    platform: str = "Twitter/X"
    raw_content: RawContent = field(default_factory=RawContent)
    author: AuthorProfile = field(default_factory=lambda: AuthorProfile("", ""))
    interactions: PostInteractions = field(default_factory=PostInteractions)
    metrics: PostMetrics = field(default_factory=PostMetrics)
    entities: PostEntities = field(default_factory=PostEntities)
    triage: InFlightTriage = field(default_factory=InFlightTriage)
    event_type: str = "NEW_POST"              # "NEW_POST" or "METRIC_UPDATE"
    changed_fields: List[str] = field(default_factory=list)
    ingested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def compute_state_signature(self) -> Dict[str, Any]:
        """Returns comparable state values for mutation and metric change tracking."""
        return {
            "text": self.raw_content.text,
            "followers_count": self.author.followers_count,
            "following_count": self.author.following_count,
            "retweet_count": self.metrics.retweet_count,
            "reply_count": self.metrics.reply_count,
            "like_count": self.metrics.like_count,
            "quote_count": self.metrics.quote_count,
            "signal_score": self.triage.signal_score,
            "is_spam": self.triage.is_spam
        }

    def to_member2_nlp_packet(self) -> Dict[str, Any]:
        """Data handoff for Member 2 (NLP & Text Intelligence Layer)."""
        return {
            "post_id": self.post_id,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "event_type": self.event_type,
            "changed_fields": self.changed_fields,
            "interaction_type": self.interactions.interaction_type,
            "raw_text": self.raw_content.text,
            "is_code_mixed": self.raw_content.is_code_mixed,
            "tokens_and_entities": {
                "hashtags": self.entities.hashtags,
                "mentioned_handles": self.interactions.mentioned_handles,
                "shared_urls": self.entities.shared_urls,
                "initial_entity_markers": self.entities.initial_entity_markers
            },
            "triage": asdict(self.triage)
        }

    def to_member3_graph_packet(self) -> Dict[str, Any]:
        """Data handoff for Member 3 (Graph Data Science & Network Intelligence Layer)."""
        return {
            "post_id": self.post_id,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "event_type": self.event_type,
            "changed_fields": self.changed_fields,
            "author": asdict(self.author),
            "interactions": asdict(self.interactions),
            "metrics": asdict(self.metrics),
            "graph_nodes": {
                "hashtags": self.entities.hashtags,
                "shared_urls": self.entities.shared_urls
            },
            "is_high_signal": self.triage.is_high_signal
        }

    def to_member5_storage_record(self) -> Dict[str, Any]:
        """Cold storage / full-text index record for Member 5 (Elasticsearch/S3)."""
        return self.to_dict()