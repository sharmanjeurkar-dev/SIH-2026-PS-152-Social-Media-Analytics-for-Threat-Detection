"""
Verification Test Suite for Trend Analytics Engine
SIH 2026 PS:152 - National Technical Research Organisation (NTRO)
"""

import unittest

from trend_topic_engine import TrendAndTopicEngine
from trending_hashtag_manager import (
    TrendingHashtagManager,
    get_trending_hashtag_manager,
)


class TestTrendAnalyticsEngine(unittest.TestCase):
    def setUp(self):
        self.engine = TrendAndTopicEngine(baseline_window_count=3)
        self.manager = get_trending_hashtag_manager()

    def test_manager_seeding_and_queries(self):
        self.assertEqual(len(self.manager.trending_pool), 200)
        self.assertEqual(len(self.manager.get_all_hashtags()), 200)
        self.assertEqual(len(self.manager.get_tier1_hashtags()), 25)

        batches = self.manager.get_search_query_batches(cycle_index=0, batch_size=5)
        self.assertGreater(len(batches), 0)
        self.assertTrue(batches[0].startswith("(") and " OR " in batches[0])

    def test_window_trend_analysis(self):
        # Window 1 events
        events_w1 = [
            {"hashtags": ["#farmersprotest", "#delhipolice"], "toxicity_score": 0.1},
            {"hashtags": ["#farmersprotest", "#chakkajam"], "toxicity_score": 0.2},
            {"hashtags": ["#nationalsecurity", "#cyberalert"], "toxicity_score": 0.05},
        ]
        res1 = self.engine.analyze_window(events_w1, dt_hours=1.0, top_n=200)
        self.assertIn("top_200_trends", res1)
        self.assertIn("topic_clusters", res1)

        # Window 2 events with a surge on #emergencyalert
        events_w2 = [
            {"hashtags": ["#emergencyalert", "#delhipolice"], "toxicity_score": 0.75},
            {"hashtags": ["#emergencyalert", "#riotnow"], "toxicity_score": 0.85},
            {"hashtags": ["#emergencyalert", "#chakkajam"], "toxicity_score": 0.70},
            {
                "hashtags": ["#emergencyalert", "#farmersprotest"],
                "toxicity_score": 0.60,
            },
        ]
        res2 = self.engine.analyze_window(events_w2, dt_hours=1.0, top_n=200)

        # Verify #emergencyalert is detected as surging
        rising_tags = [r["tag"] for r in res2["rising_trends"]]
        self.assertIn("emergencyalert", rising_tags)

        # Verify manager reflects top 200
        self.assertEqual(len(self.manager.trending_pool), 200)

    def test_generate_trend_payload(self):
        events = [
            {"hashtags": ["#emergencyalert", "#delhipolice"], "toxicity_score": 0.8},
            {"hashtags": ["#emergencyalert", "#chakkajam"], "toxicity_score": 0.6},
        ]
        analysis = self.engine.analyze_window(events, dt_hours=1.0, top_n=200)
        payload = self.engine.generate_trend_payload(
            analysis, lookback_hours=4.0, events_count=len(events)
        )

        self.assertIn("timestamp", payload)
        self.assertIn("window_summary", payload)
        self.assertIn("top_200_trending_radar", payload)
        self.assertIn("rising_trends", payload)
        self.assertIn("viral_keywords", payload)
        self.assertIn("topic_clusters", payload)
        self.assertIn("shifting_discussions", payload)
        self.assertIn("scraper_directives", payload)
        self.assertEqual(payload["window_summary"]["events_processed"], 2)


if __name__ == "__main__":
    unittest.main()
