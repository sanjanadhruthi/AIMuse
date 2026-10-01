"""
Golden set for the mood engine — the "AI" in AIMuse.

Every sentence here is something a real person would type.  If a
change to app.py breaks one of these, the change made AIMuse
understand people worse, whatever else it improved.
"""

import pytest

import app


def mood(text):
    return app.analyze_text(text)


# ------------------------------------------------ core moods

@pytest.mark.parametrize("text, expected", [
    ("I'm so happy today, got the job!", "happy"),
    ("aaj bahut khush hoon", "happy"),
    ("I feel like a failure", "sad"),
    ("missing home so much, mom's food", "sad"),
    ("bhot bura lag rha hai", "sad"),
    ("I hate myself and I'm crying", "sad"),
    ("bahut gussa aa raha hai", "angry"),
    ("so fed up with everyone, I'm furious", "angry"),
    ("my crush texted me back!!!", "romantic"),
    ("rainy evening chai and some old hindi songs", "calm"),
    ("I want to feel motivated for my exam tomorrow", "energetic"),
])
def test_core_moods(text, expected):
    assert mood(text)["emotion"] == expected


# ------------------------------------------------ the bugs we fixed

def test_not_okay_is_sad_not_neutral():
    result = mood("I'm not okay")
    assert result["emotion"] == "sad"
    assert result["valence"] == "negative"


@pytest.mark.parametrize("text", [
    "not fine", "I'm not good", "not doing well",
    "i'm not feeling good", "not feeling great", "I am not feeling happy",
])
def test_negated_wellbeing_words_are_sad(text):
    assert mood(text)["emotion"] == "sad"


def test_tiredness_does_not_swallow_sadness():
    result = mood("I got rejected from another job today and I'm tired of trying")
    assert result["emotion"] == "sad"
    assert result["arousal"] == "low"


@pytest.mark.parametrize("text", [
    "mood off yaar, kuch acha nahi lag raha",
    "khush nahi hoon",
    "feeling low today",
    "naku chala badhaga undi",
    "today was the worst day ever",
    "my best friend ignored me",
    "i dont feel like doing anything",
    "I'm not angry, just disappointed",
])
def test_hinglish_and_everyday_sadness(text):
    assert mood(text)["emotion"] == "sad"


def test_phrase_without_negation_still_counts():
    assert mood("I'm feeling good today")["emotion"] == "happy"


def test_phrases_with_apostrophes_still_match():
    # preprocessing strips apostrophes: "can't" arrives as "cant"
    result = mood("can't stop crying")
    assert result["emotion"] == "sad"
    assert "cant stop crying" in result["matched_signals"]


def test_cant_stop_is_not_a_negation():
    assert mood("I can't stop feeling good")["emotion"] == "happy"


# ------------------------------------------------ genuine in-between states

@pytest.mark.parametrize("text", ["I'm fine", "I'm okay just tired", "bore ho raha hai"])
def test_in_between_states_stay_neutral(text):
    assert mood(text)["emotion"] == "neutral"


def test_low_energy_is_low_arousal():
    assert mood("I have low energy today")["arousal"] == "low"


# ------------------------------------------------ time and contrast

def test_later_clause_wins():
    assert mood("I was sad yesterday but I'm finally happy now")["emotion"] == "happy"


# ------------------------------------------------ care

@pytest.mark.parametrize("text", [
    "nothing matters, everyone would be better without me",
    "I don't want to be here anymore",
    "I dont want to live",
    "I just want to disappear",
    "i want to sleep forever",
])
def test_distress_gets_care_and_is_never_neutral(text):
    result = mood(text)
    assert result["care"] is True
    assert result["emotion"] == "sad"
    assert result["valence"] == "negative"


@pytest.mark.parametrize("text", [
    "I'm so happy today",
    "this song is killing it",
    "I'm tired and sad",
])
def test_ordinary_text_does_not_trigger_care(text):
    assert mood(text)["care"] is False


# ------------------------------------------------ input validation

@pytest.mark.parametrize("text", ["asdfgh", "rtjulyi kfgtr", "qwertyuiop"])
def test_gibberish_is_rejected(text):
    assert mood(text).get("invalid") is True


@pytest.mark.parametrize("word", [
    "myself", "rhythm", "crying", "system", "bhot", "khush", "dhoka", "pyaar",
])
def test_real_words_are_not_gibberish(word):
    assert app.looks_like_gibberish_word(word) is False


# ------------------------------------------------ API shape

def test_analyze_endpoint_returns_care_flag():
    client = app.app.test_client()
    response = client.post("/analyze", json={"text": "I'm not okay"})
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["emotion"] == "sad"
    assert data["care"] is False


def test_analyze_endpoint_rejects_empty_text():
    response = app.app.test_client().post("/analyze", json={"text": "   "})
    assert response.status_code == 400