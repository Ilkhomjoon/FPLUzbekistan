"""Telegramga yuborishdagi himoya: takror post va xavfli qayta urinish."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from bot import config, deadline_stats, storage, telegram


class _Response:
    status_code = 200

    def json(self):
        return {"ok": True, "result": {"message_id": 1}}


class RetryTest(unittest.TestCase):
    """Javob kelmagan sendMessage qayta yuborilmasligi kerak.

    6-noyabrda aynan shu sabab deadline statistikasi kanalga ikki marta
    chiqdi: birinchi so'rov Telegramga yetib bordi, javobi esa kechikdi,
    va qayta urinish ikkinchi nusxani yaratdi.
    """

    def setUp(self):
        p = patch.object(config, "BOT_TOKEN", "test-token")
        p.start()
        self.addCleanup(p.stop)
        telegram._recent.clear()

    def test_a_lost_reply_is_not_retried(self):
        with patch.object(telegram, "session") as session:
            session.return_value.post.side_effect = requests.exceptions.ReadTimeout("kech")
            with self.assertRaises(telegram.TelegramUncertain):
                telegram._call("sendMessage", chat_id="@x", text="salom")
        self.assertEqual(session.return_value.post.call_count, 1)

    def test_a_failed_connection_is_retried(self):
        """Ulanib bo'lmagan bo'lsa so'rov serverga yetmagan — xavfsiz."""
        with patch.object(telegram, "session") as session, \
             patch.object(telegram.time, "sleep"):
            session.return_value.post.side_effect = [
                requests.exceptions.ConnectionError("tarmoq yo'q"), _Response()]
            result = telegram._call("sendMessage", chat_id="@x", text="salom")
        self.assertEqual(result, {"message_id": 1})
        self.assertEqual(session.return_value.post.call_count, 2)

    def test_reading_methods_still_retry(self):
        with patch.object(telegram, "session") as session, \
             patch.object(telegram.time, "sleep"):
            session.return_value.post.side_effect = [
                requests.exceptions.ReadTimeout("kech"), _Response()]
            telegram._call("editMessageText", chat_id="@x", text="salom")
        self.assertEqual(session.return_value.post.call_count, 2)


class RetryFlagTest(unittest.TestCase):
    """Tahrirlanadigan postlar qayta urinadi, bir martaliklari — yo'q."""

    def setUp(self):
        p = patch.object(config, "BOT_TOKEN", "test-token")
        p.start()
        self.addCleanup(p.stop)
        telegram._recent.clear()

    def test_retry_true_tries_once_more(self):
        with patch.object(telegram, "session") as session, \
             patch.object(telegram.time, "sleep"):
            session.return_value.post.side_effect = [
                requests.exceptions.ReadTimeout("kech"), _Response()]
            result = telegram._call("sendMessage", retry=True, chat_id="@x", text="a")
        self.assertEqual(result, {"message_id": 1})
        self.assertEqual(session.return_value.post.call_count, 2)

    def test_retry_true_gives_up_after_two(self):
        """Ikkitadan ko'p urinmaymiz — har urinish takror xavfini oshiradi."""
        with patch.object(telegram, "session") as session, \
             patch.object(telegram.time, "sleep"):
            session.return_value.post.side_effect = requests.exceptions.ReadTimeout("kech")
            with self.assertRaises(telegram.TelegramUncertain):
                telegram._call("sendMessage", retry=True, chat_id="@x", text="a")
        self.assertEqual(session.return_value.post.call_count, 2)

    def test_retry_false_still_stops_at_one(self):
        with patch.object(telegram, "session") as session, \
             patch.object(telegram.time, "sleep"):
            session.return_value.post.side_effect = requests.exceptions.ReadTimeout("kech")
            with self.assertRaises(telegram.TelegramUncertain):
                telegram._call("sendMessage", chat_id="@x", text="a")
        self.assertEqual(session.return_value.post.call_count, 1)

    def test_connection_errors_keep_their_own_budget(self):
        """Serverga yetmagan so'rov — qayta urinish xavfsiz, bayroqqa bog'liq emas."""
        with patch.object(telegram, "session") as session, \
             patch.object(telegram.time, "sleep"):
            session.return_value.post.side_effect = [
                requests.exceptions.ConnectionError("yo'q"),
                requests.exceptions.ConnectionError("yo'q"),
                _Response()]
            telegram._call("sendMessage", chat_id="@x", text="a")
        self.assertEqual(session.return_value.post.call_count, 3)

    def test_the_timeout_comes_from_the_setting(self):
        with patch.object(telegram, "session") as session, \
             patch.object(config, "TELEGRAM_TIMEOUT", 120):
            session.return_value.post.return_value = _Response()
            telegram._call("sendMessage", chat_id="@x", text="a")
        self.assertEqual(session.return_value.post.call_args.kwargs["timeout"], (10, 120))


class AnnotateTest(unittest.TestCase):
    """Telegram ishlamasa ham, nosozlik GitHub sahifasida ko'rinsin."""

    def test_nothing_is_printed_outside_actions(self):
        import io, contextlib
        buf = io.StringIO()
        with patch.dict("os.environ", {"GITHUB_ACTIONS": ""}, clear=False), \
             contextlib.redirect_stdout(buf):
            telegram.annotate("xatolik")
        self.assertEqual(buf.getvalue(), "")

    def test_an_error_annotation_in_actions(self):
        import io, contextlib
        buf = io.StringIO()
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False), \
             contextlib.redirect_stdout(buf):
            telegram.annotate("narx bashorati\nyiqildi")
        self.assertEqual(buf.getvalue().strip(), "::error::narx bashorati yiqildi")


class DedupeTest(unittest.TestCase):
    """Oxirgi himoya: bitta jarayon bir xil matnni ikki marta yubormaydi."""

    def setUp(self):
        telegram._recent.clear()
        for name, value in (("BOT_TOKEN", "test-token"), ("DRY_RUN", False)):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_a_failed_send_can_be_tried_again(self):
        """Yiqilgan urinish "yuborilgan" deb belgilanmasligi kerak."""
        with patch.object(telegram, "_call",
                          side_effect=[telegram.TelegramUncertain("yo'q"),
                                       {"message_id": 7}]) as call:
            with self.assertRaises(telegram.TelegramUncertain):
                telegram.send_message("matn", chat_id="@x")
            self.assertEqual(telegram.send_message("matn", chat_id="@x"),
                             {"message_id": 7})
        self.assertEqual(call.call_count, 2)

    def test_the_second_identical_message_is_dropped(self):
        with patch.object(telegram, "_call", return_value={"message_id": 7}) as call:
            first = telegram.send_message("bir xil matn", chat_id="@x")
            second = telegram.send_message("bir xil matn", chat_id="@x")
        self.assertEqual(first, {"message_id": 7})
        self.assertEqual(second, {})
        call.assert_called_once()

    def test_a_different_message_goes_through(self):
        with patch.object(telegram, "_call", return_value={"message_id": 7}) as call:
            telegram.send_message("birinchi", chat_id="@x")
            telegram.send_message("ikkinchi", chat_id="@x")
        self.assertEqual(call.call_count, 2)

    def test_other_chats_are_separate(self):
        with patch.object(telegram, "_call", return_value={"message_id": 7}) as call:
            telegram.send_message("matn", chat_id="@kanal")
            telegram.send_message("matn", chat_id="@admin")
        self.assertEqual(call.call_count, 2)


class UncertainStateTest(unittest.TestCase):
    """Javob kelmaganda ham holat yoziladi — keyingi cron takrorlamasin."""

    def test_the_round_is_marked_as_posted(self):
        import tempfile
        from datetime import datetime, timedelta, timezone
        from pathlib import Path

        now = datetime.now(timezone.utc)
        event = {"id": 11, "deadline_time":
                 (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")}

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deadline_stats.json"
            with patch.object(config, "STATS_STATE_FILE", path), \
                 patch.object(config, "STATS_LEAGUES", [(1, "Liga")]), \
                 patch.object(config, "DRY_RUN", False), \
                 patch.object(config, "BOT_TOKEN", "t"), \
                 patch.object(config, "CHANNEL_ID", "@x"), \
                 patch.object(deadline_stats.fpl_api, "get_bootstrap",
                              return_value={"events": [event], "elements": [], "teams": []}), \
                 patch.object(deadline_stats.fpl_api, "get_fixtures", return_value=[{}]), \
                 patch.object(deadline_stats.fpl_api, "players_by_id", return_value={}), \
                 patch.object(deadline_stats.fpl_api, "teams_by_id", return_value={}), \
                 patch.object(deadline_stats, "target_event", return_value=event), \
                 patch.object(deadline_stats, "first_kickoff",
                              return_value=now + timedelta(minutes=30)), \
                 patch.object(deadline_stats, "scan_league", return_value=object()), \
                 patch.object(deadline_stats, "deadline_stats_post", return_value="matn"), \
                 patch.object(deadline_stats.telegram, "send_message",
                              side_effect=telegram.TelegramUncertain("javob yo'q")), \
                 patch.object(deadline_stats.telegram, "notify_admin") as alert:
                code = deadline_stats.run(force=True)
            saved = storage.load(path, {})

        self.assertEqual(code, 1)              # workflow qizil bo'lsin
        self.assertTrue(saved.get("uncertain"))
        self.assertEqual(saved.get("event"), 11)
        alert.assert_called_once()             # admin tekshirib ko'rsin

    def test_a_normal_send_stores_the_message_id(self):
        import tempfile
        from datetime import datetime, timedelta, timezone
        from pathlib import Path

        now = datetime.now(timezone.utc)
        event = {"id": 11, "deadline_time":
                 (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")}

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deadline_stats.json"
            with patch.object(config, "STATS_STATE_FILE", path), \
                 patch.object(config, "STATS_LEAGUES", [(1, "Liga")]), \
                 patch.object(config, "DRY_RUN", False), \
                 patch.object(config, "BOT_TOKEN", "t"), \
                 patch.object(config, "CHANNEL_ID", "@x"), \
                 patch.object(deadline_stats.fpl_api, "get_bootstrap",
                              return_value={"events": [event], "elements": [], "teams": []}), \
                 patch.object(deadline_stats.fpl_api, "get_fixtures", return_value=[{}]), \
                 patch.object(deadline_stats.fpl_api, "players_by_id", return_value={}), \
                 patch.object(deadline_stats.fpl_api, "teams_by_id", return_value={}), \
                 patch.object(deadline_stats, "target_event", return_value=event), \
                 patch.object(deadline_stats, "first_kickoff",
                              return_value=now + timedelta(minutes=30)), \
                 patch.object(deadline_stats, "scan_league", return_value=object()), \
                 patch.object(deadline_stats, "deadline_stats_post", return_value="matn"), \
                 patch.object(deadline_stats.telegram, "send_message",
                              return_value={"message_id": 42}):
                code = deadline_stats.run(force=True)
            saved = storage.load(path, {})

        self.assertEqual(code, 0)
        self.assertEqual(saved.get("message_id"), 42)
        self.assertNotIn("uncertain", saved)


if __name__ == "__main__":
    unittest.main()
