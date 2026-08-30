from fastapi import APIRouter, Depends
from neo4j import AsyncGraphDatabase
from models.schemas import GraphQuery
from api_routes.auth import get_current_user

router = APIRouter()
# Initialize in a dedicated services/ module for production
neo4j_driver = AsyncGraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))

@router.post("/api/v1/network/subgraph")
async def get_threat_network(
    query: GraphQuery,
    current_user: dict = Depends(get_current_user) # <-- The lock mechanism
):
    """Fetches exportable network subgraphs for UI visualization."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (u:User)-[r:RETWEETED]->(p:Post {hashtag: $tag}) RETURN u, r, p LIMIT 50",
            tag=query.hashtag
        )
        
        # Parse the raw Neo4j records into a structured JSON payload for Cytoscape.js
        nodes = []
        async for record in result:
            nodes.append(record.data())
            
        return {"network_graph": nodes}