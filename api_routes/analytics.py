from fastapi import APIRouter
from elasticsearch import AsyncElasticsearch

router = APIRouter()
# In a production app, initialize this in a dedicated services/ module and inject it
es_client = AsyncElasticsearch("http://localhost:9200")

@router.get("/api/v1/analytics/sentiment")
async def get_sentiment_analysis(query: str, limit: int = 100):
    """Retrieves filtered text analytics and sentiment scores for the UI."""
    search_body = {
        "query": {
            "match": {"content": query}
        },
        "size": limit
    }
    response = await es_client.search(index="social_posts", body=search_body)
    
    return {"results": response["hits"]["hits"]}