# evaluate_100_cases.py
import ast
import csv
import json
import re
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# 1. Fix DeprecationWarning and double token headroom (2048) for edge-case resolution
llm = ChatNVIDIA(
    model="nvidia/nemotron-3-super-120b-a12b",
    temperature=0.0,
    max_completion_tokens=2048, 
    timeout=180.0
)

fusion_prompt = ChatPromptTemplate.from_template("""You are a JSON API for a Predictive Threat Escalation Engine.

INPUT DATA:
Semantic Intel (NLP Handoff): {semantic_context}
Network Intel (Graph Handoff): {network_context}

CRITICAL RULES (Apply in order):
1. THE BURDEN OF PROOF (SAFE/LOW_RISK CURE): If the Semantic category indicates harmless content (e.g., "Sports / Political Satire", "Civic", "Weather") or the violent_intent_probability is low, the output MUST be "SAFE" (score <= 0.15) or "LOW_RISK" (0.16-0.39). High network metrics (bot swarms) on benign semantic data do NOT create physical threats.
2. COUNTER-SPEECH: If the category indicates quoting, reporting, or awareness of violence, output "LOW_RISK" (0.20 - 0.35).
3. SCORE POLARIZATION (MODERATE/HIGH CURE): If the Semantic Intel flags "Community Coordination (Veiled)", high radicalization, or elevated violent intent, anchor the score heavily at 0.65 (MODERATE_RISK) or 0.85+ (HIGH_THREAT). Do not output ambiguous 0.40-0.55 scores.

Allowed Tiers: SAFE (0.0-0.15), LOW_RISK (0.16-0.39), MODERATE_RISK (0.40-0.69), HIGH_THREAT (0.70-1.00).

OUTPUT SCHEMA:
Respond EXACTLY with this JSON format and absolutely nothing else.
{{
  "reasoning": "Chain of thought: Does the semantic data prove a physical threat? If veiled coordination is flagged, anchor score at 0.65+.",
  "threat_level": "TIER_NAME",
  "threat_score": 0.00,
  "key_escalation_factor": "One sentence reason based on the provided intel metrics.",
  "is_anomaly": false
}}""")

fusion_chain = fusion_prompt | llm

default_network_context = {
    "graph_density": 0.45,
    "super_spreader_pagerank_max": 0.30,
    "bot_swarm_probability": 0.22,
    "louvain_cluster_count": 2
}

def clean_json_response(raw_output: str) -> dict:
    # Aggressively strip markdown and find JSON block boundaries
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_output.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    candidate = cleaned[start:end+1] if start != -1 and end != -1 else cleaned

    # Try standard JSON
    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Try AST for single quotes/booleans
    try:
        python_syntax = candidate.replace("true", "True").replace("false", "False").replace("null", "None")
        result = ast.literal_eval(python_syntax)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    # Final Fallback: Regex Regex value harvester
    level_match = re.search(r'"threat_level"\s*:\s*"([^"]+)"', candidate)
    score_match = re.search(r'"threat_score"\s*:\s*([0-9.]+)', candidate)
    factor_match = re.search(r'"key_escalation_factor"\s*:\s*"([^"]*)"', candidate)
    anomaly_match = re.search(r'"is_anomaly"\s*:\s*(true|false|True|False)', candidate, re.IGNORECASE)

    if level_match and score_match:
        return {
            "threat_level": level_match.group(1).strip().upper(),
            "threat_score": float(score_match.group(1)),
            "key_escalation_factor": factor_match.group(1) if factor_match else "",
            "is_anomaly": anomaly_match.group(1).lower() == "true" if anomaly_match else False
        }

    raise ValueError(f"Could not parse payload from raw response: {raw_output[:250]}...")

def run_batch_evaluation():
    with open("dataset_100_cases.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)
    total = len(dataset)
    passed_count = 0
    results_log = []

    print("\n============================================================")
    print(f"Starting Evaluation on {total} Benchmark Cases")
    print(f"{'CASE ID':<10} | {'EXPECTED':<25} | {'PREDICTED':<15} | {'SCORE':<6} | {'STATUS'}")
    print("-" * 75)

    for idx, case in enumerate(dataset, start=1):
        cid = case["case_id"]
        expected = case["expected_label"]
        payload = {
            "semantic_context": json.dumps(case["handoff_to_member4"]),
            "network_context": json.dumps(default_network_context)
        }

        predicted_level = "ERROR"
        threat_score = 0.0
        escalation_factor = ""

        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                res = fusion_chain.invoke(payload)
                parsed = clean_json_response(res.content)
                predicted_level = parsed.get("threat_level", "UNKNOWN").strip().upper()
                threat_score = float(parsed.get("threat_score", 0.0))
                escalation_factor = parsed.get("key_escalation_factor", "")
                break
            except Exception as e:
                err_str = str(e)
                is_server_overload = any(code in err_str for code in ["503", "429", "overloaded", "timeout"])
                wait_seconds = attempt * 8 if is_server_overload else attempt * 3

                print(f"\n[!] Reason for failure on {cid} (Attempt {attempt}/{max_attempts}): {type(e).__name__} -> {e}")
                if attempt < max_attempts:
                    print(f"    Waiting {wait_seconds}s before attempt {attempt + 1}...")
                    time.sleep(wait_seconds)
                else:
                    escalation_factor = f"FAILED: {type(e).__name__} - {e}"
                    print(f"    [X] Exhausted all {max_attempts} retries for {cid}.\n")

        # Normalize matching (ignores extra spaces/casing)
        clean_pred = predicted_level.replace(" ", "_")
        valid_targets = [x.strip().upper().replace(" ", "_") for x in expected.replace("_OR_", "/").split("/")]
        is_pass = any(target in clean_pred or clean_pred in target for target in valid_targets)
        
        status_str = "PASS" if is_pass else "CHECK"
        if is_pass:
            passed_count += 1

        print(f"{cid:<10} | {expected[:24]:<25} | {predicted_level:<15} | {threat_score:<6} | {status_str}")

        results_log.append({
            "case_id": cid,
            "type": case["type"],
            "raw_text": case["raw_text"],
            "expected": expected,
            "predicted": predicted_level,
            "threat_score": threat_score,
            "status": status_str,
            "factor": escalation_factor
        })

        time.sleep(1.0)

    with open("evaluation_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["case_id", "type", "expected", "predicted", "threat_score", "status", "factor", "raw_text"]
        )
        writer.writeheader()
        writer.writerows(results_log)

    accuracy = (passed_count / total) * 100
    print("============================================================")
    print("EVALUATION COMPLETE")
    print(f"Total Cases: {total} | Passed: {passed_count} | Accuracy: {accuracy:.2f}%")
    print("Detailed logs saved to: evaluation_results.csv\n")

if __name__ == "__main__":
    run_batch_evaluation()