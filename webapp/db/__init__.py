# Re-export the full public API so all existing import paths continue to work:
#   from webapp import db as _db  →  _db.get_all_videos(...)
#   from webapp.db import get_all_videos, MatchType, ...

from crawler.datastore import apply_aliases
from crawler.models import FetchStatus, MatchType

from webapp.db.aliases import (
    add_alias,
    add_alias_and_apply,
    delete_alias,
    delete_alias_with_cleanup,
    edit_alias,
    edit_alias_and_apply,
    retroactive_apply,
)
from webapp.db.groups import (
    add_canonical_to_group,
    create_tag_group,
    delete_tag_group,
    get_tag_groups,
    get_ungrouped_canonicals,
    remove_canonical_from_group,
)
from webapp.db.schema import init_webapp_tables
from webapp.db.suggestions import (
    accept_noise_and_dismiss_suggestion,
    confirm_and_dismiss_suggestion,
    confirm_suggestion,
    dismiss_llm_suggestion,
    get_llm_suggestion_by_id,
    get_llm_suggestions,
    is_llm_suggestion_cache_stale,
    record_suggestion_rejections,
    save_llm_suggestions,
)
from webapp.db.tags import (
    add_video_tag,
    collapse_case_variants,
    create_canonical_tag,
    create_tag,
    delete_tag,
    get_all_tags,
    get_canonical_tags,
    get_canonical_tags_for_filter,
    get_canonical_tags_for_filter_grouped,
    get_related_unclassified_tags,
    get_tag_keywords,
    get_tags_for_video,
    get_tags_with_keywords,
    get_unclassified_tags,
    get_video_titles_for_tag,
    mark_tag_noise,
    mark_tags_noise_bulk,
    remove_video_tag,
    set_tag_keywords,
)
from webapp.db.videos import (
    ALLOWED_SORT_COLUMNS,
    ALLOWED_SORT_DIRS,
    add_video,
    count_hidden_videos,
    count_videos,
    delete_video,
    get_all_channels,
    get_all_videos,
    get_hidden_videos,
    get_stats,
    get_video_by_id,
    get_videos_status_batch,
    hide_video,
    record_visit,
    unhide_video,
)

__all__ = [
    # re-exported from crawler
    "apply_aliases", "FetchStatus", "MatchType",
    # aliases
    "add_alias", "add_alias_and_apply", "delete_alias", "delete_alias_with_cleanup", "edit_alias",
    "edit_alias_and_apply", "retroactive_apply",
    # groups
    "add_canonical_to_group", "create_tag_group", "delete_tag_group", "get_tag_groups",
    "get_ungrouped_canonicals", "remove_canonical_from_group",
    # schema
    "init_webapp_tables",
    # suggestions
    "accept_noise_and_dismiss_suggestion", "confirm_and_dismiss_suggestion", "confirm_suggestion",
    "dismiss_llm_suggestion", "get_llm_suggestion_by_id", "get_llm_suggestions",
    "is_llm_suggestion_cache_stale", "record_suggestion_rejections", "save_llm_suggestions",
    # tags
    "add_video_tag", "collapse_case_variants", "create_canonical_tag", "create_tag",
    "delete_tag", "get_all_tags", "get_canonical_tags", "get_canonical_tags_for_filter",
    "get_canonical_tags_for_filter_grouped", "get_related_unclassified_tags", "get_tag_keywords",
    "get_tags_for_video", "get_tags_with_keywords", "get_unclassified_tags",
    "get_video_titles_for_tag", "mark_tag_noise", "mark_tags_noise_bulk", "remove_video_tag",
    "set_tag_keywords",
    # videos
    "ALLOWED_SORT_COLUMNS", "ALLOWED_SORT_DIRS", "add_video", "count_hidden_videos",
    "count_videos", "delete_video", "get_all_channels", "get_all_videos", "get_hidden_videos",
    "get_stats", "get_video_by_id", "get_videos_status_batch", "hide_video", "record_visit",
    "unhide_video",
]
