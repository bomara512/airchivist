import re


def find_matching_tags(title: str, description: str, tags: list) -> list:
    text = f"{title} {description}"
    matched = []
    for tag in tags:
        keywords = tag.get("keywords") or []
        if not keywords:
            continue
        for kw in keywords:
            pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
            if pattern.search(text):
                matched.append(tag)
                break
    return matched


def group_videos_by_tags(videos: list, tags: list) -> list:
    claimed = set()
    groups = []

    for tag in tags:
        matched_videos = []
        for i, video in enumerate(videos):
            if i in claimed:
                continue
            title = video.get("title") or ""
            description = video.get("description") or ""
            if find_matching_tags(title, description, [tag]):
                matched_videos.append(video)
                claimed.add(i)
        if matched_videos:
            groups.append({"tag": tag, "videos": matched_videos})

    untagged = [v for i, v in enumerate(videos) if i not in claimed]
    if untagged:
        groups.append({"tag": None, "videos": untagged})

    return groups
