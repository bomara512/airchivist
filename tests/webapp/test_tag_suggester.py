import pytest
from webapp.tag_suggester import suggest_clusters, similarity


class TestSimilarity:
    def test_identical_strings(self):
        assert similarity("guitar", "guitar") == 1.0

    def test_hyphen_variant(self):
        assert similarity("meal prep", "meal-prep") >= 0.6

    def test_plural_variant(self):
        assert similarity("guitar lesson", "guitar lessons") >= 0.6

    def test_prefix_overlap(self):
        assert similarity("meal prep", "meal prep recipes") >= 0.6

    def test_token_overlap(self):
        # "meal prep" and "meal prep recipes" share 2/3 tokens → Jaccard = 0.667
        assert similarity("meal prep", "meal prep recipes") >= 0.6

    def test_unrelated_strings(self):
        assert similarity("guitar", "cooking") < 0.6

    def test_case_insensitive(self):
        assert similarity("Guitar", "guitar") == 1.0

    def test_punctuation_ignored(self):
        assert similarity("meal-prep", "meal prep") >= 0.6


class TestSuggestClusters:
    def test_groups_similar_tags(self):
        tags = ["meal prep", "meal-prep", "meal prep recipes"]
        clusters = suggest_clusters(tags)
        assert len(clusters) == 1
        assert set(clusters[0]) == {"meal prep", "meal-prep", "meal prep recipes"}

    def test_returns_empty_when_no_similarity(self):
        tags = ["guitar", "cooking", "astronomy", "cycling"]
        clusters = suggest_clusters(tags)
        assert clusters == []

    def test_minimum_two_members(self):
        tags = ["guitar", "guitar lesson"]
        clusters = suggest_clusters(tags)
        assert all(len(c) >= 2 for c in clusters)

    def test_sorted_largest_first(self):
        tags = ["meal prep", "meal-prep", "meal prep recipes",
                "guitar", "guitar lesson"]
        clusters = suggest_clusters(tags)
        sizes = [len(c) for c in clusters]
        assert sizes == sorted(sizes, reverse=True)

    def test_filters_short_tags(self):
        tags = ["ok", "guitar", "guitar lesson"]
        clusters = suggest_clusters(tags)
        for cluster in clusters:
            assert all(len(t) >= 3 for t in cluster)

    def test_threshold_parameter(self):
        tags = ["guitar", "guitars"]
        assert suggest_clusters(tags, threshold=0.5) != []
        assert suggest_clusters(tags, threshold=0.99) == []

    def test_multiple_independent_clusters(self):
        tags = ["meal prep", "meal-prep", "guitar", "guitar lesson"]
        clusters = suggest_clusters(tags)
        assert len(clusters) == 2

    def test_members_sorted_alphabetically_within_cluster(self):
        tags = ["meal prep recipes", "meal-prep", "meal prep"]
        clusters = suggest_clusters(tags)
        assert clusters[0] == sorted(clusters[0])
