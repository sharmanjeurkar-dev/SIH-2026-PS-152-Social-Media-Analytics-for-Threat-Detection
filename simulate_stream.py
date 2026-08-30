import asyncio
import json
import random
from datetime import datetime
import redis.asyncio as redis

async def simulate_live_feed():
    # Connect to the local Redis container
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    
    threat_keywords = ["#riot", "#breach", "#unrest", "#protest"]
    locations = ["Bengaluru", "Mumbai", "New Delhi", "Chennai"]
    
    print("Starting live threat feed simulation...")
    
    try:
        while True:
            # Generate a mock threat alert payload
            payload = {
                "alert_id": f"ALT-{random.randint(1000, 9999)}",
                "timestamp": datetime.utcnow().isoformat(),
                "threat_level": random.choice(["ELEVATED", "HIGH", "CRITICAL"]),
                "keyword_detected": random.choice(threat_keywords),
                "location": random.choice(locations),
            }
            
            # Publish to the exact channel your FastAPI websocket is listening to
            await redis_client.publish("high_threat_alerts", json.dumps(payload))
            print(f"Published Alert: {payload['alert_id']} | Level: {payload['threat_level']}")
            
            # Wait 3 seconds before the next alert
            await asyncio.sleep(3)
            
    except KeyboardInterrupt:
        print("\nSimulation stopped.")

if __name__ == "__main__":
    # Suppress the KeyboardInterrupt traceback for a cleaner exit
    try:
        asyncio.run(simulate_live_feed())
    except KeyboardInterrupt:
        pass