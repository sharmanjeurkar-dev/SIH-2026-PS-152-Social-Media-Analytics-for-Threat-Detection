test_cases = [
    # =========================================================================
    # CLEAR SAFE CASES (2)
    # Baseline checks: Benign topics, high news approval, low threat metrics
    # =========================================================================
    {
        "case_id": "SAFE_01",
        "description": "Civic infrastructure inauguration announcement",
        "expected_label": "SAFE",
        "raw_text": "Mayor inaugurates the newly renovated green corridor and cycling track near Cubbon Park this morning. Great initiative for city commuters.",
        "handoff_to_member4": {
            "post_id": "safe_case_01",
            "platform": "X (Twitter)",
            "news_approved_score": 0.940,
            "passes_news_filter": True,
            "zero_shot_threat_category": "Civic Infrastructure",
            "threat_severity_score": 0.040,
            "sentiment": "POSITIVE",
            "compound_sentiment_score": 0.810,
            "primary_emotion": "Appreciation",
            "violent_intent_probability": 0.010,
            "toxicity_severity_score": 0.020,
            "radicalization_index": 0.015,
            "target_locations": ["Bengaluru"],
            "target_organizations": []
        }
    },
    {
        "case_id": "SAFE_02",
        "description": "Public weather warning without malicious intent",
        "expected_label": "SAFE",
        "raw_text": "Heavy rainfall alert issued across coastal districts for the next 48 hours. Fishermen advised not to venture into deep waters.",
        "handoff_to_member4": {
            "post_id": "safe_case_02",
            "platform": "X (Twitter)",
            "news_approved_score": 0.910,
            "passes_news_filter": True,
            "zero_shot_threat_category": "Weather Alert",
            "threat_severity_score": 0.080,
            "sentiment": "NEUTRAL",
            "compound_sentiment_score": -0.050,
            "primary_emotion": "Caution",
            "violent_intent_probability": 0.005,
            "toxicity_severity_score": 0.010,
            "radicalization_index": 0.010,
            "target_locations": ["Mangaluru", "Udupi"],
            "target_organizations": ["IMD"]
        }
    },

    # =========================================================================
    # CLEAR THREAT CASES (2)
    # Baseline checks: Explicit call to action, high toxicity, radicalization
    # =========================================================================
    {
        "case_id": "THREAT_01",
        "description": "Coordinated flash mob with intent to vandalize government buildings",
        "expected_label": "HIGH_THREAT",
        "raw_text": "Gather outside the municipal headquarters by 4 PM. Bring sticks and block all entry exits. Make sure no official leaves until demands are forced.",
        "handoff_to_member4": {
            "post_id": "threat_case_01",
            "platform": "Telegram",
            "news_approved_score": 0.050,
            "passes_news_filter": False,
            "zero_shot_threat_category": "Civil Unrest / Vandalism",
            "threat_severity_score": 0.920,
            "sentiment": "NEGATIVE",
            "compound_sentiment_score": -0.890,
            "primary_emotion": "Hostility",
            "violent_intent_probability": 0.885,
            "toxicity_severity_score": 0.860,
            "radicalization_index": 0.840,
            "target_locations": ["Ranchi"],
            "target_organizations": ["Municipal Corporation"]
        }
    },
    {
        "case_id": "THREAT_02",
        "description": "Targeted doxxing and sectarian incitement",
        "expected_label": "HIGH_THREAT",
        "raw_text": "Here are the house numbers and business shops of those who opposed the rally in Sector 4. Pay them a visit tonight, time to settle scores.",
        "handoff_to_member4": {
            "post_id": "threat_case_02",
            "platform": "WhatsApp Broadcast",
            "news_approved_score": 0.020,
            "passes_news_filter": False,
            "zero_shot_threat_category": "Communal Violence / Doxxing",
            "threat_severity_score": 0.960,
            "sentiment": "NEGATIVE",
            "compound_sentiment_score": -0.940,
            "primary_emotion": "Hatred",
            "violent_intent_probability": 0.930,
            "toxicity_severity_score": 0.910,
            "radicalization_index": 0.950,
            "target_locations": ["Sector 4", "Bokaro"],
            "target_organizations": []
        }
    },

    # =========================================================================
    # TRICKY / AMBIGUOUS CASES (6)
    # Stress tests: Sarcasm, metaphors, counter-speech, dogwhistles, false alarms
    # =========================================================================
    {
        "case_id": "TRICKY_01",
        "description": "Sports hyperbole (Metaphorical violence)",
        "expected_label": "SAFE / LOW_RISK",
        "raw_text": "Total massacre on the field tonight! Our bowlers went straight for blood and burned their batting order to ashes. Absolute slaughter.",
        "handoff_to_member4": {
            "post_id": "tricky_case_01",
            "platform": "X (Twitter)",
            "news_approved_score": 0.450,
            "passes_news_filter": True,
            "zero_shot_threat_category": "Physical Violence (Misclassified)",
            "threat_severity_score": 0.520,
            "sentiment": "NEGATIVE",
            "compound_sentiment_score": -0.720,
            "primary_emotion": "Excitement",
            "violent_intent_probability": 0.610,  # Elevated due to keywords 'blood', 'slaughter'
            "toxicity_severity_score": 0.380,
            "radicalization_index": 0.050,
            "target_locations": ["Wankhede Stadium"],
            "target_organizations": []
        }
    },
    {
        "case_id": "TRICKY_02",
        "description": "Sarcastic political satire (High negative sentiment, low real-world threat)",
        "expected_label": "LOW_RISK",
        "raw_text": "Road repairs were so high-tech that the asphalt washed away in 20 minutes. Truly a world-class European city, great job everyone.",
        "handoff_to_member4": {
            "post_id": "tricky_case_02",
            "platform": "X (Twitter)",
            "news_approved_score": 0.310,
            "passes_news_filter": False,
            "zero_shot_threat_category": "Political Agitation",
            "threat_severity_score": 0.340,
            "sentiment": "NEGATIVE",
            "compound_sentiment_score": -0.680,
            "primary_emotion": "Contempt",
            "violent_intent_probability": 0.080,
            "toxicity_severity_score": 0.220,
            "radicalization_index": 0.110,
            "target_locations": ["Patna"],
            "target_organizations": ["PWD"]
        }
    },
    {
        "case_id": "TRICKY_03",
        "description": "Coded mobilization / Dogwhistle (Polite surface tone, high escalation potential)",
        "expected_label": "MODERATE_OR_HIGH_THREAT",
        "raw_text": "Community elders remind everyone to carry their 'tools' to tomorrow's market gathering. We will clean up the neighborhood once and for all.",
        "handoff_to_member4": {
            "post_id": "tricky_case_03",
            "platform": "Telegram",
            "news_approved_score": 0.120,
            "passes_news_filter": False,
            "zero_shot_threat_category": "Community Outreach (Apparent)",
            "threat_severity_score": 0.410,  # Deceptively low due to veiled vocabulary
            "sentiment": "NEUTRAL",
            "compound_sentiment_score": 0.050,
            "primary_emotion": "Determination",
            "violent_intent_probability": 0.340,
            "toxicity_severity_score": 0.120,
            "radicalization_index": 0.620,
            "target_locations": ["Old Market Square", "Kanpur"],
            "target_organizations": []
        }
    },
    {
        "case_id": "TRICKY_04",
        "description": "Counter-speech quoting violent extremist threats to condemn them",
        "expected_label": "LOW_RISK",
        "raw_text": "Disgusted to see extremist accounts tweeting: 'Burn down their places of worship'. The police must arrest these hateful goons immediately!",
        "handoff_to_member4": {
            "post_id": "tricky_case_04",
            "platform": "X (Twitter)",
            "news_approved_score": 0.720,
            "passes_news_filter": True,
            "zero_shot_threat_category": "Hate Speech / Arson (Quoted)",
            "threat_severity_score": 0.680,  # Inflated by the quoted threat
            "sentiment": "NEGATIVE",
            "compound_sentiment_score": -0.840,
            "primary_emotion": "Outrage",
            "violent_intent_probability": 0.540,
            "toxicity_severity_score": 0.490,
            "radicalization_index": 0.080,
            "target_locations": ["Hyderabad"],
            "target_organizations": ["State Police"]
        }
    },
    {
        "case_id": "TRICKY_05",
        "description": "Peaceful democratic strike / Civil protest notice (Lawful dissent)",
        "expected_label": "MODERATE_RISK / MONITOR",
        "raw_text": "Bus transport unions declare an indefinite peaceful sit-in outside the secretariat starting Monday. No violence, just non-cooperation until wages increase.",
        "handoff_to_member4": {
            "post_id": "tricky_case_05",
            "platform": "Facebook",
            "news_approved_score": 0.810,
            "passes_news_filter": True,
            "zero_shot_threat_category": "Labor Strike / Disruption",
            "threat_severity_score": 0.440,
            "sentiment": "NEGATIVE",
            "compound_sentiment_score": -0.420,
            "primary_emotion": "Defiance",
            "violent_intent_probability": 0.120,
            "toxicity_severity_score": 0.080,
            "radicalization_index": 0.210,
            "target_locations": ["Chandigarh"],
            "target_organizations": ["Transport Workers Union", "State Secretariat"]
        }
    },
    {
        "case_id": "TRICKY_06",
        "description": "Viral health/safety rumor without direct instigation (Panic vector)",
        "expected_label": "MODERATE_RISK / MISINFORMATION",
        "raw_text": "Do not drink the municipal tap water in North Zone! Several people admitted to ICU, authorities are hiding a chemical leak cover-up!",
        "handoff_to_member4": {
            "post_id": "tricky_case_06",
            "platform": "WhatsApp Forward",
            "news_approved_score": 0.110,
            "passes_news_filter": False,
            "zero_shot_threat_category": "Public Panic / Misinformation",
            "threat_severity_score": 0.580,
            "sentiment": "NEGATIVE",
            "compound_sentiment_score": -0.660,
            "primary_emotion": "Panic",
            "violent_intent_probability": 0.090,
            "toxicity_severity_score": 0.210,
            "radicalization_index": 0.350,
            "target_locations": ["North Zone", "Ahmedabad"],
            "target_organizations": ["Municipal Water Board"]
        }
    }
]