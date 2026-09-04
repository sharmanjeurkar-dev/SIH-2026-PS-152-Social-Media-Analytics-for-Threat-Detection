import os
import sys

# Ensure root of graph-network-engine is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.GraphDB.connection import Neo4jConnection
from src.GraphDB.training_dataloader import DirectDatasetLoader

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
USERS_CSV = os.path.join(DATA_DIR, "users.csv")
TWEETS_CSV = os.path.join(DATA_DIR, "tweets.csv")


def run_ingestion(max_users: int = 50000, max_tweets: int = 50000):
    Neo4jConnection.init_schema()

    loader = DirectDatasetLoader(batch_size=5000)

    # 1. First pass: Populates (:User) nodes with authentic follower counts from users.csv
    print(f"Loading user profiles from {USERS_CSV} (limit: {max_users})...")
    loader.load_users_csv(USERS_CSV, max_rows=max_users)

    # 2. Second pass: Links (:Post), creates [:POSTED], and builds [:INTERACTED_WITH] edges
    print(
        f"Loading tweets and interaction edges from {TWEETS_CSV} (limit: {max_tweets})..."
    )
    loader.load_tweets_csv(TWEETS_CSV, max_rows=max_tweets)

    Neo4jConnection.close()
    print("Ingestion complete.")


if __name__ == "__main__":
    run_ingestion()
