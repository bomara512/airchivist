import plistlib
from pathlib import Path

import pytest

PLIST = Path(__file__).resolve().parents[2] / "scripts" / "com.airchivist.refresh.plist"


@pytest.fixture
def plist():
    with PLIST.open("rb") as f:
        return plistlib.load(f)


class TestRefreshPlist:
    def test_is_valid_plist_xml(self, plist):
        """A malformed plist fails at `launchctl load` with an unhelpful message, so
        parse it here where the error is readable."""
        assert plist["Label"] == "com.airchivist.refresh"

    def test_runs_the_refresh_subcommand(self, plist):
        args = plist["ProgramArguments"]
        assert "refresh" in args
        assert "--db" in args

    def test_runs_daily_at_3am(self, plist):
        assert plist["StartCalendarInterval"] == {"Hour": 3, "Minute": 0}

    def test_does_not_run_at_load(self, plist):
        """Loading the job must not immediately start a multi-minute run."""
        assert plist["RunAtLoad"] is False

    def test_captures_both_streams_to_a_log(self, plist):
        assert plist["StandardOutPath"].endswith("airchivist-refresh.log")
        assert plist["StandardErrorPath"].endswith("airchivist-refresh.log")

    def test_uses_absolute_paths_only(self, plist):
        """launchd does no shell expansion and does not inherit an interactive PATH,
        so a bare `airchivist-crawler` or a `~` would silently never run."""
        for arg in plist["ProgramArguments"]:
            if arg.startswith("-") or arg == "refresh":
                continue
            assert arg.startswith("/"), f"{arg!r} is not an absolute path"
