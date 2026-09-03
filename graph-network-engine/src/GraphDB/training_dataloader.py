import ast
import csv
import logging
import re
from typing import Any, Dict, List

from src.GraphDB.connection import Neo4jConnection

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

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
    p.reply_count = toInteger(row.reply_count)

// 3. Connect Author -> Post
MERGE (author)-[:POSTED {timestamp: row.timestamp}]->(p)

// 4. Connect MENTION Targets (Builds the Graph Edges)
FOREACH (target_handle IN row.mentions |
    MERGE (target:User {handle: target_handle})
    ON CREATE SET target.user_id = 'usr_' + target_handle
    MERGE (author)-[r:INTERACTED_WITH {type: 'MENTION'}]->(target)
    ON CREATE SET r.weight = 1.0, r.first_seen = row.timestamp
    ON MATCH SET r.weight = r.weight + 1.0, r.last_seen = row.timestamp
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

    def _parse_user_col(self, user_str: str) -> dict:
        """Parses the messy stringified JSON/dict in the Kaggle user column."""
        user_id, username, followers, following = "unknown", "unknown", 0, 0
        try:
            # Safely evaluate the string into a python dictionary
            user_dict = ast.literal_eval(user_str) if user_str else {}
            user_id = str(user_dict.get("id", "unknown"))
            username = str(user_dict.get("username", "unknown"))
            followers = int(user_dict.get("followersCount", 0))
            following = int(user_dict.get("friendsCount", 0))
        except Exception:
            # Fallback regex if ast fails
            u_match = re.search(r"'username':\s*'([^']+)'", user_str)
            id_match = re.search(r"'id':\s*(\d+)", user_str)
            if u_match:
                username = u_match.group(1)
            if id_match:
                user_id = id_match.group(1)

        return {
            "user_id": user_id,
            "username": username,
            "followers": followers,
            "following": following,
        }

    def load_users_csv(self, users_csv_path: str):
        logging.info(f"Starting Pass 1: Ingesting Users from {users_csv_path}")
        batch = []
        total = 0

        with open(users_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                u_data = self._parse_user_col(row.get("user", ""))

                batch.append(
                    {
                        "user_id": f"usr_{u_data['user_id']}",
                        "handle": u_data["username"],
                        "followers_count": u_data["followers"],
                        "following_count": u_data["following"],
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

    def load_tweets_csv(self, tweets_csv_path: str):
        logging.info(f"Starting Pass 2: Ingesting Tweets from {tweets_csv_path}")
        batch = []
        total = 0

        with open(tweets_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Kaggle schema: text is stored in 'content' or 'renderedContent'
                text = (
                    row.get("content")
                    or row.get("renderedContent")
                    or row.get("text")
                    or ""
                )
                post_id = str(row.get("id") or row.get("tweet_id") or total).strip()

                u_data = self._parse_user_col(row.get("user", ""))

                # Extract Hashtags and Mentions from text to build graph edges
                hashtags = self.hashtag_regex.findall(text)
                mentions = self.mention_regex.findall(text)

                batch.append(
                    {
                        "post_id": f"tweet_{post_id}",
                        "timestamp": row.get("date") or row.get("created_at") or "",
                        "author_id": f"usr_{u_data['user_id']}",
                        "author_handle": u_data["username"],
                        "mentions": list(set(mentions)),  # Deduplicate targets
                        "retweet_count": row.get("retweetCount")
                        or row.get("retweet_count")
                        or 0,
                        "reply_count": row.get("replyCount")
                        or row.get("reply_count")
                        or 0,
                        "hashtags": list(set(hashtags)),
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
