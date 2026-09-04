# evaluate_200_cases.py
import ast
import csv
import json
import re
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# 1. Initialize LLM with temperature 0.3 to inject organic variance for calculations
llm = ChatNVIDIA(
    model="nvidia/nemotron-3-super-120b-a12b",
    temperature=0.3,
    max_completion_tokens=2048, 
    timeout=180.0
)

# 2. Strict API Prompt featuring the Asymmetric Escalation Math Logic
fusion_prompt = ChatPromptTemplate.from_template("""You are a JSON API for a Predictive Threat Escalation Engine.

INPUT DATA:
Semantic Intel (NLP Handoff): {semantic_context}
Network Intel (Graph Handoff): {network_context}

CRITICAL RULES (Apply in order):
1. SAFE & LOW_RISK (Pass-Through): If the Semantic category indicates harmless content (e.g., "Sports / Political Satire", "Civic") or "Counter-Speech", output "SAFE" or "LOW_RISK". Directly pass through the "threat_severity_score" as your final score. Do not do any math.
2. MODERATE_RISK & HIGH_THREAT (Active Calculation Mode): If veiled coordination or direct threat is detected, abandon the base severity score and switch to calculation mode:
   - For MODERATE_RISK (0.40-0.69): Calculate the final score by taking the exact "violent_intent_probability" and adding 0.120 for the bot swarm penalty (e.g., 0.450 + 0.120 = 0.570).
   - For HIGH_THREAT (0.70-1.00): Calculate the final score by taking the exact "radicalization_index" and adding 0.050 for network clustering (e.g., 0.815 + 0.050 = 0.865).
3. 3-DECIMAL PRECISION: Your final output threat_score MUST have exactly 3 decimal places.

Allowed Tiers: SAFE (0.0-0.15), LOW_RISK (0.16-0.39), MODERATE_RISK (0.40-0.69), HIGH_THREAT (0.70-1.00).

OUTPUT SCHEMA:
Respond EXACTLY with this JSON format and absolutely nothing else.
{{
  "reasoning": "Step-by-step math. SAFE/LOW: Pass through threat_severity_score. MODERATE: violent_intent_probability + 0.120. HIGH: radicalization_index + 0.050. Show the equation.",
  "threat_level": "TIER_NAME",
  "threat_score": 0.000,
  "key_escalation_factor": "One sentence reason explaining the escalation or de-escalation.",
  "is_anomaly": false
}}""")

fusion_chain = fusion_prompt | llm

# Default network context injects the required bot metrics for the math equations
default_network_context = {
    "graph_density": 0.45,
    "super_spreader_pagerank_max": 0.30,
    "bot_swarm_probability": 0.22,
    "louvain_cluster_count": 2
}

def clean_json_response(raw_output: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_output.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    candidate = cleaned[start:end+1] if start != -1 and end != -1 else cleaned

    try:
        return json.loads(candidate)
    except Exception:
        pass

    try:
        python_syntax = candidate.replace("true", "True").replace("false", "False").replace("null", "None")
        result = ast.literal_eval(python_syntax)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

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
    # Reading from the 200-case dataset generated earlier
    with open("dataset_200_cases.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)

    total = len(dataset)
    passed_count = 0
    results_log = []

    print("\n============================================================")
    print(f"Starting Asymmetric Escalation Eval on {total} Cases")
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

        # Auto-retry loop for robust API handling
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

        # Handles delimiter edge-cases in validation
        clean_pred = predicted_level.replace(" ", "_")
        normalized_expected = expected.replace("_OR_", "/").replace(",", "/")
        valid_targets = [x.strip().upper().replace(" ", "_") for x in normalized_expected.split("/")]
        
        is_pass = any(target in clean_pred or clean_pred in target for target in valid_targets)
        status_str = "PASS" if is_pass else "CHECK"
        if is_pass:
            passed_count += 1

        # Format output to visually confirm 3-decimal precision in terminal
        print(f"{cid:<10} | {expected[:24]:<25} | {predicted_level:<15} | {threat_score:.3f} | {status_str}")

        results_log.append({
            "case_id": cid,
            "type": case["type"],
            "raw_text": case.get("raw_text", "[BLINDED]"),
            "expected": expected,
            "predicted": predicted_level,
            "threat_score": f"{threat_score:.3f}",
            "status": status_str,
            "factor": escalation_factor
        })

        time.sleep(1.0) 

    # Save to a distinct output file
    with open("evaluation_results_200.csv", "w", newline="", encoding="utf-8") as f:
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
    print("Detailed logs saved to: evaluation_results_200.csv\n")

if __name__ == "__main__":
    run_batch_evaluation()