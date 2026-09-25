import math
from collections.abc import Mapping
from typing import Any

from flask import request, url_for

# Params that describe *which* page is being fetched, rather than what is being
# filtered — they must never be carried into a generated pagination link.
# `append=1` marks an HTMX "load more" fetch; leaking it into a Prev/Next href
# made the Archived page's links request a bare fragment.
_TRANSIENT_ARGS = ("page", "append")


def requested_page(args: Mapping[str, Any]) -> int:
    """The caller's requested page number, coerced to at least 1.

    Junk (`?page=abc`, `?page=-5`, `?page=`) yields 1 rather than raising, so a
    hand-edited or stale URL is a harmless first page instead of a 500.
    """
    try:
        return max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        return 1


def pagination_context(endpoint: str, *, requested_page: int, total: int, page_size: int) -> dict:
    """Page numbers plus Prev/Next URLs for a paginated route.

    Returns the template variables the paginated routes all pass through:
    `page`, `total_pages`, `total`, `prev_url`, `next_url`. Filter params from
    the current request are carried into the URLs; `_TRANSIENT_ARGS` are not.

    `page` comes back clamped to the last real page. Callers that query before
    calling this (index, hidden) pass their raw page to the DB and use the
    clamped one only for display; callers that clamp first (channels) query with
    the value this returns.
    """
    total_pages = max(1, math.ceil(total / page_size))
    page = min(max(1, requested_page), total_pages)

    def url_for_page(target: int) -> str:
        params = {k: v for k, v in request.args.to_dict().items() if k not in _TRANSIENT_ARGS}
        params["page"] = target
        return url_for(endpoint, **params)

    return {
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "prev_url": url_for_page(page - 1) if page > 1 else None,
        "next_url": url_for_page(page + 1) if page < total_pages else None,
    }
