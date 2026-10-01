"""
AIMuse — YouTube Recommendation Engine (v3)
============================================

v3 adds (on top of everything in v2 below)
------------------------------------------
A.  SELF-HEALING PLAYLISTS
    When a song still fails in the browser, find_replacement()
    searches for the SAME song (title + artist) uploaded somewhere
    else — official audio, lyric video, topic channel — verifies
    the new upload, and hands it back so the playlist swaps it in
    without the person noticing a gap.

B.  CLEAN SONG NAMES
    parse_song() turns messy YouTube titles into a proper
    "song" + "artist" pair:
      NiziU 『Make you happy』 M/V        -> Make you happy / NiziU
      BTS (방탄소년단) 'Dynamite' Official MV -> Dynamite / BTS
      Drake - One Dance (Lyrics) ft. Wizkid -> One Dance / Drake ft. Wizkid

C.  SMARTER RANKING
    Uses the secondary mood ("sad with a touch of calm"), boosts a
    requested artist, rewards native-script titles for the language
    that was asked for, rewards official / Topic uploads and a
    healthy like ratio, penalises remixes / sped-up edits, and
    keeps the playlist varied (one song per artist first).

Turns an *emotional profile* (not just a single mood word) into a
multi-lingual playlist of songs that will actually play in the
embedded player.

What changed from v1
--------------------
1.  PROFILE-DRIVEN QUERIES
    The search phrase is composed from everything AIMuse understood
    about the person: mood, energy (arousal), intensity, context
    ("nostalgic", "motivational"...), activity ("studying",
    "night drive"...), genre ("lofi", "acoustic"...), a requested
    language ("play some telugu songs") and even a named artist
    ("songs like Arijit Singh").  Uplift mode moves the energy
    gradually instead of jumping from "exhausted" straight to
    "hype".

2.  THREE-LAYER PLAYABILITY VERIFICATION
    Songs that fail in the embedded player ("Video unavailable",
    errors 101/150) were the #1 complaint.  A candidate must now
    survive:
      a. the search filters (embeddable + syndicated + music),
      b. videos.list checks (public, processed, embeddable, not
         age-restricted, not live, not region-blocked, sane length),
      c. a free oEmbed probe (no quota) — YouTube answers 401 for
         videos whose owner disabled embedding and 404 for removed /
         private ones.  This catches the cases (b) can't see.
    Anything the *browser* still fails to play is reported back via
    report_bad_video() and blacklisted permanently, so it never
    appears again.

3.  BETTER RANKING
    Relevance to the query, popularity (log-scaled), song-like
    title/duration, mood words in the title, plus near-duplicate
    removal (same song uploaded by several channels) and a per-
    channel cap so one uploader can't fill the playlist.

4.  RESILIENCE
    - Distinguishes "no API key", "quota exceeded", "network error"
      and "no results" so the UI can say what is actually wrong.
    - Serves a stale cached playlist if YouTube is unreachable.
    - Remembers quota exhaustion for a few minutes instead of
      hammering the API.
    - One language failing never takes the others down.

Setup
-----
  pip install -r requirements.txt
  (or put YOUTUBE_API_KEY=... in a .env file — see .env.example)
  set YOUTUBE_API_KEY=<your key>        (Windows cmd)
  $env:YOUTUBE_API_KEY="<your key>"      (PowerShell)
  export YOUTUBE_API_KEY=<your key>      (macOS / Linux)

  Optional:
    YOUTUBE_REGION   two-letter country code, default "IN".
                     Empty string switches region filtering off.

QUOTA NOTE
----------
Each language costs one search.list call (100 units) plus a couple
of 1-unit videos.list calls.  A fresh 7-language playlist is ~700
units of the default 10,000/day.  Requests for the same profile
inside an hour are free (cached).  When the person asks for one
language ("hindi songs"), only that language is searched — cheaper
and more relevant.
"""

import difflib
import html
import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

import requests

# Optional: read settings from a .env file next to the project (see
# .env.example).  Real environment variables always win, and the
# module works fine without python-dotenv installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
YOUTUBE_REGION = os.environ.get("YOUTUBE_REGION", "IN").strip().upper()

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
OEMBED_URL = "https://www.youtube.com/oembed"

HTTP_TIMEOUT = 7
OEMBED_TIMEOUT = 3

# One shared session: the TLS connection to Google is opened once and
# reused, instead of a fresh handshake (~200-500 ms) for every request.
_SESSION = requests.Session()
_SESSION.mount(
    "https://",
    requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16)
)

# "relevance" finds songs that fit the mood; popularity is added
# back in through the scoring below.  Switch to "viewCount" to
# return to a pure most-played ordering.
SEARCH_ORDER = "relevance"


# =========================================================
# 01. STATUS CODES (what the UI can be told)
# =========================================================

STATUS_OK = "ok"
STATUS_NO_KEY = "no_api_key"
STATUS_QUOTA = "quota_exceeded"
STATUS_NETWORK = "network_error"
STATUS_NO_RESULTS = "no_results"


class _QuotaExceeded(Exception):
    pass


# =========================================================
# 02. LANGUAGES
# =========================================================

DEFAULT_LANGUAGES = [
    "hindi", "telugu", "chinese", "korean",
    "japanese", "spanish", "english"
]

# Languages a person can *ask for* in their text.  Anything here
# can be searched even though it's not in the default mix.
LANGUAGE_QUERY_SUFFIX = {
    "hindi": "hindi",
    "telugu": "telugu",
    "tamil": "tamil",
    "malayalam": "malayalam",
    "kannada": "kannada",
    "punjabi": "punjabi",
    "chinese": "chinese mandarin",
    "korean": "korean",
    "japanese": "japanese",
    "spanish": "spanish",
    "english": "english",
    "french": "french",
    "portuguese": "portuguese",
    "arabic": "arabic",
    "thai": "thai"
}

LANGUAGE_CODES = {
    "hindi": "hi", "telugu": "te", "tamil": "ta", "malayalam": "ml",
    "kannada": "kn", "punjabi": "pa", "chinese": "zh", "korean": "ko",
    "japanese": "ja", "spanish": "es", "english": "en", "french": "fr",
    "portuguese": "pt", "arabic": "ar", "thai": "th"
}

# Candidates pulled per language BEFORE verification.  A search
# costs 100 units whether it returns 5 or 50 results, so pull a
# generous pool — some will be filtered out.  When only one or two
# languages are searched (the person asked for one), each needs to
# supply far more of the final playlist, so the pool is larger.
CANDIDATES_PER_LANGUAGE = 25
CANDIDATES_WHEN_FEW_LANGUAGES = 50

DEFAULT_LIMIT = 14
MAX_PER_CHANNEL = 2


# =========================================================
# 03. QUERY BUILDING
# =========================================================
#
# Phrase per mood, per energy level.  The energy level comes from
# the arousal AIMuse detected ("low" | "medium" | "high"), which
# matters: a sad person who is *drained* wants slow songs, while a
# sad person who is *agitated* wants something with more pulse.

MOOD_QUERY = {
    "happy": {
        "low":    "warm feel good songs",
        "medium": "happy upbeat songs",
        "high":   "cheerful dance feel good songs"
    },
    "sad": {
        "low":    "slow sad songs",
        "medium": "sad emotional songs",
        "high":   "heartbreak emotional songs"
    },
    "calm": {
        "low":    "soft soothing songs",
        "medium": "calm relaxing songs",
        "high":   "peaceful uplifting songs"
    },
    "angry": {
        "low":    "dark intense songs",
        "medium": "intense rock songs",
        "high":   "aggressive rage songs"
    },
    "romantic": {
        "low":    "soft romantic songs",
        "medium": "romantic love songs",
        "high":   "passionate love songs"
    },
    "energetic": {
        "low":    "steady motivational songs",
        "medium": "upbeat energetic songs",
        "high":   "high energy pump up songs"
    },
    "neutral": {
        "low":    "lofi chill songs",
        "medium": "easy listening songs",
        "high":   "feel good pop songs"
    }
}

# Uplift = "gently lift me", so it starts where the person is.
# Drained / low-energy people get hopeful, soft music; agitated
# people get music that channels the energy positively.
UPLIFT_QUERY = {
    "sad": {
        "low":    "soft hopeful songs",
        "medium": "hopeful uplifting songs",
        "high":   "feel good motivational songs"
    },
    "angry": {
        "low":    "calming feel good songs",
        "medium": "empowering confidence songs",
        "high":   "empowering confidence songs"
    },
    "default": {
        "low":    "soft hopeful songs",
        "medium": "feel good uplifting songs",
        "high":   "mood booster happy songs"
    }
}

CONTEXT_WORD = {
    "nostalgic": "nostalgic",
    "spiritual": "spiritual",
    "motivational": "motivational",
    "romantic": "romantic",
    "reflective": "introspective",
    "aesthetic": "cinematic"
}

ACTIVITY_WORD = {
    "study": "study focus",
    "workout": "workout",
    "drive": "night drive",
    "sleep": "sleep",
    "party": "party",
    "rain": "rainy day",
    "morning": "morning",
    "night": "late night",
    "cooking": "cooking",
    "walk": "walking",
    "work": "work focus",
    "travel": "road trip",
    "breakup": "breakup",
    "meditation": "meditation"
}

GENRE_WORD = {
    "lofi": "lofi", "acoustic": "acoustic", "piano": "piano",
    "classical": "classical", "rock": "rock", "metal": "metal",
    "hiphop": "hip hop", "edm": "edm", "jazz": "jazz",
    "indie": "indie", "pop": "pop", "instrumental": "instrumental",
    "rnb": "r&b", "folk": "folk", "ghazal": "ghazal",
    "sufi": "sufi", "bollywood": "bollywood"
}

MAX_QUERY_WORDS = 8

# When two moods are close ("sad" with a touch of "calm") the second
# one adds a flavour word to the search so the playlist reflects both.
SECONDARY_HINT = {
    "happy": "cheerful",
    "sad": "emotional",
    "calm": "soothing",
    "angry": "intense",
    "romantic": "romantic",
    "energetic": "energetic",
    "neutral": ""
}

# A title written in a language's own script is a strong sign that
# the video really is in that language (romanised titles are common
# for Hindi / Telugu, so this is only ever a BONUS, never a penalty).
SCRIPT_PATTERNS = {
    "chinese":   re.compile(r"[\u4e00-\u9fff]"),
    "korean":    re.compile(r"[\uac00-\ud7af]"),
    "japanese":  re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]"),
    "thai":      re.compile(r"[\u0e00-\u0e7f]"),
    "arabic":    re.compile(r"[\u0600-\u06ff]"),
    "hindi":     re.compile(r"[\u0900-\u097f]"),
    "telugu":    re.compile(r"[\u0c00-\u0c7f]"),
    "tamil":     re.compile(r"[\u0b80-\u0bff]"),
    "malayalam": re.compile(r"[\u0d00-\u0d7f]"),
    "kannada":   re.compile(r"[\u0c80-\u0cff]"),
    "punjabi":   re.compile(r"[\u0a00-\u0a7f]")
}


def _energy(profile):

    level = profile.get("arousal", "medium")

    return level if level in ("low", "medium", "high") else "medium"


def _mood_phrase(profile):

    emotion = profile.get("emotion", "neutral")
    energy = _energy(profile)

    if profile.get("mode") == "uplift":

        table = UPLIFT_QUERY.get(emotion, UPLIFT_QUERY["default"])

        return table[energy]

    table = MOOD_QUERY.get(emotion, MOOD_QUERY["neutral"])

    return table[energy]


def build_query(profile):
    """
    Composes the search phrase from the whole emotional profile.
    Order matters for YouTube's relevance: artist, situation and
    genre first (they're the most specific things the person said),
    then the mood phrase.
    """

    parts = []

    artists = profile.get("artists") or []

    if artists:
        parts.append(artists[0])

    activities = profile.get("activities") or []

    if activities:
        parts.append(ACTIVITY_WORD.get(activities[0], activities[0]))

    genres = profile.get("genres") or []

    if genres:
        parts.append(GENRE_WORD.get(genres[0], genres[0]))

    contexts = profile.get("context") or []

    # An activity already says a lot; only add a context flavour
    # when there's room and it isn't redundant.
    if contexts and not activities:
        parts.append(CONTEXT_WORD.get(contexts[0], contexts[0]))

    parts.append(_mood_phrase(profile))

    # Blend in the second mood when the person's feelings are mixed.
    secondary = profile.get("secondary")

    if (
        secondary
        and secondary != profile.get("emotion")
        and profile.get("mode") != "uplift"
    ):
        hint = SECONDARY_HINT.get(secondary, "")

        if hint:
            parts.append(hint)

    words = []

    for word in " ".join(parts).split():
        if word.lower() not in [w.lower() for w in words]:
            words.append(word)

    return " ".join(words[:MAX_QUERY_WORDS])


# What the person can choose in the language picker.  "mix" keeps the
# original behaviour (a blend of all the default languages, or whatever
# their text asked for); any other value means ONLY that language.
LANGUAGE_CHOICES = ("mix", "telugu", "hindi", "english")


def apply_language_choice(profile, choice):
    """
    Returns a copy of `profile` with the picker's choice applied.

    An explicit language wins over a language mentioned in the text
    ("play hindi songs" typed while Telugu is selected -> Telugu).
    "mix" (or anything unknown) changes nothing.
    """

    choice = str(choice or "mix").strip().lower()

    profile = dict(profile or {})

    if choice in LANGUAGE_CHOICES and choice != "mix":
        profile["languages"] = [choice]

    return profile


def pick_languages(profile):

    requested = [
        language for language in (profile.get("languages") or [])
        if language in LANGUAGE_QUERY_SUFFIX
    ]

    return requested or list(DEFAULT_LANGUAGES)


# Title wording that nudges ranking toward real songs and away from
# mixes, reactions and other non-song content.

GOOD_TITLE_HINTS = [
    "official audio", "official video", "official mv", "m/v",
    "official music video", "lyrical", "lyrics", "audio", "song", "mv"
]

# Longer than this is a mix / compilation, not a song.
MAX_SONG_SECONDS = 600

BAD_TITLE_HINTS = [
    "reaction", "interview", "compilation", "jukebox", "hour", "hours",
    "asmr", "tutorial", "karaoke", "cover", "full album", "mashup",
    "nonstop", "#shorts", "shorts", "status", "trailer", "teaser",
    "making of", "behind the scenes", "live stream", "livestream",
    "podcast", "review", "explained", "scene", "movie", "full movie",
    "loop", "8d", "bass boosted", "slowed", "collection", "playlist",
    "best of", "greatest hits", "medley", "back to back", "top 10",
    "top 20", "top 50", "top 100"
]

# Milder: alternative edits of a song.  Penalised, not banned.
SOFT_BAD_TITLE_HINTS = [
    "remix", "sped up", "speed up", "nightcore", "reverb", "acoustic cover"
]

# Words that, if present in a title, confirm it fits the mood.
MOOD_TITLE_WORDS = {
    "happy": ["happy", "joy", "smile", "sunshine", "dance", "party", "feel good"],
    "sad": ["sad", "cry", "tears", "broken", "heartbreak", "alone", "goodbye", "miss", "dard", "judaai"],
    "calm": ["calm", "relax", "peace", "soft", "chill", "soothing", "serene", "sleep"],
    "angry": ["rage", "fight", "rock", "warrior", "fire", "angry", "war", "power"],
    "romantic": ["love", "romantic", "kiss", "heart", "forever", "pyaar", "ishq", "kadhal"],
    "energetic": ["energy", "pump", "hype", "workout", "power", "dance", "party", "run"],
    "neutral": ["chill", "lofi", "easy", "mellow", "instrumental"]
}


def _intensity_bucket(confidence):

    if confidence >= 0.8:
        return "high"

    if confidence >= 0.6:
        return "medium"

    return "low"


# =========================================================
# 04. CACHE (fresh + stale) AND QUOTA MEMORY
# =========================================================

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 60 * 60          # fresh for 1 hour
_STALE_MAX_SECONDS = 24 * 60 * 60     # usable as a fallback for a day

_QUOTA_BLOCKED_UNTIL = 0.0
_QUOTA_BACKOFF_SECONDS = 10 * 60


def _cache_get(key, allow_stale=False):

    with _CACHE_LOCK:

        entry = _CACHE.get(key)

        if not entry:
            return None

        stored_at, value = entry

        age = time.time() - stored_at

        if age <= _CACHE_TTL_SECONDS:
            return value

        if allow_stale and age <= _STALE_MAX_SECONDS:
            return value

        if age > _STALE_MAX_SECONDS:
            _CACHE.pop(key, None)

        return None


def _cache_set(key, value):

    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)


# ---------------------------------------------------------
# 04B. DEMO SNAPSHOT (survives restarts and quota exhaustion)
# ---------------------------------------------------------
#
# The in-memory cache dies with the server and the stale copy only
# lives for a day.  A deployed portfolio site gets visitors days
# apart, often after the 10,000-unit daily quota is gone.  So the
# last good playlist per (mood, mode, languages) is also written to
# data/playlist_snapshot.json and served — marked stale — whenever
# YouTube can't answer.  `flask --app app warm-cache` fills it.
# ---------------------------------------------------------

_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "playlist_snapshot.json"
)
_SNAPSHOTS = {}
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_LOADED = False


def _snapshot_key(profile, languages):

    return "|".join([
        str(profile.get("emotion", "neutral")),
        str(profile.get("mode", "match")),
        ",".join(languages)
    ])


def _load_snapshots():

    global _SNAPSHOT_LOADED

    if _SNAPSHOT_LOADED:
        return

    _SNAPSHOT_LOADED = True

    try:
        with open(_SNAPSHOT_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _SNAPSHOTS.update(data)
    except (OSError, ValueError):
        pass


def _save_snapshot(profile, languages, outcome):

    with _SNAPSHOT_LOCK:

        _load_snapshots()

        _SNAPSHOTS[_snapshot_key(profile, languages)] = {
            "saved_at": int(time.time()),
            "songs": [
                s for s in outcome.get("songs", [])
                if s.get("videoId") not in _BAD_IDS
            ],
            "query": outcome.get("query", ""),
            "languages": list(languages)
        }

        try:
            os.makedirs(os.path.dirname(_SNAPSHOT_FILE), exist_ok=True)
            tmp = _SNAPSHOT_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(_SNAPSHOTS, handle, ensure_ascii=False, indent=1)
            os.replace(tmp, _SNAPSHOT_FILE)
        except OSError:
            pass


def _snapshot_fallback(profile, languages):
    """
    Best saved playlist for this request: the exact mood + mode +
    languages first, then the same mood's "match" playlist in the
    SAME languages.  It never crosses languages — someone who picked
    English must not get a Hindi/Telugu mix.  None if nothing fits.
    """

    with _SNAPSHOT_LOCK:
        _load_snapshots()
        snapshots = dict(_SNAPSHOTS)

    emotion = str(profile.get("emotion", "neutral"))
    language_part = ",".join(languages)

    candidates = [
        snapshots.get(_snapshot_key(profile, languages)),
        snapshots.get(f"{emotion}|match|{language_part}")
    ]

    for entry in candidates:

        songs = [
            s for s in (entry or {}).get("songs", [])
            if s.get("videoId") not in _BAD_IDS
        ]

        if songs:
            return _result(
                STATUS_OK, songs,
                query=entry.get("query", ""),
                languages=entry.get("languages", []),
                stale=True,
                snapshot=True
            )

    return None


def _cache_purge_video(video_id):

    with _CACHE_LOCK:

        for key, (stored_at, value) in list(_CACHE.items()):

            songs = value.get("songs", [])

            filtered = [s for s in songs if s["videoId"] != video_id]

            if len(filtered) != len(songs):
                _CACHE[key] = (stored_at, {**value, "songs": filtered})


# =========================================================
# 05. BLACKLIST OF VIDEOS THAT FAILED IN A REAL BROWSER
# =========================================================
#
# The API can say a video *should* embed and the player can still
# refuse (regional label blocks, owner restrictions that change).
# When the browser reports a failure, the front-end tells us here
# and the video is never recommended again — across restarts.

_BAD_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bad_videos.json"
)

_BAD_IDS = set()
_BAD_LOCK = threading.Lock()


def _load_bad_ids():

    try:
        with open(_BAD_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            _BAD_IDS.update(str(item) for item in data if item)
    except (OSError, ValueError):
        pass


def _save_bad_ids():

    try:
        with open(_BAD_FILE, "w", encoding="utf-8") as handle:
            json.dump(sorted(_BAD_IDS), handle)
    except OSError:
        pass


_load_bad_ids()

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


# ---------------------------------------------------------
# 05B. CHANNELS THAT KEEP REFUSING EMBEDS
# ---------------------------------------------------------
#
# Embedding blocks come from the UPLOADER (big labels and VEVO
# accounts block many of their videos outside youtube.com), and
# neither the Data API nor oEmbed can see them.  So AIMuse learns:
# every failed video counts against its channel, and channels
# with failures sink in the ranking.  A channel needs to fail
# several times before it is pushed out completely.
# ---------------------------------------------------------

_BAD_CHANNELS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bad_channels.json"
)
_BAD_CHANNELS = {}

CHANNEL_FAIL_PENALTY = 4        # score lost per failed video
CHANNEL_FAIL_PENALTY_MAX = 16   # ~4 failures = effectively never first


def _channel_key(channel):

    return re.sub(r"\s+", " ", str(channel or "")).strip().lower()


def _load_bad_channels():

    try:
        with open(_BAD_CHANNELS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _BAD_CHANNELS.update({
                str(k): int(v) for k, v in data.items() if k
            })
    except (OSError, ValueError, TypeError):
        pass


def _save_bad_channels():

    try:
        with open(_BAD_CHANNELS_FILE, "w", encoding="utf-8") as handle:
            json.dump(_BAD_CHANNELS, handle, ensure_ascii=False, indent=1, sort_keys=True)
    except OSError:
        pass


_load_bad_channels()


def channel_penalty(channel):
    """How much a channel's embed failures cost a video in ranking."""

    failures = _BAD_CHANNELS.get(_channel_key(channel), 0)

    return min(failures * CHANNEL_FAIL_PENALTY, CHANNEL_FAIL_PENALTY_MAX)


def report_bad_video(video_id, channel=""):
    """
    Called when the embedded player failed on `video_id`.
    Returns True if it was recorded.  The uploader's failure count
    goes up once per newly failed video.
    """

    video_id = str(video_id or "").strip()

    if not _VIDEO_ID_RE.match(video_id):
        return False

    key = _channel_key(channel)

    with _BAD_LOCK:

        if video_id not in _BAD_IDS:

            _BAD_IDS.add(video_id)
            _save_bad_ids()

            if key:
                _BAD_CHANNELS[key] = _BAD_CHANNELS.get(key, 0) + 1
                _save_bad_channels()

    _cache_purge_video(video_id)

    return True


# =========================================================
# 06. SMALL HELPERS
# =========================================================

_DURATION_RE = re.compile(
    r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def _parse_duration(iso_duration):

    match = _DURATION_RE.match(iso_duration or "")

    if not match:
        return 0

    parts = match.groupdict()

    return (
        int(parts["hours"] or 0) * 3600 +
        int(parts["minutes"] or 0) * 60 +
        int(parts["seconds"] or 0)
    )


_NOISE_WORDS = re.compile(
    r"\b(official|video|audio|lyrics?|lyrical|full|song|mv|m/v|hd|4k|"
    r"visualizer|music|version|remastered|feat|ft)\b"
)


def _title_key(title):
    """
    Normalised title used to spot the same song uploaded twice
    ("X (Official Video)" vs "X - Lyrics").
    """

    text = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", title.lower())
    text = _NOISE_WORDS.sub(" ", text)
    text = re.sub(r"[^\w\u0080-\uffff]+", " ", text)

    return " ".join(text.split())[:60]


def _api_get(url, params):
    """
    GET with error classification.  Raises _QuotaExceeded for
    quota problems, requests.RequestException for the rest.
    """

    response = _SESSION.get(url, params=params, timeout=HTTP_TIMEOUT)

    if response.status_code == 403:

        try:
            reasons = [
                error.get("reason", "")
                for error in response.json().get("error", {}).get("errors", [])
            ]
        except ValueError:
            reasons = []

        if any(r in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded")
               for r in reasons):
            raise _QuotaExceeded()

    response.raise_for_status()

    return response.json()



# =========================================================
# 06B. TURNING MESSY YOUTUBE TITLES INTO "SONG" + "ARTIST"
# =========================================================
#
# YouTube titles are written for humans scrolling a feed, not for a
# playlist: they carry "Official MV", "Full HD Video Song", the film
# name, the label, hashtags...  parse_song() peels all that away.

_QUOTE_PAIR_RE = re.compile(
    "[\u300e\u300c\u300a\u3008\u3010\u201c\"]"
    "([^\u300e\u300f\u300c\u300d\u300a\u300b\u3008\u3009\u3010\u3011\u201c\u201d\"]{2,90})"
    "[\u300f\u300d\u300b\u3009\u3011\u201d\"]"
)

# 'Dynamite' — only when the quotes stand alone, so I'm / don't survive.
_SINGLE_QUOTE_RE = re.compile(
    r"(?:(?<=\s)|^)['\u2018]([^'\u2019]{2,90})['\u2019](?=\s|$|[.,])"
)

_NOISE_BRACKET_RE = re.compile(
    r"[\(\[\{\uff08\u3010][^\)\]\}\uff09\u3011]*?"
    r"\b(?:official|video|audio|lyrics?|lyrical|mv|m/v|hd|4k|"
    r"visuali[sz]er|music video|full song|color coded|colour coded|"
    r"kbps|explicit|remaster\w*)\b"
    r"[^\)\]\}\uff09\u3011]*?[\)\]\}\uff09\u3011]",
    re.IGNORECASE
)

_NOISE_PHRASE_RE = re.compile(
    r"\b(?:"
    r"official\s+(?:music\s+)?(?:video|audio|mv|m/v|lyric\s+video|visuali[sz]er)|"
    r"(?:full\s+)?(?:hd\s+)?(?:video|lyrical|lyric|audio)\s+song|"
    r"full\s+(?:hd\s+)?video|lyric\s+video|lyrical\s+video|music\s+video|"
    r"official|lyrics?|lyrical|visuali[sz]er|m/v|mv|4k|hd|audio"
    r")\b",
    re.IGNORECASE
)

# Only these say "this piece is the SONG" — Western titles almost never
# use them ("Full Video Song", "Lyrical Video"), Indian uploads always do.
_SONG_MARKER_RE = re.compile(
    r"\b(?:(?:full\s+)?(?:hd\s+)?(?:video|lyrical|lyric|audio)\s+song|"
    r"full\s+(?:hd\s+)?video|lyrical\s+video)\b",
    re.IGNORECASE
)

# For these, "A - B" almost always means "Song - Film", not "Artist - Song".
SONG_FIRST_LANGUAGES = {
    "hindi", "telugu", "tamil", "malayalam", "kannada", "punjabi"
}

_FEAT_RE = re.compile(
    r"\s*[\(\[]?\b(?:feat|ft|featuring)\b\.?\s+([^\)\]\[]+?)[\)\]]?\s*$",
    re.IGNORECASE
)


def _norm(text):
    """Lower-case letters/digits only — for comparing names."""

    return re.sub(r"[^\w]+", " ", (text or "").lower()).strip()


def _same_name(a, b):

    a, b = _norm(a), _norm(b)

    if not a or not b:
        return False

    if a == b:
        return True

    shorter, longer = sorted((a, b), key=len)

    return len(shorter) >= 3 and shorter in longer


def _strip_noise(text):

    text = _NOISE_BRACKET_RE.sub(" ", text)
    text = _NOISE_PHRASE_RE.sub(" ", text)
    text = re.sub(r"#\w+", " ", text)

    # "Hype Boy 「Official Audio」" -> "Hype Boy 「」" -> "Hype Boy"
    text = re.sub(
        "[\u300c\u300e\u300a\u3008\u3010\\(\\[\uff08\u201c\"]\\s*"
        "[\u300d\u300f\u300b\u3009\u3011\\)\\]\uff09\u201d\"]",
        " ", text
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip(" -\u2013\u2014|:\u2022\u00b7~*_/,")


def _clean_channel(channel):

    name = html.unescape(channel or "").strip()

    name = re.sub(r"\s*-\s*Topic$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*VEVO$", "", name, flags=re.IGNORECASE)

    return name.strip()


def _clean_artist_text(text):
    """'BTS (방탄소년단)' -> 'BTS'  (drop bracketed native-script copies)."""

    text = text.strip(" -\u2013\u2014|:")

    without_brackets = re.sub(
        r"\s*[\(\uff08][^\)\uff09]*[\)\uff09]", "", text
    ).strip()

    return without_brackets or text


def parse_song(title, channel="", language=""):
    """
    Returns (song, artist) for a raw YouTube title + channel name.
    Never raises; falls back to the raw title / channel.
    """

    raw = html.unescape(title or "").strip()
    channel_clean = _clean_channel(channel)

    work = _strip_noise(raw)

    feat = ""

    match = _FEAT_RE.search(work)

    if match:
        feat = match.group(1).strip(" ,&")
        work = work[:match.start()].strip()

    song = ""
    artist = ""

    quoted = _QUOTE_PAIR_RE.search(work) or _SINGLE_QUOTE_RE.search(work)

    if quoted:

        # NiziU 『Make you happy』  ->  song inside the quotes,
        # artist is whatever precedes them.
        song = quoted.group(1).strip()
        artist = _clean_artist_text(work[:quoted.start()])

    else:

        # A piece marked "Full Video Song" IS the song; a piece after it
        # is the film, a piece before it is the artist.
        raw_main = re.split(r"\s*\|+\s*", raw)[0]

        raw_pieces = [
            piece.strip()
            for piece in re.split(r"\s+[-\u2013\u2014]+\s+", raw_main)
            if piece.strip()
        ]

        marked = [
            index for index, piece in enumerate(raw_pieces)
            if _SONG_MARKER_RE.search(piece)
        ]

        if len(raw_pieces) >= 2 and len(marked) == 1:

            index = marked[0]
            cleaned = _strip_noise(raw_pieces[index])

            if cleaned:
                song = cleaned
                if index == 1 and len(raw_pieces) == 2:
                    artist = _strip_noise(raw_pieces[0])
            else:
                # the piece was pure noise ("Full Video Song") — the
                # song is the first real piece.
                song = _strip_noise(raw_pieces[0])

    if not song and not quoted:

        # "Song | Movie | Label" -> the first piece is the song.
        main = re.split(r"\s*\|+\s*", work)[0]

        pieces = [
            piece.strip()
            for piece in re.split(r"\s+[-\u2013\u2014]+\s+", main)
            if piece.strip()
        ]

        if len(pieces) >= 2:

            first, second = pieces[0], pieces[1]

            # "Song - Artist" when the 2nd piece is the uploader.
            if _same_name(second, channel_clean) and not _same_name(first, channel_clean):
                song, artist = first, second
            elif _same_name(first, channel_clean) and not _same_name(second, channel_clean):
                song, artist = second, first
            elif language in SONG_FIRST_LANGUAGES:
                # "Tera Fitoor - Genius": song first, film second.
                song, artist = first, ""
            else:
                song, artist = second, first

        elif pieces:
            song = pieces[0]

    song = song.strip(" -\u2013\u2014|:\u2022\u00b7~*_/,")

    if not song:
        song = raw or "Untitled"

    if not artist or _same_name(artist, song):
        artist = channel_clean

    if feat and artist:
        artist = f"{artist} ft. {feat}"

    return song, artist


# =========================================================
# 07. AVAILABILITY CHECKS
# =========================================================

def _allowed_in_region(content_details, region):

    if not region:
        return True

    restriction = content_details.get("regionRestriction") or {}

    blocked = restriction.get("blocked")
    allowed = restriction.get("allowed")

    if blocked and region in blocked:
        return False

    if allowed is not None and region not in allowed:
        return False

    return True


def _is_playable(item, region):
    """
    Everything the videos.list response can tell us about whether
    the embedded player will accept this video.
    """

    status = item.get("status", {})
    content = item.get("contentDetails", {})
    snippet = item.get("snippet", {})

    if status.get("privacyStatus") != "public":
        return False

    if status.get("uploadStatus", "processed") != "processed":
        return False

    if not status.get("embeddable", False):
        return False

    # Age-restricted videos can't be played in an embed.
    rating = content.get("contentRating") or {}

    if rating.get("ytRating") == "ytAgeRestricted":
        return False

    # Live streams / premieres are not songs.
    if snippet.get("liveBroadcastContent", "none") != "none":
        return False

    return _allowed_in_region(content, region)


def _oembed_ok(video_id):
    """
    Free (no quota) probe.  200 = public and embeddable.
    401/403 = embedding disabled by the owner.  404 = removed /
    private.  Anything else (timeouts, 5xx, rate limiting) fails
    OPEN — better to keep a good song than drop it because the
    probe hiccuped.
    """

    try:

        response = _SESSION.get(
            OEMBED_URL,
            params={
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "format": "json"
            },
            timeout=OEMBED_TIMEOUT
        )

    except requests.RequestException:
        return True

    if response.status_code in (401, 403, 404):
        return False

    return True


# =========================================================
# 08. SCORING
# =========================================================

def _score_video(video, rank, profile):

    emotion = profile.get("emotion", "neutral")
    secondary = profile.get("secondary")

    score = 0.0

    # YouTube's own relevance rank for this query.
    score += max(0, 20 - rank) * 0.8

    title = video["raw_title"].lower()
    channel = video["channel"].lower()

    for hint in GOOD_TITLE_HINTS:
        if hint in title:
            score += 3
            break

    for hint in BAD_TITLE_HINTS:
        if hint in title:
            score -= 7
            break

    # Remixes / sped-up edits are only welcome when asked for.
    wanted_genres = " ".join(profile.get("genres") or [])

    for hint in SOFT_BAD_TITLE_HINTS:
        if hint in title and hint not in wanted_genres:
            score -= 3
            break

    for word in MOOD_TITLE_WORDS.get(emotion, []):
        if word in title:
            score += 2.5
            break

    # The second mood counts too, just less.
    if secondary and secondary != emotion:
        for word in MOOD_TITLE_WORDS.get(secondary, []):
            if word in title:
                score += 1.2
                break

    # A named artist ("songs like Arijit Singh") is the strongest signal.
    for name in profile.get("artists") or []:

        wanted = _norm(name)

        if wanted and (
            wanted in _norm(video["raw_title"]) or wanted in _norm(video["channel"])
        ):
            score += 12
            break

    # Title written in the requested language's own script.
    pattern = SCRIPT_PATTERNS.get(video.get("language"))

    if pattern and pattern.search(video["raw_title"]):
        score += 2

    # Channels that keep refusing embeds sink (learned from real
    # playback failures — see report_bad_video).  "Topic" uploads
    # get a small bonus only while they have a clean record.
    # (VEVO / "official" used to get a bonus too, but those are
    # exactly the uploaders that block embedding most often.)
    penalty = channel_penalty(video["channel"])

    score -= penalty

    if channel.endswith("- topic") and not penalty:
        score += 2

    duration = video["duration_seconds"]

    if 120 <= duration <= 420:
        score += 6
    elif 90 <= duration < 120 or 420 < duration <= 540:
        score += 2
    elif duration < 60 or duration > MAX_SONG_SECONDS:
        score -= 10

    views = video.get("view_count") or 0

    if views > 0:
        score += min(math.log10(views + 1), 9) * 1.5

    # Like ratio: people who watched it and loved it.
    likes = video.get("like_count") or 0

    if views >= 10000 and likes > 0:
        score += min(likes / views, 0.08) / 0.08 * 3

    return score


# =========================================================
# 09. SEARCH + DETAILS
# =========================================================

def _search_language(query, language, pool_size=CANDIDATES_PER_LANGUAGE,
                     add_suffix=True, music_only=True):
    """
    Returns video IDs (relevance order) for one language.
    Raises _QuotaExceeded so the caller can stop early; any
    other failure returns [] for just this language.
    """

    suffix = LANGUAGE_QUERY_SUFFIX.get(language, "") if add_suffix else ""

    params = {
        "part": "snippet",
        "q": f"{query} {suffix}".strip(),
        "type": "video",
        "order": SEARCH_ORDER,
        "videoEmbeddable": "true",
        "videoSyndicated": "true",
        "safeSearch": "moderate",
        "maxResults": pool_size,
        "key": YOUTUBE_API_KEY
    }

    if music_only:
        params["videoCategoryId"] = "10"

    code = LANGUAGE_CODES.get(language)

    if code:
        params["relevanceLanguage"] = code

    if YOUTUBE_REGION:
        params["regionCode"] = YOUTUBE_REGION

    try:

        data = _api_get(SEARCH_URL, params)

    except _QuotaExceeded:
        raise

    except (requests.RequestException, ValueError):
        return None   # None = "network problem", [] = "no results"

    return [
        item["id"]["videoId"]
        for item in data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]


def _fetch_details(video_ids):

    all_items = []

    for start in range(0, len(video_ids), 50):

        batch = video_ids[start:start + 50]

        try:

            data = _api_get(VIDEOS_URL, {
                "part": "contentDetails,statistics,snippet,status",
                "id": ",".join(batch),
                "key": YOUTUBE_API_KEY
            })

            all_items.extend(data.get("items", []))

        except _QuotaExceeded:
            raise

        except (requests.RequestException, ValueError):
            continue

    return all_items


# =========================================================
# 10. PUBLIC ENTRY POINT
# =========================================================

def _result(status, songs=None, **extra):

    songs = songs or []

    ids = [song["videoId"] for song in songs][:50]

    return {
        "status": status,
        "songs": songs,
        "playlist_url": (
            "https://www.youtube.com/watch_videos?video_ids=" + ",".join(ids)
            if ids else ""
        ),
        **extra
    }


def _normalise_profile(emotion, mode, confidence, profile):

    merged = dict(profile or {})

    merged["emotion"] = emotion or merged.get("emotion") or "neutral"
    merged["mode"] = mode or merged.get("mode") or "match"
    merged["confidence"] = confidence

    return merged


# ---------------------------------------------------------
# 10B. PINNED SONGS — hand-picked favourites
# ---------------------------------------------------------
#
# A pinned song is always placed in matching playlists, at
# `position` (0 = first).  It applies when the playlist's mode is
# in `modes` and the pin's `language` is among the playlist's
# languages (so a Telugu pin shows up for "Telugu" and "Mix").
#
# videoId: leave empty and AIMuse finds the song itself ONCE
#   (~200-300 quota units, with the same verified search the
#   self-healing engine uses), then remembers the best few uploads
#   in data/pinned_songs.json — commit that file.  Paste a videoId
#   to skip the search entirely.  If the pinned upload ever fails
#   to play, the next remembered upload is used.
# ---------------------------------------------------------

PINNED_SONGS = [
    {
        "title": "Le Padha Padhaa",
        "artist": "Armaan Malik",
        "language": "telugu",
        "modes": ["uplift"],
        "position": 0,
        "videoId": ""
    },
]

_PINNED_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "pinned_songs.json"
)
_PINNED = {}
_PINNED_LOADED = False
_PINNED_LOCK = threading.Lock()


def _pin_key(pin):

    return "|".join([pin["title"], pin.get("artist", ""), pin["language"]]).lower()


def _load_pinned():

    global _PINNED_LOADED

    if _PINNED_LOADED:
        return

    _PINNED_LOADED = True

    try:
        with open(_PINNED_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _PINNED.update(data)
    except (OSError, ValueError):
        pass


def _save_pinned():

    try:
        os.makedirs(os.path.dirname(_PINNED_FILE), exist_ok=True)
        with open(_PINNED_FILE, "w", encoding="utf-8") as handle:
            json.dump(_PINNED, handle, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _resolve_pin(pin):
    """The uploads remembered for this pin, finding them once if needed."""

    global _QUOTA_BLOCKED_UNTIL

    key = _pin_key(pin)

    with _PINNED_LOCK:

        _load_pinned()

        if key in _PINNED:
            return _PINNED[key]

    if not YOUTUBE_API_KEY or time.time() < _QUOTA_BLOCKED_UNTIL:
        return []

    try:

        if pin.get("videoId"):
            items = _fetch_details([pin["videoId"]])
            songs = [_make_video(item, pin["language"]) for item in items]
        else:
            songs = _search_alternatives(
                pin["title"], pin.get("artist", ""), pin["language"]
            )

    except _QuotaExceeded:
        _QUOTA_BLOCKED_UNTIL = time.time() + _QUOTA_BACKOFF_SECONDS
        return []

    if songs is None:          # network trouble: try again next time
        return []

    songs = [
        {**song, "language": pin["language"], "pinned": True}
        for song in songs[:5]
    ]

    with _PINNED_LOCK:
        _PINNED[key] = songs
        _save_pinned()

    return songs


def _apply_pins(outcome, profile, languages):
    """Put matching pinned songs into an OK playlist (on a copy)."""

    if outcome.get("status") != STATUS_OK:
        return outcome

    mode = profile.get("mode", "match")

    songs = list(outcome.get("songs", []))

    for pin in PINNED_SONGS:

        if mode not in pin.get("modes", []) or pin["language"] not in languages:
            continue

        uploads = [
            s for s in _resolve_pin(pin)
            if s.get("videoId") not in _BAD_IDS
        ]

        if not uploads:
            continue

        chosen = uploads[0]
        title_key = _title_key(chosen.get("title", ""))

        # never twice: drop the same video / same song already listed
        songs = [
            s for s in songs
            if s.get("videoId") != chosen["videoId"]
            and _title_key(s.get("title", "")) != title_key
        ]

        songs.insert(min(pin.get("position", 0), len(songs)), dict(chosen))

    return {**outcome, "songs": songs}


def get_recommendations(emotion, mode, confidence,
                        profile=None, limit=DEFAULT_LIMIT):
    """Builds the playlist (see _get_recommendations_core), then adds
    any hand-picked PINNED_SONGS that match it."""

    normalised = _normalise_profile(emotion, mode, confidence, profile)

    outcome = _get_recommendations_core(
        emotion, mode, confidence, profile=profile, limit=limit
    )

    return _apply_pins(outcome, normalised, pick_languages(normalised))


def _get_recommendations_core(emotion, mode, confidence,
                              profile=None, limit=DEFAULT_LIMIT):
    """
    Returns a dict:

      {
        "status": "ok" | "no_api_key" | "quota_exceeded" |
                  "network_error" | "no_results",
        "songs":  [ {videoId, title, channel, thumbnail,
                     duration_seconds, view_count, language, url} ],
        "playlist_url": "https://www.youtube.com/watch_videos?...",
        "query": "the phrase that was searched",
        "languages": [...],
        "stale": bool          # only when served from an old cache
      }

    Never raises.  `songs` is empty unless status is "ok".
    """

    global _QUOTA_BLOCKED_UNTIL

    profile = _normalise_profile(emotion, mode, confidence, profile)

    if not YOUTUBE_API_KEY:
        return _result(STATUS_NO_KEY)

    languages = pick_languages(profile)
    query = build_query(profile)

    cache_key = (
        query, tuple(languages), YOUTUBE_REGION, limit,
        _intensity_bucket(confidence)
    )

    cached = _cache_get(cache_key)

    if cached is not None:
        return {**cached, "cached": True}

    if time.time() < _QUOTA_BLOCKED_UNTIL:

        stale = _cache_get(cache_key, allow_stale=True)

        if stale is not None:
            return {**stale, "stale": True}

        return _snapshot_fallback(profile, languages) or \
            _result(STATUS_QUOTA, query=query, languages=languages)

    try:

        outcome = _build_playlist(profile, query, languages, limit)

    except _QuotaExceeded:

        _QUOTA_BLOCKED_UNTIL = time.time() + _QUOTA_BACKOFF_SECONDS

        stale = _cache_get(cache_key, allow_stale=True)

        if stale is not None:
            return {**stale, "stale": True}

        return _snapshot_fallback(profile, languages) or \
            _result(STATUS_QUOTA, query=query, languages=languages)

    if outcome["status"] == STATUS_OK:
        _cache_set(cache_key, outcome)
        _save_snapshot(profile, languages, outcome)

    elif outcome["status"] == STATUS_NETWORK:

        stale = _cache_get(cache_key, allow_stale=True)

        if stale is not None:
            return {**stale, "stale": True}

        snapshot = _snapshot_fallback(profile, languages)

        if snapshot is not None:
            return snapshot

    return outcome


def _make_video(item, language):
    """One videos.list item -> the dict the front-end receives."""

    snippet = item.get("snippet", {})
    content_details = item.get("contentDetails", {})
    statistics = item.get("statistics", {})

    video_id = item.get("id", "")

    duration = _parse_duration(content_details.get("duration", ""))

    thumbnails = snippet.get("thumbnails", {})

    thumbnail = (
        thumbnails.get("medium") or thumbnails.get("default") or {}
    ).get("url", "")

    raw_title = html.unescape(snippet.get("title", "Untitled"))
    channel = html.unescape(snippet.get("channelTitle", ""))

    song, artist = parse_song(raw_title, channel, language)

    return {
        "videoId": video_id,
        "title": song,
        "artist": artist,
        "raw_title": raw_title,
        "channel": channel,
        "thumbnail": thumbnail,
        "duration_seconds": duration,
        "view_count": int(statistics.get("viewCount", 0) or 0),
        "like_count": int(statistics.get("likeCount", 0) or 0),
        "language": language,
        "url": f"https://www.youtube.com/watch?v={video_id}"
    }


def _build_playlist(profile, query, languages, limit):

    emotion = profile["emotion"]

    # ---- 1. Search every language at once -------------------

    pool_size = (
        CANDIDATES_WHEN_FEW_LANGUAGES
        if len(languages) <= 2 else CANDIDATES_PER_LANGUAGE
    )

    with ThreadPoolExecutor(max_workers=len(languages)) as pool:

        futures = [
            pool.submit(_search_language, query, language, pool_size)
            for language in languages
        ]

        id_lists = []

        for future in futures:
            id_lists.append(future.result())   # may raise _QuotaExceeded

    if all(ids is None for ids in id_lists):
        return _result(STATUS_NETWORK, query=query, languages=languages)

    language_by_id = {}
    rank_by_id = {}

    with _BAD_LOCK:
        known_bad = set(_BAD_IDS)

    for language, video_ids in zip(languages, id_lists):

        for position, video_id in enumerate(video_ids or []):

            if video_id in known_bad:
                continue

            if video_id not in language_by_id:
                language_by_id[video_id] = language
                rank_by_id[video_id] = position

    if not language_by_id:
        return _result(STATUS_NO_RESULTS, query=query, languages=languages)

    # ---- 2. Details + hard playability filters --------------

    detail_items = _fetch_details(list(language_by_id.keys()))

    if not detail_items:
        return _result(STATUS_NETWORK, query=query, languages=languages)

    candidates = []

    for item in detail_items:

        video_id = item.get("id", "")

        if video_id not in language_by_id:
            continue

        if not _is_playable(item, YOUTUBE_REGION):
            continue

        video = _make_video(item, language_by_id[video_id])

        # A song, not a clip or a mix.
        if video["duration_seconds"] < 60 or video["duration_seconds"] > MAX_SONG_SECONDS:
            continue

        video["_score"] = _score_video(video, rank_by_id[video_id], profile)

        candidates.append(video)

    if not candidates:
        return _result(STATUS_NO_RESULTS, query=query, languages=languages)

    # ---- 3. Rank per language, drop near-duplicates ---------

    by_language = {}

    for video in candidates:
        by_language.setdefault(video["language"], []).append(video)

    seen_titles = set()

    for language, videos in by_language.items():

        videos.sort(key=lambda v: v["_score"], reverse=True)

        unique = []

        for video in videos:

            key = _title_key(video["title"]) or _title_key(video["raw_title"])

            if key and key in seen_titles:
                continue

            if key:
                seen_titles.add(key)

            unique.append(video)

        by_language[language] = unique

    # ---- 4. oEmbed probe on the shortlist (free) ------------
    #
    # Only probe as many as we could possibly need: the top of each
    # language's queue.  Anything that fails is removed and the next
    # candidate moves up.

    shortlist_size = max(4, math.ceil(limit / max(1, len(by_language))) + 3)

    to_probe = []

    for videos in by_language.values():
        to_probe.extend(v["videoId"] for v in videos[:shortlist_size])

    with ThreadPoolExecutor(max_workers=min(12, len(to_probe))) as pool:
        verdicts = dict(zip(to_probe, pool.map(_oembed_ok, to_probe)))

    for language, videos in by_language.items():

        by_language[language] = [
            video for video in videos
            if verdicts.get(video["videoId"], True)
        ]

    # ---- 5. Take turns between languages, cap per channel ---

    ordered_languages = [
        language for language in languages
        if by_language.get(language)
    ]

    results = []
    channel_counts = {}
    artist_counts = {}

    def take_round(max_per_artist):
        """One pass of language round-robin under the given artist cap."""

        while len(results) < limit:

            made_progress = False

            for language in ordered_languages:

                queue = by_language[language]

                for index, video in enumerate(queue):

                    channel = video["channel"]
                    artist_key = _norm(video["artist"]) or channel

                    if channel_counts.get(channel, 0) >= MAX_PER_CHANNEL:
                        continue

                    if artist_counts.get(artist_key, 0) >= max_per_artist:
                        continue

                    queue.pop(index)

                    channel_counts[channel] = channel_counts.get(channel, 0) + 1
                    artist_counts[artist_key] = artist_counts.get(artist_key, 0) + 1

                    results.append(video)
                    made_progress = True

                    break

                if len(results) >= limit:
                    break

            if not made_progress:
                break

    # Strict pass first (one song per artist) for variety, then relax
    # if that leaves the playlist short — unless the person asked for
    # a specific artist, in which case several of theirs is the point.
    wants_artist = bool(profile.get("artists"))

    take_round(4 if wants_artist else 1)

    if len(results) < limit:
        take_round(4 if wants_artist else 2)

    # One language only: every song comes from a single pool, so if it
    # is still short, allow a third song per artist rather than a
    # half-empty playlist.
    if len(results) < limit and len(ordered_languages) == 1:
        take_round(4 if wants_artist else 3)

    for video in results:
        video.pop("_score", None)

    if not results:
        return _result(STATUS_NO_RESULTS, query=query, languages=languages)

    return _result(
        STATUS_OK,
        results,
        query=query,
        languages=[l for l in languages if l in {v["language"] for v in results}]
    )


# =========================================================
# 11. SELF-HEALING: SAME SONG, DIFFERENT VIDEO
# =========================================================
#
# When the embedded player refuses a video (error 100/101/150), the
# front-end calls find_replacement().  AIMuse hunts for OTHER uploads
# of the SAME track — official audio, lyric video, Topic channel,
# a fan lyric upload — and returns a whole pool of them.
#
# Why a pool, and why different channels?
#   Embedding is switched off per OWNER.  If HYBE's official video is
#   blocked, HYBE's "Performance ver." is blocked too.  So:
#     * candidates are interleaved across channels (never several
#       from the same uploader in a row),
#     * the channel that just failed goes to the very back,
#     * the browser tries them one after another in the real player
#       (instantly, no more server calls) until one plays.
#
# Cost: at most 3 searches (300 quota units) per song; the pool is
# cached, so further failures of the same song cost nothing.

MAX_ALTERNATIVES = 8

# Uploads of the same song that are NOT the song itself.
REPLACEMENT_AVOID = [
    "reaction", "reacts", "reacting", "cover", "remix", "karaoke",
    "instrumental", "slowed", "sped up", "speed up", "nightcore",
    "reverb", "8d", "bass boosted", "mashup", "tutorial", "shorts",
    "dance", "challenge", "fancam", "choreography", "practice",
    "tiktok", "trend", "review", "explained", "interview", "live",
    "compilation", "jukebox", "hour", "hours", "loop", "asmr"
]


def _hint_in(text, hint):
    """Whole-word match, so 'live' doesn't hit 'alive' or 'hour' 'hourglass'."""

    return re.search(r"(?<!\w)" + re.escape(hint) + r"(?!\w)", text) is not None


def _all_bad_ids():

    with _BAD_LOCK:
        return set(_BAD_IDS)


# How long a replacement lookup may take before returning what it has.
SEARCH_BUDGET_SECONDS = 6.0

# Only this many of the best candidates get the (free but slow) oEmbed
# probe; the rest are handed over unchecked because the browser tries
# them in the real player anyway.
PROBE_TOP = 4


def _alternatives_from_query(query, music_only, language,
                             song, artist, original_text, target):
    """
    One search -> {videoId: video} of plausible other uploads of the song.
    Returns None when the request itself failed.  Raises _QuotaExceeded.
    """

    ids = _search_language(
        query, language, pool_size=25,
        add_suffix=False, music_only=music_only
    )

    if ids is None:
        return None

    found = {}

    for rank, item in enumerate(_fetch_details(ids)):

        video_id = item.get("id", "")

        if not _is_playable(item, YOUTUBE_REGION):
            continue

        video = _make_video(item, language)

        if not 60 <= video["duration_seconds"] <= MAX_SONG_SECONDS:
            continue

        raw = video["raw_title"].lower()

        # Skip covers, dance videos, remixes... unless the original was one.
        if any(
            _hint_in(raw, hint) and not _hint_in(original_text, hint)
            for hint in REPLACEMENT_AVOID
        ):
            continue

        candidate_title = _norm(video["title"])

        ratio = difflib.SequenceMatcher(
            None, target, candidate_title
        ).ratio()

        # The PARSED song name must match (not just appear somewhere in a
        # fan-edit title) — but also accept a swapped "Song - Artist" parse.
        is_same_song = bool(target) and (
            target in candidate_title
            or target in _norm(video["artist"])
            or ratio >= 0.72
        )

        if not is_same_song:
            continue

        # "Hype Boy - NewJeans" parsed as artist/song the wrong way round.
        if target in _norm(video["artist"]) and target not in candidate_title:
            video["title"], video["artist"] = video["artist"], video["title"]

        rank_score = ratio * 10

        first_word = (_norm(artist).split() or [""])[0]

        if first_word and first_word in _norm(
            video["raw_title"] + " " + video["channel"]
        ):
            rank_score += 8

        # Plain "Official Audio / Lyrics / Topic" uploads first;
        # music-video variants ("Performance ver.") a little lower.
        if "performance" in raw or "ver." in raw:
            rank_score -= 3

        rank_score += _score_video(
            video, rank, {"emotion": "neutral"}
        ) * 0.4

        video["_score"] = rank_score

        found[video_id] = video

    return found


def _search_alternatives(song, artist, language):
    """
    Ranked list of other uploads of (song, artist).  Returns None on
    a pure network failure, [] when nothing suitable exists.
    Raises _QuotaExceeded.

    Speed: the two best queries run AT THE SAME TIME (so a lookup costs
    one search round-trip, not two), a third only runs if those found
    almost nothing, and the whole thing is capped by SEARCH_BUDGET_SECONDS.
    """

    base = f"{artist} {song}".strip()

    original_text = f"{song} {artist}".lower()
    target = _norm(song)

    def run(query, music_only):
        return _alternatives_from_query(
            query, music_only, language, song, artist, original_text, target
        )

    pool = {}
    outcomes = []

    executor = ThreadPoolExecutor(max_workers=2)

    try:

        futures = [
            executor.submit(run, f"{base} official audio", True),
            executor.submit(run, f"{base} lyrics", False)
        ]

        done, _pending = wait(futures, timeout=SEARCH_BUDGET_SECONDS)

        for future in done:
            outcomes.append(future.result())     # may raise _QuotaExceeded

    finally:
        # Don't wait for a straggler: whatever finished in time is used.
        executor.shutdown(wait=False)

    for outcome in outcomes:
        if outcome:
            pool.update(outcome)

    # Almost nothing yet: one more, broader query.
    if len(pool) < 3:

        extra = run(base, False)

        if extra:
            pool.update(extra)

        outcomes.append(extra)

    if not pool and outcomes and all(o is None for o in outcomes):
        return None

    ranked = sorted(pool.values(), key=lambda v: v["_score"], reverse=True)

    for video in ranked:
        video.pop("_score", None)

    return ranked


def _interleave_channels(ranked, failed_channel, excluded):
    """
    Best-first, but never two from the same channel in a row, with the
    channel that just failed pushed to the very end.  At most 2 per
    channel overall.
    """

    failed = _norm(failed_channel)

    groups = {}
    order = []

    for video in ranked:

        if video["videoId"] in excluded:
            continue

        key = _norm(video["channel"])

        if key not in groups:
            groups[key] = []
            order.append(key)

        if len(groups[key]) < 2:
            groups[key].append(video)

    # failing channel last
    order.sort(key=lambda key: 1 if (failed and key == failed) else 0)

    result = []

    while any(groups[key] for key in order):

        for key in order:

            if groups[key]:
                result.append(groups[key].pop(0))

    return result


def find_replacement(video_id, title, artist="", language="",
                     exclude=None, permanent=True, channel=""):
    """
    Returns {"status": ..., "song": first | None, "songs": [pool]}.

    `exclude`   every video ID already in the person's playlist, so a
                replacement is never a duplicate.
    `permanent` the failure was permanent (100/101/150): the old ID is
                blacklisted.
    `channel`   uploader of the failed video — its other uploads are
                tried last, because they're almost certainly blocked too.
    """

    global _QUOTA_BLOCKED_UNTIL

    video_id = str(video_id or "").strip()

    if permanent:
        report_bad_video(video_id, channel)

    empty = {"song": None, "songs": []}

    if not YOUTUBE_API_KEY:
        return {"status": STATUS_NO_KEY, **empty}

    song = str(title or "").strip()[:150]
    artist = str(artist or "").strip()[:150]
    language = str(language or "").strip().lower()

    if not song:
        return {"status": STATUS_NO_RESULTS, **empty}

    excluded = {str(item) for item in (exclude or []) if item}
    excluded.add(video_id)
    excluded |= _all_bad_ids()

    cache_key = ("replace", _norm(song), _norm(artist))

    cached = _cache_get(cache_key)

    ranked = cached["songs"] if cached else None

    if ranked is None:

        if time.time() < _QUOTA_BLOCKED_UNTIL:
            return {"status": STATUS_QUOTA, **empty}

        try:
            ranked = _search_alternatives(song, artist, language)

        except _QuotaExceeded:
            _QUOTA_BLOCKED_UNTIL = time.time() + _QUOTA_BACKOFF_SECONDS
            return {"status": STATUS_QUOTA, **empty}

        if ranked is None:
            return {"status": STATUS_NETWORK, **empty}

        _cache_set(cache_key, {"songs": ranked})

    ordered = _interleave_channels(ranked, channel, excluded)[:MAX_ALTERNATIVES + 4]

    if not ordered:
        return {"status": STATUS_NO_RESULTS, **empty}

    # Free oEmbed probe (in parallel) on only the best few — probing the
    # whole pool would just make everyone wait for the slowest answer.
    head, tail = ordered[:PROBE_TOP], ordered[PROBE_TOP:]

    with ThreadPoolExecutor(max_workers=max(1, len(head))) as pool:
        verdicts = list(pool.map(
            lambda video: _oembed_ok(video["videoId"]), head
        ))

    playable = (
        [dict(video) for video, ok in zip(head, verdicts) if ok] +
        [dict(video) for video in tail]
    )[:MAX_ALTERNATIVES]

    if not playable:
        return {"status": STATUS_NO_RESULTS, **empty}

    return {"status": STATUS_OK, "song": playable[0], "songs": playable}