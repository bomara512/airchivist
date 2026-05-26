import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from crawler.models import Bookmark


def _us_to_datetime(us: int) -> datetime:
    return datetime.fromtimestamp(us / 1_000_000, tz=timezone.utc).replace(tzinfo=None)


def _s_to_datetime(s: int) -> datetime:
    return datetime.fromtimestamp(s, tz=timezone.utc).replace(tzinfo=None)


def _walk_json(node: dict, results: list[Bookmark]) -> None:
    type_code = node.get("typeCode")
    uri = node.get("uri", "")

    if type_code == 1 and uri:
        date_added: Optional[datetime] = None
        if "dateAdded" in node:
            try:
                date_added = _us_to_datetime(int(node["dateAdded"]))
            except (ValueError, OSError):
                pass
        results.append(Bookmark(url=uri, title=node.get("title", ""), date_added=date_added))

    for child in node.get("children", []):
        _walk_json(child, results)


class _NetscapeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks: list[Bookmark] = []
        self._current_title = ""
        self._in_a = False
        self._current_attrs: dict = {}

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in_a = True
            self._current_attrs = dict(attrs)
            self._current_title = ""

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            href = self._current_attrs.get("href", "")
            if not href:
                return

            date_added: Optional[datetime] = None
            add_date = self._current_attrs.get("add_date")
            if add_date:
                try:
                    date_added = _s_to_datetime(int(add_date))
                except (ValueError, OSError):
                    pass

            self.bookmarks.append(
                Bookmark(url=href, title=self._current_title, date_added=date_added)
            )

    def handle_data(self, data):
        if self._in_a:
            self._current_title += data


def _parse_json(path: Path) -> list[Bookmark]:
    with open(path, encoding="utf-8") as f:
        root = json.load(f)
    results: list[Bookmark] = []
    _walk_json(root, results)
    return results


def _parse_html(path: Path) -> list[Bookmark]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    parser = _NetscapeParser()
    parser.feed(content)
    return parser.bookmarks


def parse(path: Path) -> list[Bookmark]:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return _parse_json(path)
    if suffix in (".html", ".htm"):
        return _parse_html(path)
    raise ValueError(f"Unsupported bookmark file format: {suffix!r}")
