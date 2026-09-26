from crawler.datastore import Datastore
from crawler.models import Bookmark, FetchStatus, VideoMetadata
from crawler.refresh import RefreshSummary, run_refresh


def _ok(video_id, title="T"):
    return VideoMetadata(video_id=video_id, url="u", title=title, fetch_status=FetchStatus.OK)


def _seed(ds, *video_ids):
    for vid in video_ids:
        ds.upsert_video(_ok(vid, f"Title {vid}"), Bookmark(url="u", title="T"))


class TestRunRefresh:
    def test_refreshes_every_selected_video(self, tmp_path):
        calls = []

        def fake_fetch(video_id, delay=0):
            calls.append(video_id)
            return _ok(video_id, "Updated")

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1", "aaaaaaaaaa2")
            summary = run_refresh(ds, limit=10, delay=0, fetch=fake_fetch)
            assert sorted(calls) == ["aaaaaaaaaa1", "aaaaaaaaaa2"]
            assert ds.get_video_by_id("aaaaaaaaaa1")["title"] == "Updated"
        assert summary.attempted == 2
        assert summary.counts["ok"] == 2

    def test_tallies_each_status(self, tmp_path):
        statuses = {
            "aaaaaaaaaa1": FetchStatus.OK,
            "aaaaaaaaaa2": FetchStatus.DELETED,
            "aaaaaaaaaa3": FetchStatus.PRIVATE,
        }

        def fake_fetch(video_id, delay=0):
            return VideoMetadata(video_id=video_id, url="u", title="T",
                                 fetch_status=statuses[video_id])

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, *statuses)
            summary = run_refresh(ds, limit=10, delay=0, fetch=fake_fetch)
        assert summary.counts == {"ok": 1, "deleted": 1, "private": 1}

    def test_honors_the_limit(self, tmp_path):
        def fake_fetch(video_id, delay=0):
            return _ok(video_id)

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3")
            summary = run_refresh(ds, limit=2, delay=0, fetch=fake_fetch)
        assert summary.attempted == 2

    def test_an_unexpected_exception_does_not_abort_the_run(self, tmp_path):
        """Review Focus #2: one bad video must not cost the whole nightly job. The
        row is left untouched so the next run retries it."""
        def fake_fetch(video_id, delay=0):
            if video_id == "aaaaaaaaaa2":
                raise OSError("network unreachable")
            return _ok(video_id, "Updated")

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3")
            summary = run_refresh(ds, limit=10, delay=0, fetch=fake_fetch)
            assert ds.get_video_by_id("aaaaaaaaaa1")["title"] == "Updated"
            assert ds.get_video_by_id("aaaaaaaaaa3")["title"] == "Updated"
            assert ds.get_video_by_id("aaaaaaaaaa2")["title"] == "Title aaaaaaaaaa2"
        assert summary.counts["ok"] == 2
        assert summary.counts["failed"] == 1

    def test_an_empty_library_is_a_clean_zero_run(self, tmp_path):
        """Review Focus #5."""
        def fake_fetch(video_id, delay=0):
            raise AssertionError("must not be called")

        with Datastore(tmp_path / "t.db") as ds:
            summary = run_refresh(ds, limit=200, delay=0, fetch=fake_fetch)
        assert summary.attempted == 0
        assert summary.library_total == 0
        assert summary.counts == {}
        assert "0 of 0" in summary.line()

    def test_a_library_smaller_than_the_limit_is_fine(self, tmp_path):
        def fake_fetch(video_id, delay=0):
            return _ok(video_id)

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1")
            summary = run_refresh(ds, limit=200, delay=0, fetch=fake_fetch)
        assert summary.attempted == 1
        assert summary.library_total == 1

    def test_passes_the_delay_through_to_the_fetcher(self, tmp_path):
        seen = []

        def fake_fetch(video_id, delay=0):
            seen.append(delay)
            return _ok(video_id)

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1")
            run_refresh(ds, limit=10, delay=2.5, fetch=fake_fetch)
        assert seen == [2.5]


class TestRefreshSummaryLine:
    def test_reads_as_one_scannable_line(self):
        summary = RefreshSummary(
            attempted=200, library_total=2958,
            counts={"ok": 196, "deleted": 3, "private": 1},
            elapsed_seconds=312.0,
        )
        line = summary.line()
        assert line.startswith("refreshed 200 of 2958")
        assert "196 ok" in line
        assert "3 deleted" in line
        assert "5m12s" in line

    def test_a_sub_minute_run_reads_in_seconds(self):
        summary = RefreshSummary(attempted=1, library_total=1, counts={"ok": 1},
                                 elapsed_seconds=4.0)
        assert "4s" in summary.line()

    def test_a_zero_run_still_produces_a_line(self):
        assert "refreshed 0 of 0" in RefreshSummary(
            attempted=0, library_total=0, counts={}, elapsed_seconds=0.0
        ).line()
