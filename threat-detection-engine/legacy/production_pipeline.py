import json
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from services import search_and_extract_by_keyword

# 1. Initialize Fusion Engine with an active, high-capacity enterprise model
llm = ChatNVIDIA(model="nvidia/nemotron-3-super-120b-a12b", temperature=0, timeout=300.0)

fusion_prompt = ChatPromptTemplate.from_template("""
You are the Predictive Escalation Engine. Evaluate the threat probability based on:

1. YOUTUBE CONTEXT (Raw Extraction):
{yt_context}

2. SEMANTIC INTELLIGENCE (Member 2 NLP Output):
{semantic_context}

3. NETWORK INTELLIGENCE (Member 3 Graph Output):
{network_context}

Return a valid JSON threat assessment evaluating the likelihood of civil unrest.
The JSON must contain: "threat_level", "threat_score", "key_escalation_factor", and "is_anomaly".
""")

fusion_chain = fusion_prompt | llm

def execute_member_4_fusion(keyword: str, max_retries=3):
    print("============================================================")
    print(f"STAGE 1: Member 4 Pulling Context for '{keyword}'")
    
    # Keeps your full 5,000-character payload intact
    yt_transcript = search_and_extract_by_keyword(keyword, max_videos=1)[:5000]
    
    print("\nSTAGE 2: Receiving Inbound Handoffs (Members 2 & 3)")
    inbound_member_2_data = {
        "toxicity_score": 0.88,
        "threat_category": "COMMUNAL_TENSION",
        "ner_locations": ["Bengaluru", "Connaught Place"],
        "sentiment_polarity": -0.92
    }
    
    inbound_member_3_data = {
        "graph_density": 0.91,
        "super_spreader_pagerank_max": 0.84,
        "bot_swarm_probability": 0.78,
        "louvain_cluster_count": 3
    }
    
    print("\nSTAGE 3: Member 4 Multimodal Threat Fusion (LLM Processing...)")
    
    payload = {
        "yt_context": yt_transcript,
        "semantic_context": json.dumps(inbound_member_2_data),
        "network_context": json.dumps(inbound_member_3_data)
    }

    # Auto-retry loop to gracefully handle temporary public server spikes (503s)
    for attempt in range(1, max_retries + 1):
        try:
            response = fusion_chain.invoke(payload)
            print("\n============================================================")
            print("FINAL ESCALATION OUTPUT")
            print(response.content)
            return response.content
        except Exception as e:
            print(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                wait_time = attempt * 5
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("❌ Max retries reached.")
                raise e

if __name__ == "__main__":
    execute_member_4_fusion("breaking news live")