"""
In-Flight Stream Triage and Pre-processing for Member 1
Implements:
1. Regex extraction for hashtags, user mentions, shared URLs.
2. Lightweight entity marker detection (geospatial / dates / key entities).
3. Language & script detection (Indic scripts, English, and Romanized Hinglish).
4. Spam and low-signal noise filtering heuristics.
"""

import re
from typing import Tuple, List, Dict, Any
from models import PostEntities, InFlightTriage


GEO_MARKERS = {
    "delhi", "new delhi", "red fort", "connaught place", "mumbai", "bengaluru",
    "bangalore", "kolkata", "hyderabad", "chennai", "punjab", "haryana",
    "uttar pradesh", "kashmir", "srinagar", "jammu", "gujarat", "ahmedabad",
    "maharashtra", "pune", "bihar", "patna", "bhopal", "rajasthan", "jaipur",
    "lucknow", "chandigarh", "noida", "gurugram", "gurgaon", "kerala", "assam",
    "manipur", "ladakh", "amritsar", "varanasi", "ayodhya"
}

HINGLISH_KEYWORDS = {
    "hai", "hain", "hoga", "hogi", "nahi", "karo", "karna", "raha", "rahi",
    "rahe", "bhai", "desh", "sarkar", "andolan", "dharna", "chalo", "bandh",
    "sab", "aaj", "kal", "log", "apne", "wale", "kuch", "aisa", "kaise",
    "shuru", "rok", "police", "prashasan", "danga", "morcha", "virodh"
}

SPAM_PATTERNS = [
    r"(?i)\b(crypto|airdrop|binance|giveaway|dm me for|passive income|guaranteed profit|telegram group link|whatsapp group link|follow to win)\b",
    r"(?i)\b(free btc|free eth|claim now|100x gem|pump and dump|casinobonus)\b",
    r"(?i)(whatsapp|telegram)\s*:\s*\+?[0-9\s\-]{8,}",
]

DATE_TIME_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|\b(?:today|tomorrow|yesterday|tonight|aaj|kal)\b)",
    re.IGNORECASE
)


class InFlightTriager:
    @staticmethod
    def extract_entities(text: str) -> PostEntities:
        raw_hashtags = re.findall(r"#([\w]+)", text, flags=re.UNICODE)
        hashtags = [f"#{h}" for h in raw_hashtags]
        urls = re.findall(r"https?://[^\s]+", text)

        entity_markers = []
        text_lower = text.lower()

        for geo in GEO_MARKERS:
            if " " in geo:
                if geo in text_lower:
                    entity_markers.append(geo.title())
            else:
                if re.search(r"\b" + re.escape(geo) + r"\b", text_lower):
                    entity_markers.append(geo.title())

        for date_match in DATE_TIME_PATTERN.findall(text):
            entity_markers.append(date_match.strip())

        return PostEntities(
            hashtags=hashtags,
            shared_urls=urls,
            initial_entity_markers=list(dict.fromkeys(entity_markers))
        )

    @staticmethod
    def detect_language_and_script(text: str) -> Tuple[str, str, bool]:
        total_chars = len(text)
        if total_chars == 0:
            return "unknown", "none", False

        devanagari_count = len(re.findall(r"[\u0900-\u097F]", text))
        bengali_count = len(re.findall(r"[\u0980-\u09FF]", text))
        tamil_count = len(re.findall(r"[\u0B80-\u0BFF]", text))
        telugu_count = len(re.findall(r"[\u0C00-\u0C7F]", text))
        gurmukhi_count = len(re.findall(r"[\u0A00-\u0A7F]", text))
        latin_count = len(re.findall(r"[a-zA-Z]", text))

        if devanagari_count > total_chars * 0.25:
            if latin_count > 10:
                return "Hindi", "Devanagari/Latin", True
            return "Hindi", "Devanagari", False
        elif bengali_count > total_chars * 0.25:
            return "Bengali", "Bengali", latin_count > 10
        elif tamil_count > total_chars * 0.25:
            return "Tamil", "Tamil", latin_count > 10
        elif telugu_count > total_chars * 0.25:
            return "Telugu", "Telugu", latin_count > 10
        elif gurmukhi_count > total_chars * 0.25:
            return "Punjabi", "Gurmukhi", latin_count > 10

        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
        if words:
            hinglish_hits = sum(1 for w in words if w in HINGLISH_KEYWORDS)
            hinglish_ratio = hinglish_hits / len(words)
            if hinglish_hits >= 2 or (len(words) >= 4 and hinglish_ratio >= 0.20):
                return "Hinglish", "Latin", True

        return "English", "Latin", False

    @staticmethod
    def evaluate_spam_and_signal(text: str, hashtags: List[str], author_followers: int = 0) -> Tuple[bool, float, List[str]]:
        notes = []
        is_spam = False
        signal = 0.5

        for pat in SPAM_PATTERNS:
            if re.search(pat, text):
                is_spam = True
                signal -= 0.4
                notes.append("Matches spam regex pattern")
                break

        if len(hashtags) > 8:
            is_spam = True
            signal -= 0.3
            notes.append("Excessive hashtag stuffing (>8 hashtags)")
        elif len(hashtags) in (1, 2, 3, 4):
            signal += 0.15

        clean_text = re.sub(r"https?://[^\s]+|#\w+|@\w+", "", text).strip()
        if len(clean_text) < 10 and not hashtags:
            signal -= 0.2
            notes.append("Short low-context message")

        critical_words = [
            "riot", "protest", "strike", "clash", "violence", "arrest", "attack",
            "emergency", "lockdown", "dharna", "morcha", "bandh", "tear gas",
            "curfew", "mobilize", "gather", "march", "fir", "warning"
        ]
        threat_hits = sum(1 for w in critical_words if re.search(r"\b" + w + r"\b", text, re.IGNORECASE))
        if threat_hits > 0:
            signal += min(0.35, 0.15 * threat_hits)
            notes.append(f"Contains {threat_hits} threat/escalation event terms")

        signal = max(0.0, min(1.0, signal))
        is_high_signal = signal >= 0.40 and not is_spam

        return is_spam, round(signal, 2), notes

    @classmethod
    def triage_post(cls, text: str, author_followers: int = 0) -> Tuple[PostEntities, InFlightTriage, bool]:
        entities = cls.extract_entities(text)
        language, script, is_code_mixed = cls.detect_language_and_script(text)
        is_spam, signal_score, notes = cls.evaluate_spam_and_signal(text, entities.hashtags, author_followers)

        triage = InFlightTriage(
            language=language,
            detected_script=script,
            is_spam=is_spam,
            signal_score=signal_score,
            is_high_signal=(not is_spam and signal_score >= 0.35),
            triage_notes=notes
        )

        return entities, triage, is_code_mixed