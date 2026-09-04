import json
import re
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# Initialize active model
llm = ChatNVIDIA(model="nvidia/nemotron-3-super-120b-a12b", temperature=0, timeout=120.0)

fusion_prompt = ChatPromptTemplate.from_template("""
You are the Predictive Threat Escalation Engine.
Evaluate the threat probability based on:

1. RAW SOCIAL / FIELD TEXT:
{raw_text}

2. SEMANTIC INTELLIGENCE (Member 2 NLP Handoff):
{semantic_context}

3. NETWORK INTELLIGENCE (Member 3 Graph Handoff):
{network_context}

Respond ONLY with a valid JSON object with these exact keys:
{{
  "threat_level": "SAFE" | "LOW_RISK" | "MODERATE_RISK" | "HIGH_THREAT",
  "threat_score": <float between 0.0 and 1.0>,
  "key_escalation_factor": "<short explanation>",
  "is_anomaly": <true or false>
}}
""")

fusion_chain = fusion_prompt | llm

# Synthetic Member 3 baseline network graph data
default_network_context = {
    "graph_density": 0.42,
    "super_spreader_pagerank_max": 0.35,
    "bot_swarm_probability": 0.20,
    "louvain_cluster_count": 2
}

def clean_json_response(raw_output: str) -> dict:
    match = re.search(r"\{.*\}", raw_output, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return json.loads(raw_output)

def run_evaluation(test_cases: list):
    results = []
    print(f"\n🚀 Running Evaluation across {len(test_cases)} scenarios...\n")
    print(f"{'CASE ID':<12} | {'EXPECTED':<22} | {'PREDICTED':<16} | {'SCORE':<6} | {'STATUS'}")
    print("-" * 75)

    for case in test_cases:
        cid = case["case_id"]
        expected = case["expected_label"]
        payload = {
            "raw_text": case["raw_text"],
            "semantic_context": json.dumps(case["handoff_to_member4"]),
            "network_context": json.dumps(default_network_context)
        }

        # 3-Attempt retry wrapper to handle busy server queues
        predicted_level = "ERROR"
        threat_score = 0.0
        for attempt in range(1, 4):
            try:
                res = fusion_chain.invoke(payload)
                parsed = clean_json_response(res.content)
                predicted_level = parsed.get("threat_level", "UNKNOWN")
                threat_score = parsed.get("threat_score", 0.0)
                break
            except Exception:
                time.sleep(attempt * 3)

        # Match check
        matched = "✅ PASS" if predicted_level in expected else "⚠️ CHECK"
        print(f"{cid:<12} | {expected:<22} | {predicted_level:<16} | {threat_score:<6} | {matched}")
        
        results.append({
            "case_id": cid,
            "expected": expected,
            "predicted": predicted_level,
            "threat_score": threat_score
        })
        time.sleep(1) # Prevent rapid API rate drops

    return results

if __name__ == "__main__":
    from test_cases_dataset import test_cases
    run_evaluation(test_cases)