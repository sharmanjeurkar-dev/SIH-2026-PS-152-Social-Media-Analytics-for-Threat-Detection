import json
import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from fusion_engine import ThreatFusionNode

llm = ChatNVIDIA(
    model="nvidia/nemotron-3-super-120b-a12b", 
    temperature=0.5,
    timeout=300.0
)

fusion_node = ThreatFusionNode(temperature=0.5, max_retries=5)

class NewsCredibilityAssessment(BaseModel):
    credibility_score: float = Field(description="Float from 0.0 to 1.0")
    is_volatile: bool = Field(description="True if high viral potential")

class ThreatAssessment(BaseModel):
    threat_level: str = Field(description="Strictly: SAFE, LOW_RISK, MODERATE_RISK, or HIGH_THREAT")
    threat_score: float = Field(description="3-decimal numerical float")
    key_escalation_factor: str = Field(description="One sentence summary")
    is_anomaly: bool = Field(description="True if coordinated anomaly")

news_filter_prompt = ChatPromptTemplate.from_template("""
You are a news validation and disinformation filter. 
Analyze the post and return ONLY a valid JSON object with these exact keys:
- "credibility_score": a float between 0.0 and 1.0
- "is_volatile": a boolean (true or false)

Post content:
"{content}"
""")
news_filter_chain = news_filter_prompt | llm

def evaluate_news_credibility(content: str) -> float:
    try:
        response = news_filter_chain.invoke({"content": content})
        clean_text = response.content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        return float(data.get("credibility_score", 0.3))
    except Exception as e:
        print(f"News filter fallback triggered: {e}")
        return 0.3

def search_and_extract_by_keyword(query: str, max_videos: int = 1) -> str:
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
        
        transcript_list = YouTubeTranscriptApi.get_transcript(vid_id, languages=['en', 'hi'])
        full_transcript = " ".join([chunk['text'] for chunk in transcript_list])        
        return f"Full Video URL: {yt_url} | Transcript: {full_transcript}"
        
    except Exception as e:
        return f"Captions unavailable or extraction failed: {str(e)}"

def evaluate_threat(
    threat_severity: float, 
    violent_intent: float, 
    radicalization: float, 
    graph_density: float,
    pagerank_max: float,
    bot_prob: float,
    malicious_prob: float,
    ordinary_prob: float,
    cluster_count: int
) -> dict:
    semantic_payload = {
        "threat_severity_score": threat_severity,
        "violent_intent_probability": violent_intent,
        "radicalization_index": radicalization
    }
    
    network_payload = {
        "graph_density": graph_density,
        "super_spreader_pagerank_max": pagerank_max,
        "bot_probability": bot_prob,
        "malicious_user_probability": malicious_prob,
        "ordinary_user_probability": ordinary_prob,
        "louvain_cluster_count": cluster_count
    }
    
    return fusion_node.evaluate_threat(semantic_payload, network_payload)