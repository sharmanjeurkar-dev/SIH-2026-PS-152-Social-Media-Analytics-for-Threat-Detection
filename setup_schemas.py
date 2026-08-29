import asyncio
from elasticsearch import AsyncElasticsearch
from neo4j import AsyncGraphDatabase
from database import engine, Base
from models.user import User

async def setup_elasticsearch():
    """Defines the index and mappings for Member 2's NLP output."""
    index_name = "social_posts"
    
    # In ESv8, you pass the properties directly to the 'mappings' parameter
    mapping_properties = {
        "properties": {
            "post_id": {"type": "keyword"},
            "content": {"type": "text"},
            "toxicity_score": {"type": "float"},
            "threat_category": {"type": "keyword"},
            "location": {"type": "keyword"},
            "timestamp": {"type": "date"}
        }
    }

    # The async context manager properly opens and closes the background session
    async with AsyncElasticsearch("http://localhost:9200") as es_client:
        # Wait for the database to be fully initialized before sending requests
        await es_client.cluster.health(wait_for_status="yellow")
        
        exists = await es_client.indices.exists(index=index_name)
        if not exists:
            await es_client.indices.create(index=index_name, mappings=mapping_properties)
            print(f"Elasticsearch: Created index '{index_name}' with strict mappings.")
        else:
            print(f"Elasticsearch: Index '{index_name}' already exists.")

async def setup_neo4j():
    """Enforces unique constraints for Member 3's network graphs."""
    driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
    
    async with driver.session() as session:
        await session.run("CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE")
        await session.run("CREATE CONSTRAINT post_id IF NOT EXISTS FOR (p:Post) REQUIRE p.post_id IS UNIQUE")
        print("Neo4j: Constraints established for Users and Posts.")
        
    await driver.close()

async def setup_postgres():
    """Generates the relational tables for authentication."""
    async with engine.begin() as conn:
        # This creates the tables based on the models defined
        await conn.run_sync(Base.metadata.create_all)
        print("PostgreSQL: Officer authentication tables established.")

async def main():
    print("Initializing Database Schemas...")
    await setup_elasticsearch()
    await setup_neo4j()
    await setup_postgres()
    print("Schema setup complete.")

if __name__ == "__main__":
    asyncio.run(main())