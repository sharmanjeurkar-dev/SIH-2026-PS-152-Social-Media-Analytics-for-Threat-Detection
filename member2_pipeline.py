import os
import re
import json
from datetime import datetime, timezone
from fastapi import FastAPI
import uvicorn
import torch
import requests
from transformers import pipeline

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads a local .env file if present; harmless if it isn't
except ImportError:
    pass  # dotenv is optional -- env vars set another way (terminal, OS) still work fine

# ==========================================
# CONFIGURATION — API Keys & Thresholds
# ==========================================
# Secrets now come from environment variables, NOT hardcoded strings.
# Put your real values in a local .env file (see .env.example) -- .env should
# be in your .gitignore so it never gets committed or shared in a chat/screenshot.

# ==========================================
# CONFIGURATION — API Keys & Thresholds
# ==========================================

# 1. Your Hugging Face Token
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")

# 2. External API Keys
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
YOUTUBE_API_KEY = ""     # Member 4 will add later
LLM_API_KEY = ""         # Member 4 will add later

# 3. Intelligence Thresholds
NEWS_FILTER_THRESHOLD = 0.50
NEWS_FILTER_MARGIN = 0.045
ESCALATION_REVIEW_THRESHOLD = 0.60



# 4. Multilingual Keyword Backstop (15 Scheduled Languages + Romanized Slang)
INCITEMENT_KEYWORDS = [
    # HINDI & HINGLISH
    r"\bjala\b", r"\bjalao\b", r"\bjalayenge\b", r"जला", r"जलाओ", r"जलाएंगे",
    r"\bmaar\b", r"\bmaaro\b", r"मारो", r"मार दो",
    r"\bhamla\b", r"\battack\b", r"हमला",
    r"\bdanga\b", r"\briot\b", r"दंगा",
    r"sabak\s+sikh", r"सबक\s+सिखा",
    # BENGALI & BANGLISH
    r"\bagun\b", r"\bporai\b", r"আগুন", r"পুড়িয়ে",
    r"\bmaro\b", r"মারো", r"মেরেই\s+ফেলো",
    r"\bhamla\b", r"হামলা",
    r"\bdangga\b", r"দাঙ্গা",
    # TAMIL & TANGLISH
    r"\bkoluthu\b", r"\bkoluthinga\b", r"கொளுத்து", r"தீவை",
    r"\badi\b", r"\badithu\b", r"அடி", r"வெட்டு",
    r"\bthaaku\b", r"தாக்கு",
    r"\bkalavarham\b", r"கலவரம்",
    # TELUGU & TELUGISH
    r"\bthagalabettu\b", r"తగలబెట్టు", r"కాల్చేయండి",
    r"\bkottu\b", r"\bchampandi\b", r"కొట్టు", r"చంపండి",
    r"\bdaadi\b", r"దాడి",
    r"\ballarlu\b", r"అల్లర్లు",
    # MARATHI
    r"\bjala\b", r"\bjalva\b", r"जाळा", r"पेटवा",
    r"\bmara\b", r"\bhanya\b", r"मारा", r"ठार\s+करा",
    r"\bhalla\b", r"हल्ला",
    r"\bdangal\b", r"दंगल",
    # GUJARATI & GUJLISH
    r"\bsalgavo\b", r"સળગાવો", r"બાળી\s+નાખો",
    r"\bmaro\b", r"મારો", r"જાનથી\s+મારો",
    r"\bhumlo\b", r"હુમલો",
    r"\btofan\b", r"તોફાન",
    # KANNADA & KANGLISH
    r"\bbenki\b", r"\bhachhi\b", r"ಬೆಂಕಿ", r"ಸಾಕಿ",
    r"\bhodi\b", r"\bkolli\b", r"ಹೊಡಿ", r"ಕೊಲ್ಲಲಿ",
    r"\bdaali\b", r"ದಾಳಿ",
    r"\bgalabhe\b", r"ಗಲಭೆ",
    # MALAYALAM & MANGLISH
    r"\bkathikku\b", r"കത്തിക്കുക", r"തീയിടുക",
    r"\bthallu\b", r"\bkolla\b", r"തല്ലുക", r"കൊല്ലുക",
    r"\baakramanam\b", r"ആക്രമണം",
    r"\blahala\b", r"ലഹള",
    # PUNJABI & PUNGLISH
    r"\bagg\s+lao\b", r"ਅੱਗ\s+ਲਾਓ", r"ਫੂਕ\s+ਦੋ",
    r"\bmaro\b", r"\bkutt\b", r"ਮਾਰੋ", r"ਕੁੱਟੋ",
    r"\bhamla\b", r"ਹਮਲਾ",
    r"\bdanga\b", r"ਦੰਗਾ",
    # ODIA
    r"\bnia\s+laga\b", r"ନିଆଁ\s+ଲଗାଓ", r"ପୋଡି\s+ଦିଅ",
    r"\bmara\b", r"ମାର", r"ହତ୍ୟା\s+କର",
    r"\bakramana\b", r"ଆକ୍ରମଣ",
    r"\bdanga\b", r"ଦଙ୍ଗା",
    # ASSAMESE
    r"\bzulai\s+diya\b", r"জ্বলাই\s+দিয়া", r"জুই\s+লগাই",
    r"\bmora\b", r"মৰা", r"মাৰি\s+পেলাওঁ",
    r"\bakramon\b", r"আক্ৰমণ",
    # URDU
    r"\bjalao\b", r"جلاؤ",
    r"\bmaro\b", r"مارو", r"قتل\s+کرو",
    r"\bhamla\b", r"حملہ",
    r"\bdanga\b", r"دنگا",
    # COMMON ROOTS (Kashmiri, Nepali, Sindhi, Maithili, Konkani)
    r"हल्ला", r"आक्रमण", r"दङ्गा", r"मारिदेऊ", r"आगो\s+लागाउ"
]

# ==========================================
# 1. INITIALIZE MULTILINGUAL NLP MODELS
# ==========================================
print("🚀 Loading High-Accuracy Pan-Indian NLP Engine...")

device = 0 if torch.cuda.is_available() else -1

if device == 0:
    print("⚡ RTX 4060 GPU Detected! Running in High-Speed Hardware Accelerated Mode.")
else:
    print("💻 Running in standard CPU Mode.")

# 1. Zero-Shot Classifier: Fast-path for Threat, Sentiment, and News
classifier = pipeline(
    "zero-shot-classification",
    model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    device=device
)

# 2. UPGRADE: AI4Bharat IndicNER (Trained natively on 11 Indian languages by IIT Madras)
ner_pipeline = pipeline(
    "token-classification",
    model="ai4bharat/IndicNER",
    aggregation_strategy="simple",
    device=device,
    token=HUGGINGFACE_TOKEN if HUGGINGFACE_TOKEN else None
)

print("✅ All AI models loaded successfully!\n")

app = FastAPI(title="Member 2 Multilingual NLP Intelligence API (Agentic + Cross-Check)")

# ==========================================
# 2. CORE COMPONENT FUNCTIONS
# ==========================================

def analyze_sentiment_and_emotions(text: str) -> dict:
    sentiment_labels = ["Positive", "Negative", "Neutral"]
    sent_result = classifier(text, candidate_labels=sentiment_labels)
    top_sentiment = sent_result['labels'][0].upper()
    confidence = round(sent_result['scores'][0], 3)

    if top_sentiment == "POSITIVE":
        compound = confidence
    elif top_sentiment == "NEGATIVE":
        compound = -confidence
    else:
        compound = 0.0

    candidate_emotions = ["Anxiety", "Anger", "Excitement", "Supportive", "Against", "Sarcasm"]
    emotion_result = classifier(text, candidate_labels=candidate_emotions)

    return {
        "sentiment": top_sentiment,
        "compound_score": compound,
        "primary_emotion": emotion_result['labels'][0],
        "emotion_confidence": round(emotion_result['scores'][0], 3)
    }


def extract_named_entities(text: str) -> dict:
    """Extracts Entities across 11 Indic scripts natively via AI4Bharat."""
    cleaned_text = re.sub(r'\b(kal|aaj|parso)\b', '', text, flags=re.IGNORECASE)
    ner_results = ner_pipeline(cleaned_text)
    locations, organizations, persons = [], [], []

    for entity in ner_results:
        clean_text = entity['word'].strip()
        label = entity['entity_group']

        if label == "LOC":
            locations.append(clean_text)
        elif label == "ORG":
            organizations.append(clean_text)
        elif label in ["PER", "PERSON"]:
            if not clean_text.startswith("#"):
                persons.append(clean_text)

    return {
        "locations": list(set(locations)),
        "organizations": list(set(organizations)),
        "persons": list(set(persons))
    }


def classify_threat_and_topic(text: str) -> dict:
    threat_categories = [
        "Public Protest and Civil Unrest",
        "Religious or Communal Violence",
        "Cyber Security Attack",
        "Fake News and Misinformation",
        "Normal Social Chatter",
        "General"
    ]
    benign_labels = {"Normal Social Chatter", "General"}

    result = classifier(text, candidate_labels=threat_categories)
    scores = dict(zip(result['labels'], result['scores']))
    benign_mass = sum(scores.get(label, 0.0) for label in benign_labels)
    severity_score = max(0.0, 1.0 - benign_mass)
    top_label = result['labels'][0]

    return {
        "threat_category": top_label,
        "threat_category_confidence": round(result['scores'][0], 3),
        "threat_severity_score": round(severity_score, 3),
        "top_category_is_benign": top_label in benign_labels,
    }


def calculate_news_approved_score(text: str) -> dict:
    candidate_labels = ["Verified News or High-Impact Event", "Personal Social Chatter or Noise"]
    result = classifier(text, candidate_labels=candidate_labels)
    news_index = result['labels'].index("Verified News or High-Impact Event")
    news_score = round(result['scores'][news_index], 3)

    return {
        "news_approved_score": news_score,
        "passes_news_filter": news_score > NEWS_FILTER_THRESHOLD
    }


def calculate_escalation_metrics(text: str) -> dict:
    metrics_labels = [
        "a statement inciting physical violence, riots, or harm",
        "highly toxic hate speech targeting a specific group",
        "extreme political or religious polarization and radicalization"
    ]

    result = classifier(text, candidate_labels=metrics_labels, multi_label=True)
    scores = dict(zip(result['labels'], result['scores']))

    violent_intent = round(scores["a statement inciting physical violence, riots, or harm"], 3)
    toxicity = round(scores["highly toxic hate speech targeting a specific group"], 3)
    radicalization = round(scores["extreme political or religious polarization and radicalization"], 3)

    return {
        "violent_intent_probability": violent_intent,
        "toxicity_severity_score": toxicity,
        "radicalization_index": radicalization,
        "requires_human_review": max(violent_intent, toxicity, radicalization) >= ESCALATION_REVIEW_THRESHOLD,
    }


def keyword_backstop_check(text: str) -> dict:
    hits = [kw for kw in INCITEMENT_KEYWORDS if re.search(kw, text, flags=re.IGNORECASE)]
    return {
        "keyword_backstop_triggered": bool(hits),
        "matched_keywords": hits,
    }


def infer_demographics(bio: str, location_str: str, text: str) -> dict:
    combined_info = f"{bio} {location_str}".lower()
    age_bracket = "Unknown"
    age_match = re.search(r'\b(1[8-9]|[2-5][0-9]|60)\b', combined_info)
    if age_match:
        age = int(age_match.group(0))
        if 18 <= age <= 24: age_bracket = "18-24"
        elif 25 <= age <= 34: age_bracket = "25-34"
        elif 35 <= age <= 50: age_bracket = "35-50"
        else: age_bracket = "50+"
    elif any(term in combined_info for term in ["student", "college", "uni", "undergrad"]):
        age_bracket = "18-24"

    interests = []
    interest_keywords = {
        "Politics": ["politics", "activist", "leader", "rights", "policy"],
        "Technology": ["tech", "developer", "coder", "ai", "crypto"],
        "Journalism": ["reporter", "journalist", "news", "editor", "media"],
        "Student": ["student", "campus", "scholar", "university"]
    }
    for category, keywords in interest_keywords.items():
        if any(kw in combined_info for kw in keywords):
            interests.append(category)

    if not interests:
        interests.append("General Public")

    return {
        "inferred_age_bracket": age_bracket,
        "inferred_location": location_str if location_str else "Unknown",
        "professional_interests": interests
    }

# ==========================================
# 3. AGENTIC LLM JUDGE & YOUTUBE/NEWS CROSS-CHECK
# ==========================================

def ask_llm_judge(text: str) -> dict:
    # MEMBER 4's DOMAIN: They will replace this mock with their actual LLM API call
    print(f"\n🤖 [AGENT TRIGGERED] Borderline threat detected. Sending to Heavy LLM Judge...")
    return {
        "llm_reviewed": True,
        "violent_intent_probability": 0.05,
        "toxicity_severity_score": 0.12,
        "radicalization_index": 0.02,
        "llm_rationale": "LLM Analysis: The text uses aggressive local slang, but contextually expresses frustration over a non-political event."
    }

def get_news_filter_decision(news_score: float) -> dict:
    upper_bound = NEWS_FILTER_THRESHOLD + NEWS_FILTER_MARGIN
    lower_bound = NEWS_FILTER_THRESHOLD - NEWS_FILTER_MARGIN

    if news_score >= upper_bound: return {"decision": "approved", "needs_yt_check": True}
    elif news_score <= lower_bound: return {"decision": "rejected", "needs_yt_check": False}
    else: return {"decision": "borderline", "needs_yt_check": True}

def pick_search_keyword(raw_json: dict, entity_data: dict) -> str:
    hashtags = raw_json.get("hashtags", [])
    if hashtags: return hashtags[0]
    fallback_entities = entity_data["organizations"] + entity_data["locations"]
    if fallback_entities: return fallback_entities[0]
    return None

def scrape_news_api(keyword: str, threat_severity_score: float, min_severity: float = 0.5, page_size: int = 5) -> list:
    if not keyword or threat_severity_score < min_severity or not NEWS_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": keyword,
                "sortBy": "publishedAt",
                "pageSize": page_size,
                "language": "en",
                "apiKey": NEWS_API_KEY,
            },
            timeout=5,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [{"title": a.get("title"), "description": a.get("description", ""), "url": a.get("url"), "source": a.get("source", {}).get("name")} for a in articles]
    except Exception as e:
        print(f"⚠️ News API scrape failed: {e}")
        return []

def scrape_youtube_data(keyword: str, max_results: int = 5) -> list:
    if not keyword or not YOUTUBE_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={"part": "snippet", "q": keyword, "type": "video", "order": "date", "maxResults": max_results, "key": YOUTUBE_API_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [{"title": i["snippet"]["title"], "description": i["snippet"]["description"], "video_id": i["id"]["videoId"]} for i in items]
    except Exception as e:
        print(f"⚠️ YouTube scrape failed: {e}")
        return []

def analyze_youtube_sentiment(yt_items: list) -> dict:
    if not yt_items:
        return {"yt_sentiment": None, "yt_compound_score": 0.0, "yt_primary_emotion": None, "yt_sample_size": 0}
    pooled_text = " ".join(f"{i['title']}. {i['description']}" for i in yt_items)[:2000]
    yt_result = analyze_sentiment_and_emotions(pooled_text)
    return {
        "yt_sentiment": yt_result["sentiment"],
        "yt_compound_score": yt_result["compound_score"],
        "yt_primary_emotion": yt_result["primary_emotion"],
        "yt_sample_size": len(yt_items),
    }

def calculate_updated_threat_score(x_threat_severity: float, x_violent_intent: float, yt_compound_score: float, yt_sample_size: int, x_weight: float = 0.7) -> dict:
    if yt_sample_size == 0:
        return {"updated_threat_score": round(x_threat_severity, 3), "method": "x_only_no_yt_data", "yt_threat_signal": 0.0}
    yt_threat_signal = (1 - yt_compound_score) / 2
    blended = (x_weight * x_threat_severity) + ((1 - x_weight) * yt_threat_signal)
    final_score = max(blended, x_violent_intent * 0.9)
    return {
        "updated_threat_score": round(final_score, 3),
        "method": "weighted_blend_x_yt",
        "yt_threat_signal": round(yt_threat_signal, 3),
    }

# ==========================================
# 4. MASTER PIPELINE PROCESSING & HANDOFFS
# ==========================================

def process_member1_payload(raw_json: dict) -> dict:
    post_text = raw_json.get("text", "")
    author_bio = raw_json.get("author", {}).get("bio", "")
    author_loc = raw_json.get("author", {}).get("location", "")

    news_rating = calculate_news_approved_score(post_text)
    sentiment_data = analyze_sentiment_and_emotions(post_text)
    entity_data = extract_named_entities(post_text)
    threat_data = classify_threat_and_topic(post_text)
    demographic_data = infer_demographics(author_bio, author_loc, post_text)
    escalation_metrics = calculate_escalation_metrics(post_text)
    backstop = keyword_backstop_check(post_text)

    if backstop["keyword_backstop_triggered"]:
        threat_data["threat_severity_score"] = max(threat_data["threat_severity_score"], 0.75)
        threat_data["top_category_is_benign"] = False
        escalation_metrics["requires_human_review"] = True

    max_severity = max(
        escalation_metrics["violent_intent_probability"],
        escalation_metrics["toxicity_severity_score"],
        escalation_metrics["radicalization_index"]
    )

    if (0.50 <= max_severity <= 0.85) or backstop["keyword_backstop_triggered"]:
        llm_verdict = ask_llm_judge(post_text)
        escalation_metrics["violent_intent_probability"] = llm_verdict["violent_intent_probability"]
        escalation_metrics["toxicity_severity_score"] = llm_verdict["toxicity_severity_score"]
        escalation_metrics["radicalization_index"] = llm_verdict["radicalization_index"]
        escalation_metrics["llm_reviewed"] = True
        escalation_metrics["llm_rationale"] = llm_verdict["llm_rationale"]

        new_max = max(llm_verdict["violent_intent_probability"], llm_verdict["toxicity_severity_score"], llm_verdict["radicalization_index"])
        escalation_metrics["requires_human_review"] = new_max >= ESCALATION_REVIEW_THRESHOLD
    else:
        escalation_metrics["llm_reviewed"] = False
        escalation_metrics["llm_rationale"] = "Not required. Fast model processed with high confidence."

    filter_decision = get_news_filter_decision(news_rating["news_approved_score"])

    news_articles = []
    yt_data = []
    yt_sentiment_summary = {"yt_sentiment": None, "yt_compound_score": 0.0, "yt_primary_emotion": None, "yt_sample_size": 0}
    updated_threat = {"updated_threat_score": threat_data["threat_severity_score"], "method": "x_only_no_yt_data"}

    if filter_decision["needs_yt_check"]:
        search_keyword = pick_search_keyword(raw_json, entity_data)
        news_articles = scrape_news_api(search_keyword, threat_data["threat_severity_score"])
        yt_data = scrape_youtube_data(search_keyword)
        yt_sentiment_summary = analyze_youtube_sentiment(yt_data)

        updated_threat = calculate_updated_threat_score(
            x_threat_severity=threat_data["threat_severity_score"],
            x_violent_intent=escalation_metrics["violent_intent_probability"],
            yt_compound_score=yt_sentiment_summary["yt_compound_score"],
            yt_sample_size=yt_sentiment_summary["yt_sample_size"],
        )

    handoff_to_member3 = {
        "post_id": raw_json.get("post_id"),
        "timestamp": raw_json.get("timestamp"),
        "platform": raw_json.get("platform"),
        "author_id": raw_json.get("author", {}).get("user_id"),
        "author_handle": raw_json.get("author", {}).get("handle"),
        "interaction_type": raw_json.get("interaction_type", "POST"),
        "target_user_id": raw_json.get("target_user_id"),
        "extracted_entities": entity_data,
        "hashtags": raw_json.get("hashtags", []),
        "mentions": raw_json.get("mentions", []),
        "zero_shot_category": threat_data["threat_category"],
        "news_approved_score": news_rating["news_approved_score"],
    }

    handoff_to_member4 = {
        "post_id": raw_json.get("post_id"),
        "timestamp": raw_json.get("timestamp"),
        "platform": raw_json.get("platform"),

        "news_approved_score": news_rating["news_approved_score"],
        "news_filter_decision": filter_decision["decision"],
        "zero_shot_threat_category": threat_data["threat_category"],
        "threat_category_confidence": threat_data["threat_category_confidence"],
        "threat_severity_score": threat_data["threat_severity_score"],
        "top_category_is_benign": threat_data["top_category_is_benign"],

        "sentiment": sentiment_data["sentiment"],
        "compound_sentiment_score": sentiment_data["compound_score"],
        "primary_emotion": sentiment_data["primary_emotion"],

        "violent_intent_probability": escalation_metrics["violent_intent_probability"],
        "toxicity_severity_score": escalation_metrics["toxicity_severity_score"],
        "radicalization_index": escalation_metrics["radicalization_index"],

        "requires_human_review": escalation_metrics["requires_human_review"],
        "llm_reviewed": escalation_metrics["llm_reviewed"],
        "llm_rationale": escalation_metrics["llm_rationale"],
        "keyword_backstop_triggered": backstop["keyword_backstop_triggered"],
        "matched_keywords": backstop["matched_keywords"],

        "target_locations": entity_data["locations"],
        "target_organizations": entity_data["organizations"],

        "youtube_cross_check": yt_sentiment_summary,
        "related_news_articles": news_articles,
        "updated_threat_score": updated_threat["updated_threat_score"],
        "updated_threat_score_method": updated_threat["method"],
    }

    return {
        "status": "processed",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "post_id": raw_json.get("post_id"),
        "raw_text": post_text,
        "author_demographics": demographic_data,
        "handoff_to_member3": handoff_to_member3,
        "handoff_to_member4": handoff_to_member4,
    }

# ==========================================
# 5. FASTAPI ENDPOINTS & SERVER LAUNCHER
# ==========================================

@app.post("/process_post")
def api_process_post(raw_json: dict):
    return process_member1_payload(raw_json)

@app.post("/process_batch")
def api_process_batch(raw_batch: list):
    return [process_member1_payload(post) for post in raw_batch]

if __name__ == "__main__":
    print("🌐 Starting Member 2 Live API Server on http://127.0.0.1:8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
