import ast
import json
import re
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA

class ThreatFusionNode:
    def __init__(self, temperature=0.5, max_retries=5):
        self.max_retries = max_retries
        
        self.llm = ChatNVIDIA(
            model="nvidia/nemotron-3-super-120b-a12b",
            temperature=temperature,
            max_completion_tokens=2048, 
            timeout=180.0
        )
        
        self.prompt = ChatPromptTemplate.from_template("""You are a JSON API for a Predictive Threat Escalation Engine.

INPUT DATA (NUMERICAL ONLY):
Semantic Intel: {semantic_context}
Network Intel: {network_context}

CRITICAL RULES (Apply in order):
1. SAFE & LOW_RISK (Random Mode): If the base "threat_severity_score" is below 0.40, do NOT pass the exact score through. Instead, generate a random, organic score within the exact tier boundary (SAFE: 0.000-0.150, LOW_RISK: 0.151-0.399).
2. MODERATE_RISK & HIGH_THREAT (Hard Calculation Mode): If the base score is 0.40 or higher, switch to hard calculation:
   - For MODERATE_RISK (0.40-0.69): Calculate by taking the exact "violent_intent_probability" and adding 0.120.
   - For HIGH_THREAT (0.70-1.00): Calculate by taking the exact "radicalization_index" and adding 0.050.
3. 3-DECIMAL PRECISION: Your final output threat_score MUST have exactly 3 decimal places.
4. ANOMALY DETECTION: Set "is_anomaly" to true if the Network Intel shows high "bot_probability" or a high "super_spreader_pagerank_max". Otherwise, false.
5. ESCALATION REASONING: Your "key_escalation_factor" MUST synthesize both Semantic intent and Network Intel (e.g., mention the PageRank or bot swarm presence).

Allowed Tiers: SAFE (0.0-0.15), LOW_RISK (0.16-0.39), MODERATE_RISK (0.40-0.69), HIGH_THREAT (0.70-1.00).

OUTPUT SCHEMA:
Respond EXACTLY with this JSON format and absolutely nothing else.
{{
  "reasoning": "Step-by-step logic. SAFE/LOW: Random organic score applied. MODERATE: violent_intent_probability + 0.120. HIGH: radicalization_index + 0.050.",
  "threat_level": "TIER_NAME",
  "threat_score": 0.000,
  "key_escalation_factor": "One sentence explaining the escalation based strictly on both semantic and network metrics.",
  "is_anomaly": false
}}""")
        
        self.chain = self.prompt | self.llm

    def _clean_json(self, raw_output: str) -> dict:
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
        return {"error": "Failed to parse LLM output", "raw_output": raw_output}

    def evaluate_threat(self, semantic_data: dict, network_data: dict) -> dict:
        payload = {
            "semantic_context": json.dumps(semantic_data),
            "network_context": json.dumps(network_data)
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                res = self.chain.invoke(payload)
                return self._clean_json(res.content)
            except Exception as e:
                if attempt == self.max_retries:
                    return {"threat_level": "ERROR", "threat_score": 0.0, "key_escalation_factor": str(e)}
                time.sleep(attempt * 2)