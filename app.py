import difflib
import os
import re

from flask import Flask, jsonify, request, render_template, url_for

from src.preprocessing import preprocess_text
from src.sample_names import sample_meta
from src import curated_samples
from src.auth import init_auth
from src.youtube_recommender import (
    get_recommendations,
    find_replacement,
    apply_language_choice,
    report_bad_video,
    YOUTUBE_API_KEY
)


app = Flask(__name__, template_folder=".")

init_auth(app)    # accounts + database (src/auth.py, src/db.py)


@app.url_defaults
def static_file_version(endpoint, values):
    """
    Every url_for('static', ...) gets ?v=<file's last-change time>.
    Phones keep old CSS/JS in their cache; a new version number
    makes them download the changed file the moment it changes.
    """

    if endpoint != "static" or "filename" not in values:
        return

    path = os.path.join(app.static_folder, values["filename"])

    try:
        values["v"] = int(os.stat(path).st_mtime)
    except OSError:
        pass


# =========================================================
# AIMuse — EMOTIONAL UNDERSTANDING ENGINE
# =========================================================
#
# Core philosophy:
#
# AIMuse does NOT try to create hundreds of emotions.
#
# Instead, we have 7 core musical moods:
#
#     happy
#     sad
#     calm
#     angry
#     romantic
#     energetic
#     neutral
#
# The language around those moods can be much richer.
#
# Example:
#
#     "I'm exhausted and don't know what I'm feeling"
#
# does not create a new "exhausted" mood.
#
# It is understood as a neutral / in-between emotional state.
#
# Later, this rule-based emotional knowledge can become the
# foundation for a real ML/NLP model trained on mood examples.
# =========================================================


CORE_MOODS = [
    "happy",
    "sad",
    "calm",
    "angry",
    "romantic",
    "energetic",
    "neutral"
]


# =========================================================
# 01. MOOD KNOWLEDGE
# =========================================================
#
# These are not just random keywords.
#
# Each mood contains:
#
#     strong signals
#     supporting signals
#     phrases
#
# Strong signals carry more weight because they are more
# emotionally specific.
#
# Supporting signals are weaker contextual clues.
# =========================================================


MOOD_KNOWLEDGE = {

    "happy": {

        "strong": [
            "happy",
            "joyful",
            "delighted",
            "thrilled",
            "cheerful",
            "ecstatic",
            "overjoyed",
            "blissful",
            "elated",
            "content",
            "euphoric"
        ],

        "supporting": [
            "good",
            "great",
            "amazing",
            "wonderful",
            "fun",
            "smiling",
            "laughing",
            "positive",
            "celebrate",
            "celebrating",
            "celebratory",
            "grateful",
            "glad",
            "pleased",
            "excited",
            "amused",
            "satisfied",
            "surprised",
            "amazed",
            "astonished",
            "hopeful",
            "sociable",
            "welcomed",
            "cooperative",
            "accepted",
            "cute",
            "magical",
            "whimsical"
        ],

        "phrases": [
            "feeling good",
            "feeling great",
            "in a good mood",
            "best day",
            "so happy",
            "really happy",
            "can't stop smiling",
            "feeling amazing",
            "life feels good"
        ]
    },


    "sad": {

        "strong": [
            "sad",
            "heartbroken",
            "devastated",
            "miserable",
            "hopeless",
            "grief",
            "grieving",
            "crying",
            "sobbing"
        ],

        "supporting": [
            "lonely",
            "alone",
            "hurt",
            "pain",
            "upset",
            "lost",
            "unhappy",
            "down",
            "tears",
            "miss",
            "missing",
            "regret",
            "empty",
            "disappointed",
            "vulnerable",
            "nostalgic",
            "melancholic",
            "afraid",
            "anxious",
            "nervous",
            "worried",
            "uneasy",
            "insecure",
            "panicked",
            "suspicious",
            "dreadful",
            "rejected",
            "bittersweet",
            "regretful",
            "guilty",
            "ashamed",
            "homesick",
            "desperate",
            "disillusioned",
            "defeated",
            "discouraged",
            "isolated",
            "dark",
            "haunting"
        ],

        "phrases": [
            "feeling sad",
            "feel so alone",
            "feel completely alone",
            "can't stop crying",
            "feel like crying",
            "heart feels heavy",
            "broken inside",
            "nothing feels right",
            "miss them",
            "miss someone"
        ]
    },


    "calm": {

        "strong": [
            "calm",
            "peaceful",
            "relaxed",
            "serene",
            "tranquil",
            "content"
        ],

        "supporting": [
            "quiet",
            "comfortable",
            "soft",
            "peace",
            "chill",
            "restful",
            "still",
            "gentle",
            "slow",
            "breathing",
            "meditation",
            "mindful",
            "settled",
            "at ease",
            "soothing",
            "meditative",
            "centered",
            "grounded",
            "relieved",
            "forgiving",
            "focused",
            "productive",
            "disciplined",
            "spiritual",
            "ethereal",
            "hypnotic",
            "comfort"
        ],

        "phrases": [
            "feeling calm",
            "feeling peaceful",
            "feel at peace",
            "at ease",
            "nice and quiet",
            "completely relaxed",
            "peace of mind",
            "slow evening",
            "quiet moment"
        ]
    },


    "angry": {

        "strong": [
            "angry",
            "furious",
            "rage",
            "raging",
            "enraged",
            "outraged",
            "mad"
        ],

        "supporting": [
            "annoyed",
            "irritated",
            "frustrated",
            "frustrating",
            "hate",
            "fed",
            "aggressive",
            "pissed",
            "resentful",
            "infuriated",
            "irritating",
            "bitter",
            "hostile",
            "defiant",
            "disgusted",
            "repulsed",
            "disturbed",
            "contemptuous",
            "jealous",
            "envious",
            "distrustful"
        ],

        "phrases": [
            "so angry",
            "really angry",
            "extremely angry",
            "fed up",
            "sick of this",
            "had enough",
            "can't stand this",
            "driving me crazy",
            "makes me angry"
        ]
    },


    "romantic": {

        "strong": [
            "romantic",
            "romance",
            "crush",
            "lover",
            "affection",
            "adore",
            "infatuated",
            "affectionate",
            "adoring"
        ],

        "supporting": [
            "love",
            "loving",
            "date",
            "dating",
            "relationship",
            "kiss",
            "kissing",
            "beautiful",
            "together",
            "partner",
            "darling",
            "someone",
            "attracted",
            "passionate",
            "intimate",
            "tender",
            "flirty",
            "yearning",
            "connected",
            "sensual",
            "elegant",
            "enchanting",
            "soulful"
        ],

        "phrases": [
            "in love",
            "falling in love",
            "thinking about them",
            "thinking about someone",
            "miss my love",
            "want to be with them",
            "can't stop thinking about them",
            "feel close to someone",
            "my person"
        ]
    },


    "energetic": {

        "strong": [
            "energetic",
            "energy",
            "hyped",
            "hype",
            "motivated",
            "powerful",
            "excited"
        ],

        "supporting": [
            "dance",
            "party",
            "workout",
            "gym",
            "motivation",
            "strong",
            "active",
            "alive",
            "charged",
            "pumped",
            "ready",
            "drive",
            "adventure",
            "adventurous",
            "confident",
            "bold",
            "fearless",
            "rebellious",
            "frenzied",
            "victorious",
            "determined",
            "ambitious",
            "inspired",
            "empowered",
            "mischievous",
            "competitive",
            "intense",
            "epic",
            "triumphant"
        ],

        "phrases": [
            "full of energy",
            "feeling energetic",
            "ready to go",
            "can't sit still",
            "want to dance",
            "let's go",
            "feeling pumped",
            "ready for anything",
            "full of life"
        ]
    }
}


# =========================================================
# 02. SECONDARY / IN-BETWEEN EMOTIONAL STATES
# =========================================================
#
# These are intentionally NOT separate AIMuse moods.
#
# They describe a person's state, but do not necessarily tell
# us what musical emotional direction they want.
#
# Therefore:
#
#     confused
#     exhausted
#     tired
#     drained
#     overwhelmed
#     uncertain
#     unsure
#     conflicted
#     bored
#     numb
#     blank
#
# are treated as NEUTRAL when they appear without a stronger
# core mood.
#
# We give these states high confidence because AIMuse is
# deliberately saying:
#
#     "I understand that this isn't clearly one of my
#      core emotional directions."
#
# =========================================================


NEUTRAL_STATES = {

    "confused",
    "confusing",
    "uncertain",
    "unsure",
    "unclear",
    "conflicted",
    "torn",
    "exhausted",
    "exhausting",
    "tired",
    "drained",
    "burnt",
    "burned",
    "burnout",
    "overwhelmed",
    "overwhelming",
    "bored",
    "boring",
    "numb",
    "blank",
    "indifferent",
    "unsure",
    "okay",
    "ok",
    "fine",
    "normal",
    "whatever",
    "meh",
    "nothing",
    "nothingness",
    "stressed",
    "stressful",
    "restless",
    "sleepy",
    "groggy",
    "foggy",
    "distracted",
    "spacedout",
    "sluggish",
    "lazy",
    "reflective",
    "contemplative",
    "thoughtful",
    "pensive",
    "philosophical",
    "curious",
    "intrigued",
    "bewildered",
    "shocked",
    "unbothered",
    "detached",
    "apathetic",
    "embarrassed",
    "awkward",
    "resigned",
    "unmotivated"
}


NEUTRAL_STATE_PHRASES = [

    "don't know what i feel",
    "dont know what i feel",
    "don't know how i feel",
    "dont know how i feel",
    "not sure how i feel",
    "not sure what i feel",
    "i feel confused",
    "i'm confused",
    "im confused",
    "i feel exhausted",
    "i'm exhausted",
    "im exhausted",
    "i feel drained",
    "i'm drained",
    "im drained",
    "i feel tired",
    "i'm tired",
    "im tired",
    "i feel overwhelmed",
    "i'm overwhelmed",
    "im overwhelmed",
    "i feel numb",
    "i'm numb",
    "im numb",
    "nothing in particular",
    "not feeling anything",
    "don't feel anything",
    "dont feel anything",
    "i feel stressed",
    "i'm stressed",
    "im stressed",
    "i feel restless",
    "i'm restless",
    "im restless",
    "self conscious",
    "emotionally conflicted",
    "emotionally numb",
    "comfort seeking"
]


# =========================================================
# 03. EMOTION VALENCE
# =========================================================

EMOTION_VALENCE = {

    "happy": "positive",
    "energetic": "positive",
    "romantic": "positive",

    "calm": "neutral",
    "neutral": "neutral",

    "sad": "negative",
    "angry": "negative"
}


# =========================================================
# 03B. AROUSAL (ENERGY) + CONTEXT TAGS
# =========================================================
#
# Emotion isn't the whole picture — the roadmap's dimensional
# model calls out arousal (energy) and context as their own
# axes, separate from which of the 7 core moods wins.
#
# These run independently of the core-mood scoring above and
# never change which mood or confidence gets returned — they
# only add two extra, purely descriptive fields.
#
# NOTE: dominance (powerless <-> powerful) and social
# (isolated <-> connected) from the same chart are NOT
# implemented here. A keyword list can't say much reliable
# about those two without turning into guesswork, so rather
# than fake it, they're left out until there's a real way to
# measure them.
# =========================================================

HIGH_AROUSAL_WORDS = {
    "energetic", "energy", "hyped", "hype", "motivated", "powerful",
    "excited", "pumped", "ready", "adventurous", "thrilled", "confident",
    "bold", "fearless", "aggressive", "rebellious", "chaotic", "frenzied",
    "ecstatic", "euphoric", "victorious", "determined", "furious", "rage",
    "raging", "enraged", "outraged", "mad", "anxious", "nervous", "panicked",
    "worried", "uneasy", "insecure", "intense", "epic", "triumphant",
    "ambitious", "inspired", "empowered", "mischievous", "competitive",
    "hostile", "defiant", "dreadful"
}

LOW_AROUSAL_WORDS = {
    "calm", "peaceful", "relaxed", "serene", "tranquil", "sleepy", "tired",
    "drained", "exhausted", "lazy", "dreamy", "soothing", "meditative",
    "centered", "grounded", "sad", "heartbroken", "devastated", "miserable",
    "hopeless", "grief", "grieving", "empty", "lonely", "numb", "blank",
    "resigned", "melancholic", "quiet", "restful", "still", "gentle",
    "slow", "mystical", "ethereal", "hypnotic", "spiritual", "focused",
    "productive", "disciplined", "defeated", "discouraged"
}


CONTEXT_TAGS = {

    "romantic": [
        "romantic", "romance", "love", "loving", "affection",
        "affectionate", "crush", "adore", "adoring", "infatuated",
        "intimate", "passionate", "sensual", "flirty", "tender",
        "enchanting"
    ],

    "motivational": [
        "motivated", "motivation", "determined", "ambitious", "inspired",
        "empowered", "victorious", "fearless", "rebellious", "disciplined",
        "productive", "driven"
    ],

    "nostalgic": [
        "nostalgic", "nostalgia", "longing", "yearning", "homesick",
        "bittersweet", "reminisce", "memories"
    ],

    "spiritual": [
        "spiritual", "soulful", "meditation", "meditative", "mindful",
        "mystical", "sacred", "divine"
    ],

    "reflective": [
        "thoughtful", "reflective", "contemplative", "pensive",
        "philosophical", "introspective"
    ],

    "aesthetic": [
        "dreamy", "ethereal", "cinematic", "mystical", "dark",
        "mysterious", "haunting", "magical", "whimsical", "atmospheric",
        "hypnotic", "epic", "triumphant", "elegant", "majestic",
        "enchanting", "soulful"
    ]

}


def detect_arousal(words):
    """
    Returns "high", "low", or "medium" energy — separate from
    which mood won, since a sad song and an angry song can
    both be "high arousal" while a calm one and a hopeless one
    can both be "low arousal".
    """

    high = sum(1 for word in words if word in HIGH_AROUSAL_WORDS)
    low = sum(1 for word in words if word in LOW_AROUSAL_WORDS)

    if high == 0 and low == 0:
        return "medium"

    if high > low:
        return "high"

    if low > high:
        return "low"

    return "medium"


def detect_context(normalized, words):
    """
    Returns the list of context tags whose keywords appear in
    the text (romantic / motivational / nostalgic / spiritual
    / reflective / aesthetic). A text can match more than one.
    """

    word_set = set(words)
    matched = []

    for tag, keywords in CONTEXT_TAGS.items():

        for keyword in keywords:

            if " " in keyword:
                found = keyword in normalized
            else:
                found = keyword in word_set

            if found:
                matched.append(tag)
                break

    return matched


def label_intensity(confidence):
    """
    A friendly subtle <-> extreme label over the existing
    confidence score — presentation only, changes nothing
    about how confidence itself is calculated.
    """

    if confidence >= 0.9:
        return "extreme"

    if confidence >= 0.75:
        return "intense"

    if confidence >= 0.55:
        return "moderate"

    return "subtle"


# =========================================================
# 04. INTENSIFIERS
# =========================================================
#
# These make the engine understand:
#
#     "a little sad"
#
# differently from:
#
#     "completely devastated"
#
# =========================================================


INTENSIFIERS = {

    "very": 1.25,
    "really": 1.25,
    "extremely": 1.50,
    "completely": 1.50,
    "absolutely": 1.50,
    "deeply": 1.45,
    "totally": 1.40,
    "so": 1.20,
    "super": 1.30,
    "incredibly": 1.45,
    "slightly": 0.70,
    "a little": 0.65,
    "little": 0.70
}


# =========================================================
# 05. NEGATION
# =========================================================
#
# Simple contextual handling:
#
#     "not sad"
#     "don't feel angry"
#     "not happy"
#
# should not automatically become that emotion.
#
# =========================================================


NEGATION_WORDS = {
    "not",
    "no",
    "never",
    "dont",
    "don't",
    "isnt",
    "isn't",
    "wasnt",
    "wasn't",
    "cant",
    "can't",
    "cannot",
    "hardly"
}


# =========================================================
# 06. TEXT NORMALIZATION
# =========================================================

def normalize_text(text):

    text = preprocess_text(text)

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# =========================================================
# 07. CONTEXTUAL WORD WEIGHT
# =========================================================

def get_context_multiplier(words, index):

    multiplier = 1.0

    start = max(0, index - 3)

    nearby = words[start:index]

    for word in nearby:

        if word in INTENSIFIERS:
            multiplier *= INTENSIFIERS[word]

    return multiplier


# =========================================================
# 08. NEGATION CHECK
# =========================================================

def is_negated(words, index):

    start = max(0, index - 3)

    nearby = words[start:index]

    return any(
        word in NEGATION_WORDS
        for word in nearby
    )


# =========================================================
# 09. PHRASE SCORING
# =========================================================

PHRASE_WEIGHT = 3


def _phrase_is_negated(text, start, end):
    """
    "not feeling good" -> the phrase "feeling good" is negated.
    Looks at up to 3 words BEFORE the phrase (English negation) and
    2 words AFTER it (Hindi: "khush hoon nahi"), with the same
    "can't stop / can't help" exception as single words.
    """

    before = text[:start].split()[-3:]

    for position, word in enumerate(before):

        if word in NEGATION_WORDS:

            if any(item in NEGATION_BREAKERS for item in before[position + 1:]):
                return False

            return True

    after = text[end:].split()[:2]

    return any(word in POST_NEGATION_WORDS for word in after)


def score_phrases(text, knowledge):
    """
    Returns (score, matched, negated).  A phrase that is itself
    negated ("not feeling good") scores nothing for its mood; its
    weight goes to `negated`, which detect_emotion flips to the
    opposite mood — exactly like a negated single word.
    """

    score = 0
    negated = 0

    matched = []

    for phrase in knowledge.get("phrases", []):

        # whole-word start, so "mood on" can't match "mood one"
        match = re.search(r"(?<![\w'])" + re.escape(phrase), text)

        if not match:
            continue

        # Phrases that already contain a negation ("not okay",
        # "acha nahi") are judged as written.
        phrase_words = set(phrase.split())
        has_own_negation = bool(
            phrase_words & (NEGATION_WORDS | POST_NEGATION_WORDS)
        )

        if not has_own_negation and _phrase_is_negated(text, match.start(), match.end()):
            negated += PHRASE_WEIGHT
            continue

        score += PHRASE_WEIGHT

        matched.append(phrase)

    return score, matched, negated


# =========================================================
# 10. WORD SCORING
# =========================================================

def score_words(words, knowledge):

    score = 0

    matched = []

    strong_words = set(
        knowledge.get("strong", [])
    )

    supporting_words = set(
        knowledge.get("supporting", [])
    )

    for index, word in enumerate(words):

        if is_negated(words, index):
            continue

        multiplier = get_context_multiplier(words, index) 

        if word in strong_words:

            score += 3 * multiplier

            matched.append(word)

        elif word in supporting_words:

            score += 1 * multiplier

            matched.append(word)

    return score, matched


# =========================================================
# 11. NEUTRAL STATE DETECTION
# =========================================================

def detect_neutral_state(text, words):

    matched = []

    for phrase in NEUTRAL_STATE_PHRASES:

        if phrase in text:
            matched.append(phrase)

    for index, word in enumerate(words):

        # "not okay" / "not fine" is NOT an in-between state — it is
        # handled as sadness by the phrase list instead.
        if word in NEUTRAL_STATES and not is_negated_v2(words, index):
            matched.append(word)

    return list(dict.fromkeys(matched))


# =========================================================
# 06B. WORD-SHAPE PLAUSIBILITY (BACKEND SAFETY NET)
# =========================================================
#
# Mirrors the same check the frontend already runs before a
# request is even sent. This exists purely as a safety net —
# in case the frontend check is ever bypassed — so AIMuse
# never dresses up nonsense as a confident "neutral" mood.
#
# A word can contain vowels and still not be a real English
# word: "rtjulyi" has two vowels, but no English word starts
# with "rt" or "rtj". Real words only ever open with a small,
# known set of consonant clusters.
# =========================================================


VALID_INITIAL_CLUSTERS = {
    "bl", "br", "ch", "ck", "cl", "cr", "dr", "dw",
    "fl", "fr", "gh", "gl", "gn", "gr", "kn", "ph",
    "pl", "pr", "ps", "pt", "qu", "rh", "sc", "sh",
    "sk", "sl", "sm", "sn", "sp", "st", "sw", "th",
    "tr", "tw", "wh", "wr",
    "sch", "scr", "shr", "spl", "spr", "squ", "str", "thr",
    # Romanised Hindi / Telugu / Tamil ("bhot", "dhoka", "khush",
    # "jhooth", "gyaan", "kyun", "pyaar", "nyay", "tyohar", "chhod")
    "bh", "dh", "kh", "jh", "gy", "ky", "py", "ny", "ty", "by", "my",
    "chh"
}


def looks_like_gibberish_word(word):

    letters_only = re.sub(r"[^a-z]", "", word)

    # "y" counts as a vowel here: rhythm, myself, crying, system.
    if len(letters_only) >= 6 and not re.search(r"[aeiouy]", letters_only):
        return True

    if len(letters_only) < 4:
        return False

    leading = re.match(r"^[^aeiouy]+", letters_only)

    if leading and len(leading.group(0)) >= 2:

        cluster = leading.group(0)

        if cluster[:2] not in VALID_INITIAL_CLUSTERS and \
           cluster[:3] not in VALID_INITIAL_CLUSTERS:
            return True

    return False


def looks_like_gibberish_text(words):

    if not words:
        return False

    joined = "".join(words)

    keyboard_patterns = [
        "asdfgh", "qwerty", "zxcvbn", "qazwsx", "wsxedc"
    ]

    if any(pattern in joined for pattern in keyboard_patterns):
        return True

    flagged = sum(
        1 for word in words if looks_like_gibberish_word(word)
    )

    return flagged >= max(1, len(words) // 2) if len(words) <= 4 else flagged / len(words) >= 0.5


# =========================================================
# 12. INTELLIGENCE LAYER
# =========================================================
#
# v1 counted keywords.  v2 understands a few things a keyword
# counter can't:
#
#   - EXTRA VOCABULARY + LIGHT MORPHOLOGY + TYPO TOLERANCE
#       "cried", "happier", "frustated", "heartbrokn" all resolve
#       to the signal words above.
#   - CLAUSES, CONTRAST AND TIME
#       "I was sad yesterday but I'm finally happy now" is HAPPY:
#       the later clause carries more weight and past-tense
#       clauses count for less than present ones.
#   - SMARTER NEGATION
#       "not happy" nudges toward sad, "not angry" toward calm,
#       and "can't stop smiling" is NOT treated as negated.
#   - EMOJI
#       😭 💔 😡 ❤️ 🔥 😴 ... are read before text preprocessing
#       can strip them.
#   - BLENDS
#       A secondary mood is reported when two moods are close.
#   - PREFERENCES
#       "hindi songs for studying", "lofi for a rainy night",
#       "songs like Arijit Singh" are understood and forwarded to
#       the recommender, so the playlist reflects what the person
#       actually asked for — not just their mood label.
# =========================================================


EXTRA_SIGNALS = {

    "happy": {
        "strong": ["joy", "radiant", "glowing", "jubilant"],
        "supporting": [
            "vibing", "yay", "blessed", "proud", "sunny", "smile",
            "smiled", "laugh", "laughed", "exciting", "lucky",
            "winning", "won", "promoted", "hired", "graduated"
        ],
        "phrases": [
            "on top of the world", "good news", "got the job",
            "nailed it", "passed my exam", "made my day",
            "so proud", "feeling lucky"
        ]
    },

    "sad": {
        "strong": [
            "depressed", "heartache", "heartbreak", "cry", "cried",
            "sob", "weeping", "weep", "gloomy", "sorrow", "mourning"
        ],
        "supporting": [
            "breakup", "lonesome", "hurting", "missed",
            "longing", "tearful", "shattered", "abandoned",
            "betrayed", "unloved", "worthless"
        ],
        "phrases": [
            "broke up", "broken heart", "lost someone", "passed away",
            "miss you", "no one cares", "feel empty", "want to cry",
            "feel like nothing matters"
        ]
    },

    "calm": {
        "strong": ["unwind", "unwinding"],
        "supporting": [
            "chilling", "cozy", "cosy", "mellow", "easygoing",
            "tranquility", "stillness", "sunday"
        ],
        "phrases": [
            "taking it easy", "winding down", "sunday morning",
            "no rush", "feeling zen"
        ]
    },

    "angry": {
        "strong": ["livid", "seething", "fuming", "irate", "hated"],
        "supporting": [
            "annoying", "ugh", "toxic", "betrayal", "unfair",
            "disrespected", "furiously", "screw"
        ],
        "phrases": [
            "so done", "screw this", "sick and tired", "lost my temper",
            "want to scream", "can't take it anymore"
        ]
    },

    "romantic": {
        "strong": ["smitten", "besotted", "soulmate"],
        "supporting": [
            "crushing", "butterflies", "valentine", "wedding",
            "anniversary", "cuddle", "cuddling", "babe", "honey"
        ],
        "phrases": [
            "love of my life", "head over heels", "missing you",
            "want to hold you", "candlelight dinner"
        ]
    },

    "energetic": {
        "strong": ["pumped", "hyped", "unstoppable", "adrenaline"],
        "supporting": [
            "sprint", "running", "grind", "hustle", "beast",
            "rave", "festival", "lifting", "cardio", "fired"
        ],
        "phrases": [
            "fired up", "beast mode", "on fire", "let's do this",
            "can't wait", "bring it on"
        ]
    }

}


# ---------------------------------------------------------
# 12-I. HINGLISH / INDIAN-ENGLISH
# ---------------------------------------------------------
#
# AIMuse's default languages are Hindi, Telugu and English, so its
# users type the way people text in India: "mood off yaar",
# "bahut tension hai", "aaj khush hoon".  Romanised spellings vary
# a lot, so the common variants are listed explicitly.
# ---------------------------------------------------------

HINGLISH_SIGNALS = {

    "happy": {
        "strong": ["khush", "khushi", "santosham", "anandam"],
        "supporting": [
            "mast", "badhiya", "badiya", "bindaas", "maza", "mazaa",
            "mazza", "bagundi", "superb", "awesome"
        ],
        "phrases": [
            "mood on", "maza aa gaya", "mazaa aa gaya", "dil khush",
            "bahut khush", "full happy", "chala bagundi"
        ]
    },

    "sad": {
        "strong": [
            "dukhi", "udaas", "udas", "rona", "baadha", "failure",
            "hopeless"
        ],
        "supporting": [
            "akela", "akeli", "tanha", "dard", "useless", "loser",
            "failed", "failing", "pointless", "rejection"
        ],
        "phrases": [
            "mood off", "mood kharab", "mood is off", "acha nahi",
            "accha nahi", "achha nahi", "nahi lag raha", "nahi lag rha",
            "dil toot", "dil tut", "dil dukh", "bura lag", "rona aa",
            "feeling low", "feel low", "feeling down", "not okay",
            "not ok", "not fine", "not good", "not alright",
            "not doing well", "not well", "tired of trying",
            "tired of everything", "give up", "giving up",
            "what's the point", "whats the point", "nothing matters",
            "not good enough", "never good enough", "let everyone down",
            "let myself down", "everything is going wrong"
        ]
    },

    "calm": {
        "strong": ["sukoon", "shanti", "prashanti"],
        "supporting": ["araam", "aaram", "chai", "thanda"],
        "phrases": ["sukoon chahiye", "dil ko sukoon", "peace chahiye"]
    },

    "angry": {
        "strong": ["gussa", "gusse", "kopam"],
        "supporting": ["irritate", "irritating", "chid", "chidchida", "bakwas"],
        "phrases": [
            "dimag kharab", "dimaag kharab", "bahut gussa",
            "pagal kar diya", "sar dard"
        ]
    },

    "romantic": {
        "strong": ["pyaar", "pyar", "ishq", "mohabbat", "prema", "prem"],
        "supporting": ["jaan", "jaanu", "dil", "saathi"],
        "phrases": ["pyaar ho gaya", "dil de", "uski yaad"]
    },

    "energetic": {
        "strong": ["josh", "jazba"],
        "supporting": ["dhamaka", "jhakaas", "zabardast"],
        "phrases": ["full josh", "full power", "full energy", "chalo let's go"]
    }

}


def _merge_extra_signals():

    for mood, groups in EXTRA_SIGNALS.items():

        for group, entries in groups.items():

            existing = MOOD_KNOWLEDGE[mood].setdefault(group, [])

            for entry in entries:
                if entry not in existing:
                    existing.append(entry)


_merge_extra_signals()


def _merge_hinglish_signals():

    for mood, groups in HINGLISH_SIGNALS.items():

        for group, entries in groups.items():

            existing = MOOD_KNOWLEDGE[mood].setdefault(group, [])

            for entry in entries:
                if entry not in existing:
                    existing.append(entry)


_merge_hinglish_signals()

# ---- more everyday phrasing (found by testing real sentences) ----

_EVERYDAY_EXTRA = {
    "sad": {
        "strong": ["disappointed", "betrayed", "abandoned", "badhaga", "baadhaga", "edupu"],
        "supporting": [
            "ignored", "ignoring", "scared", "afraid", "terrified",
            "unmotivated", "useless", "badha", "baadha"
        ],
        "phrases": [
            "worst day", "bad day", "terrible day", "horrible day",
            "don't feel like doing anything", "no motivation",
            "can't get out of bed", "left out", "let down",
            "nobody cares", "no one cares", "badhaga undi", "chala badha"
        ]
    }
}

for _mood, _groups in _EVERYDAY_EXTRA.items():
    for _group, _entries in _groups.items():
        _existing = MOOD_KNOWLEDGE[_mood].setdefault(_group, [])
        for _entry in _entries:
            if _entry not in _existing:
                _existing.append(_entry)


NEUTRAL_STATES |= {"bore", "boring", "tension", "tensed", "confuse"}
NEUTRAL_STATE_PHRASES += [
    "bore ho raha", "bore ho rahi", "bore ho rha", "bore ho rhi",
    "pata nahi", "pata nhi", "kuch nahi", "tension hai"
]


# ---------------------------------------------------------
# Apostrophe-free twins of every phrase.
#
# preprocess_text() strips everything except letters and
# spaces, so "can't stop smiling" arrives as "cant stop
# smiling" and "i'm tired" as "im tired". Without these twins
# no phrase containing an apostrophe could ever match.
# ---------------------------------------------------------

def _apostrophe_free(phrase):

    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s]", "", phrase.lower())).strip()


def _add_phrase_twins(phrases):

    for phrase in list(phrases):

        twin = _apostrophe_free(phrase)

        if twin and twin not in phrases:
            phrases.append(twin)


for _knowledge in MOOD_KNOWLEDGE.values():
    _add_phrase_twins(_knowledge.setdefault("phrases", []))

_add_phrase_twins(NEUTRAL_STATE_PHRASES)


# ---------------------------------------------------------
# 12A. VOCABULARY, MORPHOLOGY AND TYPO TOLERANCE
# ---------------------------------------------------------

def _build_signal_vocab():

    vocab = set()

    for knowledge in MOOD_KNOWLEDGE.values():

        for group in ("strong", "supporting"):

            for entry in knowledge.get(group, []):

                if " " not in entry:
                    vocab.add(entry)

    vocab |= set(NEUTRAL_STATES)
    vocab |= HIGH_AROUSAL_WORDS
    vocab |= LOW_AROUSAL_WORDS

    return vocab


SIGNAL_VOCAB = _build_signal_vocab()

_VOCAB_BY_INITIAL = {}

for _entry in SIGNAL_VOCAB:
    _VOCAB_BY_INITIAL.setdefault(_entry[0], []).append(_entry)

_RESOLVE_CACHE = {}


def _word_forms(word):
    """
    Cheap, dependency-free stemming: candidate base forms of a
    word ("crying" -> "cry", "happier" -> "happy", "loved" ->
    "love").  Every form is checked against the signal vocabulary,
    so a wrong stem is harmless.
    """

    forms = [word]

    if word.endswith("ies") and len(word) > 4:
        forms.append(word[:-3] + "y")

    if word.endswith("ied") and len(word) > 4:
        forms.append(word[:-3] + "y")

    if word.endswith("ier") or word.endswith("iest"):
        forms.append(re.sub(r"ie(r|st)$", "y", word))

    for suffix in ("ing", "ed", "es", "s", "ly", "ness", "er", "est"):

        if word.endswith(suffix) and len(word) - len(suffix) >= 3:

            stem = word[:-len(suffix)]

            forms.append(stem)
            forms.append(stem + "e")

            if len(stem) >= 2 and stem[-1] == stem[-2]:
                forms.append(stem[:-1])

    return forms


def resolve_word(word):
    """
    Maps a word to the signal-vocabulary word it means: itself if
    known, else a stemmed form, else a close spelling (typo).
    Unknown words are returned unchanged.
    """

    if word in SIGNAL_VOCAB or len(word) < 4 or not word.isalpha():
        return word

    cached = _RESOLVE_CACHE.get(word)

    if cached is not None:
        return cached

    result = word

    for form in _word_forms(word):

        if form in SIGNAL_VOCAB:
            result = form
            break

    else:

        if len(word) >= 5:

            pool = [
                candidate for candidate in _VOCAB_BY_INITIAL.get(word[0], [])
                if abs(len(candidate) - len(word)) <= 2
            ]

            matches = difflib.get_close_matches(
                word, pool, n=1, cutoff=0.86
            )

            if matches:
                result = matches[0]

    _RESOLVE_CACHE[word] = result

    return result


# ---------------------------------------------------------
# 12B. EMOJI
# ---------------------------------------------------------

EMOJI_MOODS = {

    "sad": "😢😭😞😔💔🥺😿☹🙁😥😓😩😪🌧",
    "angry": "😡😠🤬👿💢😤🖕",
    "happy": "😀😃😄😁😊🙂😂🤣🥳🎉😆😎🤩☀🌈✨",
    "romantic": "❤💕💖😍🥰😘💘💗💞💓💝😻🌹",
    "calm": "😌🧘☺🌿🍃☁🕊🌊🍵☕🌙",
    "energetic": "🔥💪🚀⚡🏋🏃🕺💃🎸🤘"
}

NEUTRAL_EMOJI = "😐😑😴🥱😵🤷😶🙃"
HIGH_EMOJI = "🔥💪🚀⚡🏋🏃🕺💃🤬😡🤩"
LOW_EMOJI = "😴🥱😔😢😭😌🧘🌙😞"

_EMOJI_TO_MOOD = {
    char: mood
    for mood, chars in EMOJI_MOODS.items()
    for char in chars
}


def read_emoji(raw_text):
    """
    Returns (scores_by_mood, neutral_hits, high_count, low_count).
    Each emoji is worth 2 points, capped at 3 per mood so a wall of
    emoji can't overwhelm the words.
    """

    counts = {}
    neutral = 0
    high = 0
    low = 0

    for char in raw_text:

        mood = _EMOJI_TO_MOOD.get(char)

        if mood:
            counts[mood] = counts.get(mood, 0) + 1

        if char in NEUTRAL_EMOJI:
            neutral += 1

        if char in HIGH_EMOJI:
            high += 1

        if char in LOW_EMOJI:
            low += 1

    scores = {
        mood: 2.0 * min(count, 3)
        for mood, count in counts.items()
    }

    return scores, neutral, high, low


# ---------------------------------------------------------
# 12C. CLAUSES, CONTRAST AND TIME
# ---------------------------------------------------------

SENTENCE_SPLIT = re.compile(r"[.!?;\n]+")

CONTRAST_SPLIT = re.compile(
    r"\b(?:but|however|although|though|yet|except|otherwise|anyway)\b",
    re.IGNORECASE
)

PAST_MARKERS = {
    "was", "were", "used", "yesterday", "earlier", "before",
    "previously", "ago", "last"
}

PRESENT_MARKERS = {
    "now", "today", "currently", "still", "tonight", "finally",
    "lately", "these", "days"
}

# Words that end a negation's reach: "can't STOP smiling",
# "not angry, JUST disappointed" (commas are stripped by the
# preprocessing, so these words are the only clue left).
NEGATION_BREAKERS = {"stop", "help", "but", "just", "only", "rather", "actually"}

# Hindi puts the negation AFTER the word: "khush nahi hoon".
POST_NEGATION_WORDS = {"nahi", "nahin", "nhi", "mat"}

# "low energy", "no energy", "zero energy" deny energy even though
# the word itself is a strong energetic signal.
ENERGY_DENIERS = {
    "low", "no", "zero", "little", "less", "lack", "lacking", "without"
}


def split_clauses(text):

    pieces = []

    for sentence in SENTENCE_SPLIT.split(text):

        for piece in CONTRAST_SPLIT.split(sentence):

            if piece and piece.strip():
                pieces.append(piece.strip())

    return pieces or [text]


def position_weight(index, total):
    """
    Later clauses matter more: "I was sad, but now I'm okay".
    Ranges from 0.85 (first) to 1.2 (last).
    """

    if total <= 1:
        return 1.0

    return 0.85 + 0.35 * (index / (total - 1))


def temporal_weight(words):

    word_set = set(words)

    past = bool(word_set & PAST_MARKERS)
    present = bool(word_set & PRESENT_MARKERS)

    if present:
        return 1.15

    if past:
        return 0.6

    return 1.0


def is_negated_v2(words, index):
    """
    Like is_negated(), but "can't stop smiling" / "can't help
    crying" are not negations of the feeling — the negation word
    applies to "stop", not to "smiling".
    """

    if any(word in POST_NEGATION_WORDS for word in words[index + 1:index + 3]):
        return True

    start = max(0, index - 3)

    window = words[start:index]

    for position, word in enumerate(window):

        if word in NEGATION_WORDS:

            after = window[position + 1:]

            if any(item in NEGATION_BREAKERS for item in after):
                return False

            return True

    return False


def score_words_v2(words, knowledge):
    """
    Returns (score, matched_words, negated_amount).
    `negated_amount` measures how strongly this mood was denied —
    used to nudge toward the opposite mood ("not happy").
    """

    score = 0.0
    negated = 0.0
    matched = []

    strong_words = set(knowledge.get("strong", []))
    supporting_words = set(knowledge.get("supporting", []))

    for index, word in enumerate(words):

        is_strong = word in strong_words
        is_supporting = word in supporting_words

        if not (is_strong or is_supporting):
            continue

        base = 3 if is_strong else 1

        lacks_energy = (
            word in ("energy", "energetic") and
            index > 0 and
            words[index - 1] in ENERGY_DENIERS
        )

        if lacks_energy or is_negated_v2(words, index):
            negated += base * 0.5
            continue

        score += base * get_context_multiplier(words, index)
        matched.append(word)

    return score, matched, negated


# "I'm not X" -> where does the evidence go instead?
NEGATION_FLIPS = {
    "happy": ("sad", 0.8),
    "romantic": ("sad", 0.4),
    "sad": ("calm", 0.6),
    "angry": ("calm", 0.6)
}


# ---------------------------------------------------------
# 12D. AROUSAL v2
# ---------------------------------------------------------

AROUSAL_PRIOR = {
    "calm": "low",
    "sad": "low",
    "energetic": "high",
    "angry": "high"
}


def detect_arousal_v2(words, raw_text, emotion, emoji_high=0, emoji_low=0):
    """
    Energy level from signal words, punctuation, ALL-CAPS and
    emoji — falling back to a sensible prior for the mood when
    the text says nothing about energy.
    """

    # "low energy" / "no energy" is LOW arousal, not high.
    denied_energy = sum(
        1 for index, word in enumerate(words)
        if word in ("energy", "energetic")
        and index > 0 and words[index - 1] in ENERGY_DENIERS
    )

    high = sum(1 for word in words if word in HIGH_AROUSAL_WORDS) - denied_energy
    low = sum(1 for word in words if word in LOW_AROUSAL_WORDS) + denied_energy

    signalled = high + low

    high += min(2, raw_text.count("!") // 2)
    high += min(2, len(re.findall(r"\b[A-Z]{3,}\b", raw_text)))
    high += min(2, emoji_high)
    low += min(2, emoji_low)

    if high > low:
        return "high"

    if low > high:
        return "low"

    if signalled == 0 and high == 0 and low == 0:
        return AROUSAL_PRIOR.get(emotion, "medium")

    return "medium"


# ---------------------------------------------------------
# 12E. PREFERENCES — WHAT DID THEY ASK FOR?
# ---------------------------------------------------------

LANGUAGE_ALIASES = {
    "hindi": ["hindi", "bollywood", "hindustani"],
    "telugu": ["telugu", "tollywood"],
    "tamil": ["tamil", "kollywood"],
    "malayalam": ["malayalam", "mollywood"],
    "kannada": ["kannada"],
    "punjabi": ["punjabi"],
    "korean": ["korean", "kpop", "k-pop"],
    "japanese": ["japanese", "jpop", "j-pop", "anime"],
    "chinese": ["chinese", "mandarin", "cantopop", "cpop", "c-pop"],
    "spanish": ["spanish", "latin", "reggaeton"],
    "english": ["english"],
    "french": ["french"],
    "portuguese": ["portuguese", "brazilian"],
    "arabic": ["arabic"],
    "thai": ["thai"]
}

# These imply a language by themselves ("bollywood", "kpop"); a
# plain language name ("hindi") only counts near a music word, so
# "my hindi teacher yelled at me" doesn't hijack the playlist.
SELF_EVIDENT_ALIASES = {
    "bollywood", "tollywood", "kollywood", "mollywood", "kpop", "k-pop",
    "jpop", "j-pop", "cpop", "c-pop", "cantopop", "reggaeton", "anime"
}

MUSIC_CUE_WORDS = {
    "song", "songs", "music", "track", "tracks", "playlist", "listen",
    "listening", "play", "hear", "vibe", "vibes", "beats", "numbers",
    "melodies", "tunes", "ballads"
}

ACTIVITY_PATTERNS = [

    ("breakup", ["breakup", "break up", "broke up", "split up", "divorce", "my ex"]),
    ("sleep", ["sleep", "sleeping", "bedtime", "insomnia", "before bed",
               "falling asleep", "can't sleep", "cant sleep"]),
    ("study", ["study", "studying", "exam", "exams", "homework",
               "revising", "revision", "assignment"]),
    ("workout", ["workout", "work out", "gym", "exercise", "exercising",
                 "running", "lifting", "cardio"]),
    ("drive", ["drive", "driving", "road trip", "roadtrip", "commute",
               "commuting", "car ride", "long drive"]),
    ("meditation", ["meditate", "meditating", "meditation", "yoga",
                    "prayer", "mindfulness"]),
    ("party", ["party", "partying", "club", "celebration", "celebrating",
               "dance floor", "birthday"]),
    ("cooking", ["cooking", "baking", "kitchen"]),
    ("walk", ["walk", "walking", "stroll", "hiking", "hike"]),
    ("rain", ["rain", "raining", "rainy", "monsoon", "drizzle", "storm"]),
    ("travel", ["travel", "travelling", "traveling", "flight", "journey",
                "vacation", "holiday"]),
    ("work", ["coding", "programming", "deadline", "office work"]),
    ("morning", ["morning", "sunrise", "wake up", "woke up"]),
    ("night", ["late night", "midnight", "after midnight", "at night",
               "3am", "2am"])

]

GENRE_PATTERNS = [
    ("lofi", ["lofi", "lo-fi", "lo fi"]),
    ("acoustic", ["acoustic", "unplugged"]),
    ("piano", ["piano"]),
    ("classical", ["classical", "orchestral", "symphony"]),
    ("metal", ["metal"]),
    ("rock", ["rock"]),
    ("hiphop", ["hip hop", "hiphop", "rap", "trap"]),
    ("edm", ["edm", "techno", "dubstep", "electronic music"]),
    ("jazz", ["jazz"]),
    ("indie", ["indie"]),
    ("instrumental", ["instrumental", "no lyrics", "without lyrics"]),
    ("rnb", ["r&b", "rnb"]),
    ("folk", ["folk"]),
    ("ghazal", ["ghazal"]),
    ("sufi", ["sufi", "qawwali"]),
    ("pop", ["pop"])
]

ARTIST_STOP_WORDS = {
    "when", "because", "and", "for", "to", "that", "i", "but", "right",
    "now", "so", "as", "while", "since", "which", "who", "please", "today",
    "tonight", "then", "with", "in", "on", "at", "or", "if"
}

ARTIST_GENERIC_WORDS = {
    "me", "you", "us", "this", "that", "it", "the", "a", "an", "my",
    "your", "mine", "something", "anything", "everything", "nothing",
    "them", "him", "her", "then", "now", "here", "there", "one", "some"
}

ARTIST_PATTERNS = [

    re.compile(
        r"\b(?:songs?|music|tracks?|playlist|something|stuff|vibes?|"
        r"artists?)\s+(?:by|like|from)\s+"
        r"([\w'’.\-]+(?:\s+[\w'’.\-]+){0,3})",
        re.IGNORECASE
    ),

    re.compile(
        r"\b(?:listen(?:ing)?\s+to|play|hear|put\s+on)\s+"
        r"([\w'’.\-]+(?:\s+[\w'’.\-]+){0,3})",
        re.IGNORECASE
    )

]


def _contains_phrase(lowered, phrase):

    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"

    return re.search(pattern, lowered) is not None


def _extract_languages(lowered):

    tokens = re.findall(r"[a-z0-9\-']+", lowered)

    found = []

    for language, aliases in LANGUAGE_ALIASES.items():

        for alias in aliases:

            if not _contains_phrase(lowered, alias):
                continue

            if alias in SELF_EVIDENT_ALIASES:
                found.append(language)
                break

            # Plain language name: needs a music word nearby.

            for index, token in enumerate(tokens):

                if token != alias:
                    continue

                window = tokens[max(0, index - 4):index + 5]

                if any(word in MUSIC_CUE_WORDS for word in window):
                    found.append(language)
                    break

            if language in found:
                break

    return found[:3]


def _extract_from_patterns(lowered, patterns, limit):

    found = []

    for name, phrases in patterns:

        if any(_contains_phrase(lowered, phrase) for phrase in phrases):
            found.append(name)

    return found[:limit]


def _known_non_artist_words():

    words = set(ARTIST_GENERIC_WORDS)

    words |= SIGNAL_VOCAB

    for aliases in LANGUAGE_ALIASES.values():
        words |= set(aliases)

    for _, phrases in GENRE_PATTERNS:
        for phrase in phrases:
            words |= set(phrase.split())

    for _, phrases in ACTIVITY_PATTERNS:
        for phrase in phrases:
            words |= set(phrase.split())

    return words


_NON_ARTIST_WORDS = _known_non_artist_words()


def _extract_artists(raw_text):

    artists = []

    for pattern in ARTIST_PATTERNS:

        for match in pattern.finditer(raw_text):

            candidate = []

            for word in match.group(1).split():

                if word.lower().strip(".,") in ARTIST_STOP_WORDS:
                    break

                candidate.append(word.strip(".,!?"))

            if not candidate:
                continue

            lowered = [word.lower() for word in candidate]

            if any(word in _NON_ARTIST_WORDS for word in lowered):
                continue

            name = " ".join(candidate).strip()

            if len(name) >= 3 and name.lower() not in [a.lower() for a in artists]:
                artists.append(name.title() if name.islower() else name)

    return artists[:1]


def extract_preferences(raw_text):
    """
    Pulls out what the person *asked for*, separate from how they
    feel: languages, activities/situations, genres and an artist.
    Everything is optional; the recommender uses whatever is there.
    """

    lowered = raw_text.lower()

    return {
        "languages": _extract_languages(lowered),
        "activities": _extract_from_patterns(lowered, ACTIVITY_PATTERNS, 2),
        "genres": _extract_from_patterns(lowered, GENRE_PATTERNS, 2),
        "artists": _extract_artists(raw_text)
    }


# ---------------------------------------------------------
# 12F. CORE-MOOD DETECTION (v2)
# ---------------------------------------------------------

def detect_emotion(text):

    raw_text = str(text or "")

    normalized = normalize_text(raw_text)

    emoji_scores, emoji_neutral, emoji_high, emoji_low = read_emoji(raw_text)

    if not normalized and not emoji_scores and not emoji_neutral:

        return {
            "emotion": "neutral",
            "confidence": 0.0,
            "valence": "neutral",
            "scores": {},
            "matched_signals": []
        }

    original_words = normalized.split()

    canonical_words = [resolve_word(word) for word in original_words]

    # -----------------------------------------------------
    # Score clause by clause.
    # -----------------------------------------------------

    scoring_moods = [mood for mood in CORE_MOODS if mood != "neutral"]

    scores = {mood: 0.0 for mood in scoring_moods}
    matched_signals = {mood: [] for mood in scoring_moods}
    denied = {mood: 0.0 for mood in scoring_moods}

    clauses = split_clauses(raw_text)

    for index, clause in enumerate(clauses):

        clause_normalized = normalize_text(clause)

        if not clause_normalized:
            continue

        clause_words = [
            resolve_word(word) for word in clause_normalized.split()
        ]

        weight = (
            position_weight(index, len(clauses)) *
            temporal_weight(clause_words)
        )

        for mood in scoring_moods:

            knowledge = MOOD_KNOWLEDGE[mood]

            phrase_score, phrase_matches, phrase_negated = score_phrases(
                clause_normalized, knowledge
            )

            word_score, word_matches, negated = score_words_v2(
                clause_words, knowledge
            )

            scores[mood] += (phrase_score + word_score) * weight
            denied[mood] += (negated + phrase_negated) * weight

            matched_signals[mood].extend(phrase_matches + word_matches)

    # "not happy" -> evidence for the opposite direction.

    for mood, amount in denied.items():

        if amount <= 0:
            continue

        target = NEGATION_FLIPS.get(mood)

        if target:
            scores[target[0]] += amount * target[1]

    # Emoji.

    for mood, value in emoji_scores.items():

        if mood in scores:
            scores[mood] += value
            matched_signals[mood].append("emoji")

    scores = {mood: round(value, 3) for mood, value in scores.items()}

    neutral_matches = detect_neutral_state(normalized, canonical_words)

    if emoji_neutral:
        neutral_matches.append("emoji")

    if denied.get("energetic", 0) > 0:
        neutral_matches.append("low energy")

    # -----------------------------------------------------
    # Strongest mood, runner-up, blend.
    # -----------------------------------------------------

    sorted_scores = sorted(
        scores.items(), key=lambda item: item[1], reverse=True
    )

    best_emotion, best_score = sorted_scores[0]

    second_emotion, second_score = (
        sorted_scores[1] if len(sorted_scores) > 1 else (None, 0)
    )

    def with_extras(result):

        contenders = [
            (mood, value) for mood, value in sorted_scores if value > 0
        ][:3]

        total = sum(value for _, value in contenders)

        result["blend"] = (
            [
                {"mood": mood, "weight": round(value / total, 2)}
                for mood, value in contenders
            ]
            if total > 0 else []
        )

        result["secondary"] = (
            second_emotion
            if (
                result.get("emotion") == best_emotion
                and best_score > 0
                and second_score >= max(2.0, best_score * 0.55)
            )
            else None
        )

        return result

    # -----------------------------------------------------
    # Only an in-between state (tired / confused / numb...).
    # -----------------------------------------------------

    if neutral_matches and best_score == 0:

        return with_extras({
            "emotion": "neutral",
            "confidence": 0.90,
            "valence": EMOTION_VALENCE["neutral"],
            "scores": {**scores, "neutral": 4.0},
            "matched_signals": neutral_matches
        })

    # -----------------------------------------------------
    # Nothing recognisable.
    # -----------------------------------------------------

    if best_score == 0:

        if looks_like_gibberish_text(original_words):

            return {
                "emotion": "neutral",
                "confidence": 0.0,
                "valence": EMOTION_VALENCE["neutral"],
                "scores": {},
                "matched_signals": [],
                "invalid": True
            }

        return with_extras({
            "emotion": "neutral",
            "confidence": 0.45,
            "valence": EMOTION_VALENCE["neutral"],
            "scores": {**scores, "neutral": 1.0},
            "matched_signals": []
        })

    # -----------------------------------------------------
    # In-between state + NEGATIVE core evidence.
    #
    # "I got rejected again and I'm tired of trying" is not a
    # neutral state: the tiredness is how the sadness feels.
    # Keep the negative mood (arousal will come out low).
    # -----------------------------------------------------

    if neutral_matches and best_score < 3 and \
            EMOTION_VALENCE.get(best_emotion) == "negative" and best_score >= 1:

        confidence = 0.62 + min(best_score / 8, 1.0) * 0.15

        return with_extras({
            "emotion": best_emotion,
            "confidence": round(confidence, 2),
            "valence": EMOTION_VALENCE[best_emotion],
            "scores": scores,
            "matched_signals": matched_signals[best_emotion] + neutral_matches
        })

    # -----------------------------------------------------
    # In-between state + weak positive evidence stays neutral.
    # -----------------------------------------------------

    if neutral_matches and best_score < 3:

        return with_extras({
            "emotion": "neutral",
            "confidence": 0.86,
            "valence": EMOTION_VALENCE["neutral"],
            "scores": {**scores, "neutral": 3.5},
            "matched_signals": neutral_matches + matched_signals[best_emotion]
        })

    # -----------------------------------------------------
    # Confidence: amount of evidence + separation from runner-up.
    # -----------------------------------------------------

    evidence_strength = min(best_score / 8, 1.0)

    separation = (best_score - second_score) / best_score

    confidence = 0.55 + evidence_strength * 0.25 + separation * 0.20

    confidence = max(0.55, min(0.96, confidence))

    return with_extras({
        "emotion": best_emotion,
        "confidence": round(confidence, 2),
        "valence": EMOTION_VALENCE.get(best_emotion, "neutral"),
        "scores": scores,
        "matched_signals": matched_signals.get(best_emotion, [])
    })


# ---------------------------------------------------------
# 12F-2. CARE — WHEN SOMEONE NEEDS MORE THAN A PLAYLIST
# ---------------------------------------------------------
#
# A small, deliberate list of phrases that signal real distress.
# When one appears AIMuse still answers with music, but it reads
# the mood as sad (never "neutral"), recommends the gentle uplift
# playlist, and the page shows a quiet card with a helpline.
# It is a safety net, not a diagnosis: false positives only cost
# a kind message, so the list leans inclusive.
# ---------------------------------------------------------

CARE_PHRASES = [
    "better without me", "better off without me", "better off dead",
    "don't want to be here", "dont want to be here",
    "don't want to live", "dont want to live", "no reason to live",
    "not worth living", "want to disappear", "wish i could disappear",
    "want to die", "wanna die", "wish i was dead", "wish i were dead",
    "end it all", "end my life", "kill myself", "hurt myself",
    "harm myself", "suicide", "suicidal", "can't go on", "cant go on",
    "jeena nahi", "jeene ka mann nahi", "mar jaana", "mar jana",
    "marna chahta", "marna chahti", "sleep forever", "never wake up",
    "don't want to wake up", "dont want to wake up"
]

_CARE_RE = re.compile(
    r"(?<![a-z])(?:" + "|".join(
        re.escape(p).replace("'", "['’]?") for p in CARE_PHRASES
    ) + r")(?![a-z])",
    re.IGNORECASE
)


def needs_care(raw_text):

    return bool(_CARE_RE.search(str(raw_text or "")))


# ---------------------------------------------------------
# 12G. THE FULL PICTURE
# ---------------------------------------------------------

ENERGY_LABEL = {"low": "Low energy", "high": "High energy"}

ACTIVITY_LABEL = {
    "study": "Studying", "workout": "Workout", "drive": "On the road",
    "sleep": "Winding down for sleep", "party": "Party", "rain": "Rainy mood",
    "morning": "Morning", "night": "Late night", "cooking": "Cooking",
    "walk": "Walking", "work": "Working", "travel": "Travelling",
    "breakup": "Heartbreak", "meditation": "Meditation"
}


def build_understanding(result, preferences):
    """
    A short, human description of what AIMuse understood — shown
    to the person so the playlist never feels like a black box.
    """

    chips = []

    emotion = result.get("emotion", "neutral")

    chips.append({"kind": "mood", "label": emotion.capitalize()})

    if result.get("secondary"):
        chips.append({
            "kind": "mood",
            "label": f"+ {result['secondary'].capitalize()}"
        })

    energy = ENERGY_LABEL.get(result.get("arousal"))

    if energy:
        chips.append({"kind": "energy", "label": energy})

    for tag in (result.get("context") or [])[:2]:
        chips.append({"kind": "context", "label": tag.capitalize()})

    for activity in preferences.get("activities", []):
        chips.append({
            "kind": "activity",
            "label": ACTIVITY_LABEL.get(activity, activity.capitalize())
        })

    for language in preferences.get("languages", []):
        chips.append({"kind": "language", "label": language.capitalize()})

    for genre in preferences.get("genres", []):
        chips.append({"kind": "genre", "label": genre.capitalize()})

    for artist in preferences.get("artists", []):
        chips.append({"kind": "artist", "label": f"Like {artist}"})

    headline = f"Reads as {emotion}"

    if result.get("secondary"):
        headline += f" with a touch of {result['secondary']}"

    return {"headline": headline, "chips": chips}


def analyze_text(text):
    """
    Everything AIMuse understands about a piece of text, in one
    place — used by /analyze and re-used by /recommend so the
    recommender sees exactly what the person saw.
    """

    text = str(text or "").strip()[:1000]

    care = needs_care(text)

    result = detect_emotion(text)

    if result.get("invalid") and not care:
        return result

    result.pop("invalid", None)

    if care:

        # Never call real distress "neutral".
        if result.get("emotion") != "sad":
            result["emotion"] = "sad"
            result["secondary"] = None

        result["valence"] = "negative"
        result["confidence"] = max(result.get("confidence", 0), 0.85)
        result.setdefault("blend", [])

    normalized = normalize_text(text)

    words = [resolve_word(word) for word in normalized.split()]

    _, _, emoji_high, emoji_low = read_emoji(text)

    # "I was drained, but now I'm pumped": energy follows the most
    # recent clause when it says anything about energy.  When it
    # doesn't, words that belong to a DIFFERENT mood than the winner
    # ("sad" in "I was sad but I'm happy now") are ignored, so the
    # old mood can't drag the energy level along with it.

    arousal_words = words

    clauses = split_clauses(text)

    if len(clauses) > 1:

        last_words = [
            resolve_word(word)
            for word in normalize_text(clauses[-1]).split()
        ]

        if any(
            word in HIGH_AROUSAL_WORDS or word in LOW_AROUSAL_WORDS
            for word in last_words
        ):

            arousal_words = last_words

        elif result["emotion"] in MOOD_KNOWLEDGE:

            own = set(MOOD_KNOWLEDGE[result["emotion"]].get("strong", [])) | \
                  set(MOOD_KNOWLEDGE[result["emotion"]].get("supporting", []))

            other = set()

            for mood, knowledge in MOOD_KNOWLEDGE.items():

                if mood != result["emotion"]:
                    other |= set(knowledge.get("strong", []))
                    other |= set(knowledge.get("supporting", []))

            other -= own

            arousal_words = [word for word in words if word not in other]

    result["arousal"] = detect_arousal_v2(
        arousal_words, text, result["emotion"], emoji_high, emoji_low
    )

    result["context"] = detect_context(normalized, words)

    result["intensity_label"] = label_intensity(result["confidence"])

    result["preferences"] = extract_preferences(text)

    result["understanding"] = build_understanding(
        result, result["preferences"]
    )

    result["care"] = care

    return result


# =========================================================
# 13. SAMPLE SONGS — SCANNED FROM static/moods
# =========================================================
#
# The sample playlists come straight from the folders on disk, so
# adding, renaming or removing a song is just a file operation —
# nothing to edit in JavaScript, and no filename typos to break
# playback.  The folder name is matched case-insensitively
# (static/Moods, static/moods and static/MOODS all work, as do
# Happy/happy, Angry/angry ...).
#
# Titles and artists come from src/sample_names.py (SAMPLE_METADATA) when known,
# otherwise from an "Artist - Title" filename, otherwise the
# filename itself.
# =========================================================

AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac", ".opus", ".webm"
}

def _find_child_dir(parent, wanted_lower):
    """Case-insensitive lookup of a sub-directory."""

    try:
        names = os.listdir(parent)
    except OSError:
        return None

    for name in names:

        full = os.path.join(parent, name)

        if name.lower() == wanted_lower and os.path.isdir(full):
            return full

    return None


def scan_sample_songs():
    """
    Returns {mood: [ {title, artist, file, url} ]} for every core
    mood folder found under static/moods, plus a "missing" list of
    moods with no folder or no audio (so the UI can say so).
    """

    static_root = app.static_folder

    moods_dir = _find_child_dir(static_root, "moods")

    playlists = {mood: [] for mood in CORE_MOODS}

    if not moods_dir:
        return playlists

    moods_name = os.path.basename(moods_dir)

    for mood in CORE_MOODS:

        mood_dir = _find_child_dir(moods_dir, mood)

        if not mood_dir:
            continue

        folder_name = os.path.basename(mood_dir)

        for filename in sorted(os.listdir(mood_dir), key=str.lower):

            stem, extension = os.path.splitext(filename)

            if extension.lower() not in AUDIO_EXTENSIONS:
                continue

            relative = f"{moods_name}/{folder_name}/{filename}"

            title, artist = sample_meta(stem)

            playlists[mood].append({
                "title": title,
                "artist": artist,
                "file": relative,
                "url": url_for("static", filename=relative)
            })

    return playlists


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def home():

    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():

    data = request.get_json(silent=True)

    if not data or "text" not in data:

        return jsonify({
            "success": False,
            "error": "Please provide text."
        }), 400

    text = str(data["text"]).strip()

    if not text:

        return jsonify({
            "success": False,
            "error": "Text cannot be empty."
        }), 400

    result = analyze_text(text)

    return jsonify({
        "success": True,
        "input": text[:1000],
        **result
    })


RECOMMEND_MESSAGES = {
    "no_api_key": (
        "YouTube isn't connected yet. Set the YOUTUBE_API_KEY "
        "environment variable and restart the server."
    ),
    "quota_exceeded": (
        "YouTube's daily search quota is used up for now. "
        "It resets daily — the sample songs still work."
    ),
    "network_error": "Couldn't reach YouTube right now. Try again in a moment.",
    "no_results": "YouTube didn't return playable songs for this mood."
}


@app.route("/recommend", methods=["POST"])
def recommend():
    """
    text -> understanding -> query -> verified YouTube songs.

    The frontend sends the person's original text along with the
    mood it detected; the profile (energy, context, activity,
    language, genre, artist) is rebuilt here so the recommender
    sees the whole picture.
    """

    data = request.get_json(silent=True)

    if not data:

        return jsonify({
            "success": False,
            "error": "Missing request body."
        }), 400

    text = str(data.get("text", "")).strip()[:1000]

    emotion = str(data.get("emotion", "neutral")).lower()

    if emotion not in CORE_MOODS:
        emotion = "neutral"

    mode = "uplift" if data.get("mode") == "uplift" else "match"

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    confidence = max(0.0, min(1.0, confidence))

    analysis = analyze_text(text) if text else {}

    if analysis.get("invalid"):
        analysis = {}

    preferences = analysis.get("preferences") or {}

    profile = {
        "emotion": emotion,
        "mode": mode,
        "secondary": analysis.get("secondary"),
        "arousal": analysis.get("arousal", "medium"),
        "context": analysis.get("context", []),
        "languages": preferences.get("languages", []),
        "activities": preferences.get("activities", []),
        "genres": preferences.get("genres", []),
        "artists": preferences.get("artists", [])
    }

    # The language picker in the UI: telugu / hindi / english = ONLY that
    # language; "mix" (or missing) = the usual blend.
    profile = apply_language_choice(profile, data.get("language"))

    outcome = get_recommendations(emotion, mode, confidence, profile=profile)

    status = outcome.get("status")

    songs = outcome.get("songs", [])

    return jsonify({
        "success": status == "ok" and bool(songs),
        "source": "youtube",
        "status": status,
        "message": RECOMMEND_MESSAGES.get(status, ""),
        "songs": songs,
        "playlist_url": outcome.get("playlist_url", ""),
        "query": outcome.get("query", ""),
        "languages": outcome.get("languages", []),
        "stale": bool(outcome.get("stale"))
    })


@app.route("/recommend/report", methods=["POST"])
def recommend_report():
    """
    The browser's player couldn't play a video the API said was
    fine.  Remember it so it's never recommended again.
    """

    data = request.get_json(silent=True) or {}

    recorded = report_bad_video(data.get("videoId"), data.get("channel", ""))

    return jsonify({"success": recorded})


@app.route("/recommend/replace", methods=["POST"])
def recommend_replace():
    """
    A song failed in the browser's player.  Find the SAME song from a
    different video, verify it, and return it so the playlist can swap
    it in.  (The failed video is blacklisted when the failure was a
    permanent one.)
    """

    data = request.get_json(silent=True) or {}

    exclude = data.get("exclude") or []

    if not isinstance(exclude, list):
        exclude = []

    outcome = find_replacement(
        video_id=data.get("videoId"),
        title=data.get("title"),
        artist=data.get("artist"),
        language=data.get("language"),
        exclude=[str(item) for item in exclude[:60]],
        permanent=bool(data.get("permanent", True)),
        channel=data.get("channel")
    )

    songs = outcome.get("songs") or []

    return jsonify({
        "success": bool(songs),
        "status": outcome.get("status"),
        "song": outcome.get("song"),
        "songs": songs
    })


@app.route("/api/samples")
def api_samples():
    """
    Sample songs for the "Explore moods" tabs.

    Hand-picked songs played from YouTube (data/sample_videos.json,
    see src/curated_samples.py) — these work on the public website.
    A mood with no YouTube songs saved yet falls back to local files
    in static/Moods/<mood>/ (laptop only; they're git-ignored).
    """

    local = scan_sample_songs()

    youtube = curated_samples.youtube_playlists()

    playlists = {
        mood: youtube.get(mood) or local.get(mood, [])
        for mood in CORE_MOODS
    }

    return jsonify({
        "success": True,
        "playlists": playlists,
        "total": sum(len(songs) for songs in playlists.values())
    })


# The four AIMuse originals that play on the entry screen.  Must
# match the file names in static/ exactly (script.js has the same
# list) — /health reports which ones are actually there.
ENTRY_TRACK_FILES = [
    "Where Snow Meets the Sunlight.mp3",
    "Floating on Silver Mist.mp3",
    "Footsteps in the Falling Snow.mp3",
    "Whispers in the Moonlight.mp3"
]


# ---------------------------------------------------------
# INSTALLABLE APP (PWA)
# ---------------------------------------------------------
# The service worker must be served from the site root to
# control every page, so it gets its own route.  The manifest
# lives in static/ and is linked from index.html.
# ---------------------------------------------------------

@app.route("/sw.js")
def service_worker():

    response = app.send_static_file("sw.js")
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"

    return response


@app.route("/manifest.webmanifest")
def web_manifest():

    response = app.send_static_file("manifest.webmanifest")
    response.headers["Content-Type"] = "application/manifest+json"

    return response


@app.route("/health")
def health():
    """
    Quick diagnostics — open http://127.0.0.1:5000/health to see
    whether the YouTube key is set, how many sample songs were
    found per mood, and whether the four entry tracks exist in
    static/ with exactly the right file names.
    """

    playlists = scan_sample_songs()

    entry_tracks = {
        name: os.path.isfile(os.path.join(app.static_folder, name))
        for name in ENTRY_TRACK_FILES
    }

    return jsonify({
        "status": "online",
        "project": "AIMuse",
        "message": "AIMuse backend is running.",
        "youtube_configured": bool(YOUTUBE_API_KEY),
        "entry_tracks": entry_tracks,
        "entry_tracks_ok": all(entry_tracks.values()),
        "sample_songs": {
            mood: len(songs) for mood, songs in playlists.items()
        }
    })


# =========================================================
# RUN APPLICATION
# =========================================================

@app.cli.command("warm-samples")
def warm_samples_command():
    """
    flask --app app warm-samples

    Finds each hand-picked sample song (src/curated_samples.py) on
    YouTube once — about 100 quota units per song, ~3,500 for all 35 —
    and saves them to data/sample_videos.json.  Commit that file.
    Already-saved songs are skipped, so it's safe to run again.
    """

    curated_samples.warm()


@app.cli.command("warm-cache")
def warm_cache_command():
    """
    flask --app app warm-cache

    Builds one playlist per mood (plus uplift for sad / angry) and
    saves them to data/playlist_snapshot.json.  Commit that file:
    the deployed site falls back to it when YouTube's quota runs
    out, so a visitor never sees an empty playlist box.
    Costs roughly 3,000 of the 10,000 daily quota units — run it
    once, not on every deploy.
    """

    jobs = [(mood, "match") for mood in CORE_MOODS] + \
           [("sad", "uplift"), ("angry", "uplift")]

    for mood, mode in jobs:

        profile = {"emotion": mood, "mode": mode}

        outcome = get_recommendations(mood, mode, 0.8, profile=profile)

        print(f"{mood:10} {mode:7} -> {outcome.get('status'):15} "
              f"{len(outcome.get('songs', []))} songs")


if __name__ == "__main__":

    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1"
    )