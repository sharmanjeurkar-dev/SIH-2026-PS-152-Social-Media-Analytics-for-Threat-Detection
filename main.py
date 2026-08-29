import json
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from api_routes import analytics, network

app = FastAPI(title="NTRO Analytics Command Center")

# Include REST routing modules from the renamed folder
app.include_router(analytics.router, tags=["Analytics"])
app.include_router(network.router, tags=["Network Intelligence"])

# Initialize Redis client for pub/sub streaming
redis_client = redis.Redis(host='localhost', port=6379, db=0)
active_connections = []

@app.websocket("/ws/live-feed")
async def live_social_feed(websocket: WebSocket):
    """Streams real-time threat alerts directly to the frontend."""
    await websocket.accept()
    active_connections.append(websocket)
    
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("high_threat_alerts")
    
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                payload = json.loads(message["data"])
                await websocket.send_json(payload)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        await pubsub.unsubscribe("high_threat_alerts")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)