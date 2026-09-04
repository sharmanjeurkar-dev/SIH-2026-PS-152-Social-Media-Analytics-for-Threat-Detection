from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time

from services import (
    ThreatAssessment,
    evaluate_news_credibility,
    search_and_extract_by_keyword,
    evaluate_threat
)

app = FastAPI(title="Multimodal Escalation Fusion Engine - Production API")

class SocialMediaPayload(BaseModel):
    source: str
    content: str
    threat_severity_score: float
    violent_intent_probability: float
    radicalization_index: float
    youtube_search_keywords: list[str]
    graph_density: float
    super_spreader_pagerank_max: float
    bot_probability: float
    malicious_user_probability: float
    ordinary_user_probability: float
    louvain_cluster_count: int

@app.post("/process-chatter", response_model=ThreatAssessment)
def process_chatter(payload: SocialMediaPayload):
    try:
        credibility = evaluate_news_credibility(payload.content)

        if credibility < 0.5:
            print("Volatility threshold crossed. Triggering YT Enrichment...")
            if payload.youtube_search_keywords:
                extracted_video_data = search_and_extract_by_keyword(payload.youtube_search_keywords[0])
            time.sleep(1)

        assessment = evaluate_threat(
            threat_severity=payload.threat_severity_score,
            violent_intent=payload.violent_intent_probability,
            radicalization=payload.radicalization_index,
            graph_density=payload.graph_density,
            pagerank_max=payload.super_spreader_pagerank_max,
            bot_prob=payload.bot_probability,
            malicious_prob=payload.malicious_user_probability,
            ordinary_prob=payload.ordinary_user_probability,
            cluster_count=payload.louvain_cluster_count
        )
        return assessment

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)