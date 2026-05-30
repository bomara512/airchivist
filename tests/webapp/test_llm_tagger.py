import os
import pytest
from unittest.mock import MagicMock, patch

from webapp.llm_tagger import (
    compute_pool_hash,
    _build_user_message,
    get_suggestions,
    is_available,
)


def _mock_anthropic(mock_client):
    """Return a fake anthropic module whose Anthropic() returns mock_client."""
    mod = MagicMock()
    mod.Anthropic.return_value = mock_client
    return mod


def _make_mock_response(tool_input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input
    response = MagicMock()
    response.content = [block]
    return response


class TestComputePoolHash:
    def test_stable(self):
        tags = [{"name": "guitar"}, {"name": "cooking"}]
        assert compute_pool_hash(tags) == compute_pool_hash(tags)

    def test_order_independent(self):
        a = [{"name": "guitar"}, {"name": "cooking"}]
        b = [{"name": "cooking"}, {"name": "guitar"}]
        assert compute_pool_hash(a) == compute_pool_hash(b)

    def test_different_inputs_differ(self):
        assert compute_pool_hash([{"name": "guitar"}]) != compute_pool_hash([{"name": "cooking"}])

    def test_empty_list(self):
        assert isinstance(compute_pool_hash([]), str)
        assert len(compute_pool_hash([])) == 16


class TestBuildUserMessage:
    def test_includes_canonical_tags(self):
        msg = _build_user_message(
            [{"name": "guitar", "video_count": 5}],
            [{"name": "beginner guitar", "video_count": 3}],
        )
        assert "guitar" in msg
        assert "5 videos" in msg

    def test_includes_unclassified_tags(self):
        msg = _build_user_message(
            [],
            [{"name": "beginner guitar", "video_count": 3}],
        )
        assert "beginner guitar" in msg
        assert "3 videos" in msg

    def test_no_canonical_tags_message(self):
        msg = _build_user_message([], [{"name": "some tag", "video_count": 1}])
        assert "No canonical tags" in msg

    def test_singular_video_count(self):
        msg = _build_user_message([], [{"name": "test", "video_count": 1}])
        assert "1 video)" in msg
        assert "1 videos)" not in msg


class TestIsAvailable:
    def test_false_when_package_missing(self):
        with patch.dict("sys.modules", {"anthropic": None}):
            assert is_available() is False

    def test_false_when_key_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict("sys.modules", {"anthropic": MagicMock()}), \
             patch.dict("os.environ", env, clear=True):
            assert is_available() is False

    def test_true_when_available(self):
        with patch.dict("sys.modules", {"anthropic": MagicMock()}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            assert is_available() is True


class TestGetSuggestions:
    def test_returns_assignment_suggestions(self):
        mock_input = {
            "assignments": [
                {"canonical": "guitar", "members": ["beginner guitar"], "confidence": "high"}
            ],
            "noise": [],
            "unassigned": [],
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(mock_input)

        with patch.dict("sys.modules", {"anthropic": _mock_anthropic(mock_client)}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            result = get_suggestions(
                [{"name": "guitar", "video_count": 5}],
                [{"name": "beginner guitar", "video_count": 3}],
            )

        assert len(result) == 1
        assert result[0]["canonical"] == "guitar"
        assert result[0]["members"] == ["beginner guitar"]
        assert result[0]["confidence"] == "high"
        assert result[0]["is_noise"] is False

    def test_noise_tags_grouped_as_noise_suggestion(self):
        mock_input = {
            "assignments": [],
            "noise": ["#ad", "HD"],
            "unassigned": [],
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(mock_input)

        with patch.dict("sys.modules", {"anthropic": _mock_anthropic(mock_client)}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            result = get_suggestions([], [{"name": "#ad", "video_count": 2}])

        noise = [s for s in result if s["is_noise"]]
        assert len(noise) == 1
        assert noise[0]["canonical"] == "_noise"
        assert "#ad" in noise[0]["members"]
        assert "HD" in noise[0]["members"]

    def test_empty_member_lists_skipped(self):
        mock_input = {
            "assignments": [
                {"canonical": "guitar", "members": [], "confidence": "high"},
                {"canonical": "cooking", "members": ["recipe"], "confidence": "medium"},
            ],
            "noise": [],
            "unassigned": [],
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(mock_input)

        with patch.dict("sys.modules", {"anthropic": _mock_anthropic(mock_client)}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            result = get_suggestions([], [{"name": "recipe", "video_count": 1}])

        assert len(result) == 1
        assert result[0]["canonical"] == "cooking"

    def test_raises_when_api_key_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict("sys.modules", {"anthropic": MagicMock()}), \
             patch.dict("os.environ", env, clear=True):
            with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                get_suggestions([], [])

    def test_raises_when_anthropic_not_installed(self):
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="anthropic"):
                get_suggestions([], [])

    def test_raises_when_no_tool_use_in_response(self):
        block = MagicMock()
        block.type = "text"
        response = MagicMock()
        response.content = [block]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = response

        with patch.dict("sys.modules", {"anthropic": _mock_anthropic(mock_client)}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with pytest.raises(ValueError, match="categorize_tags"):
                get_suggestions([], [])

    def test_passes_correct_model_to_api(self):
        mock_input = {"assignments": [], "noise": [], "unassigned": []}
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(mock_input)

        with patch.dict("sys.modules", {"anthropic": _mock_anthropic(mock_client)}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            get_suggestions([], [], model="claude-sonnet-4-6")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    def test_tool_choice_forces_categorize_tags(self):
        mock_input = {"assignments": [], "noise": [], "unassigned": []}
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(mock_input)

        with patch.dict("sys.modules", {"anthropic": _mock_anthropic(mock_client)}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            get_suggestions([], [])

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "categorize_tags"}
