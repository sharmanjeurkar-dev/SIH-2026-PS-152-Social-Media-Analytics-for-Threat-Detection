import asyncio
from elasticsearch import AsyncElasticsearch
from neo4j import AsyncGraphDatabase

async def seed_elasticsearch():
    """Injects mock NLP text and sentiment data into Elasticsearch."""
    es_client = AsyncElasticsearch("http://localhost:9200")
    
    mock_posts = [
        {
            "post_id": "post_001",
            "content": "Huge crowd gathering at the town square. #protest",
            "toxicity_score": 0.45,
            "threat_category": "Civil Unrest",
            "location": "Town Square"
        },
        {
            "post_id": "post_002",
            "content": "We need to burn this system to the ground tonight! #riot",
            "toxicity_score": 0.92,
            "threat_category": "Extremism",
            "location": "Downtown"
        },
        {
            "post_id": "post_003",
            "content": "Avoid the downtown area, roads are blocked. #safety",
            "toxicity_score": 0.15,
            "threat_category": "Safety Update",
            "location": "Downtown"
        }
    ]

    for post in mock_posts:
        await es_client.index(index="social_posts", id=post["post_id"], document=post)
    
    print("Elasticsearch: Mock NLP data injected.")
    await es_client.close()

async def seed_neo4j():
    """Injects a mock bot-swarm network into Neo4j."""
    driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
    
    cypher_query = """
    // Create a super-spreader post
    MERGE (p:Post {post_id: 'post_002', hashtag: '#riot'})
    
    // Create a central agitator and bot accounts
    MERGE (agitator:User {user_id: 'user_99', handle: '@system_burner'})
    MERGE (bot1:User {user_id: 'user_100', handle: '@bot_alpha'})
    MERGE (bot2:User {user_id: 'user_101', handle: '@bot_beta'})
    
    // Map the retweet relationships
    MERGE (agitator)-[:RETWEETED]->(p)
    MERGE (bot1)-[:RETWEETED]->(p)
    MERGE (bot2)-[:RETWEETED]->(p)
    """
    
    async with driver.session() as session:
        await session.run(cypher_query)
        print("Neo4j: Mock network graph injected.")
        
    await driver.close()

async def main():
    print("Seeding dummy data...")
    await seed_elasticsearch()
    await seed_neo4j()
    print("Database seeding complete.")

if __name__ == "__main__":
    asyncio.run(main())