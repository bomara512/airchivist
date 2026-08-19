#!/usr/bin/env python3
"""Seed a fresh SQLite file with real public YouTube content and fabricated
personal-engagement data, for a one-command "try it now" ViewTube demo.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler.datastore import _SCHEMA as _CRAWLER_SCHEMA
from crawler.models import ChannelMetadata, FetchStatus
from webapp.db import add_video, init_webapp_tables, upsert_channel

ANCHOR = datetime(2026, 8, 19, tzinfo=timezone.utc)

# channel_name -> (channel_id, channel_url). Real, verified via `yt-dlp` on 2026-08-19.
CHANNELS: dict[str, tuple[str, str]] = {
    "freeCodeCamp.org": ("UC8butISFwT-Wl7EV0hUK0BQ", "https://www.youtube.com/@freecodecamp"),
    "Bon Appétit": ("UCbpMy0Fg74eXXkvxJrtEn3w", "https://www.youtube.com/@bonappetit"),
    "JustinGuitar": ("UCBNkm8o5LiEVLxO8w0p2sfQ", "https://www.youtube.com/@justinguitar"),
    "Rick Astley": ("UCuAXFkgsw1L7xaCfnd5JJOw", "https://www.youtube.com/@RickAstleyYT"),
    "officialpsy": ("UCrDkAvwZum-UTjHmzDI2iIw", "https://www.youtube.com/@officialpsy"),
    "TV Norge": ("UCYM3pKj9tFQOXc2XcJmj8Vg", "https://www.youtube.com/@tvnorge"),
    "Kurzgesagt – In a Nutshell": ("UCsXVk37bltHxD1rDPwtNM8Q", "https://www.youtube.com/@kurzgesagt"),
    "TED": ("UCAuUUnT6oDeKwE6v1NGQxug", "https://www.youtube.com/@TED"),
    "NASA": ("UCLA_DiR1FfKNvjuUpBHmylQ", "https://www.youtube.com/@NASA"),
    "NASA Jet Propulsion Laboratory": ("UCryGec9PdUCLjpJW2mgCuLw", "https://www.youtube.com/@NASAJPL"),
    "National Geographic": ("UCpVm7bg6pXKo1Pr6k5kxG9A", "https://www.youtube.com/@NatGeo"),
    "Steve Ramsey - Woodworking for Mere Mortals": ("UCBB7sYb14uBtk8UqSQYc9-w", "https://www.youtube.com/@SteveRamsey"),
}

# 44 real videos. Real, verified via `yt-dlp` on 2026-08-19 — see
# docs/superpowers/specs/2026-08-19-demo-seed-data-design.md for the source table.
VIDEOS: list[dict] = [
    {"video_id": "rfscVS0vtbw", "title": "Learn Python - Full Course for Beginners [Tutorial]", "channel_name": "freeCodeCamp.org", "duration_seconds": 16012, "yt_view_count": 49122814},
    {"video_id": "HXV3zeQKqGY", "title": "SQL Tutorial - Full Database Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 15639, "yt_view_count": 20888367},
    {"video_id": "i_LwzRVP7bg", "title": "Machine Learning for Everybody – Full Course", "channel_name": "freeCodeCamp.org", "duration_seconds": 14033, "yt_view_count": 10291171},
    {"video_id": "bMknfKXIFA8", "title": "React Course - Beginner's Tutorial for React JavaScript Library [2022]", "channel_name": "freeCodeCamp.org", "duration_seconds": 42927, "yt_view_count": 4266110},
    {"video_id": "916GWv2Qs08", "title": "HTML Tutorial - Website Crash Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 2719, "yt_view_count": 664733},
    {"video_id": "n8mNX2YqkUs", "title": "Learn JavaScript Interactively in NEW freeCodeCamp.org Curriculum", "channel_name": "freeCodeCamp.org", "duration_seconds": 3206, "yt_view_count": 100453},
    {"video_id": "a_iQb1lnAEQ", "title": "Learn HTML & CSS – Full Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 19304, "yt_view_count": 932945},
    {"video_id": "OXGznpKZ_sA", "title": "CSS Tutorial – Full Course for Beginners", "channel_name": "freeCodeCamp.org", "duration_seconds": 40090, "yt_view_count": 2945708},
    {"video_id": "g1GFJxVeH9c", "title": "Pastry Chef Attempts to Make Gourmet Instant Ramen | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1532, "yt_view_count": 12341661},
    {"video_id": "mvDj7DF1jsk", "title": "Pastry Chef Attempts to Make Gourmet M&M's | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 2411, "yt_view_count": 6638849},
    {"video_id": "Xi28pEbMdTw", "title": "Pastry Chef Attempts to Make Gourmet Tater Tots | Gourmet Makes | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 2304, "yt_view_count": 6096692},
    {"video_id": "FyMWRcVTGAI", "title": "Pastry Chef Attempts to Make Gourmet Ben & Jerry's Ice Cream | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1780, "yt_view_count": 7070664},
    {"video_id": "O1JDBt6WE7A", "title": "6 Pro Chefs Make Their Favorite 15-Minute Meal | Test Kitchen Talks | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1132, "yt_view_count": 3471143},
    {"video_id": "lF2sKFnuALw", "title": "Pro Chefs Make Their Favorite Sandwiches | Test Kitchen Talks | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1357, "yt_view_count": 7233139},
    {"video_id": "KUHp3ve4m50", "title": "Brad Makes Fermented Citrus Fruits | It's Alive | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1468, "yt_view_count": 4015353},
    {"video_id": "YGpK6U56oHM", "title": "Brad Makes Beef Jerky | It's Alive | Bon Appétit", "channel_name": "Bon Appétit", "duration_seconds": 1093, "yt_view_count": 7381390},
    {"video_id": "_QCt3UBTS1Y", "title": "JustinGuitar Beginner Course Grade 1 Introduction", "channel_name": "JustinGuitar", "duration_seconds": 75, "yt_view_count": 1396839},
    {"video_id": "BI3S9xSK8Iw", "title": "How to Pass JustinGuitar Beginners Course Grade 1", "channel_name": "JustinGuitar", "duration_seconds": 483, "yt_view_count": 185267},
    {"video_id": "zfBkJggF9aU", "title": "Welcome to Module 2: Rhythm & Chord Change Essentials + Your First Riff!", "channel_name": "JustinGuitar", "duration_seconds": 169, "yt_view_count": 333147},
    {"video_id": "G-X1RemAzks", "title": "Minor Pentatonic Scale - Stage 7 Guitar Lesson - Guitar For Beginners [BC-176]", "channel_name": "JustinGuitar", "duration_seconds": 327, "yt_view_count": 781016},
    {"video_id": "eaUbs13xBl0", "title": "How to Change Acoustic Guitar Strings (Step-by-Step Guide)", "channel_name": "JustinGuitar", "duration_seconds": 1515, "yt_view_count": 203261},
    {"video_id": "ihlDFZjNM6g", "title": "No Tuner? Learn How to Tune Your Guitar by Ear (using Harmonics!)", "channel_name": "JustinGuitar", "duration_seconds": 355, "yt_view_count": 60135},
    {"video_id": "XiOJRhikCBg", "title": "How often should you REALLY change your guitar strings?", "channel_name": "JustinGuitar", "duration_seconds": 515, "yt_view_count": 52000},
    {"video_id": "y5D3jMuCipk", "title": "How to change strings on electric guitars (PRS/locking tuners/strat-style)", "channel_name": "JustinGuitar", "duration_seconds": 1274, "yt_view_count": 30190},
    {"video_id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)", "channel_name": "Rick Astley", "duration_seconds": 213, "yt_view_count": 1805594426},
    {"video_id": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE(강남스타일) M/V", "channel_name": "officialpsy", "duration_seconds": 252, "yt_view_count": 6032168341},
    {"video_id": "jofNR_WkoCE", "title": "Ylvis - The Fox (What Does The Fox Say?) [Official music video HD]", "channel_name": "TV Norge", "duration_seconds": 225, "yt_view_count": 1206159962},
    {"video_id": "h6fcK_fRYaI", "title": "The Egg - A Short Story", "channel_name": "Kurzgesagt – In a Nutshell", "duration_seconds": 486, "yt_view_count": 36078996},
    {"video_id": "sNhhvQGsMEc", "title": "The Fermi Paradox — Where Are All The Aliens? (1/2)", "channel_name": "Kurzgesagt – In a Nutshell", "duration_seconds": 380, "yt_view_count": 35291620},
    {"video_id": "1fQkVqno-uI", "title": "The Fermi Paradox II — Solutions and Ideas – Where Are All The Aliens?", "channel_name": "Kurzgesagt – In a Nutshell", "duration_seconds": 377, "yt_view_count": 17192728},
    {"video_id": "iG9CE55wbtY", "title": "Do schools kill creativity? | Sir Ken Robinson | TED", "channel_name": "TED", "duration_seconds": 1203, "yt_view_count": 24913231},
    {"video_id": "4czjS9h4Fpg", "title": "Perseverance Rover's Descent and Touchdown on Mars (Official NASA Video)", "channel_name": "NASA", "duration_seconds": 205, "yt_view_count": 17916318},
    {"video_id": "wE-aQO9XD1g", "title": "NASA's Perseverance Rover's First 360 View of Mars (Official)", "channel_name": "NASA Jet Propulsion Laboratory", "duration_seconds": 60, "yt_view_count": 7147132},
    {"video_id": "FlpstXNjImY", "title": "Historic Apollo 11 Moon Landing Footage", "channel_name": "NASA", "duration_seconds": 1746, "yt_view_count": 2586458},
    {"video_id": "l24FBVeu3Z4", "title": "Great White Sharks | National Geographic", "channel_name": "National Geographic", "duration_seconds": 149, "yt_view_count": 78436},
    {"video_id": "JvzoijD2YaY", "title": "A woodworker's guide to installing keyhole hangers. They aren't hard.", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 317, "yt_view_count": 29585},
    {"video_id": "QLSYADN_BzM", "title": "2026 BEGINNERS' GUIDE to the TOOLS and SUPPLIES you need to start a woodworking hobby", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 921, "yt_view_count": 28953},
    {"video_id": "F5oV9FoAKHM", "title": "Finding simplicity in woodworking. And life.", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 818, "yt_view_count": 25153},
    {"video_id": "3lzPv_iHEyQ", "title": "6 Simple Ways to Reset Your Workshop and Enjoy It Even More", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 495, "yt_view_count": 58447},
    {"video_id": "V7u78RQxjPg", "title": "The myth of \"fine woodworking\" and joinery", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 949, "yt_view_count": 96886},
    {"video_id": "SIzDi6pSD4U", "title": "They Say Not to Do This… But It Works. (Finishing technique.)", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 460, "yt_view_count": 155325},
    {"video_id": "JgLVfwRltZY", "title": "Simple, sturdy picture frame with splined corner miters", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 776, "yt_view_count": 78157},
    {"video_id": "C28ghmZVvd0", "title": "Modifying my standing workstation", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 462, "yt_view_count": 61849},
    {"video_id": "IcQxYrNNDcg", "title": "Simple garden hose storage container. LIMITED TOOLS NEEDED!", "channel_name": "Steve Ramsey - Woodworking for Mere Mortals", "duration_seconds": 643, "yt_view_count": 89404},
]


def bootstrap_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_CRAWLER_SCHEMA)  # base tables: videos, tags, video_tags, channels
    conn.close()
    init_webapp_tables(db_path)  # webapp extension tables + column migrations


def _channel_metadata(name: str) -> ChannelMetadata:
    channel_id, channel_url = CHANNELS[name]
    # No avatar image: thumbnail_url stays None so the UI falls back to the existing
    # .no-thumb placeholder, sidestepping the yt3.googleusercontent.com rate-limit risk.
    return ChannelMetadata(
        channel_id=channel_id, channel_name=name, channel_url=channel_url,
        description=None, subscriber_count=None, thumbnail_url=None,
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
        )
        # add_video always stamps date_added=now(); backdate it here so the library
        # looks like it grew over time rather than everything arriving in one instant.
        # No public setter exists for an arbitrary date_added — see Global Constraints.
        date_added = (ANCHOR - timedelta(days=10 + i * 14)).isoformat()
        conn.execute(
            "UPDATE videos SET date_added = ? WHERE video_id = ?",
            (date_added, v["video_id"]),
        )
    conn.commit()


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed a ViewTube demo database.")
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
    if output_path.exists():
        output_path.unlink()

    bootstrap_schema(str(output_path))
    conn = sqlite3.connect(str(output_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    seed_content(conn, VIDEOS)
    conn.close()
    print(f"Seeded {output_path} with {len(VIDEOS)} videos.")


if __name__ == "__main__":
    run()
