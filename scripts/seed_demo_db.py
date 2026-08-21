#!/usr/bin/env python3
"""Seed a fresh SQLite file with real public YouTube content and fabricated
personal-engagement data, for a one-command "try it now" Airchivist demo.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Running this file directly (`python scripts/seed_demo_db.py`, as demo.sh and the
# README do) sets sys.path[0] to scripts/, not the repo root, so the editable
# `webapp`/`crawler` install isn't found. Insert the repo root explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler.datastore import _SCHEMA as _CRAWLER_SCHEMA
from crawler.models import ChannelMetadata, FetchStatus
from webapp.db import (
    add_canonical_to_group,
    add_to_watch_later,
    add_video,
    add_video_tag,
    create_canonical_tag,
    create_tag,
    create_tag_group,
    hide_video,
    init_webapp_tables,
    set_favorite,
    set_watched,
    upsert_channel,
)

ANCHOR = datetime.now(timezone.utc)

# channel_name -> (channel_id, channel_url, avatar_thumbnail_url). Real, verified via
# `yt-dlp`/`crawler.metadata_fetcher.fetch_channel_metadata` on 2026-08-20. An earlier pass
# wrongly concluded these fail under concurrent load and reverted to no avatar — that was a
# test artifact (subsequent navigation cancelled in-flight `loading="lazy"` image requests
# mid-fetch, which looks identical to a real failure). Direct `new Image()` loads of every
# URL here succeed in well under a second each; the real app's own /channels page (1900+
# channels, same avatar mechanism) also confirms these load fine in normal use.
CHANNELS: dict[str, tuple[str, str, str]] = {
    "Spring I/O": ("UCLMPXsvSrhNPN3i9h-u8PYg", "https://www.youtube.com/@SpringIOConference", "https://yt3.googleusercontent.com/WZblQzigEED1WlfnrsMds4u-uL5y7_sgN4K_Ct5_MmCQmXfd-iULG4061RquXHBv7l_Jb3NNjc0=s0"),
    "Bon Appétit": ("UCbpMy0Fg74eXXkvxJrtEn3w", "https://www.youtube.com/@bonappetit", "https://yt3.googleusercontent.com/cXS_yturdFtxAvqzJRnbMtZRYKCv3CDD7VHqHmhGZ2jgM8PYnOAbAbhZaK-Wb1NWgIrxrUjJiA=s0"),
    "JustinGuitar": ("UCBNkm8o5LiEVLxO8w0p2sfQ", "https://www.youtube.com/@justinguitar", "https://yt3.googleusercontent.com/ytc/AIdro_m0JgCBMCYDFIhw7p5T9hzaXP71VvZbEiGDL33_kzeasw=s0"),
    "Rick Astley": ("UCuAXFkgsw1L7xaCfnd5JJOw", "https://www.youtube.com/@RickAstleyYT", "https://yt3.googleusercontent.com/MOWpaiGJdgN4aKMI-NGQLL4jMVP3aDORlQpOBWooi0GSE2TGt4_9ncyepk1pCh-yWQ795AhPbw=s0"),
    "officialpsy": ("UCrDkAvwZum-UTjHmzDI2iIw", "https://www.youtube.com/@officialpsy", "https://yt3.googleusercontent.com/kJ8zwS_VhJ0TE-XDumnshGQ86hazfhHjjU4xn80Dc8xmSghA_2xw4OJTHaGreyeoro6q_vcT=s0"),
    "TV Norge": ("UCYM3pKj9tFQOXc2XcJmj8Vg", "https://www.youtube.com/@tvnorge", "https://yt3.googleusercontent.com/IjZuI0ypNm3zSXtq4rmz0Hp-V2RsoOMGVSTRu_NL-PzoRKwnZeGvtwqgTUJOfZjbiLihKS-e=s0"),
    "Kurzgesagt – In a Nutshell": ("UCsXVk37bltHxD1rDPwtNM8Q", "https://www.youtube.com/@kurzgesagt", "https://yt3.googleusercontent.com/ytc/AIdro_n1Ribd7LwdP_qKtqWL3ZDfIgv9M1d6g78VwpHGXVR2Ir4=s0"),
    "TED": ("UCAuUUnT6oDeKwE6v1NGQxug", "https://www.youtube.com/@TED", "https://yt3.googleusercontent.com/ytc/AIdro_koIFcCOrvh0KThLNOiazAIDu6hcs8bjkGNwe1f6A_OYm8=s0"),
    "NASA": ("UCLA_DiR1FfKNvjuUpBHmylQ", "https://www.youtube.com/@NASA", "https://yt3.googleusercontent.com/eIf5fNPcIcj9ig-wZBeq4stFy1lgjWTW1nLT5dYlFkHZprZ03QBiMcbpwNMB6XSBjrSFGtAGQg=s0"),
    "NASA Jet Propulsion Laboratory": ("UCryGec9PdUCLjpJW2mgCuLw", "https://www.youtube.com/@NASAJPL", "https://yt3.googleusercontent.com/Qc8LKJsm3lqSGkKSb9kkJbJWW4PXBgt25eLVwWuMFZiSRl6RHptXnC2MwfmSl2kddj4Fhb3yQw=s0"),
    "National Geographic": ("UCpVm7bg6pXKo1Pr6k5kxG9A", "https://www.youtube.com/@NatGeo", "https://yt3.googleusercontent.com/-FOFg8o1y4dAHDB2MvhORHnLMOaaOKnaNUNsrU-U57Eac6gjB5VO8sYJQC1KkULGQvKP2XpArA=s0"),
    "Steve Ramsey - Woodworking for Mere Mortals": ("UCBB7sYb14uBtk8UqSQYc9-w", "https://www.youtube.com/@SteveRamsey", "https://yt3.googleusercontent.com/ytc/AIdro_nQ0eOGcisyW6KnwWnidTVPqCoUr5o9hiYODFlke6W5cg=s0"),
}

# 44 real videos. Real, verified via `yt-dlp` on 2026-08-19 — see
# docs/superpowers/specs/2026-08-19-demo-seed-data-design.md for the source table.
VIDEOS: list[dict] = [
    {"video_id": "pYDMhBVspIY", "title": "Spring I/O 2026 Keynote", "channel_name": "Spring I/O", "date_published": "2026-05-21", "duration_seconds": 4123, "yt_view_count": 4688},
    {"video_id": "nHnKReitDXc", "title": "Bootiful Spring AI by Josh Long / James Ward @ Spring I/O 2026", "channel_name": "Spring I/O", "date_published": "2026-05-22", "duration_seconds": 2523, "yt_view_count": 4369},
    {"video_id": "zO-bktrLju8", "title": "New in Spring Security 7: MFA, OAuth2 and more by Daniel Garnier @ Spring I/O 2026", "channel_name": "Spring I/O", "date_published": "2026-06-18", "duration_seconds": 2803, "yt_view_count": 5349},
    {"video_id": "QXQiGS9CL20", "title": "Architectural Patterns for Spring Security You Wish Your Tech Lead Knew @ Spring I/O 2026", "channel_name": "Spring I/O", "date_published": "2026-07-10", "duration_seconds": 2984, "yt_view_count": 5849},
    {"video_id": "KnLJ-vFsjwE", "title": "Inside Spring Boot 4: Restructuring for the Future by Moritz Halbritter @ Spring I/O 2026", "channel_name": "Spring I/O", "date_published": "2026-06-09", "duration_seconds": 2751, "yt_view_count": 8811},
    {"video_id": "BvkGbpKb_BY", "title": "Code Once, Use Everywhere: Building a Shared Module used by Multiple Projects @ Spring I/O 2026", "channel_name": "Spring I/O", "date_published": "2026-07-11", "duration_seconds": 2707, "yt_view_count": 6375},
    {"video_id": "2GHM153fs8g", "title": "Bootiful gRPC by Josh Long & Dave Syer @ Spring I/O 2026", "channel_name": "Spring I/O", "date_published": "2026-06-18", "duration_seconds": 2028, "yt_view_count": 4707},
    {"video_id": "f5ehQCijgdw", "title": "The Joy of Queries by Mark Paluch @ Spring I/O 2026", "channel_name": "Spring I/O", "date_published": "2026-06-10", "duration_seconds": 2331, "yt_view_count": 1704},
    {"video_id": "g1GFJxVeH9c", "title": "Pastry Chef Attempts to Make Gourmet Instant Ramen | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2018-11-29", "duration_seconds": 1532, "yt_view_count": 12341661},
    {"video_id": "mvDj7DF1jsk", "title": "Pastry Chef Attempts to Make Gourmet M&M's | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2019-09-11", "duration_seconds": 2411, "yt_view_count": 6638849},
    {"video_id": "Xi28pEbMdTw", "title": "Pastry Chef Attempts to Make Gourmet Tater Tots | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2020-05-05", "duration_seconds": 2304, "yt_view_count": 6096692},
    {"video_id": "FyMWRcVTGAI", "title": "Pastry Chef Attempts to Make Gourmet Ben & Jerry's Ice Cream | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2020-01-27", "duration_seconds": 1780, "yt_view_count": 7070664},
    {"video_id": "O1JDBt6WE7A", "title": "6 Pro Chefs Make Their Favorite 15-Minute Meal | Test Kitchen Talks | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2022-10-31", "duration_seconds": 1132, "yt_view_count": 3471143},
    {"video_id": "lF2sKFnuALw", "title": "Pro Chefs Make Their Favorite Sandwiches | Test Kitchen Talks | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2019-12-30", "duration_seconds": 1357, "yt_view_count": 7233139},
    {"video_id": "KUHp3ve4m50", "title": "Brad Makes Fermented Citrus Fruits | It's Alive | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2019-08-22", "duration_seconds": 1468, "yt_view_count": 4015353},
    {"video_id": "YGpK6U56oHM", "title": "Brad Makes Beef Jerky | It's Alive | Bon Appétit", "channel_name": "Bon Appétit", "date_published": "2018-09-06", "duration_seconds": 1093, "yt_view_count": 7381390},
    {"video_id": "_QCt3UBTS1Y", "title": "JustinGuitar Beginner Course Grade 1 Introduction", "channel_name": "JustinGuitar", "date_published": "2020-05-11", "duration_seconds": 75, "yt_view_count": 1396839},
    {"video_id": "BI3S9xSK8Iw", "title": "How to Pass JustinGuitar Beginners Course Grade 1", "channel_name": "JustinGuitar", "date_published": "2020-05-28", "duration_seconds": 483, "yt_view_count": 185267},
    {"video_id": "zfBkJggF9aU", "title": "Welcome to Module 2: Rhythm & Chord Change Essentials + Your First Riff!", "channel_name": "JustinGuitar", "date_published": "2020-05-11", "duration_seconds": 169, "yt_view_count": 333147},
    {"video_id": "G-X1RemAzks", "title": "Minor Pentatonic Scale - Stage 7 Guitar Lesson - Guitar For Beginners [BC-176]", "channel_name": "JustinGuitar", "date_published": "2009-08-25", "duration_seconds": 327, "yt_view_count": 781016},
    {"video_id": "eaUbs13xBl0", "title": "How to Change Acoustic Guitar Strings (Step-by-Step Guide)", "channel_name": "JustinGuitar", "date_published": "2025-06-17", "duration_seconds": 1515, "yt_view_count": 203261},
    {"video_id": "ihlDFZjNM6g", "title": "No Tuner? Learn How to Tune Your Guitar by Ear (using Harmonics!)", "channel_name": "JustinGuitar", "date_published": "2025-06-13", "duration_seconds": 355, "yt_view_count": 60135},
    {"video_id": "XiOJRhikCBg", "title": "How often should you REALLY change your guitar strings?", "channel_name": "JustinGuitar", "date_published": "2025-06-05", "duration_seconds": 515, "yt_view_count": 52000},
    {"video_id": "y5D3jMuCipk", "title": "How to change strings on electric guitars (PRS/locking tuners/strat-style)", "channel_name": "JustinGuitar", "date_published": "2025-06-10", "duration_seconds": 1274, "yt_view_count": 30190},
    {"video_id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)", "channel_name": "Rick Astley", "date_published": "2009-10-25", "duration_seconds": 213, "yt_view_count": 1805594426},
    {"video_id": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE(강남스타일) M/V", "channel_name": "officialpsy", "date_published": "2012-07-15", "duration_seconds": 252, "yt_view_count": 6032168341},
    {"video_id": "jofNR_WkoCE", "title": "Ylvis - The Fox (What Does The Fox Say?) [Official music video HD]", "channel_name": "TV Norge", "date_published": "2013-09-03", "duration_seconds": 225, "yt_view_count": 1206159962},
    {"video_id": "h6fcK_fRYaI", "title": "The Egg - A Short Story", "channel_name": "Kurzgesagt – In a Nutshell", "date_published": "2019-09-01", "duration_seconds": 486, "yt_view_count": 36078996},
    {"video_id": "sNhhvQGsMEc", "title": "The Fermi Paradox — Where Are All The Aliens? (1/2)", "channel_name": "Kurzgesagt – In a Nutshell", "date_published": "2015-05-06", "duration_seconds": 380, "yt_view_count": 35291620},
    {"video_id": "1fQkVqno-uI", "title": "The Fermi Paradox II — Solutions and Ideas – Where Are All The Aliens?", "channel_name": "Kurzgesagt – In a Nutshell", "date_published": "2015-06-04", "duration_seconds": 377, "yt_view_count": 17192728},
    {"video_id": "iG9CE55wbtY", "title": "Do schools kill creativity? | Sir Ken Robinson | TED", "channel_name": "TED", "date_published": "2007-01-07", "duration_seconds": 1203, "yt_view_count": 24913231},
    {"video_id": "4czjS9h4Fpg", "title": "Perseverance Rover's Descent and Touchdown on Mars (Official NASA Video)", "channel_name": "NASA", "date_published": "2021-02-22", "duration_seconds": 205, "yt_view_count": 17916318},
    {"video_id": "wE-aQO9XD1g", "title": "NASA's Perseverance Rover's First 360 View of Mars (Official)", "channel_name": "NASA Jet Propulsion Laboratory", "date_published": "2021-02-22", "duration_seconds": 60, "yt_view_count": 7147132},
    {"video_id": "FlpstXNjImY", "title": "Historic Apollo 11 Moon Landing Footage", "channel_name": "NASA", "date_published": "2019-07-20", "duration_seconds": 1746, "yt_view_count": 2586458},
    {"video_id": "l24FBVeu3Z4", "title": "Great White Sharks | National Geographic", "channel_name": "National Geographic", "date_published": "2012-08-13", "duration_seconds": 149, "yt_view_count": 78436},
    {"video_id": "JvzoijD2YaY", "title": "A woodworker's guide to installing keyhole hangers. They aren't hard.", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2026-04-23", "duration_seconds": 317, "yt_view_count": 29585},
    {"video_id": "QLSYADN_BzM", "title": "2026 BEGINNERS' GUIDE to the TOOLS and SUPPLIES you need to start a woodworking hobby", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2026-04-15", "duration_seconds": 921, "yt_view_count": 28953},
    {"video_id": "F5oV9FoAKHM", "title": "Finding simplicity in woodworking. And life.", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2026-02-20", "duration_seconds": 818, "yt_view_count": 25153},
    {"video_id": "3lzPv_iHEyQ", "title": "6 Simple Ways to Reset Your Workshop and Enjoy It Even More", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2026-01-02", "duration_seconds": 495, "yt_view_count": 58447},
    {"video_id": "V7u78RQxjPg", "title": "The myth of \"fine woodworking\" and joinery", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2025-07-23", "duration_seconds": 949, "yt_view_count": 96886},
    {"video_id": "SIzDi6pSD4U", "title": "They Say Not to Do This… But It Works. (Finishing technique.)", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2025-04-16", "duration_seconds": 460, "yt_view_count": 155325},
    {"video_id": "JgLVfwRltZY", "title": "Simple, sturdy picture frame with splined corner miters", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2025-01-11", "duration_seconds": 776, "yt_view_count": 78157},
    {"video_id": "C28ghmZVvd0", "title": "Modifying my standing workstation", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2024-11-12", "duration_seconds": 462, "yt_view_count": 61849},
    {"video_id": "IcQxYrNNDcg", "title": "Simple garden hose storage container. LIMITED TOOLS NEEDED!", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "date_published": "2024-06-18", "duration_seconds": 643, "yt_view_count": 89404},
]

# Tag groups -> canonical tag names.
TAG_GROUPS: dict[str, list[str]] = {
    "Coding & Tech": ["keynote", "spring-ai", "spring-security", "spring-boot"],
    "Cooking": ["baking", "home-cooking", "chef-technique"],
    "Guitar & Music": ["beginner-guitar", "guitar-technique", "music-video"],
}

# Canonical tags that exist but aren't in any group yet (realistic incremental tagging).
UNGROUPED_CANONICAL_TAGS = ["science-explainer", "nature-documentary"]

# canonical tag name -> video_ids it applies to.
CANONICAL_TAG_VIDEOS: dict[str, list[str]] = {
    "keynote": ["pYDMhBVspIY"],
    "spring-ai": ["nHnKReitDXc"],
    "spring-security": ["zO-bktrLju8", "QXQiGS9CL20"],
    "spring-boot": ["KnLJ-vFsjwE", "BvkGbpKb_BY", "2GHM153fs8g"],
    "baking": ["g1GFJxVeH9c", "mvDj7DF1jsk", "Xi28pEbMdTw", "FyMWRcVTGAI"],
    "home-cooking": ["O1JDBt6WE7A", "lF2sKFnuALw"],
    "chef-technique": ["KUHp3ve4m50", "YGpK6U56oHM"],
    "beginner-guitar": ["_QCt3UBTS1Y", "BI3S9xSK8Iw", "zfBkJggF9aU", "G-X1RemAzks"],
    "guitar-technique": ["eaUbs13xBl0", "ihlDFZjNM6g", "y5D3jMuCipk"],
    "music-video": ["dQw4w9WgXcQ", "9bZkp7q19f0", "jofNR_WkoCE"],
    "science-explainer": ["h6fcK_fRYaI", "sNhhvQGsMEc", "1fQkVqno-uI", "iG9CE55wbtY"],
    "nature-documentary": ["l24FBVeu3Z4"],
}

# Non-canonical tag name -> video_ids it applies to. These sit in the "unclassified" pool
# on the /tags page (real tags, never promoted to canonical) — gives the tagging UI
# something to do, and mirrors how a real library accumulates raw, uncategorized tags.
# Every tag here needs >= 2 videos: get_unclassified_tags() defaults to min_videos=2, so a
# 1-video tag never actually surfaces in the pool it's meant to demonstrate. "queries" and
# "guitar-maintenance" each pick up a second video (a video that already has a canonical
# tag elsewhere) purely to clear that threshold.
UNCLASSIFIED_TAG_VIDEOS: dict[str, list[str]] = {
    "queries": ["f5ehQCijgdw", "KnLJ-vFsjwE"],
    "guitar-maintenance": ["XiOJRhikCBg", "y5D3jMuCipk"],
    "space": ["4czjS9h4Fpg", "wE-aQO9XD1g", "FlpstXNjImY"],
    "woodworking": ["JvzoijD2YaY", "QLSYADN_BzM", "F5oV9FoAKHM", "V7u78RQxjPg", "JgLVfwRltZY"],
    "workshop": ["3lzPv_iHEyQ", "SIzDi6pSD4U", "C28ghmZVvd0", "IcQxYrNNDcg"],
}

FAVORITE_VIDEO_IDS = [
    "dQw4w9WgXcQ", "h6fcK_fRYaI", "pYDMhBVspIY", "V7u78RQxjPg", "l24FBVeu3Z4", "KUHp3ve4m50",
]

# Order matters: add_to_watch_later assigns position by call order.
# Mix of watched and unwatched entries on purpose — a queue where every card shows the
# same "already watched" checkmark looks repetitive for a demo. 4 of these overlap with
# WATCHED_VIDEO_IDS (queued-and-watched is a valid real state); 4 don't.
WATCH_LATER_VIDEO_IDS = [
    "pYDMhBVspIY", "KnLJ-vFsjwE", "_QCt3UBTS1Y", "h6fcK_fRYaI",
    "4czjS9h4Fpg", "zfBkJggF9aU", "mvDj7DF1jsk", "iG9CE55wbtY",
]

HIDDEN_VIDEO_IDS = ["QXQiGS9CL20", "YGpK6U56oHM", "XiOJRhikCBg"]

# Previously-watched videos, spread from 2 weeks to ~17 months ago so the Rediscover
# shelf has a real least-recently-viewed pool to draw from, not 1-2 eligible videos.
WATCHED_VIDEO_IDS = [
    "pYDMhBVspIY", "g1GFJxVeH9c", "_QCt3UBTS1Y", "h6fcK_fRYaI", "4czjS9h4Fpg",
    "JvzoijD2YaY", "nHnKReitDXc", "O1JDBt6WE7A", "dQw4w9WgXcQ", "9bZkp7q19f0",
    "V7u78RQxjPg", "l24FBVeu3Z4", "KUHp3ve4m50", "eaUbs13xBl0", "sNhhvQGsMEc",
    "3lzPv_iHEyQ",
]


def bootstrap_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_CRAWLER_SCHEMA)  # base tables: videos, tags, video_tags, channels
    conn.close()
    init_webapp_tables(db_path)  # webapp extension tables + column migrations


def _channel_metadata(name: str) -> ChannelMetadata:
    channel_id, channel_url, thumbnail_url = CHANNELS[name]
    return ChannelMetadata(
        channel_id=channel_id, channel_name=name, channel_url=channel_url,
        description=None, subscriber_count=None, thumbnail_url=thumbnail_url,
        fetch_status=FetchStatus.OK,
    )


def seed_content(conn: sqlite3.Connection, videos: list[dict]) -> None:
    for name in {v["channel_name"] for v in videos}:
        upsert_channel(conn, _channel_metadata(name))

    for i, v in enumerate(videos):
        add_video(
            conn,
            video_id=v["video_id"],
            url=f"https://www.youtube.com/watch?v={v['video_id']}",
            title=v["title"],
            channel_name=v["channel_name"],
            channel_id=CHANNELS[v["channel_name"]][0],
            yt_view_count=v["yt_view_count"],
            duration_seconds=v["duration_seconds"],
            thumbnail_url=f"https://i.ytimg.com/vi/{v['video_id']}/hqdefault.jpg",
            date_published=v["date_published"],
        )
        # add_video always stamps date_added=now(); backdate it here so the library
        # looks like it grew over time rather than everything arriving in one instant.
        # No public setter exists for an arbitrary date_added — see Global Constraints.
        # Leading offset is small (2 days) so the newest video or two land inside the
        # app's own "added in the last 7 days" filter — a fresh demo shouldn't come up
        # empty for the exact feature meant to show the library looking alive.
        date_added = (ANCHOR - timedelta(days=2 + i * 14)).isoformat()
        conn.execute(
            "UPDATE videos SET date_added = ? WHERE video_id = ?",
            (date_added, v["video_id"]),
        )
    conn.commit()


def seed_tags(conn: sqlite3.Connection) -> None:
    for group_name, tag_names in TAG_GROUPS.items():
        group_id = create_tag_group(conn, group_name)
        for tag_name in tag_names:
            tag_id = create_canonical_tag(conn, tag_name)
            add_canonical_to_group(conn, group_id, tag_id)
            for video_id in CANONICAL_TAG_VIDEOS[tag_name]:
                add_video_tag(conn, video_id, tag_id)

    for tag_name in UNGROUPED_CANONICAL_TAGS:
        tag_id = create_canonical_tag(conn, tag_name)
        for video_id in CANONICAL_TAG_VIDEOS[tag_name]:
            add_video_tag(conn, video_id, tag_id)

    for tag_name, video_ids in UNCLASSIFIED_TAG_VIDEOS.items():
        tag_id = create_tag(conn, tag_name)
        for video_id in video_ids:
            add_video_tag(conn, video_id, tag_id)


def seed_engagement(conn: sqlite3.Connection) -> None:
    for video_id in FAVORITE_VIDEO_IDS:
        set_favorite(conn, video_id, True)

    for video_id in WATCH_LATER_VIDEO_IDS:
        add_to_watch_later(conn, video_id)

    for video_id in HIDDEN_VIDEO_IDS:
        hide_video(conn, video_id)

    for j, video_id in enumerate(WATCHED_VIDEO_IDS):
        set_watched(conn, video_id, True)
        view_count = 1 + (j % 4)
        # date_last_viewed must never predate the video's own date_added — you can't view
        # something before you bookmarked it. Derive it from that video's actual
        # date_added (not from ANCHOR directly, which is indexed independently by
        # seed_content) plus a small positive spread, capped at "now" so it never lands
        # in the future.
        row = conn.execute(
            "SELECT date_added FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        video_date_added = datetime.fromisoformat(row[0])
        date_last_viewed = min(
            video_date_added + timedelta(days=1 + (j % 6)), ANCHOR
        ).isoformat()
        # No public setter for an arbitrary personal_view_count/date_last_viewed —
        # see Global Constraints at the top of this plan.
        conn.execute(
            "UPDATE videos SET personal_view_count = ?, date_last_viewed = ? "
            "WHERE video_id = ?",
            (view_count, date_last_viewed, video_id),
        )
    conn.commit()


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed an Airchivist demo database.")
    parser.add_argument("--output", required=True, help="Path to write the demo database")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing file")
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(
            f"Error: {output_path} already exists. Pass --force to regenerate it.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Seed to a temporary path first and only move it to the real --output path on full
    # success. If bootstrap_schema/seed_content/seed_tags/seed_engagement run partway and
    # then crash, the half-seeded file is left at <output>.tmp, never at the real path —
    # so demo.sh's `[ ! -f demo.db ]` check still triggers a full re-seed next run instead
    # of picking up a broken database forever.
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    bootstrap_schema(str(tmp_path))
    conn = sqlite3.connect(str(tmp_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    seed_content(conn, VIDEOS)
    seed_tags(conn)
    seed_engagement(conn)
    conn.close()

    tmp_path.replace(output_path)  # atomic on the same filesystem
    print(f"Seeded {output_path} with {len(VIDEOS)} videos.")


if __name__ == "__main__":
    run()
