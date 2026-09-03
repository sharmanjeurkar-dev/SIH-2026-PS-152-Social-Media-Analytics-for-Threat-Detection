from src.GraphDB.connection import Neo4jConnection
from src.GraphDB.training_dataloader import DirectDatasetLoader

if __name__ == "__main__":
    Neo4jConnection.init_schema()

    loader = DirectDatasetLoader(batch_size=5000)

    # 1. First pass: Populates (:User) nodes with authentic follower counts
    loader.load_users_csv(
        "/Users/sharmanjeurkar/Projects/social_media_graph_engine/graph-network-engine/data/tweets.csv"
    )

    # 2. Second pass: Links (:Post), creates [:POSTED], and builds [:INTERACTED_WITH] edges
    loader.load_tweets_csv(
        "/Users/sharmanjeurkar/Projects/social_media_graph_engine/graph-network-engine/data/tweets.csv"
    )

    Neo4jConnection.close()
