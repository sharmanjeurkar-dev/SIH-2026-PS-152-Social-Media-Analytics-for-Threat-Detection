# SIH 2026 PS:152 - Member 1: Ingestion Layer & Live X (Twitter) Scraper

**Team Role**: Member 1 — Data Ingestion & Stream Engineer  
**Organization**: National Technical Research Organisation (NTRO)  
**Problem Statement**: PS 152 — Social Media Analytics Platform  
**Workspace Location**: `/Users/sharmanjeurkar/.gemini/antigravity/scratch/sih_member1_x_scraper`

---

## 🎯 Member 1 Mission & Scope
As **Member 1**, this module functions as the high-throughput shock absorber at the mouth of the NTRO intelligence pipeline:
- **No Official API Needed**: Employs resilient web syndication, mirror feeds, and guest token endpoints to capture live social media streams from X.
- **In-Flight Stream Triage**: Micro-batches incoming posts, extracts fundamental entities (hashtags, mentions, URLs, Indian geo-markers, dates), detects languages (Devanagari, regional scripts, Latin-script Hinglish), and filters low-signal spam/bot noise.
- **Polyglot Storage & Queue Routing**: Automatically routes segregated JSON payloads to downstream team members:
  - **Member 2 (NLP & Text Intelligence)**: Clean text payloads, Hinglish markers, and language triage tags.
  - **Member 3 (Graph Data Science & Neo4j)**: Relational topology, author metadata, interaction edges (`RETWEET`, `REPLY`, `QUOTE`, `MENTION`), and object nodes.
  - **Member 5 (Backend Storage & Elasticsearch)**: Complete raw ingestion JSON records partitioned by date/hour.

---

## 🏗️ Architecture & Data Flow

```text
       [Live X / Twitter Streams] (Public Web Feeds / Syndication / RSS Mirrors)
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │   Member 1 Ingestion Core     │
                     │  - XScraper (Non-API Engine)  │
                     │  - InFlightTriager (NLP Prep) │
                     │  - StreamBuffer (Queue/Batch) │
                     └───────────────┬───────────────┘
                                     │
       ┌─────────────────────────────┼─────────────────────────────┐
       ▼                             ▼                             ▼
 [Member 2 NLP Queue]      [Member 3 Graph Queue]       [Member 5 & Cold Storage]
 data/member2_nlp_queue/   data/member3_graph_queue/    data/ingested/YYYY-MM-DD/
 - raw_text & Hinglish     - author & target IDs        - Full raw JSONL archive
 - hashtags & entities     - interaction edges          - Elasticsearch index feed
 - language/spam flags     - Sybil/bot heuristic meta
```

---

## 📦 Directory Structure

```
sih_member1_x_scraper/
├── models.py           # Unified JSON schemas for Member 1, 2, 3, and 5
├── triage.py           # In-flight language detection (Hinglish/Indic), regex entities, spam scoring
├── x_scraper.py        # Unofficial live X scraper engine with automatic multi-source failover
├── stream_buffer.py    # Thread-safe buffer queue, micro-batching, and partitioned file routing
├── main.py             # CLI runner (demo, live search, streaming daemon)
├── test_ingestion.py   # Complete unit and integration test suite
└── data/
    ├── ingested/             # Partitioned raw JSONL archives (Cold Storage)
    ├── member2_nlp_queue/    # Tailored packets for Member 2 (NLP worker)
    ├── member3_graph_queue/  # Tailored packets for Member 3 (Neo4j worker)
    └── member5_storage_buffer/ # Search index buffer for Member 5
```

---

## 🚀 Running the Pipeline

### 1. Run the Full Verification Demo
```bash
python3 main.py --mode demo
```

### 2. Live Scrape a Specific Hashtag or Keyword
```bash
python3 main.py --mode live --query "#FlashProtest" --count 10
```

### 3. Continuous Live Streaming Daemon
Streams posts in real-time, buffing them into memory and periodically flushing micro-batches to disk:
```bash
python3 main.py --mode stream --interval 2.0 --batches 10 --count 5
```

### 4. Run Automated Tests
```bash
python3 test_ingestion.py
```

---

## 📋 Data Handoff Schemas

### Member 2 (NLP & Text Intelligence) Payload
```json
{
  "post_id": "tweet_18924190824",
  "timestamp": "2026-09-01T12:38:37Z",
  "platform": "Twitter/X",
  "interaction_type": "REPLY",
  "raw_text": "@ground_reporter_v Stay safe bhai. Situation is escalating quickly in Bengaluru as well. #BengaluruBandh",
  "is_code_mixed": true,
  "tokens_and_entities": {
    "hashtags": ["#BengaluruBandh"],
    "mentioned_handles": ["ground_reporter_v"],
    "shared_urls": [],
    "initial_entity_markers": ["Bengaluru", "tomorrow"]
  },
  "triage": {
    "language": "Hinglish",
    "detected_script": "Latin",
    "is_spam": false,
    "is_high_signal": true,
    "signal_score": 0.8
  }
}
```

### Member 3 (Graph Data Science & Neo4j) Payload
```json
{
  "post_id": "tweet_18924190824",
  "timestamp": "2026-09-01T12:38:37Z",
  "platform": "Twitter/X",
  "author": {
    "user_id": "usr_144001",
    "handle": "kiran_tech9",
    "followers_count": 320,
    "following_count": 410,
    "verified": false,
    "profile_location": "Bengaluru, India"
  },
  "interactions": {
    "interaction_type": "REPLY",
    "target_user_id": "usr_901830",
    "target_handle": "ground_reporter_v",
    "target_post_id": null,
    "mentioned_handles": ["ground_reporter_v"]
  },
  "graph_nodes": {
    "hashtags": ["#BengaluruBandh"],
    "shared_urls": []
  },
  "is_high_signal": true
}
```
