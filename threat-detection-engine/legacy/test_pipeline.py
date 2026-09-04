import os
import json
from services import search_and_extract_by_keyword, evaluate_threat

def test_full_fusion_engine():
    print("=" * 60)
    print("1. Extracting live context via YouTube scraper...")
    print("=" * 60)
    
    query = "breaking news security situation"
    yt_context = search_and_extract_by_keyword(query, max_videos=1)
    print(f"-> Pulled {len(yt_context)} characters of context.")

    print("\n" + "=" * 60)
    print("2. Evaluating Threat via Llama 3.3 NIM Fusion Engine...")
    print("=" * 60)
    
    simulated_sentiment = 0.85
    simulated_graph_density = 0.78

    assessment = evaluate_threat(
        base_sentiment=simulated_sentiment,
        graph_data=simulated_graph_density,
        yt_context=yt_context
    )

    print("\n" + "=" * 60)
    print("FINAL THREAT ASSESSMENT OUTPUT:")
    print("=" * 60)
    print(json.dumps(assessment.model_dump(), indent=2))

if __name__ == "__main__":
    test_full_fusion_engine()