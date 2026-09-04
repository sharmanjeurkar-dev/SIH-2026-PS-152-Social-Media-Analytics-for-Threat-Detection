import ast
import csv
import logging
import re
from typing import Any, Dict, List, Optional

from src.GraphDB.connection import Neo4jConnection

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# Threat and hostility keywords for NLP scoring fallback
THREAT_KEYWORDS = {
    "kill", "killing", "dead", "death", "attack", "attacker", "attacking", "destroy",
    "violence", "violent", "blood", "bloody", "riot", "riots", "rioting", "burn", "burning",
    "terror", "terrorist", "terrorism", "weapon", "weapons", "bomb", "blast", "hang",
    "gundas", "gunda", "goons", "goon", "enemy", "enemies", "threat", "threats", "threaten",
    "hate", "hateful", "hating", "shame", "shameful", "traitor", "traitors", "protest",
    "chakkajam", "extremist", "extremists", "clash", "clashes", "conspiracy", "anti-national"
}

# ==========================================================
# Cypher Queries for Two-Pass Ingestion
# ==========================================================

PASS1_USERS_CYPHER = """
UNWIND $batch AS row
MERGE (u:User {user_id: row.user_id})
ON CREATE SET 
    u.handle = row.handle,
    u.followers_count = toInteger(row.followers_count),
    u.following_count = toInteger(row.following_count)
ON MATCH SET
    u.handle = coalesce(row.handle, u.handle),
    u.followers_count = toInteger(row.followers_count),
    u.following_count = toInteger(row.following_count)
"""

PASS2_TWEETS_CYPHER = """
UNWIND $batch AS row

// 1. Ensure author exists
MERGE (author:User {user_id: row.author_id})
ON CREATE SET author.handle = row.author_handle

// 2. Merge Tweet / Post
MERGE (p:Post {post_id: row.post_id})
ON CREATE SET 
    p.timestamp = row.timestamp,
    p.retweet_count = toInteger(row.retweet_count),
    p.reply_count = toInteger(row.reply_count),
    p.toxicity_score = toFloat(row.toxicity_score),
    p.sentiment_score = toFloat(row.sentiment_score),
    p.threat_category = row.threat_category
ON MATCH SET
    p.toxicity_score = toFloat(row.toxicity_score),
    p.sentiment_score = toFloat(row.sentiment_score),
    p.threat_category = row.threat_category

// 3. Connect Author -> Post
MERGE (author)-[:POSTED {timestamp: row.timestamp}]->(p)

// 4. Connect MENTION Targets (Builds the Graph Edges)
FOREACH (target_handle IN row.mentions |
    MERGE (target:User {user_id: 'usr_' + target_handle})
    ON CREATE SET target.handle = target_handle
    MERGE (author)-[r:INTERACTED_WITH {type: 'MENTION'}]->(target)
    ON CREATE SET r.weight = 1.0 + (toFloat(row.toxicity_score) * 2.0), r.first_seen = row.timestamp
    ON MATCH SET r.weight = r.weight + 1.0 + (toFloat(row.toxicity_score) * 2.0), r.last_seen = row.timestamp
)

// 5. Connect Hashtags
FOREACH (ht IN row.hashtags |
    MERGE (h:Hashtag {tag: toLower(ht)})
    MERGE (p)-[:TAGGED_WITH]->(h)
    MERGE (author)-[:USED_HASHTAG]->(h)
)
"""


class DirectDatasetLoader:
    def __init__(self, batch_size: int = 5000):
        self.batch_size = batch_size
        self.driver = Neo4jConnection.get_driver()
        self.hashtag_regex = re.compile(r"#(\w+)")
        self.mention_regex = re.compile(r"@(\w+)")
        self.url_author_regex = re.compile(r"twitter\.com/([^/]+)/status")

    def _compute_nlp_metrics(self, text: str, row: dict) -> tuple[float, float, str]:
        """Derives toxicity, sentiment, and threat category from CSV or text heuristics."""
        # 1. Check if precomputed scores exist
        pre_tox = row.get("threat_severity_score") or row.get("toxicity_score")
        pre_cat = row.get("threat_category")
        if pre_tox is not None:
            try:
                score = float(pre_tox)
                if score > 0.0:
                    cat = str(pre_cat or "THREAT")
                    sent = -score
                    return round(score, 3), round(sent, 3), cat
            except (ValueError, TypeError):
                pass

        # 2. Text keyword heuristic
        words = re.findall(r"\b[a-zA-Z]+\b", (text or "").lower())
        if not words:
            return 0.0, 0.0, "BENIGN"

        threat_hits = sum(1 for w in words if w in THREAT_KEYWORDS)
        toxicity = min(threat_hits / 3.0, 1.0)
        sentiment = -min(threat_hits / 2.0, 1.0)

        if toxicity >= 0.6:
            category = "HIGH_THREAT"
        elif toxicity >= 0.3:
            category = "MEDIUM_THREAT"
        else:
            category = "BENIGN"

        return round(toxicity, 3), round(sentiment, 3), category

    def load_users_csv(self, users_csv_path: str, max_rows: Optional[int] = None):
        logging.info(f"Starting Pass 1: Ingesting Users from {users_csv_path}")
        batch = []
        total = 0

        with open(users_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader):
                if max_rows and total >= max_rows:
                    break

                # Support both column structures (direct or stringified JSON)
                username = row.get("username", "").strip()
                followers = 0
                following = 0

                if not username and "user" in row:
                    try:
                        u_dict = ast.literal_eval(row["user"]) if row["user"] else {}
                        username = str(u_dict.get("username", "")).strip()
                        followers = int(u_dict.get("followersCount", 0))
                        following = int(u_dict.get("friendsCount", 0))
                    except Exception:
                        pass
                else:
                    try:
                        followers = int(float(row.get("followersCount") or row.get("followers") or 0))
                    except (ValueError, TypeError):
                        followers = 0
                    try:
                        following = int(float(row.get("friendsCount") or row.get("following") or 0))
                    except (ValueError, TypeError):
                        following = 0

                if not username:
                    continue

                batch.append(
                    {
                        "user_id": f"usr_{username}",
                        "handle": username,
                        "followers_count": followers,
                        "following_count": following,
                    }
                )

                if len(batch) >= self.batch_size:
                    self._commit_batch(PASS1_USERS_CYPHER, batch)
                    total += len(batch)
                    logging.info(f"Ingested {total} users...")
                    batch = []

            if batch:
                self._commit_batch(PASS1_USERS_CYPHER, batch)
                total += len(batch)

        logging.info(f"[PASS 1 COMPLETE] Ingested {total} users.")

    def load_tweets_csv(self, tweets_csv_path: str, max_rows: Optional[int] = None):
        logging.info(f"Starting Pass 2: Ingesting Tweets from {tweets_csv_path}")
        batch = []
        total = 0

        with open(tweets_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader):
                if max_rows and total >= max_rows:
                    break

                text = (
                    row.get("renderedContent")
                    or row.get("content")
                    or row.get("text")
                    or ""
                )

                # Extract post ID safely
                raw_tid = str(
                    row.get("tweetId")
                    or row.get("tweet_id")
                    or row.get("id")
                    or row_idx
                ).strip()
                if raw_tid.endswith(".0"):
                    raw_tid = raw_tid[:-2]
                post_id = f"tweet_{raw_tid}"

                # Extract Author Handle from tweetUrl, or fallback to userId/user dict
                author_handle = ""
                url = row.get("tweetUrl", "")
                url_match = self.url_author_regex.search(url)
                if url_match:
                    author_handle = url_match.group(1).strip()
                elif "user" in row and row["user"]:
                    try:
                        u_dict = ast.literal_eval(row["user"])
                        author_handle = str(u_dict.get("username", "")).strip()
                    except Exception:
                        pass

                if not author_handle:
                    raw_uid = str(row.get("userId") or row.get("user_id") or "unknown").strip()
                    if raw_uid.endswith(".0"):
                        raw_uid = raw_uid[:-2]
                    author_handle = raw_uid

                author_id = f"usr_{author_handle}"

                # Extract mentions from mentionedUsers or regex from text
                mentions = []
                if "mentionedUsers" in row and row["mentionedUsers"]:
                    try:
                        mu_list = ast.literal_eval(row["mentionedUsers"])
                        if isinstance(mu_list, list):
                            for m in mu_list:
                                if isinstance(m, dict) and m.get("username"):
                                    mentions.append(m["username"].strip())
                    except Exception:
                        pass
                if not mentions:
                    mentions = self.mention_regex.findall(text)

                # Remove self-mentions and deduplicate
                cleaned_mentions = list(
                    {m for m in mentions if m.lower() != author_handle.lower() and m}
                )

                hashtags = list(set(self.hashtag_regex.findall(text)))

                # Compute or extract NLP metrics
                toxicity, sentiment, category = self._compute_nlp_metrics(text, row)

                try:
                    retweet_cnt = int(float(row.get("retweetCount") or row.get("retweet_count") or 0))
                except (ValueError, TypeError):
                    retweet_cnt = 0
                try:
                    reply_cnt = int(float(row.get("replyCount") or row.get("reply_count") or 0))
                except (ValueError, TypeError):
                    reply_cnt = 0

                batch.append(
                    {
                        "post_id": post_id,
                        "timestamp": row.get("date") or row.get("created_at") or "",
                        "author_id": author_id,
                        "author_handle": author_handle,
                        "mentions": cleaned_mentions,
                        "retweet_count": retweet_cnt,
                        "reply_count": reply_cnt,
                        "hashtags": hashtags,
                        "toxicity_score": toxicity,
                        "sentiment_score": sentiment,
                        "threat_category": category,
                    }
                )

                if len(batch) >= self.batch_size:
                    self._commit_batch(PASS2_TWEETS_CYPHER, batch)
                    total += len(batch)
                    logging.info(f"Ingested {total} tweets and interaction edges...")
                    batch = []

            if batch:
                self._commit_batch(PASS2_TWEETS_CYPHER, batch)
                total += len(batch)

        logging.info(f"[PASS 2 COMPLETE] Ingested {total} tweets.")

    def _commit_batch(self, query: str, batch: List[Dict[str, Any]]):
        with self.driver.session() as session:
            session.run(query, batch=batch)
