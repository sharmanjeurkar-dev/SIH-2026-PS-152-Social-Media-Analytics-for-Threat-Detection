import json
import random

def generate_synthetic_cases(count=200, start_id=1):
    dataset = []
    
    # Define the archetypes that Member 2 (NLP) might output
    archetypes = [
        {
            "type": "Civic Update",
            "category": "Civic Announcement",
            "expected": "SAFE",
            "severity_range": (0.01, 0.10),
            "violent_range": (0.00, 0.05),
            "radical_range": (0.00, 0.02)
        },
        {
            "type": "Satire/Sports",
            "category": "Sports / Political Satire",
            "expected": "SAFE / LOW_RISK",
            "severity_range": (0.05, 0.15),
            "violent_range": (0.10, 0.25), 
            "radical_range": (0.05, 0.10)
        },
        {
            "type": "Counter-Speech",
            "category": "Counter-Speech / Reporting",
            "expected": "LOW_RISK",
            "severity_range": (0.15, 0.30),
            "violent_range": (0.10, 0.20),
            "radical_range": (0.10, 0.20)
        },
        {
            "type": "Veiled Mobilization",
            "category": "Community Coordination (Veiled)",
            "expected": "MODERATE_RISK",
            "severity_range": (0.35, 0.55),
            "violent_range": (0.30, 0.55),
            "radical_range": (0.45, 0.65)
        },
        {
            "type": "Direct Threat",
            "category": "Targeted Hate / Mobilization",
            "expected": "HIGH_THREAT",
            "severity_range": (0.75, 0.95),
            "violent_range": (0.80, 0.99),
            "radical_range": (0.70, 0.90)
        }
    ]

    for i in range(count):
        case_id = f"CASE_{start_id + i:03d}"
        archetype = random.choice(archetypes)
        
        # Generate bounded random metrics based on the archetype
        sev_score = round(random.uniform(*archetype["severity_range"]), 3)
        viol_score = round(random.uniform(*archetype["violent_range"]), 3)
        rad_score = round(random.uniform(*archetype["radical_range"]), 3)
        
        case = {
            "case_id": case_id,
            "type": archetype["type"],
            "raw_text": f"[BLINDED FOR FUSION EVALUATION - TYPE: {archetype['type'].upper()}]",
            "expected_label": archetype["expected"],
            "handoff_to_member4": {
                "zero_shot_threat_category": archetype["category"],
                "threat_severity_score": sev_score,
                "violent_intent_probability": viol_score,
                "radicalization_index": rad_score,
                "toxicity_severity_score": round(random.uniform(0.0, sev_score + 0.1), 3),
                "sentiment": "NEGATIVE" if sev_score > 0.4 else "NEUTRAL"
            }
        }
        dataset.append(case)

    return dataset

if __name__ == "__main__":
    # Generates 200 cases and writes to the newly designated JSON file
    new_cases = generate_synthetic_cases(count=200, start_id=1)
    
    with open("dataset_200_cases.json", "w", encoding="utf-8") as f:
        json.dump(new_cases, f, indent=4)
        
    print(f"Successfully generated {len(new_cases)} cases and saved to dataset_200_cases.json")