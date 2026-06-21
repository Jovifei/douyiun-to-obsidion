"""M4 E2E tests — cookie rotation, backoff retry, sleep-wake zombie reclaim.

Scenario 1: cookie expired → probe_and_rotate → backup available → auto-rotate → download success
Scenario 2: download failure → exponential backoff retry (verify sleep time sequence)
Scenario 3: clock jump > 60s → sleep-wake detect → zombie reclaim triggered
"""
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# Scenario 1 — cookie expired → probe_and_rotate → auto-rotate
# ---------------------------------------------------------------------------

class TestScenario1CookieRotation:
    """probe_and_rotate detects expired cookie, finds backup, auto-rotates."""

    def test_probe_and_rotate_replaces_from_backup(self, tmp_path):
        """Current cookie fails probe, backup succeeds → backup replaces main."""
        from src.utils.cookie_probe import probe_and_rotate

        # Create main cookies file (expired)
        main_cookies = tmp_path / "cookies.txt"
        main_cookies.write_text("expired_token\txxx\n")

        # Create backup dir with one backup
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        backup_file = backup_dir / "cookies_backup_20260620.txt"
        backup_file.write_text("fresh_token\tyyy\n")

        # Mock probe_cookie: fail for main, succeed for backup
        call_count = 0
        def mock_probe(path, test_url="https://v.douyin.com/test/"):
            nonlocal call_count
            call_count += 1
            # First call: main cookies → expired
            if call_count == 1:
                return False
            # Second call: backup cookies → valid
            return True

        with patch("src.utils.cookie_probe.probe_cookie", side_effect=mock_probe):
            result = probe_and_rotate(str(main_cookies), str(backup_dir))

        assert result is True
        # Verify main cookies file now contains backup content
        assert main_cookies.read_text() == "fresh_token\tyyy\n"

    def test_probe_and_rotate_no_backup_returns_false(self, tmp_path):
        """Current cookie fails, no backup files → returns False."""
        from src.utils.cookie_probe import probe_and_rotate

        main_cookies = tmp_path / "cookies.txt"
        main_cookies.write_text("expired_token\n")

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        with patch("src.utils.cookie_probe.probe_cookie", return_value=False):
            result = probe_and_rotate(str(main_cookies), str(backup_dir))

        assert result is False

    def test_probe_and_rotate_all_backups_expired_returns_false(self, tmp_path):
        """Current cookie fails, backups also expired → returns False."""
        from src.utils.cookie_probe import probe_and_rotate

        main_cookies = tmp_path / "cookies.txt"
        main_cookies.write_text("expired\n")

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "cookies_backup_old.txt").write_text("also_expired\n")

        with patch("src.utils.cookie_probe.probe_cookie", return_value=False):
            result = probe_and_rotate(str(main_cookies), str(backup_dir))

        assert result is False
        # Main file unchanged
        assert main_cookies.read_text() == "expired\n"

    def test_probe_and_rotate_valid_main_skips_backup(self, tmp_path):
        """Current cookie is valid → no backup check needed."""
        from src.utils.cookie_probe import probe_and_rotate

        main_cookies = tmp_path / "cookies.txt"
        main_cookies.write_text("valid_token\n")

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "cookies_backup.txt").write_text("backup_token\n")

        with patch("src.utils.cookie_probe.probe_cookie", return_value=True):
            result = probe_and_rotate(str(main_cookies), str(backup_dir))

        assert result is True
        # Main file unchanged
        assert main_cookies.read_text() == "valid_token\n"


# ---------------------------------------------------------------------------
# Scenario 2 — download failure → exponential backoff retry
# ---------------------------------------------------------------------------

class TestScenario2BackoffRetry:
    """Download fails with retryable errors → backoff [0, 5, 30, 120, 600]."""

    def test_backoff_sleep_sequence(self, tmp_path):
        """Retryable error triggers sleep with correct backoff delays."""
        from src.pipeline.scheduler import _download_with_fallback

        config = {
            "downloader": {
                "yt_dlp_retries": 3,
                "temp_dir": str(tmp_path),
                "douk_path": "",
                "cookies_path": "",
            },
        }

        sleep_calls = []

        def mock_sleep(delay):
            sleep_calls.append(delay)

        def mock_download(**kwargs):
            raise TimeoutError("network timeout")

        with (
            patch("src.pipeline.scheduler.download_video", side_effect=mock_download),
            patch("src.pipeline.scheduler.time.sleep", side_effect=mock_sleep),
            patch("src.pipeline.scheduler.is_retryable", return_value=True),
            pytest.raises(TimeoutError),
        ):
            _download_with_fallback(
                video_id="test001",
                canonical_url="https://example.com/video",
                tmp_dir=tmp_path,
                config=config,
                correlation_id="backoff-test",
            )

        # backoff_seconds = [0, 5, 30, 120, 600]
        # 3 retries → sleep after attempt 0 and 1 (not after last)
        assert sleep_calls == [0, 5]

    def test_non_retryable_skips_to_end(self, tmp_path):
        """Non-retryable error (403) → no sleep, no retry."""
        from src.pipeline.scheduler import _download_with_fallback

        config = {
            "downloader": {
                "yt_dlp_retries": 3,
                "temp_dir": str(tmp_path),
                "douk_path": "",
                "cookies_path": "",
            },
        }

        sleep_calls = []

        def mock_sleep(delay):
            sleep_calls.append(delay)

        def mock_download(**kwargs):
            raise ValueError("403 forbidden")

        with (
            patch("src.pipeline.scheduler.download_video", side_effect=mock_download),
            patch("src.pipeline.scheduler.time.sleep", side_effect=mock_sleep),
            patch("src.pipeline.scheduler.is_retryable", return_value=False),
            pytest.raises(ValueError, match="403"),
        ):
            _download_with_fallback(
                video_id="test002",
                canonical_url="https://example.com/video",
                tmp_dir=tmp_path,
                config=config,
                correlation_id="no-retry-test",
            )

        # No sleep calls — non-retryable error breaks immediately
        assert sleep_calls == []

    def test_success_on_first_attempt_no_sleep(self, tmp_path):
        """First attempt succeeds → no sleep, no retry."""
        from src.pipeline.scheduler import _download_with_fallback

        config = {
            "downloader": {
                "yt_dlp_retries": 3,
                "temp_dir": str(tmp_path),
                "douk_path": "",
                "cookies_path": "",
            },
        }

        mock_result = {"video_path": Path("video.mp4")}

        with (
            patch("src.pipeline.scheduler.download_video", return_value=mock_result),
            patch("src.pipeline.scheduler.time.sleep") as mock_sleep,
        ):
            result = _download_with_fallback(
                video_id="test003",
                canonical_url="https://example.com/video",
                tmp_dir=tmp_path,
                config=config,
                correlation_id="first-attempt-ok",
            )

        assert result == mock_result
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 3 — clock jump → sleep-wake detect → zombie reclaim
# ---------------------------------------------------------------------------

class TestScenario3SleepWakeReclaim:
    """Clock jump > 60s triggers zombie reclaim."""

    def test_detect_sleep_wake_on_clock_jump(self):
        """time.time() diff > 60 → detect_sleep_wake returns True."""
        from src.utils.sleep_wake import detect_sleep_wake

        last_time = 1000.0
        current_time = 1070.0  # 70 seconds later

        with patch("src.utils.sleep_wake.time") as mock_time:
            mock_time.time.return_value = current_time
            result = detect_sleep_wake(last_time, threshold=60)

        assert result is True

    def test_detect_no_sleep_wake_on_normal_interval(self):
        """time.time() diff <= 60 → detect_sleep_wake returns False."""
        from src.utils.sleep_wake import detect_sleep_wake

        last_time = 1000.0
        current_time = 1005.0  # 5 seconds later

        with patch("src.utils.sleep_wake.time") as mock_time:
            mock_time.time.return_value = current_time
            result = detect_sleep_wake(last_time, threshold=60)

        assert result is False

    def test_detect_sleep_wake_on_first_start(self):
        """First start (last_loop_time=None) → returns True."""
        from src.utils.sleep_wake import detect_sleep_wake

        result = detect_sleep_wake(None)
        assert result is True

    def test_clock_jump_triggers_zombie_reclaim(self, tmp_path):
        """Simulate scheduler loop: clock jump > 60s → zombie tasks reclaimed."""
        from src.queue import db
        from src.utils.sleep_wake import detect_sleep_wake

        db_path = tmp_path / "test.sqlite3"
        conn = db.init_db(db_path)

        # Insert zombie task
        from datetime import datetime, timedelta, timezone
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn.execute(
            "INSERT INTO task (video_id, source_url, source_url_type, "
            "correlation_id, payload_json, status, claimed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("zombie1", "https://example.com/1", "full", "z1", "{}", "fetching", stale_time),
        )
        conn.commit()

        # Verify zombie is in 'fetching'
        row = conn.execute("SELECT status FROM task WHERE video_id='zombie1'").fetchone()
        assert row["status"] == "fetching"

        # Simulate clock jump detection
        last_loop_time = 1000.0
        current_time = 1070.0

        with patch("src.utils.sleep_wake.time") as mock_time:
            mock_time.time.return_value = current_time
            should_reclaim = detect_sleep_wake(last_loop_time, threshold=60)

        assert should_reclaim is True

        # Execute zombie reclaim (same logic as scheduler startup)
        reclaimed = db.reclaim_zombie_tasks(conn, timeout_minutes=30)
        assert reclaimed >= 1

        # Verify zombie was reclaimed
        row = conn.execute("SELECT * FROM task WHERE video_id='zombie1'").fetchone()
        assert row["status"] == "pending"
        assert row["claimed_at"] is None

        conn.close()
