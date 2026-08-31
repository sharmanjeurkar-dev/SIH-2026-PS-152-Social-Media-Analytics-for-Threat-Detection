from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time

from services import (
    ThreatAssessment,
    evaluate_news_credibility,
    extract_keywords_from_post,
    search_and_extract_by_keyword,
    evaluate_threat
)

app = FastAPI(title="Multimodal Escalation Fusion Engine")

class SocialMediaPayload(BaseModel):
    source: str
    content: str
    base_sentiment_score: float
    graph_density: float

@app.post("/process-chatter", response_model=ThreatAssessment)
async def process_chatter(payload: SocialMediaPayload):
    try:
        # 1. Gatekeeper: News Rating Filter
        credibility = evaluate_news_credibility(payload.content)
        youtube_context = None

        # 2. Decision Diamond: Trigger YouTube extraction if unverified/volatile
        if credibility < 0.5:
            print("Volatility threshold crossed. Triggering YT Enrichment...")
            queries = extract_keywords_from_post(payload.content)
            if queries:
                youtube_context = search_and_extract_by_keyword(queries[0])
            time.sleep(1)

        # 3. Final Fusion Threat Score
        assessment = evaluate_threat(
            base_sentiment=payload.base_sentiment_score,
            graph_data=payload.graph_density,
            yt_context=youtube_context
        )
        return assessment

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)