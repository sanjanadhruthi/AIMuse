"""
AIMuse — sample-song names
==========================

Turns the file names in static/moods/<mood>/ into a clean
(title, artist) pair for the UI.

Ripped / downloaded files are messy:

    "Keng Harit 'Mantra' (Khemjira The Series OST) Lyrics (Color Coded) - (320 Kbps).mp3"
    "New West - Those Eyes (Lyrics) - (320 Kbps).mp3"

Order of attempts (see sample_meta):
  1. exact match in SAMPLE_METADATA on the cleaned name,
  2. a known song whose title appears inside the name,
  3. otherwise split the cleaned name as "Artist - Title".

To fix a wrongly-labelled song, add or edit a line in SAMPLE_METADATA:
the KEY is the cleaned file name in lower case, the VALUE is
(title, artist).
"""

import re

SAMPLE_METADATA = {

    # happy
    "together with the wind": ("Together With The Wind", "Toma君想吃番茄"),
    "sapphire": ("Sapphire", "Ed Sheeran"),
    "permission to dance": ("Permission to Dance", "BTS"),
    "love you zindagi": ("Love You Zindagi", "Sony Music India"),
    "dreamers": ("Dreamers", "Jung Kook"),

    # sad
    "bulleya": ("Bulleya", "Sony Music India"),
    "dooron dooron": ("Dooron Dooron", "Paresh Pahuja"),
    "husn": ("Husn", "Anuv Jain"),
    "jeff satur - why don't you stay": ("Why Don't You Stay", "Jeff Satur"),
    "slander - love is gone": ("Love Is Gone", "SLANDER"),

    # calm
    "ruth b. - dandelions": ("Dandelions", "Ruth B."),
    "rihanna - somewhere only we know": ("Somewhere Only We Know", "Rihanna"),
    "kasturi": ("Kasturi", "Amar Prem Ki Prem Kahani"),
    "fade - jeff satur": ("Fade", "Jeff Satur"),
    "chemtrails over the country club": ("Chemtrails Over The Country Club", "Lana Del Rey"),

    # angry
    "believer": ("Believer", "Imagine Dragons"),
    "labour": ("Labour", "Paris Paloma"),
    "story of a warrior": ("Story of a Warrior", "Unknown"),
    "that's my girl": ("That's My Girl", "Fifth Harmony"),
    "usnisa vijaya dharani": ("Usnisa Vijaya Dharani", "Buddhist Mantra"),

    # romantic
    "yung kai - blue (with minnie)": ("blue", "yung kai (with MINNIE)"),
    "would you like that - 金銀玲 (jin yinling)": ("Would You Like That", "金銀玲 (Jin Yinling)"),
    "would you like that - 金银玲 (jin yinling)": ("Would You Like That", "金银玲 (Jin Yinling)"),
    "taylor swift - enchanted": ("Enchanted", "Taylor Swift"),
    "new west - those eyes": ("Those Eyes", "New West"),
    "keng harit 'mantra'": ("Mantra (Khemjira The Series OST)", "Keng Harit"),

    # energetic
    "seventeen super": ("Super", "SEVENTEEN"),
    "rihanna - breakin' dishes": ("Breakin' Dishes", "Rihanna"),
    "måneskin - beggin'": ("Beggin'", "Måneskin"),
    "like jennie - jennie mma": ("Like Jennie", "Jennie"),
    "jump": ("JUMP", "BLACKPINK"),

    # neutral
    "blossom all the way (yī lù shēng huā)": ("Blossom All the Way (一路生花)", "温奕心"),
    "duel in the mist - inazuma ost battle theme": ("Duel in the Mist - Inazuma OST Battle Theme", "Genshin Impact"),
    "kiliye (instrumental)": ("Kiliye (Instrumental)", "Dhibu Ninan Thomas"),
    "warm twilight": ("Warm Twilight", "Velvet Memories"),
    "road to success - lin wanxing theme": ("Road to Success - Lin Wanxing Theme", "Lin Wanxing")

}


# Junk that downloaded / ripped file names carry around:
#   "(320 Kbps)", "(Lyrics)", "(Color Coded)", "(Official Video)" ...
_SAMPLE_JUNK_BRACKETS = re.compile(
    r"[\(\[][^\)\]]*?\b(?:kbps|lyrics?|lyrical|official|audio|video|"
    r"color coded|colour coded|hd|4k|mv|m/v|visuali[sz]er|full song)\b"
    r"[^\)\]]*?[\)\]]",
    re.IGNORECASE
)

_SAMPLE_JUNK_WORDS = re.compile(
    r"\b(?:\d{2,3}\s*kbps|lyrics?|lyrical|color coded|colour coded|"
    r"official\s+(?:music\s+)?(?:video|audio)|full song)\b",
    re.IGNORECASE
)


def _clean_sample_stem(stem):
    """
    'Keng Harit 'Mantra' (Khemjira The Series OST) Lyrics (Color Coded) - (320 Kbps)'
        -> 'Keng Harit 'Mantra' (Khemjira The Series OST)'
    """

    text = stem.replace("_", " ")

    text = _SAMPLE_JUNK_BRACKETS.sub(" ", text)
    text = _SAMPLE_JUNK_WORDS.sub(" ", text)

    text = re.sub(r"\s+", " ", text)

    # dangling separators left behind ("Song - ", " - Artist")
    text = re.sub(r"^[\s\-–—]+|[\s\-–—]+$", "", text)

    return text.strip() or stem.strip()


def _sample_norm(text):

    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def _lookup_known_sample(cleaned):
    """
    1. exact match on the cleaned name,
    2. otherwise a known song whose title (>= 6 letters, so short
       ones like 'Jump' can't match by accident) is inside the name.
    """

    key = cleaned.lower().strip()

    if key in SAMPLE_METADATA:
        return SAMPLE_METADATA[key]

    haystack = _sample_norm(cleaned)

    for known_key, (title, artist) in SAMPLE_METADATA.items():

        wanted = _sample_norm(title)

        if len(wanted) >= 6 and wanted in haystack:
            return title, artist

        wanted_key = _sample_norm(known_key)

        if len(wanted_key) >= 6 and wanted_key in haystack:
            return title, artist

    return None


def sample_meta(stem):
    """
    (title, artist) for a sample file name.  Known songs come from
    SAMPLE_METADATA; anything else is cleaned and split as
    'Artist - Title'.
    """

    cleaned = _clean_sample_stem(stem)

    known = _lookup_known_sample(cleaned)

    if known:
        return known

    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", cleaned) if p.strip()]

    if len(parts) >= 2:
        return parts[1], parts[0]

    return cleaned, ""