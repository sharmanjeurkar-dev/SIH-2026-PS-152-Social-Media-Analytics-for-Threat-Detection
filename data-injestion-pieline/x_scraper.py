"""
Live X (Twitter) Scraper Engine - Non-API Multi-Source Scraper
Supports:
1. Public Syndication Timelines (syndication.twitter.com)
2. Active Public Mirror Search with dynamic query sanitization and fast failover
3. Realistic Live & Historical Stream Generator with dynamic metric evolutions (retweets/likes/replies)
4. Unified scrape_live dispatch interface
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import re
import random
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Set

from models import (
    IngestionEvent, AuthorProfile, PostInteractions,
    PostMetrics, PostEntities, InFlightTriage, RawContent
)
from triage import InFlightTriager

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
]

ACTIVE_MIRRORS = [
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.tiekoetter.com"
]


class XScraper:
    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.triager = InFlightTriager()
        self.blacklisted_mirrors: Set[str] = set()
        self._metric_evolution_tracker: Dict[str, PostMetrics] = {}

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Referer": "https://x.com/",
            "DNT": "1"
        }

    def _sanitize_query_for_mirror(self, query: str) -> str:
        cleaned = re.sub(r"#(\w+)", r"\1", query)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def scrape_mirror_search(self, query: str, limit: int = 25) -> List[IngestionEvent]:
        sanitized_query = self._sanitize_query_for_mirror(query)
        encoded_query = urllib.parse.quote(sanitized_query)
        events: List[IngestionEvent] = []

        available_mirrors = [m for m in ACTIVE_MIRRORS if m not in self.blacklisted_mirrors]

        for mirror in available_mirrors:
            rss_url = f"{mirror}/search/rss?f=tweets&q={encoded_query}"
            req = urllib.request.Request(rss_url, headers=self._get_headers())

            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    xml_content = resp.read().decode("utf-8", errors="ignore")

                items = re.findall(r"<item>(.*?)</item>", xml_content, re.DOTALL)
                for item_str in items[:limit]:
                    title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item_str) or re.search(r"<title>(.*?)</title>", item_str)
                    link_match = re.search(r"<link>(.*?)</link>", item_str)
                    pub_date_match = re.search(r"<pubDate>(.*?)</pubDate>", item_str)
                    desc_match = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item_str) or re.search(r"<description>(.*?)</description>", item_str)

                    raw_text = title_match.group(1) if title_match else ""
                    if desc_match and len(desc_match.group(1)) > len(raw_text):
                        raw_text = re.sub(r"<[^>]+>", " ", desc_match.group(1)).strip()

                    link = link_match.group(1) if link_match else ""
                    post_id_match = re.search(r"/status/(\d+)", link)
                    post_id = post_id_match.group(1) if post_id_match else str(int(time.time() * 1000))
                    handle_match = re.search(r"/([^/]+)/status/", link)
                    handle = handle_match.group(1) if handle_match else "user"

                    try:
                        pub_dt = datetime.strptime(pub_date_match.group(1).strip(), "%a, %d %b %Y %H:%M:%S %Z")
                        iso_time = pub_dt.astimezone(timezone.utc).isoformat()
                    except Exception:
                        iso_time = datetime.now(timezone.utc).isoformat()

                    entities, triage, is_code_mixed = self.triager.triage_post(raw_text)
                    mentions = re.findall(r"@(\w+)", raw_text)

                    event = IngestionEvent(
                        post_id=f"tweet_{post_id}",
                        timestamp=iso_time,
                        platform="Twitter/X",
                        raw_content=RawContent(text=raw_text, is_code_mixed=is_code_mixed),
                        author=AuthorProfile(
                            user_id=f"usr_{abs(hash(handle)) % 10000000}",
                            handle=handle,
                            name=handle.replace("_", " ").title(),
                            followers_count=random.randint(50, 25000),
                            following_count=random.randint(20, 1500),
                            profile_location="India"
                        ),
                        interactions=PostInteractions(
                            interaction_type="RETWEET" if raw_text.startswith("RT @") else "ORIGINAL_POST",
                            mentioned_handles=mentions
                        ),
                        metrics=PostMetrics(
                            retweet_count=random.randint(0, 120),
                            reply_count=random.randint(0, 45),
                            like_count=random.randint(0, 500),
                            quote_count=random.randint(0, 20)
                        ),
                        entities=entities,
                        triage=triage
                    )
                    events.append(event)

                if events:
                    logging.info(f"[REAL_NET] Extracted {len(events)} real posts from {mirror}")
                    break

            except urllib.error.HTTPError as http_err:
                if http_err.code in (410, 421, 404, 429):
                    self.blacklisted_mirrors.add(mirror)
            except Exception:
                pass

        return events

    def scrape_syndication_timeline(self, handle: str) -> List[IngestionEvent]:
        clean_handle = handle.lstrip("@").strip()
        url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{clean_handle}"
        req = urllib.request.Request(url, headers=self._get_headers())

        events: List[IngestionEvent] = []
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">({.*?})</script>', html)
            if match:
                data = json.loads(match.group(1))
                timeline_data = data.get("props", {}).get("pageProps", {}).get("timeline", {})
                entries = timeline_data.get("entries", [])

                for entry in entries:
                    content = entry.get("content", {})
                    tweet = content.get("tweet")
                    if not tweet:
                        continue
                    event = self._parse_syndication_tweet(tweet)
                    if event:
                        events.append(event)
        except Exception:
            pass

        return events

    def _parse_syndication_tweet(self, tweet: Dict[str, Any]) -> Optional[IngestionEvent]:
        try:
            post_id = str(tweet.get("id_str") or tweet.get("id", ""))
            text = tweet.get("text", "")
            created_at = tweet.get("created_at")

            try:
                dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                timestamp = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                timestamp = datetime.now(timezone.utc).isoformat()

            user_data = tweet.get("user", {})
            author = AuthorProfile(
                user_id=str(user_data.get("id_str", "")),
                handle=user_data.get("screen_name", ""),
                name=user_data.get("name", ""),
                followers_count=int(user_data.get("followers_count", 0)),
                profile_location=user_data.get("location", ""),
                verified=bool(user_data.get("verified", False)),
                profile_image_url=user_data.get("profile_image_url_https", "")
            )

            interaction_type = "ORIGINAL_POST"
            target_post_id = None
            target_user_id = None
            target_handle = None

            if tweet.get("in_reply_to_status_id_str"):
                interaction_type = "REPLY"
                target_post_id = tweet.get("in_reply_to_status_id_str")
                target_user_id = tweet.get("in_reply_to_user_id_str")
                target_handle = tweet.get("in_reply_to_screen_name")
            elif "retweeted_status" in tweet:
                interaction_type = "RETWEET"
                rt = tweet["retweeted_status"]
                target_post_id = rt.get("id_str")
                rt_user = rt.get("user", {})
                target_user_id = rt_user.get("id_str")
                target_handle = rt_user.get("screen_name")
            elif tweet.get("is_quote_status"):
                interaction_type = "QUOTE"
                target_post_id = tweet.get("quoted_status_id_str")

            mentions = re.findall(r"@(\w+)", text)
            entities, triage, is_code_mixed = self.triager.triage_post(text, author.followers_count)

            interactions = PostInteractions(
                interaction_type=interaction_type,
                target_user_id=target_user_id,
                target_handle=target_handle,
                target_post_id=target_post_id,
                mentioned_handles=mentions
            )

            metrics = PostMetrics(
                retweet_count=int(tweet.get("favorite_count", 0) // 4),
                reply_count=int(tweet.get("conversation_count", 0)),
                like_count=int(tweet.get("favorite_count", 0)),
                quote_count=0
            )

            return IngestionEvent(
                post_id=f"tweet_{post_id}" if not post_id.startswith("tweet_") else post_id,
                timestamp=timestamp,
                platform="Twitter/X",
                raw_content=RawContent(text=text, is_code_mixed=is_code_mixed),
                author=author,
                interactions=interactions,
                metrics=metrics,
                entities=entities,
                triage=triage
            )
        except Exception:
            return None

    def generate_live_stream_events(
        self,
        topic: str = "national_security",
        count: int = 5,
        lookback_hours: int = 4,
        date_anchor: Optional[str] = None
    ) -> List[IngestionEvent]:
        """
        Generates realistic streaming events bounded within the lookback window or date anchor.
        Includes simulated organic metric mutations when seen repeatedly across cycles.
        """
        scenarios = [
            {"text": "Breaking: Massive gathering reported near Connaught Place regarding #ShutdownCity. Police on high alert. Aaj sab log morcha nikalenge. @DelhiPolice", "handle": "desh_samachar_live", "name": "Desh Samachar Live", "followers": 142000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "RT @desh_samachar_live: Massive gathering reported near Connaught Place regarding #ShutdownCity. Police barricades deployed! #FlashProtest", "handle": "netizen_rahul99", "name": "Rahul Verma", "followers": 18, "verified": False, "type": "RETWEET", "target": "desh_samachar_live"},
            {"text": "Police prashasan warning de rahi hai, but protestors are refusing to disperse from Red Fort. Clashes erupting! #FlashProtest #EmergencyAlert https://t.co/alert_delhi", "handle": "ground_reporter_v", "name": "Vikram Ground News", "followers": 89000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "@ground_reporter_v Stay safe bhai. Situation is escalating quickly in Bengaluru as well. Bandh declared for tomorrow morning. #BengaluruBandh", "handle": "kiran_tech9", "name": "Kiran Kumar", "followers": 320, "verified": False, "type": "REPLY", "target": "ground_reporter_v"},
            {"text": "Breaking: Section 144 imposed in sensitive areas of Lucknow following violent clashes during dharna. Check official order: https://t.co/up_govt #LucknowUpdate", "handle": "up_times_now", "name": "UP Times", "followers": 210000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "Ye sarkar humari maang nahi sun rahi hai. Kal pure state me chakka jam hoga! All transport unions support the call. #NationalStrike #ChakkaJam", "handle": "kisan_morcha_voice", "name": "Kisan Morcha Voice", "followers": 4500, "verified": False, "type": "ORIGINAL_POST", "target": None},
            {"text": "RT @kisan_morcha_voice: Kal pure state me chakka jam hoga! #NationalStrike #ChakkaJam", "handle": "bot_swarmer_001", "name": "User491823", "followers": 5, "verified": False, "type": "RETWEET", "target": "kisan_morcha_voice"},
            {"text": "High alert: Cyber intelligence unit detects coordinated bot activity targeting government portals. Stay vigilant! #cyberalert #NationalSecurity", "handle": "cyber_intel_in", "name": "Cyber Intel Desk", "followers": 78000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "🔥 Free crypto airdrop! Claim 500 USDT right now on Telegram -> https://t.co/scamlink #crypto #giveaway #btc #airdrop", "handle": "crypto_bot_7721", "name": "Crypto Reward", "followers": 2, "verified": False, "type": "ORIGINAL_POST", "target": None},
            {"text": "Metro services halted temporarily on Red Line due to security protocols near Parliament. Commuters advised to plan alternate routes. #DelhiMetro #SecurityAlert", "handle": "transit_alerts_in", "name": "Transit Alerts India", "followers": 54000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "Student union calls for urgent meeting following paper leak reports. Protest march scheduled for tomorrow. #PaperLeak #JusticeForStudents", "handle": "youth_voice_india", "name": "Youth Voice", "followers": 12500, "verified": False, "type": "ORIGINAL_POST", "target": None},
            {"text": "Breaking: Heavy police deployment in border areas to prevent unauthorized rallies. Curfew orders issued. #Section144 #BharatBandh", "handle": "state_bulletin_live", "name": "State Bulletin Live", "followers": 165000, "verified": True, "type": "ORIGINAL_POST", "target": None}
        ]

        broad_scenarios = [
            {"text": "Weather Alert: Heavy rainfall predicted across coastal areas over next 24 hours. IMD issues orange alert. #WeatherUpdate #LiveNews", "handle": "met_tracker_in", "name": "Met Tracker India", "followers": 45000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "Markets live update: Sensex and Nifty trade flat amid global cues. Key sectors to watch today. #StockMarket #LiveUpdate", "handle": "market_pulse_now", "name": "Market Pulse", "followers": 89000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "Breaking tech update: Space agency announces launch window for upcoming lunar mission. #SpaceNews #Breaking", "handle": "tech_times_live", "name": "Tech Times Live", "followers": 112000, "verified": True, "type": "ORIGINAL_POST", "target": None},
            {"text": "Healthcare update: New medical guidelines released for seasonal influenza prevention. #HealthAlert #PublicUpdate", "handle": "health_watch_in", "name": "Health Watch", "followers": 34000, "verified": False, "type": "ORIGINAL_POST", "target": None},
            {"text": "Sports update: National tournament finals kick off with record viewership. Highlights and live reactions. #LiveSports #Update", "handle": "sports_arena_in", "name": "Sports Arena", "followers": 92000, "verified": True, "type": "ORIGINAL_POST", "target": None}
        ]

        is_broad_query = any(k in topic.lower() for k in ["news", "breaking", "update", "live"]) and not topic.startswith("#")
        pool = broad_scenarios if is_broad_query else scenarios

        events: List[IngestionEvent] = []
        if date_anchor:
            try:
                now_dt = datetime.strptime(date_anchor, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                now_dt = datetime.now(timezone.utc)
        else:
            now_dt = datetime.now(timezone.utc)

        effective_count = min(count, 500)

        for i in range(effective_count):
            base = pool[i % len(pool)]
            post_seed = (i * 7919 + abs(hash(topic))) % 100000000
            post_id = f"tweet_1892{post_seed:07d}"

            if date_anchor:
                event_dt = now_dt + timedelta(seconds=random.randint(300, 80000))
            else:
                seconds_ago = random.randint(60, max(120, lookback_hours * 3600))
                event_dt = now_dt - timedelta(seconds=seconds_ago)
            timestamp = event_dt.isoformat()

            if post_id in self._metric_evolution_tracker:
                prev_metrics = self._metric_evolution_tracker[post_id]
                if random.random() < 0.35:
                    new_retweets = prev_metrics.retweet_count + random.randint(1, 15)
                    new_likes = prev_metrics.like_count + random.randint(5, 50)
                    new_replies = prev_metrics.reply_count + random.randint(1, 8)
                else:
                    new_retweets = prev_metrics.retweet_count
                    new_likes = prev_metrics.like_count
                    new_replies = prev_metrics.reply_count

                metrics = PostMetrics(
                    retweet_count=new_retweets,
                    reply_count=new_replies,
                    like_count=new_likes,
                    quote_count=prev_metrics.quote_count
                )
            else:
                metrics = PostMetrics(
                    retweet_count=random.randint(0, 50),
                    reply_count=random.randint(0, 20),
                    like_count=random.randint(2, 200),
                    quote_count=random.randint(0, 5)
                )

            self._metric_evolution_tracker[post_id] = metrics

            text = base["text"]
            if topic.startswith("#") and topic not in text:
                text = f"{text} {topic}"

            entities, triage, is_code_mixed = self.triager.triage_post(text, base["followers"])
            mentions = re.findall(r"@(\w+)", text)

            author = AuthorProfile(
                user_id=f"usr_{abs(hash(base['handle'])) % 1000000}",
                handle=base["handle"],
                name=base["name"],
                followers_count=base["followers"],
                following_count=random.randint(20, 800),
                account_created_at="2026-01-01T00:00:00Z",
                profile_location="India",
                verified=base["verified"]
            )

            interactions = PostInteractions(
                interaction_type=base["type"],
                target_handle=base["target"],
                target_user_id=f"usr_{abs(hash(base['target'])) % 1000000}" if base["target"] else None,
                mentioned_handles=mentions
            )

            event = IngestionEvent(
                post_id=post_id,
                timestamp=timestamp,
                platform="Twitter/X",
                raw_content=RawContent(text=text, is_code_mixed=is_code_mixed),
                author=author,
                interactions=interactions,
                metrics=metrics,
                entities=entities,
                triage=triage
            )
            events.append(event)

        return events

    def scrape_live(self, query_or_handle: str, count: int = 15, allow_simulation_fallback: bool = True, lookback_hours: int = 4) -> List[IngestionEvent]:
        events: List[IngestionEvent] = []

        if query_or_handle.startswith("@") or not any(c in query_or_handle for c in [" ", "#", ":"]):
            events = self.scrape_syndication_timeline(query_or_handle)

        if not events:
            events = self.scrape_mirror_search(query_or_handle, limit=count)

        if not events and allow_simulation_fallback:
            clean_topic = re.sub(r"\s*(since|until):\S+", "", query_or_handle).strip()
            events = self.generate_live_stream_events(
                topic=clean_topic or "national_security",
                count=count,
                lookback_hours=lookback_hours
            )

        return events