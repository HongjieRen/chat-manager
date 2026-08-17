import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import chat_manager


class PurgeQuarantineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.quarantine_base = Path(self.temp_dir.name) / "chat-manager-quarantine"
        self.real_expanduser = os.path.expanduser

    def run_purge(self, days: int, *, apply: bool = False) -> str:
        def expanduser(path: str) -> str:
            if path == "~/.claude/chat-manager-quarantine":
                return str(self.quarantine_base)
            return self.real_expanduser(path)

        output = io.StringIO()
        with mock.patch.object(chat_manager.os.path, "expanduser", side_effect=expanduser):
            with contextlib.redirect_stdout(output):
                chat_manager.cmd_purge_quarantine(days, apply=apply)
        return output.getvalue()

    def make_quarantined_session(
        self,
        quarantined_at: datetime,
        *,
        file_age_days: int,
    ) -> Path:
        batch = quarantined_at.strftime("%Y%m%d-%H%M%S")
        session = (
            self.quarantine_base
            / batch
            / "Users"
            / "tester"
            / ".codex"
            / "sessions"
            / "rollout-test.jsonl"
        )
        session.parent.mkdir(parents=True)
        session.write_text("{}\n")
        file_time = (datetime.now() - timedelta(days=file_age_days)).timestamp()
        os.utime(session, (file_time, file_time))
        return session

    def test_purge_finds_hidden_codex_path_and_uses_batch_age(self) -> None:
        session = self.make_quarantined_session(
            datetime.now() - timedelta(days=8),
            file_age_days=0,
        )

        output = self.run_purge(7)

        self.assertIn("Found 1 file(s) older than 7 days", output)
        self.assertTrue(session.exists(), "dry run must not delete the session")

        output = self.run_purge(7, apply=True)

        self.assertIn("purged=1", output)
        self.assertFalse(session.exists())

    def test_purge_does_not_use_old_transcript_mtime_for_new_batch(self) -> None:
        session = self.make_quarantined_session(
            datetime.now(),
            file_age_days=30,
        )

        output = self.run_purge(7, apply=True)

        self.assertIn("No quarantined files older than 7 days", output)
        self.assertTrue(session.exists())


if __name__ == "__main__":
    unittest.main()
