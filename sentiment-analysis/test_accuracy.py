"""
Accuracy-checking harness for the Member 2 NLP pipeline.

Run this LOCALLY, once your server (member2_nlp_intelligence_api.py) is up
and listening on port 8000. It sends a small hand-labeled test set to your
running API and reports how many it got right against ground-truth labels
I assigned by reading each sentence myself.

Important: this does NOT prove the pipeline is "100% accurate" -- it proves
it's accurate on THESE 8 examples. A zero-shot classifier will always miss
edge cases on text it's never seen. The honest way to build confidence
before your demo is running a set like this (ideally bigger, with your own
real examples added in) and seeing where it actually breaks -- not chasing
a perfect score on a handful of sentences.
"""

import requests

API_URL = "http://127.0.0.1:8000/process_post"

TEST_CASES = [
    {
        "text": "Traffic itna bura tha aaj, poora din waste ho gaya.",
        "expected_sentiment": "NEGATIVE",
        "expected_benign": True,
        "note": "Everyday complaint -- negative but harmless.",
    },
    {
        "text": "Mumbai mein aaj bahut accha weather hai, sab log park mein enjoy kar rahe hain.",
        "expected_sentiment": "POSITIVE",
        "expected_benign": True,
        "note": "Clearly positive, harmless chatter.",
    },
    {
        "text": "Wow, government ne phir se promise tod diya, kitna 'accha' kaam kiya unhone.",
        "expected_sentiment": "NEGATIVE",
        "expected_benign": True,
        "note": "Sarcasm -- tests emotion detection, still harmless underneath.",
    },
    {
        "text": "Kal wale incident ke baad log bahut gussa mein hain, sab jagah confusion phaila hua hai.",
        "expected_sentiment": "NEGATIVE",
        "expected_benign": True,
        "note": "The sample you already tested -- vague complaint, no real threat.",
    },
    {
        "text": "Hazaaron log shaanti se sadak par march kar rahe hain apne rights ke liye.",
        "expected_sentiment": None,  # not graded -- reasonable people could read this either way
        "expected_benign": False,  # SHOULD land in "Public Protest and Civil Unrest" as the category
        "note": "Peaceful protest -- good test of whether it can tell 'protest' apart from 'violent'. Watch violent_intent_probability here especially; it should stay LOW even though the category itself correctly flags as protest-related.",
    },
    {
        "text": "Sab log gate par jama ho jao, unhe sabak sikhana hai, kuch bhi jala dena padega.",
        "expected_sentiment": "NEGATIVE",
        "expected_benign": False,
        "note": "Generic incitement-style phrasing -- should trip high violent_intent/toxicity.",
    },
    {
        "text": "BREAKING: XYZ company band hone wali hai kal se, sabko pata hona chahiye, source verified nahi hai.",
        "expected_sentiment": None,
        "expected_benign": False,  # should land in Fake News / Misinformation
        "note": "Unverified claim phrased as breaking news -- tests the misinformation category.",
    },
    {
        "text": "Kisi ne mera account hack kar liya aur sab passwords leak kar diye online.",
        "expected_sentiment": "NEGATIVE",
        "expected_benign": False,  # should land in Cyber Security Attack
        "note": "Tests the Cyber Security Attack category specifically.",
    },
]


def run():
    sentiment_correct = 0
    sentiment_graded = 0
    benign_correct = 0

    for i, case in enumerate(TEST_CASES, 1):
        payload = {
            "post_id": f"eval_{i}",
            "timestamp": "2026-09-02T00:00:00Z",
            "platform": "Twitter",
            "text": case["text"],
            "author": {"user_id": f"eval_user_{i}", "handle": f"eval_{i}", "bio": "", "location": ""},
            "hashtags": [],
            "mentions": [],
        }
        print(f"[{i}/{len(TEST_CASES)}] sending... (each post runs ~5-6 model calls, this can take a while on CPU)")
        # 180s, not 30s -- a single post can mean ~20 forward passes through the
        # zero-shot model on CPU. If this still times out for you, that's real
        # signal your setup is CPU-bound and slow, not that something's broken.
        resp = requests.post(API_URL, json=payload, timeout=180)
        resp.raise_for_status()
        result = resp.json()["handoff_to_member4"]

        actual_sentiment = result["sentiment"]
        actual_benign = result["top_category_is_benign"]

        sentiment_ok = "-"
        if case["expected_sentiment"] is not None:
            sentiment_graded += 1
            sentiment_ok = "PASS" if actual_sentiment == case["expected_sentiment"] else "FAIL"
            if sentiment_ok == "PASS":
                sentiment_correct += 1

        benign_ok = "PASS" if actual_benign == case["expected_benign"] else "FAIL"
        if benign_ok == "PASS":
            benign_correct += 1

        print(f"[{i}] {case['note']}")
        print(f"    text: {case['text']}")
        print(f"    sentiment: expected={case['expected_sentiment']} actual={actual_sentiment} -> {sentiment_ok}")
        print(f"    benign?: expected={case['expected_benign']} actual={actual_benign} -> {benign_ok}")
        print(f"    threat_category={result['zero_shot_threat_category']}  severity={result['threat_severity_score']}")
        print()

    print("=" * 60)
    if sentiment_graded:
        print(f"Sentiment accuracy: {sentiment_correct}/{sentiment_graded} ({100*sentiment_correct/sentiment_graded:.0f}%)")
    print(f"Benign-vs-risk classification accuracy: {benign_correct}/{len(TEST_CASES)} ({100*benign_correct/len(TEST_CASES):.0f}%)")
    print("\nWhatever these numbers are, that's your real, current accuracy on this")
    print("set -- not a guess. If something FAILs, that's the specific case to look")
    print("at and decide: tweak the candidate labels, add a rule, or accept the")
    print("model's limit and note it as a known edge case for your presentation.")


if __name__ == "__main__":
    run()
