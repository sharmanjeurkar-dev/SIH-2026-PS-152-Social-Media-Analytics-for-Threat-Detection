import itertools
import logging
<<<<<<< HEAD
from typing import Any, Dict, List, Optional

from neo4j import Driver
from pydantic import BaseModel, Field, model_validator

<<<<<<< HEAD
from src.connection import Neo4jConnection
=======
from typing import Optional

from neo4j import Driver
from pydantic import BaseModel, Field

from src.GraphDB.connection import Neo4jConnection
>>>>>>> f5d817d (Clean history without large files)
=======
from src.GraphDB.connection import Neo4jConnection
>>>>>>> aff0160 (Latest no error/issue commit)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

<<<<<<< HEAD
# ==========================================
# 1. Pydantic Schemas for Inbound Validation
# ==========================================


class AuthorSchema(BaseModel):
    user_id: str
    handle: Optional[str] = "unknown_user"
    account_created_at: Optional[str] = None
    followers_count: int = Field(default=0, ge=0)
    following_count: int = Field(default=0, ge=0)


class PlatformMetadataSchema(BaseModel):
    telegram_channel: Optional[str] = None
    youtube_channel: Optional[str] = None
    conversation_id: Optional[str] = None
    is_quote_tweet: bool = False


class InteractionsSchema(BaseModel):
    interaction_type: Optional[str] = "ORIGINAL_POST"
    target_user_id: Optional[str] = None
    target_handle: Optional[str] = None
    mentioned_user_ids: List[str] = Field(default_factory=list)
    forwarded_from_user_id: Optional[str] = None


class EntitiesSchema(BaseModel):
    hashtags: List[str] = Field(default_factory=list)
    hashtag_pairs: List[List[str]] = Field(default_factory=list)
    shared_urls: List[str] = Field(default_factory=list)
    ner_locations: List[str] = Field(default_factory=list)
    ner_organizations: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def generate_hashtag_pairs(self) -> "EntitiesSchema":
        if self.hashtags and not self.hashtag_pairs:
            cleaned = sorted(list({h.lower().lstrip("#") for h in self.hashtags if h}))
            self.hashtag_pairs = [list(p) for p in itertools.combinations(cleaned, 2)]
        return self


class NLPEnrichmentSchema(BaseModel):
    threat_category: Optional[str] = "GENERAL"
    toxicity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    sentiment_label: Optional[str] = "NEUTRAL"
    news_approved_score: float = Field(default=0.0, ge=0.0, le=1.0)
=======

class Platform(BaseModel):
    conversation_id: Optional[str] = None
    is_quote_tweet: bool = False
    telegram_channel: Optional[str] = None
    youtube_channel: Optional[str] = None


class AuthorSchema(BaseModel):
    userId: str
    handle_name: Optional[str] = "unknown_user"
    account_create_at: Optional[str] = None
    follower_count: int = Field(default=0, ge=0)
    following_count: int = Field(default=0, ge=0)


class PostInteractionschema(BaseModel):
    interaction_type: Optional[str] = "ORIGINAL_POST"  # RETWEET, REPLY, MENTION, QUOTE
    target_user_id: Optional[str] = None
    target_user_handle: Optional[str] = None
    mentioned_user_handle: Optional[str] = None
    forwarded_from_user_id: Optional[str] = None


class PostMetaDataSchema(BaseModel):
    hashtags: list[str] = Field(default_factory=list)
    shared_urls: list[str] = Field(default_factory=list)
    ner_locations: list[str] = Field(default_factory=list)
    ner_organizations: list[str] = Field(default_factory=list)


class NLPLayeredMetrics(BaseModel):
    threat_catagory: Optional[str] = "General"
    threat_score: Optional[float] = 0.0
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    sentiment_label: Optional[str] = "NEUTRAL"
    news_approved_score: float = Field(
        default=0.0, ge=0.0, le=1.0
    )  # The credibility filter score
>>>>>>> f5d817d (Clean history without large files)
    intent: Optional[str] = "NEUTRAL"
    language: Optional[str] = "en"


<<<<<<< HEAD
class EnrichedSocialEvent(BaseModel):
    post_id: str
    timestamp: str
    platform: str
    author: AuthorSchema
    platform_metadata: PlatformMetadataSchema = Field(
        default_factory=PlatformMetadataSchema
    )
    interactions: InteractionsSchema = Field(default_factory=InteractionsSchema)
    entities: EntitiesSchema = Field(default_factory=EntitiesSchema)
    nlp_enrichment: NLPEnrichmentSchema = Field(default_factory=NLPEnrichmentSchema)

    @model_validator(mode="before")
    @classmethod
    def flatten_member2_payload(cls, values: Any) -> Any:
        """
        Intercepts the nested 'handoff' JSON from Member 2 and maps it into
        the flat EnrichedSocialEvent structure required by Member 3 Cypher ingestion.
        """
        if isinstance(values, dict) and "handoff_to_member3" in values:
            m3 = values["handoff_to_member3"]
            m4 = values.get("handoff_to_member4", {})

            # Map nested entities block
            extracted = m3.get("extracted_entities", {})

            return {
                "post_id": m3.get("post_id"),
                "timestamp": m3.get("timestamp"),
                "platform": m3.get("platform"),
                "author": {
                    "user_id": m3.get("author_id"),
                    "handle": m3.get("author_handle"),
                },
                "interactions": {
                    "interaction_type": m3.get("interaction_type"),
                    "target_user_id": m3.get("target_user_id"),
                    "mentioned_user_ids": m3.get("mentions", []),
                },
                "entities": {
                    "hashtags": m3.get("hashtags", []),
                    "ner_locations": extracted.get("locations", []),
                    "ner_organizations": extracted.get("organizations", []),
                },
                "nlp_enrichment": {
                    "threat_category": m3.get("zero_shot_category"),
                    "toxicity_score": m4.get("toxicity_severity_score", 0.0),
                    "sentiment_score": m4.get("compound_sentiment_score", 0.0),
                    "sentiment_label": m4.get("sentiment", "NEUTRAL"),
                    "news_approved_score": m3.get("news_approved_score", 0.0),
                },
            }
        # If it's already flat, just pass it through
        return values


# (Keep the rest of your CYPHER_BATCH_INGEST query and GraphIngestor class below exactly the same)
=======
class SocialPostEvent(BaseModel):
    post_id: str
    timestamp: str
    platform: str  # e.g., "Telegram", "Reddit", "YouTube",'x'
    author: AuthorSchema
    platform_posted_on: Platform = Field(default_factory=Platform)
    post_interactions: PostInteractionschema = Field(
        default_factory=PostInteractionschema
    )
    entities: PostMetaDataSchema = Field(default_factory=PostMetaDataSchema)
    nlp_enrichment: NLPLayeredMetrics = Field(default_factory=NLPLayeredMetrics)

>>>>>>> f5d817d (Clean history without large files)

CYPHER_BATCH_INGEST = """
UNWIND $events AS event

// A. Merge Author User Node
MERGE (author:User {user_id: event.author.user_id})
ON CREATE SET 
    author.handle = event.author.handle,
    author.created_at = event.author.account_created_at,
    author.followers_count = event.author.followers_count,
    author.following_count = event.author.following_count,
    author.first_seen = event.timestamp
ON MATCH SET 
    author.followers_count = event.author.followers_count,
    author.following_count = event.author.following_count,
    author.last_seen = event.timestamp

// B. Merge Post Node with News Rating & Sentiment metrics[cite: 2]
MERGE (post:Post {post_id: event.post_id})
ON CREATE SET 
    post.timestamp = event.timestamp,
    post.platform = event.platform,
    post.toxicity_score = event.nlp_enrichment.toxicity_score,
    post.sentiment_score = event.nlp_enrichment.sentiment_score,
    post.news_approved_score = event.nlp_enrichment.news_approved_score,
    post.threat_category = event.nlp_enrichment.threat_category,
    post.intent = event.nlp_enrichment.intent

// C. Connect Author to Post
MERGE (author)-[:POSTED {timestamp: event.timestamp}]->(post)

// D. Platform Specific Contexts (Telegram & YouTube)
FOREACH (_ IN CASE WHEN event.platform_metadata.telegram_channel IS NOT NULL THEN [1] ELSE [] END |
    MERGE (tc:TelegramChannel {name: event.platform_metadata.telegram_channel})
    MERGE (post)-[:PUBLISHED_IN]->(tc)
)
FOREACH (_ IN CASE WHEN event.platform_metadata.youtube_channel IS NOT NULL THEN [1] ELSE [] END |
    MERGE (yc:YouTubeChannel {name: event.platform_metadata.youtube_channel})
    MERGE (post)-[:PUBLISHED_IN]->(yc)
)

// E. Connect Direct Target User (Retweet, Reply, Quote on X/YouTube)
FOREACH (_ IN CASE WHEN event.interactions.target_user_id IS NOT NULL THEN [1] ELSE [] END |
    MERGE (target:User {user_id: event.interactions.target_user_id})
    ON CREATE SET target.handle = coalesce(event.interactions.target_handle, "unknown")
    MERGE (author)-[r:INTERACTED_WITH {type: event.interactions.interaction_type}]->(target)
    ON CREATE SET 
        r.weight = 1.0 + (event.nlp_enrichment.toxicity_score * 2.0),
        r.first_interaction = event.timestamp,
        r.last_interaction = event.timestamp
    ON MATCH SET 
        r.weight = r.weight + 1.0 + (event.nlp_enrichment.toxicity_score * 2.0),
        r.last_interaction = event.timestamp
)

// F. Connect Mentioned Users
FOREACH (mentioned_id IN event.interactions.mentioned_user_ids |
    MERGE (mentioned:User {user_id: mentioned_id})
    MERGE (author)-[rm:INTERACTED_WITH {type: "MENTION"}]->(mentioned)
    ON CREATE SET 
        rm.weight = 1.0,
        rm.first_interaction = event.timestamp,
        rm.last_interaction = event.timestamp
    ON MATCH SET 
        rm.weight = rm.weight + 1.0,
        rm.last_interaction = event.timestamp
)

// G. Telegram Forward Chains (Mapping how information hops)[cite: 2]
FOREACH (_ IN CASE WHEN event.interactions.forwarded_from_user_id IS NOT NULL THEN [1] ELSE [] END |
    MERGE (source_user:User {user_id: event.interactions.forwarded_from_user_id})
    MERGE (author)-[rf:FORWARDED_FROM]->(source_user)
    ON CREATE SET rf.timestamp = event.timestamp
)

// H. Connect Hashtags & URLs
FOREACH (ht IN event.entities.hashtags |
    MERGE (h:Hashtag {tag: toLower(ht)})
    ON CREATE SET 
        h.frequency = 1,
        h.first_seen = event.timestamp,
        h.last_seen = event.timestamp,
        h.avg_toxicity = coalesce(event.nlp_enrichment.toxicity_score, 0.0)
    ON MATCH SET 
        h.frequency = coalesce(h.frequency, 0) + 1,
        h.last_seen = event.timestamp,
        h.avg_toxicity = (coalesce(h.avg_toxicity, 0.0) * 0.9) + (coalesce(event.nlp_enrichment.toxicity_score, 0.0) * 0.1)
    MERGE (post)-[:TAGGED_WITH]->(h)
    MERGE (author)-[:USED_HASHTAG {last_used: event.timestamp}]->(h)
)

// H2. Connect Co-occurring Hashtags (Semantic Topic Network)
FOREACH (pair IN event.entities.hashtag_pairs |
    MERGE (h1:Hashtag {tag: pair[0]})
    MERGE (h2:Hashtag {tag: pair[1]})
    MERGE (h1)-[co:CO_OCCURS_WITH]-(h2)
    ON CREATE SET 
        co.weight = 1,
        co.first_seen = event.timestamp,
        co.last_seen = event.timestamp
    ON MATCH SET 
        co.weight = coalesce(co.weight, 1) + 1,
        co.last_seen = event.timestamp
)
FOREACH (link IN event.entities.shared_urls |
    MERGE (u:URL {link: link})
    MERGE (post)-[:CONTAINS_URL]->(u)
    MERGE (author)-[:SHARED]->(u)
)

// I. Connect Named Entity Recognition (NER) Targets (Geospatial heatmapping context)[cite: 1]
FOREACH (loc IN event.entities.ner_locations |
    MERGE (l:Location {name: loc})
    MERGE (post)-[:TARGETS_LOCATION]->(l)
)
FOREACH (org IN event.entities.ner_organizations |
    MERGE (o:Organization {name: org})
    MERGE (post)-[:TARGETS_ORGANIZATION]->(o)
)
"""


class GraphInjestor:
    def __init__(self) -> None:
        self.driver: Driver = Neo4jConnection.get_driver()

    def ingest_batch(self, raw_events: list[dict]) -> int:

        if not raw_events:
            logging.warning("Empty batch passed")
            return 0

        validated_events = []
        for raw in raw_events:
            try:
<<<<<<< HEAD
                eventobj = EnrichedSocialEvent(**raw)
=======
                eventobj = SocialPostEvent(**raw)
>>>>>>> f5d817d (Clean history without large files)
                validated_events.append(eventobj.model_dump())

            except Exception as e:
                logging.error(
                    f"Payload validation failed for post_id: {raw.get('post_id')}. Error: {e}"
                )

        if not validated_events:
            logging.error("No valid events to ingest after validation step.")
            return 0

        with self.driver.session() as session:
            try:
                session.run(CYPHER_BATCH_INGEST, events=validated_events)
                logging.info(
                    f"Successfully ingested {len(validated_events)} events into Neo4j."
                )
                return len(validated_events)
            except Exception as e:
                logging.error(f"Cypher ingestion failed: {e}")
                raise
