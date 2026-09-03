"""
Unit and Integration Tests for Member 1 Ingestion Pipeline
"""

import unittest
import os
import shutil
import json
from models import IngestionEvent, AuthorProfile, PostInteractions, RawContent
from triage import InFlightTriager
from stream_buffer import StreamBuffer
from x_scraper import XScraper


class TestMember1Ingestion(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_data_output"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_triage_hinglish_and_entities(self):
        triager = InFlightTriager()
        text = "Protestors gathering at Red Fort near Connaught Place. Aaj police prashasan rok nahi payegi! #DelhiBandh #FlashProtest https://short.link/123"

        entities, triage, is_code_mixed = triager.triage_post(text, author_followers=500)

        # Entity checks
        self.assertIn("#DelhiBandh", entities.hashtags)
        self.assertIn("#FlashProtest", entities.hashtags)
        self.assertIn("https://short.link/123", entities.shared_urls)
        self.assertTrue(any("Red Fort" in m for m in entities.initial_entity_markers))

        # Language & code-mixed checks
        self.assertEqual(triage.language, "Hinglish")
        self.assertTrue(is_code_mixed)

        # Threat/Signal check
        self.assertTrue(triage.is_high_signal)
        self.assertFalse(triage.is_spam)
        self.assertGreaterEqual(triage.signal_score, 0.6)

    def test_triage_spam_detection(self):
        triager = InFlightTriager()
        spam_text = "Join our VIP Telegram group link now for guaranteed profit and free btc airdrop! #crypto #airdrop #giveaway #bonus #rich #coin #token #pump"

        entities, triage, _ = triager.triage_post(spam_text, author_followers=10)

        self.assertTrue(triage.is_spam)
        self.assertFalse(triage.is_high_signal)
        self.assertLess(triage.signal_score, 0.4)

    def test_member_handoff_schemas(self):
        triager = InFlightTriager()
        text = "Emergency alert: Clashes reported at New Delhi. RT @target_acc #BreakingNews"
        entities, triage, is_code_mixed = triager.triage_post(text)

        event = IngestionEvent(
            post_id="tweet_18920194812",
            timestamp="2026-08-28T00:15:30Z",
            platform="Twitter/X",
            raw_content=RawContent(text=text, is_code_mixed=is_code_mixed),
            author=AuthorProfile(
                user_id="usr_991823",
                handle="agent_alpha",
                followers_count=14,
                following_count=850
            ),
            interactions=PostInteractions(
                interaction_type="RETWEET",
                target_handle="target_acc"
            ),
            entities=entities,
            triage=triage
        )

        # Member 2 NLP packet validation
        m2_packet = event.to_member2_nlp_packet()
        self.assertIn("raw_text", m2_packet)
        self.assertIn("is_code_mixed", m2_packet)
        self.assertIn("tokens_and_entities", m2_packet)
        self.assertIn("triage", m2_packet)
        self.assertEqual(m2_packet["tokens_and_entities"]["hashtags"], ["#BreakingNews"])

        # Member 3 Graph packet validation
        m3_packet = event.to_member3_graph_packet()
        self.assertIn("author", m3_packet)
        self.assertIn("interactions", m3_packet)
        self.assertIn("graph_nodes", m3_packet)
        self.assertEqual(m3_packet["author"]["user_id"], "usr_991823")
        self.assertEqual(m3_packet["interactions"]["target_handle"], "target_acc")

    def test_stream_buffer_storage_routing(self):
        buffer = StreamBuffer(base_data_dir=self.test_dir)
        scraper = XScraper()

        events = scraper.generate_live_stream_events(count=4)
        self.assertEqual(len(events), 4)

        buffer.push_many(events)
        flushed_count = buffer.flush_now()
        self.assertEqual(flushed_count, 4)

        # Verify files were created
        m2_files = os.listdir(os.path.join(self.test_dir, "member2_nlp_queue"))
        m3_files = os.listdir(os.path.join(self.test_dir, "member3_graph_queue"))
        m5_files = os.listdir(os.path.join(self.test_dir, "member5_storage_buffer"))

        self.assertTrue(len(m2_files) > 0)
        self.assertTrue(len(m3_files) > 0)
        self.assertTrue(len(m5_files) > 0)

        # Verify JSONL lines can be loaded
        with open(os.path.join(self.test_dir, "member2_nlp_queue", m2_files[0]), "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(lines), 4)


if __name__ == "__main__":
    unittest.main()
