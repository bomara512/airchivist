import pytest
from webapp.keyword_matcher import find_matching_tags, group_videos_by_tags

TAGS = [
    {"id": 1, "name": "guitar", "keywords": ["guitar", "chord", "lesson"]},
    {"id": 2, "name": "thai food", "keywords": ["thai", "recipe", "pad thai"]},
    {"id": 3, "name": "empty", "keywords": []},
]

VIDEOS = [
    {"title": "Guitar Lesson 1", "description": "Learn basic guitar chords", "tags": "guitar"},
    {"title": "Advanced Chords", "description": "Advanced guitar chord progressions", "tags": "guitar"},
    {"title": "Thai Food Recipe", "description": "Authentic pad thai recipe with shrimp", "tags": "thai food"},
    {"title": "Pad Thai Tutorial", "description": "Step by step thai cooking tutorial", "tags": "thai food"},
    {"title": "Random Video", "description": "Nothing in particular", "tags": ""},
]


class TestFindMatchingTags:
    def test_matches_tag_by_keyword_in_title(self):
        tags = find_matching_tags("Guitar Lesson 1", "", TAGS)
        names = [t["name"] for t in tags]
        assert "guitar" in names

    def test_matches_tag_by_keyword_in_description(self):
        tags = find_matching_tags("Some Video", "Learn about thai cuisine recipes", TAGS)
        names = [t["name"] for t in tags]
        assert "thai food" in names

    def test_no_match_returns_empty(self):
        tags = find_matching_tags("Nothing here", "Totally unrelated", TAGS)
        assert tags == []

    def test_does_not_match_partial_word(self):
        # "chord" should not match "chords" within another word boundary
        tags = find_matching_tags("dischordant music", "", TAGS)
        names = [t["name"] for t in tags]
        assert "guitar" not in names

    def test_matches_are_case_insensitive(self):
        tags = find_matching_tags("GUITAR TUTORIAL", "", TAGS)
        names = [t["name"] for t in tags]
        assert "guitar" in names

    def test_tag_with_no_keywords_never_matches(self):
        tags = find_matching_tags("anything", "anything", TAGS)
        names = [t["name"] for t in tags]
        assert "empty" not in names

    def test_multi_word_keyword_matches(self):
        tags = find_matching_tags("Pad Thai Tutorial", "", TAGS)
        names = [t["name"] for t in tags]
        assert "thai food" in names

    def test_returns_list_of_tag_dicts(self):
        tags = find_matching_tags("guitar lesson", "", TAGS)
        assert isinstance(tags, list)
        assert all("name" in t for t in tags)


class TestGroupVideosByTags:
    def test_groups_videos_under_matching_tag(self):
        groups = group_videos_by_tags(VIDEOS, TAGS)
        guitar_group = next((g for g in groups if g["tag"]["name"] == "guitar"), None)
        assert guitar_group is not None
        titles = [v["title"] for v in guitar_group["videos"]]
        assert "Guitar Lesson 1" in titles

    def test_unmatched_videos_in_untagged_group(self):
        groups = group_videos_by_tags(VIDEOS, TAGS)
        untagged = next((g for g in groups if g["tag"] is None), None)
        assert untagged is not None
        titles = [v["title"] for v in untagged["videos"]]
        assert "Random Video" in titles

    def test_no_empty_tagged_groups(self):
        groups = group_videos_by_tags(VIDEOS, TAGS)
        tagged_groups = [g for g in groups if g["tag"] is not None]
        assert all(len(g["videos"]) > 0 for g in tagged_groups)

    def test_each_video_appears_at_most_once(self):
        groups = group_videos_by_tags(VIDEOS, TAGS)
        all_titles = [v["title"] for g in groups for v in g["videos"]]
        assert len(all_titles) == len(set(all_titles))

    def test_returns_list_of_dicts_with_tag_and_videos(self):
        groups = group_videos_by_tags(VIDEOS, TAGS)
        assert isinstance(groups, list)
        for g in groups:
            assert "tag" in g
            assert "videos" in g

    def test_empty_videos_returns_single_untagged_group_or_empty(self):
        groups = group_videos_by_tags([], TAGS)
        assert groups == [] or all(len(g["videos"]) == 0 for g in groups)
