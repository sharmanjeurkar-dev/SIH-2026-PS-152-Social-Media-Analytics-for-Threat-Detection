import os
import json
import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# --- 1. LLM Model Selection ---
# Using Llama 3.2 90B with a 120-second timeout to handle payload stability
llm = ChatNVIDIA(
    model="meta/llama-3.2-90b-vision-instruct", 
    temperature=0,
    timeout=300.0
)


# --- 2. Pydantic Schemas ---

class ExtractedKeywords(BaseModel):
    search_queries: list[str] = Field(
        description="1 to 2 concise search keywords optimized for YouTube query discovery"
    )

class NewsCredibilityAssessment(BaseModel):
    credibility_score: float = Field(
        description="Float from 0.0 (completely unverified/viral panic) to 1.0 (verified factual reporting)"
    )
    is_volatile: bool = Field(
        description="True if the text contains high viral panic or escalation potential"
    )

class ThreatAssessment(BaseModel):
    threat_level: str = Field(description="Strictly output: LOW, MEDIUM, HIGH, or CRITICAL")
    threat_score: float = Field(description="A numerical float between 0.0 and 1.0")
    key_escalation_factor: str = Field(description="One sentence explaining the primary risk identified")
    is_anomaly: bool = Field(description="True if coordinated activity or sudden escalation is surging")


# --- 3. LangChain Evaluation Chains (Standard Invocation with JSON Formatting) ---

news_filter_prompt = ChatPromptTemplate.from_template("""
You are a news validation and disinformation filter. 
Analyze the post and return ONLY a valid JSON object with these exact keys:
- "credibility_score": a float between 0.0 and 1.0
- "is_volatile": a boolean (true or false)

Post content:
"{content}"
""")
news_filter_chain = news_filter_prompt | llm


keyword_prompt = ChatPromptTemplate.from_template("""
Extract 1 to 2 precise YouTube search terms. Return ONLY a valid JSON object with this exact key:
- "search_queries": a list of strings

Chatter:
"{content}"
""")
keyword_chain = keyword_prompt | llm


threat_prompt = ChatPromptTemplate.from_template("""
You are an intelligence threat scoring engine. Synthesize all provided data layers:
- Base Sentiment Score: {sentiment}
- Graph Network Density: {graph}
- Enriched YouTube Context: {yt_context}

You must return ONLY a valid JSON object matching this exact structure:
{{
    "threat_level": "LOW", "MEDIUM", "HIGH", or "CRITICAL",
    "threat_score": a float between 0.0 and 1.0,
    "key_escalation_factor": "One sentence explaining the primary risk",
    "is_anomaly": true or false
}}
""")
threat_chain = threat_prompt | llm


# --- 4. Service Functions ---

def evaluate_news_credibility(content: str) -> float:
    """Evaluates post credibility. Returns score < 0.5 if unverified or volatile."""
    try:
        response = news_filter_chain.invoke({"content": content})
        clean_text = response.content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        return float(data.get("credibility_score", 0.3))
    except Exception as e:
        print(f"News filter fallback triggered: {e}")
        return 0.3


def extract_keywords_from_post(content: str) -> list[str]:
    """Extracts YouTube search queries from post text."""
    try:
        response = keyword_chain.invoke({"content": content})
        clean_text = response.content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        return data.get("search_queries", [content[:40]])
    except Exception as e:
        print(f"Keyword extraction fallback triggered: {e}")
        return [content[:40]]


def search_and_extract_by_keyword(query: str, max_videos: int = 1) -> str:
    """Searches YouTube prioritizing recent uploads, prints direct URL, and extracts full transcripts."""
    recent_query = f"{query} live breaking news"
    print(f"Executing YouTube Discovery for: '{recent_query}'")
    try:
        videos = scrapetube.get_search(query=recent_query, limit=max_videos, sort_by="upload_date")
        video_entry = next(videos, None)
        
        if not video_entry:
            return "No matching videos found."

        vid_id = video_entry['videoId']
        yt_url = f"https://www.youtube.com/watch?v={vid_id}"
        
        print(f">>> [VERIFY VIDEO] Inspect source clip here: {yt_url}")
        
        transcript = YouTubeTranscriptApi().fetch(vid_id, languages=['en', 'hi'])
        full_transcript = " ".join([chunk.text for chunk in transcript])        
        return f"Full Video URL: {yt_url} | Transcript: {full_transcript}"
        
    except Exception as e:
        return f"Captions unavailable or extraction failed: {str(e)}"


def evaluate_threat(base_sentiment: float, graph_data: float, yt_context: str | None = None) -> ThreatAssessment:
    """Fuses all data streams into the final structured threat score with safe context sizing."""
    
    # Safely trim context to the first 2500 characters to prevent API read timeouts
    if yt_context:
        context_str = yt_context[:5000] + "\n[Transcript context truncated for length...]"
    else:
        context_str = "None required (standard verified flow)."
        
    try:
        response = threat_chain.invoke({
            "sentiment": base_sentiment,
            "graph": graph_data,
            "yt_context": context_str
        })
        clean_text = response.content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        return ThreatAssessment(**data)
    except Exception as e:
        print(f"Threat evaluation or JSON parsing error: {e}")
        return ThreatAssessment(
            threat_level="HIGH",
            threat_score=0.82,
            key_escalation_factor="Parsed via fallback due to syntax/format exception.",
            is_anomaly=True
        )