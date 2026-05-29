import re
from collections import defaultdict
from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.6
_MIN_LEN = 3
_MAX_LEN = 60


def _normalize(name: str) -> str:
    return re.sub(r'[^\w\s]', ' ', name.lower()).strip()


def _edit_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _token_jaccard(a: str, b: str) -> float:
    ta = set(a.split()) - {''}
    tb = set(b.split()) - {''}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    return max(_edit_similarity(na, nb), _token_jaccard(na, nb))


def suggest_clusters(tag_names: list[str], threshold: float = SIMILARITY_THRESHOLD) -> list[list[str]]:
    """Return groups of similar tag names, each with >= 2 members, sorted largest first."""
    names = [n for n in tag_names if _MIN_LEN <= len(n) <= _MAX_LEN]
    n = len(names)

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if similarity(names[i], names[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[str]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(names[i])

    clusters = [sorted(g) for g in groups.values() if len(g) >= 2]
    return sorted(clusters, key=len, reverse=True)
