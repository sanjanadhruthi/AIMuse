"""
AIMuse — hand-picked sample songs, played from YouTube
======================================================

The "Sample songs, by mood" tabs used to play MP3 files from
static/Moods/.  Those are copyrighted, so they can't go on the public
website.  Now the same hand-picked songs are played from YouTube:

  1. CURATED_SAMPLES below lists the songs for each mood.
  2. `flask --app app warm-samples` finds each song on YouTube ONCE
     (one search per song, 100 quota units each) and saves the best
     few uploads to data/sample_videos.json.  Commit that file.
  3. /api/samples serves them from that file — no quota at all.

Add a song: add a line below, run warm-samples again — only the new
songs are searched.  If the daily quota runs out half-way, just run
it again the next day; finished songs are kept.

Each entry: (title, artist, extra search words[, match title]).  The
title and artist here are what the UI shows; the search words only
help YouTube find the right upload.  The optional 4th value is the
name the uploads actually use, when it differs from the display
title (e.g. the Chinese title of a Chinese song).
"""

import json
import os
import threading
import time

from src import youtube_recommender as yt


CURATED_SAMPLES = {

    "happy": [
        ("Together With The Wind", "Toma君想吃番茄", ""),
        ("Sapphire", "Ed Sheeran", ""),
        ("Permission to Dance", "BTS", ""),
        ("Love You Zindagi", "Dear Zindagi", "song"),
        ("Dreamers", "Jung Kook", ""),
    ],

    "sad": [
        ("Bulleya", "Ae Dil Hai Mushkil", "song"),
        ("Dooron Dooron", "Paresh Pahuja", ""),
        ("Husn", "Anuv Jain", ""),
        ("Why Don't You Stay", "Jeff Satur", ""),
        ("Love Is Gone", "SLANDER", ""),
    ],

    "calm": [
        ("Dandelions", "Ruth B.", ""),
        ("Somewhere Only We Know", "Keane", ""),
        ("Kasturi", "Amar Prem Ki Prem Kahani", "song"),
        ("Fade", "Jeff Satur", ""),
        ("Chemtrails Over The Country Club", "Lana Del Rey", ""),
    ],

    "angry": [
        ("Believer", "Imagine Dragons", ""),
        ("Labour", "Paris Paloma", ""),
        ("Story of a Warrior", "", "song"),
        ("That's My Girl", "Fifth Harmony", ""),
        ("Usnisa Vijaya Dharani", "", "mantra"),
    ],

    "romantic": [
        ("blue", "yung kai", ""),
        ("Would You Like That", "金銀玲", ""),
        ("Enchanted", "Taylor Swift", ""),
        ("Those Eyes", "New West", ""),
        ("Mantra", "Keng Harit", "Khemjira OST"),
    ],

    "energetic": [
        ("Super", "SEVENTEEN", ""),
        ("Breakin' Dishes", "Rihanna", ""),
        ("Beggin'", "Måneskin", ""),
        ("Like JENNIE", "JENNIE", ""),
        ("JUMP", "BLACKPINK", ""),
    ],

    "neutral": [
        ("Blossom All the Way (一路生花)", "温奕心", "", "一路生花"),
        ("Duel in the Mist", "Genshin Impact", "Inazuma battle theme"),
        ("Kiliye (Instrumental)", "Dhibu Ninan Thomas", ""),
        ("Warm Twilight", "Velvet Memories", ""),
        ("Road to Success", "Lin Wanxing Theme", ""),
    ],

}


UPLOADS_PER_SONG = 4

RETRIES = 3
RETRY_WAIT_SECONDS = 3

# YouTube answers 429 ("slow down") to bursts of searches, so warm()
# paces itself and, when told to slow down, waits a full minute.
PAUSE_BETWEEN_SONGS = 2
RATE_LIMIT_WAIT_SECONDS = 60

_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sample_videos.json"
)

_LOCK = threading.Lock()


def _key(title, artist):

    return f"{title}|{artist}".lower()


def _load():

    try:
        with open(_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):

    os.makedirs(os.path.dirname(_FILE), exist_ok=True)

    tmp = _FILE + ".tmp"

    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)

    os.replace(tmp, _FILE)


def _entry(entry):
    """(title, artist, extra, match) — the 4th value is optional."""

    title, artist, extra, *rest = entry

    return title, artist, extra, (rest[0] if rest else title)


def _find_uploads(title, artist, extra, match=None):
    """
    One YouTube search (100 units) -> the best few uploads of this
    exact song, already checked for playability.  None = network
    trouble (try again later).  Raises yt._QuotaExceeded.
    """

    query = " ".join(part for part in (artist, title, extra) if part)

    found = yt._alternatives_from_query(
        query,
        True,
        "",
        title,
        artist,
        f"{title} {artist} {extra}".lower(),
        yt._norm(match or title),
    )

    if found is None:
        return None

    ranked = sorted(found.values(), key=lambda v: v["_score"], reverse=True)

    uploads = []

    for video in ranked[:UPLOADS_PER_SONG]:
        uploads.append({
            "videoId": video["videoId"],
            "channel": video["channel"],
            "duration_seconds": video["duration_seconds"],
            "thumbnail": video["thumbnail"],
        })

    return uploads


def warm(print_line=print):
    """
    Finds every curated song that isn't saved yet.  Safe to run again:
    finished songs are skipped, and it stops cleanly if the quota runs
    out (run it again tomorrow to finish).
    """

    if not yt.YOUTUBE_API_KEY:
        print_line("No YOUTUBE_API_KEY set — nothing to do.")
        return

    with _LOCK:
        saved = _load()

    for mood, songs in CURATED_SAMPLES.items():

        for entry in songs:

            title, artist, extra, match = _entry(entry)

            key = _key(title, artist)

            if saved.get(key):
                print_line(f"{mood:10} {title[:34]:36} already saved")
                continue

            uploads = None

            # Slow or flaky connections: try up to 3 times, waiting a
            # little longer each time.
            for attempt in range(RETRIES):

                try:
                    uploads = _find_uploads(title, artist, extra, match)

                except yt._RateLimited:

                    if attempt == RETRIES - 1:
                        print_line("YouTube keeps saying 'too many searches'. "
                                   "Stopping — run this again later (or tomorrow "
                                   "after 12:30 PM IST). Saved songs are kept.")
                        return

                    print_line(f"{mood:10} {title[:34]:36} YouTube says slow down — "
                               f"waiting {RATE_LIMIT_WAIT_SECONDS} s…")
                    time.sleep(RATE_LIMIT_WAIT_SECONDS)
                    continue

                except yt._QuotaExceeded:
                    print_line("Daily YouTube quota reached — run this again "
                               "tomorrow to finish the rest.")
                    return

                if uploads is not None:
                    break

                status = yt.LAST_ERROR.get("status")

                # 400 / 401 / 403 won't fix themselves by retrying:
                # it's the key or the project settings.
                if status in (400, 401, 403):
                    print_line(f"{mood:10} {title[:34]:36} failed — "
                               f"{yt.LAST_ERROR['text']}")
                    print_line("This is a key / project problem, not the network. "
                               "Stopping so no quota is wasted.")
                    return

                time.sleep(RETRY_WAIT_SECONDS * (attempt + 1))

            if uploads is None:
                print_line(f"{mood:10} {title[:34]:36} failed after {RETRIES} "
                           f"tries — {yt.LAST_ERROR['text']}")
                continue

            if not uploads:
                # nothing matched: not saved, so the next run tries again
                print_line(f"{mood:10} {title[:34]:36} no matching upload found — "
                           f"check the title / artist in CURATED_SAMPLES")
                continue

            saved[key] = uploads

            with _LOCK:
                _save(saved)

            print_line(f"{mood:10} {title[:34]:36} {len(uploads)} uploads")

            time.sleep(PAUSE_BETWEEN_SONGS)


def youtube_playlists():
    """
    {mood: [song, ...]} from data/sample_videos.json.  Each song's
    first working upload is the one played; the others travel along
    as `alternates` so the browser can switch instantly if YouTube
    refuses one.  Songs whose every upload failed are left out.
    """

    saved = _load()

    playlists = {mood: [] for mood in CURATED_SAMPLES}

    for mood, songs in CURATED_SAMPLES.items():

        for entry in songs:

            title, artist, _extra, _match = _entry(entry)

            uploads = [
                u for u in saved.get(_key(title, artist), [])
                if u.get("videoId") and u["videoId"] not in yt._BAD_IDS
            ]

            if not uploads:
                continue

            first, *rest = uploads

            playlists[mood].append({
                **first,
                "title": title,
                "artist": artist,
                "language": "",
                "sample": True,
                "alternates": [
                    {**u, "title": title, "artist": artist, "language": ""}
                    for u in rest
                ],
            })

    return playlists