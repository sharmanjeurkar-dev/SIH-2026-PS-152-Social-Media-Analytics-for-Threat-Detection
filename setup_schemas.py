import asyncio
from elasticsearch import AsyncElasticsearch
from neo4j import AsyncGraphDatabase

# Initialize connections matching your docker-compose setup
es_client = AsyncElasticsearch("http://localhost:9200")
neo4j_driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

async def setup_elasticsearch():
    """Defines the index and mappings for Member 2's NLP output."""
    index_name = "social_posts"
    
    mapping = {
        "mappings": {
            "properties": {
                "post_id": {"type": "keyword"},
                "content": {"type": "text"}, # Full-text search
                "toxicity_score": {"type": "float"}, # ML output
                "threat_category": {"type": "keyword"}, # e.g., "Communal Tension"
                "location": {"type": "keyword"},
                "timestamp": {"type": "date"}
            }
        }
    }

    # Check if index exists, if not, create it
    exists = await es_client.indices.exists(index=index_name)
    if not exists:
        await es_client.indices.create(index=index_name, body=mapping)
        print(f"Elasticsearch: Created index '{index_name}' with strict mappings.")
    else:
        print(f"Elasticsearch: Index '{index_name}' already exists.")

async def setup_neo4j():
    """Enforces unique constraints for Member 3's network graphs."""
    async with neo4j_driver.session() as session:
        # Ensure User nodes are unique by user_id
        await session.run("CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE")
        # Ensure Post nodes are unique by post_id
        await session.run("CREATE CONSTRAINT post_id IF NOT EXISTS FOR (p:Post) REQUIRE p.post_id IS UNIQUE")
        print("Neo4j: Constraints established for Users and Posts.")

async def main():
    print("Initializing Database Schemas...")
    await setup_elasticsearch()
    await setup_neo4j()
    
    # Close connections
    await es_client.close()
    await neo4j_driver.close()
    print("Schema setup complete.")

if __name__ == "__main__":
    asyncio.run(main())