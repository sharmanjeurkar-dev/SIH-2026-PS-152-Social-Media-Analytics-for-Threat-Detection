import logging
from typing import Optional

from neo4j import Driver
from pydantic import BaseModel, Field

from src.GraphDB.connection import Neo4jConnection

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


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
    intent: Optional[str] = "NEUTRAL"
    language: Optional[str] = "en"


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
    MERGE (h:Hashtag {tag: ht})
    MERGE (post)-[:TAGGED_WITH]->(h)
    MERGE (author)-[:USED_HASHTAG {last_used: event.timestamp}]->(h)
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
                eventobj = SocialPostEvent(**raw)
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
