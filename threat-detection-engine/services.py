from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi
import time

# --- 1. FastAPI & Pydantic Setup ---
app = FastAPI(title="Multimodal Escalation Fusion Engine")

class SocialMediaPayload(BaseModel):
    source: str
    content: str
    base_sentiment_score: float
    graph_density: float

class ExtractedKeywords(BaseModel):
    search_queries: list[str] = Field(description="1 to 2 concise YouTube search queries derived from the text")

class ThreatAssessment(BaseModel):
    threat_level: str = Field(description="Strictly output: LOW, MEDIUM, HIGH, or CRITICAL")
    threat_score: float = Field(description="A numerical float between 0.0 and 1.0")
    key_escalation_factor: str = Field(description="One sentence explaining the primary risk")
    is_anomaly: bool = Field(description="True if coordinated activity is surging")

# --- 2. LangChain Evaluators ---
# Ensure OPENAI_API_KEY is in your .env file
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# News Rating Filter (Determines if YT scrape is needed)
def evaluate_news_credibility(content: str) -> float:
    # A mock function replacing Member 4's previous Isolation Forest logic.
    # In production, this would be an LLM call evaluating verification status.
    # Returning < 0.5 triggers the YouTube branch.
    return 0.3 

# Keyword Extractor
keyword_extractor = llm.with_structured_output(ExtractedKeywords)
keyword_prompt = ChatPromptTemplate.from_template("Extract optimal YouTube search keywords from this alert: {text}")
keyword_chain = keyword_prompt | keyword_extractor

# Final Threat Judge
threat_judge = llm.with_structured_output(ThreatAssessment)
threat_prompt = ChatPromptTemplate.from_template("""
Analyze the pipeline data and assign a threat score.
Base Sentiment: {sentiment}
Graph Density: {graph}
YouTube Context (if any): {yt_context}
""")
threat_chain = threat_prompt | threat_judge

# --- 3. YouTube Scraper Logic ---
def get_youtube_context(query: str) -> str:
    print(f"Executing YouTube Discovery for: {query}")
    try:
        videos = scrapetube.get_search(query=query, limit=1, sort_by="upload_date")
        vid_id = next(videos)['videoId']
        transcript = YouTubeTranscriptApi().fetch(vid_id, languages=['en', 'hi'])
        text = " ".join([chunk['text'] for chunk in transcript[:5]]) # First 5 chunks
        return f"Found related video context: {text}"
    except Exception as e:
        return "No accessible video context found."

# --- 4. The Main Routing Endpoint ---
@app.post("/process-chatter", response_model=ThreatAssessment)
async def process_chatter(payload: SocialMediaPayload):
    try:
        news_score = evaluate_news_credibility(payload.content)
        youtube_context = "None required."
        
        # The Decision Diamond
        if news_score < 0.5:
            print("Volatility threshold crossed. Triggering YT Enrichment...")
            extracted = keyword_chain.invoke({"text": payload.content})
            primary_query = extracted.search_queries[0]
            youtube_context = get_youtube_context(primary_query)
            # Add a small delay to prevent API rate limits if scaling up
            time.sleep(1)
            
        # Final Fusion
        final_threat = threat_chain.invoke({
            "sentiment": payload.base_sentiment_score,
            "graph": payload.graph_density,
            "yt_context": youtube_context
        })
        
        return final_threat

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)