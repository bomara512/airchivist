from webapp.video_filters import VideoListFilters, group_videos


class TestFromArgs:
    def test_defaults_when_no_args(self):
        f = VideoListFilters.from_args({})
        assert f.sort_by == "date_added"
        assert f.sort_dir == "desc"
        assert f.channel is None
        assert f.watch_status == ""
        assert f.active_count == 0

    def test_empty_string_params_are_normalized_to_none(self):
        f = VideoListFilters.from_args({"channel": "", "tag": "", "duration": ""})
        assert f.channel is None
        assert f.tag is None
        assert f.duration is None
        assert f.active_count == 0

    def test_watch_status_drives_the_two_derived_flags(self):
        assert VideoListFilters.from_args({"watch_status": "unwatched"}).unwatched_only is True
        assert VideoListFilters.from_args({"watch_status": "unwatched"}).unwatched_first is False
        assert VideoListFilters.from_args({"watch_status": "unwatched_first"}).unwatched_first is True
        assert VideoListFilters.from_args({"watch_status": "unwatched_first"}).unwatched_only is False

    def test_unrecognized_watch_status_sets_neither_flag(self):
        f = VideoListFilters.from_args({"watch_status": "bogus"})
        assert f.unwatched_only is False
        assert f.unwatched_first is False
        assert f.active_count == 1  # still counts as "a filter is active"


class TestAddedWithin:
    """Review Focus #2: junk is swallowed here; out-of-allowlist is the DB layer's 400."""

    def test_non_numeric_becomes_none(self):
        assert VideoListFilters.from_args({"added_within": "notanumber"}).added_within is None

    def test_numeric_is_kept_verbatim_even_if_not_in_the_db_allowlist(self):
        # 5 is not in _ADDED_WITHIN_DAYS; get_all_videos raises ValueError on it,
        # which the index route turns into a 400. Parsing must not swallow it.
        assert VideoListFilters.from_args({"added_within": "5"}).added_within == 5


class TestActiveCount:
    def test_counts_each_active_filter_once(self):
        f = VideoListFilters.from_args({
            "channel": "SomeChannel",
            "tag": "some-tag",
            "sort_by": "title",
            "sort_dir": "asc",
            "group": "channel",
            "favorites": "1",
            "watch_status": "unwatched",
            "duration": "short",
            "added_within": "7",
        })
        assert f.active_count == 9

    def test_search_does_not_count(self):
        assert VideoListFilters.from_args({"search": "anything"}).active_count == 0


class TestDbKwargs:
    def test_maps_watch_status_onto_unwatched_only(self):
        kwargs = VideoListFilters.from_args({"watch_status": "unwatched"}).db_kwargs()
        assert kwargs["unwatched_only"] is True
        assert "unwatched_first" not in kwargs   # get_all_videos takes that separately
        assert set(kwargs) == {
            "channel", "tag", "search", "favorites_only",
            "unwatched_only", "duration", "added_within",
        }


class TestGroupVideos:
    VIDEOS = [
        {"video_id": "v1", "channel_name": "A", "tags": "x,y"},
        {"video_id": "v2", "channel_name": "B", "tags": ""},
        {"video_id": "v3", "channel_name": "A", "tags": "x"},
    ]

    def test_returns_none_when_not_grouping(self):
        assert group_videos(self.VIDEOS, None) is None
        assert group_videos(self.VIDEOS, "") is None

    def test_groups_by_channel(self):
        groups = group_videos(self.VIDEOS, "channel")
        assert [g["tag"]["name"] for g in groups] == ["A", "B"]
        assert len(groups[0]["videos"]) == 2

    def test_missing_channel_name_becomes_unknown(self):
        groups = group_videos([{"video_id": "v9", "channel_name": None, "tags": ""}], "channel")
        assert groups[0]["tag"]["name"] == "Unknown"

    def test_groups_by_tag_with_untagged_last(self):
        groups = group_videos(self.VIDEOS, "tag")
        assert [g["tag"]["name"] for g in groups] == ["x", "y", "Untagged"]

    def test_a_video_with_two_tags_appears_in_both_groups(self):
        groups = {g["tag"]["name"]: g["videos"] for g in group_videos(self.VIDEOS, "tag")}
        assert groups["x"] == [self.VIDEOS[0], self.VIDEOS[2]]
        assert groups["y"] == [self.VIDEOS[0]]
