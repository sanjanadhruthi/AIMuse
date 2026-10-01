"""Query building, ordering and the self-healing replacement engine.

Nothing here touches the network: the YouTube calls are replaced with
in-memory fakes.
"""

import pytest

from src import youtube_recommender as yt


# ---------------------------------------------------------------- queries

def test_query_reflects_mood_and_energy():
    low = yt.build_query({"emotion": "sad", "arousal": "low"})
    high = yt.build_query({"emotion": "sad", "arousal": "high"})
    assert "slow" in low
    assert low != high


def test_uplift_mode_does_not_search_for_more_sadness():
    query = yt.build_query({"emotion": "sad", "arousal": "medium", "mode": "uplift"})
    assert "hopeful" in query or "uplifting" in query
    assert "sad" not in query


def test_named_artist_leads_the_query():
    query = yt.build_query({"emotion": "happy", "artists": ["Arijit Singh"]})
    assert query.startswith("Arijit Singh")


def test_secondary_mood_adds_a_flavour_word():
    plain = yt.build_query({"emotion": "sad", "arousal": "medium"})
    mixed = yt.build_query({"emotion": "sad", "arousal": "medium", "secondary": "calm"})
    assert "soothing" in mixed and "soothing" not in plain


def test_query_is_capped():
    query = yt.build_query({
        "emotion": "romantic", "arousal": "high", "activities": ["drive"],
        "genres": ["indie"], "context": ["nostalgic"], "artists": ["Someone Long Name"],
        "secondary": "sad",
    })
    assert len(query.split()) <= yt.MAX_QUERY_WORDS


def test_language_request_only_searches_that_language():
    assert yt.pick_languages({"languages": ["telugu"]}) == ["telugu"]
    assert yt.pick_languages({}) == yt.DEFAULT_LANGUAGES


# ---------------------------------------------------------------- helpers

def test_duration_parsing():
    assert yt._parse_duration("PT3M30S") == 210
    assert yt._parse_duration("PT1H2M3S") == 3723
    assert yt._parse_duration("garbage") == 0


def test_same_song_uploaded_twice_shares_a_dedupe_key():
    assert yt._title_key("Hype Boy (Official MV)") == yt._title_key("Hype Boy - Lyrics")


# ------------------------------------------------- channel interleaving

def _video(video_id, channel):
    return {"videoId": video_id, "channel": channel}


def test_failed_channel_goes_last_and_channels_alternate():
    ranked = [
        _video("h1", "HYBE LABELS"), _video("h2", "HYBE LABELS"),
        _video("l1", "Lyrics Ch"), _video("t1", "NewJeans - Topic"),
    ]
    order = [v["videoId"] for v in yt._interleave_channels(ranked, "HYBE LABELS", set())]
    assert order[:2] == ["l1", "t1"]
    assert order[-2:] == ["h1", "h2"]


def test_at_most_two_per_channel_and_excluded_ids_dropped():
    ranked = [_video(f"a{i}", "Same") for i in range(5)] + [_video("b", "Other")]
    order = yt._interleave_channels(ranked, "", {"a0"})
    assert sum(v["channel"] == "Same" for v in order) == 2
    assert "a0" not in [v["videoId"] for v in order]


# ------------------------------------------------ replacement engine

def _item(video_id, title, channel, views=1_000_000, duration="PT3M"):
    return {
        "id": video_id,
        "snippet": {"title": title, "channelTitle": channel, "thumbnails": {}},
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": str(views), "likeCount": str(views // 30)},
        "status": {"privacyStatus": "public", "embeddable": True, "uploadStatus": "processed"},
    }


@pytest.fixture
def fake_youtube(monkeypatch, tmp_path):
    """A world where HYBE's uploads exist next to lyric / Topic / junk uploads."""

    videos = [
        _item("hybe0000001", "NewJeans 'Hype Boy' Official MV (Performance ver.1)", "HYBE LABELS", 250_000_000),
        _item("hybe0000002", "NewJeans 'Hype Boy' Official MV", "HYBE LABELS", 90_000_000),
        _item("lyric000001", "NewJeans 'Hype Boy' Lyrics (Color Coded Lyrics)", "Jaeguchi", 63_000_000),
        _item("topic000001", "Hype Boy", "NewJeans - Topic", 40_000_000),
        _item("kmusic00001", "NewJeans - Hype Boy 「Official Audio」", "K MUSIC", 3_000_000),
        # junk that must never be offered as "the same song"
        _item("dance000001", "NewJeans 'Hype Boy' Dance // heyitskimmy", "kim"),
        _item("short000001", "V did Hype Boy challenge #shorts", "x", duration="PT0M40S"),
        _item("cover000001", "Hype Boy (cover) by someone", "z"),
        _item("other000001", "Cupid - FIFTY FIFTY", "FIFTY FIFTY"),
    ]
    db = {v["id"]: v for v in videos}

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(yt, "_BAD_FILE", str(tmp_path / "bad.json"))
    yt._BAD_IDS.clear()
    yt._CACHE.clear()
    monkeypatch.setattr(yt, "_QUOTA_BLOCKED_UNTIL", 0.0)

    calls = {"searches": 0}

    def fake_search(query, language, pool_size=25, add_suffix=True, music_only=True):
        calls["searches"] += 1
        return list(db)

    monkeypatch.setattr(yt, "_search_language", fake_search)
    monkeypatch.setattr(yt, "_fetch_details", lambda ids: [db[i] for i in ids if i in db])
    monkeypatch.setattr(yt, "_oembed_ok", lambda video_id: True)

    return calls


def test_replacement_offers_a_pool_from_other_channels_first(fake_youtube):
    result = yt.find_replacement(
        "hybe0000002", "Hype Boy", "NewJeans", "korean",
        exclude=["hybe0000002"], channel="HYBE LABELS",
    )
    assert result["status"] == yt.STATUS_OK
    channels = [s["channel"] for s in result["songs"]]
    assert channels[0] != "HYBE LABELS"
    assert channels[-1] == "HYBE LABELS"          # the blocked owner is tried last
    assert len(result["songs"]) >= 3


def test_replacement_never_offers_junk_or_other_songs(fake_youtube):
    result = yt.find_replacement("hybe0000002", "Hype Boy", "NewJeans", "korean", channel="HYBE LABELS")
    offered = {s["videoId"] for s in result["songs"]}
    assert offered.isdisjoint({"dance000001", "short000001", "cover000001", "other000001"})


def test_failed_video_is_blacklisted_and_not_offered_again(fake_youtube):
    yt.find_replacement("hybe0000001", "Hype Boy", "NewJeans", "korean", channel="HYBE LABELS")
    assert "hybe0000001" in yt._BAD_IDS
    again = yt.find_replacement("hybe0000002", "Hype Boy", "NewJeans", "korean", channel="HYBE LABELS")
    assert "hybe0000001" not in {s["videoId"] for s in again["songs"]}


def test_pool_is_cached_so_a_second_failure_costs_no_quota(fake_youtube):
    yt.find_replacement("hybe0000002", "Hype Boy", "NewJeans", "korean", channel="HYBE LABELS")
    searches_after_first = fake_youtube["searches"]
    yt.find_replacement("lyric000001", "Hype Boy", "NewJeans", "korean", channel="Jaeguchi")
    assert fake_youtube["searches"] == searches_after_first


def test_embed_probe_removes_videos_youtube_refuses(fake_youtube, monkeypatch):
    monkeypatch.setattr(yt, "_oembed_ok", lambda video_id: video_id != "lyric000001")
    result = yt.find_replacement("hybe0000002", "Hype Boy", "NewJeans", "korean", channel="HYBE LABELS")
    assert "lyric000001" not in {s["videoId"] for s in result["songs"]}


def test_no_api_key_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "")
    result = yt.find_replacement("abc", "Song", "Artist")
    assert result["status"] == yt.STATUS_NO_KEY and result["songs"] == []


def test_quota_exhaustion_is_reported_and_remembered(fake_youtube, monkeypatch):
    def boom(*args, **kwargs):
        raise yt._QuotaExceeded()

    monkeypatch.setattr(yt, "_search_alternatives", boom)
    first = yt.find_replacement("a1", "Song", "Artist")
    assert first["status"] == yt.STATUS_QUOTA

    # remembered: the second call must not even try the API
    monkeypatch.setattr(yt, "_search_alternatives", lambda *a, **k: pytest.fail("API called during quota back-off"))
    assert yt.find_replacement("a2", "Song", "Artist")["status"] == yt.STATUS_QUOTA


# ------------------------------------------------ speed rules

def test_rich_results_need_only_the_two_parallel_searches(fake_youtube):
    yt.find_replacement("hybe0000002", "Hype Boy", "NewJeans", "korean", channel="HYBE LABELS")
    assert fake_youtube["searches"] == 2      # the third, broader search was not needed


def test_sparse_results_trigger_the_broader_third_search(fake_youtube, monkeypatch):
    # every search finds just one matching upload -> pool stays under 3
    only = ["lyric000001"]
    counter = {"n": 0}

    def sparse(query, language, pool_size=25, add_suffix=True, music_only=True):
        counter["n"] += 1
        return only

    monkeypatch.setattr(yt, "_search_language", sparse)
    yt._CACHE.clear()
    yt.find_replacement("hybe0000002", "Hype Boy", "NewJeans", "korean", channel="HYBE LABELS")
    assert counter["n"] == 3


def test_only_the_best_few_candidates_are_probed(fake_youtube, monkeypatch):
    # ten uploads of the same song, each from a different channel
    many = {
        f"vid{i:08d}": _item(f"vid{i:08d}", f"Hype Boy (Official Audio) {i}", f"Channel {i}")
        for i in range(10)
    }
    monkeypatch.setattr(yt, "_search_language", lambda *a, **k: list(many))
    monkeypatch.setattr(yt, "_fetch_details", lambda ids: [many[i] for i in ids if i in many])
    yt._CACHE.clear()

    probed = []
    monkeypatch.setattr(yt, "_oembed_ok", lambda video_id: probed.append(video_id) or True)

    result = yt.find_replacement("dead0000001", "Hype Boy", "NewJeans", "korean", channel="Somewhere")

    assert 0 < len(probed) <= yt.PROBE_TOP           # only the best few were probed...
    assert len(result["songs"]) > len(probed)         # ...yet the rest are still handed over



# ------------------------------------------------ language picker

def test_a_chosen_language_means_only_that_language():
    profile = yt.apply_language_choice({"emotion": "happy"}, "telugu")
    assert yt.pick_languages(profile) == ["telugu"]


def test_mix_keeps_the_usual_blend():
    profile = yt.apply_language_choice({"emotion": "happy"}, "mix")
    assert yt.pick_languages(profile) == yt.DEFAULT_LANGUAGES


def test_mix_still_honours_a_language_typed_in_the_text():
    # "play some telugu songs" was detected in the text; the picker says Mix.
    profile = yt.apply_language_choice({"languages": ["telugu"]}, "mix")
    assert yt.pick_languages(profile) == ["telugu"]


def test_the_picker_beats_a_language_typed_in_the_text():
    profile = yt.apply_language_choice({"languages": ["hindi"]}, "english")
    assert yt.pick_languages(profile) == ["english"]


@pytest.mark.parametrize("junk", [None, "", "klingon", "TELUGU ", 42])
def test_unknown_or_missing_choice_is_harmless(junk):
    profile = yt.apply_language_choice({"emotion": "sad"}, junk)
    if str(junk).strip().lower() == "telugu":
        assert profile["languages"] == ["telugu"]     # case / spaces are forgiven
    else:
        assert yt.pick_languages(profile) == yt.DEFAULT_LANGUAGES


def test_the_original_profile_is_not_modified():
    original = {"emotion": "happy", "languages": ["hindi"]}
    yt.apply_language_choice(original, "telugu")
    assert original["languages"] == ["hindi"]


def test_a_single_language_playlist_is_filled_even_when_artists_repeat(monkeypatch, tmp_path):
    """5 artists x 4 songs each, ONE language: the playlist should still reach 14."""

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(yt, "_BAD_FILE", str(tmp_path / "bad.json"))
    yt._BAD_IDS.clear()
    yt._CACHE.clear()

    artists = ["Ed Sheeran", "Adele", "Coldplay", "Dua Lipa", "The Weeknd"]
    videos = {}

    for a, artist in enumerate(artists):
        for n in range(4):
            vid = f"eng{a}{n}" + "0" * 6
            # a different channel per video, so only the ARTIST cap is in play
            videos[vid] = _item(vid, f"{artist} - Song Number {a}{n} (Official Audio)", f"Channel {a}{n}")

    monkeypatch.setattr(yt, "_search_language", lambda *a, **k: list(videos))
    monkeypatch.setattr(yt, "_fetch_details", lambda ids: [videos[i] for i in ids if i in videos])
    monkeypatch.setattr(yt, "_oembed_ok", lambda video_id: True)

    profile = yt._normalise_profile("happy", "match", 0.8, {"languages": ["english"]})
    outcome = yt._build_playlist(profile, "happy songs english", ["english"], 14)

    assert len(outcome["songs"]) == 14
    assert {song["language"] for song in outcome["songs"]} == {"english"}


# ------------------------------------------------ demo snapshot

def _snapshot_world(monkeypatch, tmp_path):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(yt, "_BAD_FILE", str(tmp_path / "bad.json"))
    monkeypatch.setattr(yt, "_QUOTA_BLOCKED_UNTIL", 0.0)
    yt._BAD_IDS.clear()
    yt._CACHE.clear()

    songs = [{"videoId": f"snap{i:07d}", "title": f"Song {i}", "channel": "C"} for i in range(5)]

    monkeypatch.setattr(
        yt, "_build_playlist",
        lambda profile, query, languages, limit: yt._result(
            yt.STATUS_OK, songs, query=query, languages=languages
        )
    )

    return songs


def test_a_good_playlist_is_saved_and_served_when_quota_runs_out(monkeypatch, tmp_path):

    songs = _snapshot_world(monkeypatch, tmp_path)

    first = yt.get_recommendations("sad", "match", 0.8, profile={"emotion": "sad"})
    assert first["status"] == yt.STATUS_OK

    # server restarts (memory cache gone) and the quota is exhausted
    yt._CACHE.clear()
    monkeypatch.setattr(yt, "_SNAPSHOT_LOADED", False)
    yt._SNAPSHOTS.clear()

    def boom(*args, **kwargs):
        raise yt._QuotaExceeded()

    monkeypatch.setattr(yt, "_build_playlist", boom)

    again = yt.get_recommendations("sad", "match", 0.8, profile={"emotion": "sad"})
    assert again["status"] == yt.STATUS_OK
    assert again["stale"] is True
    assert [s["videoId"] for s in again["songs"]] == [s["videoId"] for s in songs]


def test_snapshot_skips_videos_that_later_failed(monkeypatch, tmp_path):

    _snapshot_world(monkeypatch, tmp_path)
    yt.get_recommendations("happy", "match", 0.8, profile={"emotion": "happy"})

    yt._BAD_IDS.add("snap0000000")
    yt._CACHE.clear()
    monkeypatch.setattr(yt, "_QUOTA_BLOCKED_UNTIL", 10 ** 12)

    served = yt.get_recommendations("happy", "match", 0.8, profile={"emotion": "happy"})
    assert "snap0000000" not in {s["videoId"] for s in served["songs"]}


def test_no_snapshot_means_an_honest_quota_message(monkeypatch, tmp_path):

    _snapshot_world(monkeypatch, tmp_path)
    monkeypatch.setattr(yt, "_QUOTA_BLOCKED_UNTIL", 10 ** 12)

    result = yt.get_recommendations("angry", "match", 0.8, profile={"emotion": "angry"})
    assert result["status"] == yt.STATUS_QUOTA and result["songs"] == []



# ------------------------------------------------ learning blocked channels

def test_failures_teach_aimuse_to_rank_a_channel_lower(monkeypatch, tmp_path):

    monkeypatch.setattr(yt, "_BAD_FILE", str(tmp_path / "bad.json"))
    yt._BAD_IDS.clear()

    assert yt.channel_penalty("Some VEVO") == 0

    yt.report_bad_video("aaaaaaaaaa1", "Some VEVO")
    yt.report_bad_video("aaaaaaaaaa1", "Some VEVO")       # same video twice counts once
    assert yt.channel_penalty("some  vevo") == yt.CHANNEL_FAIL_PENALTY

    for i in range(10):
        yt.report_bad_video(f"bbbbbbbbbb{i}", "Some VEVO")
    assert yt.channel_penalty("Some VEVO") == yt.CHANNEL_FAIL_PENALTY_MAX


def test_long_compilations_are_not_songs():
    assert yt.MAX_SONG_SECONDS <= 600



def test_snapshot_never_crosses_languages(monkeypatch, tmp_path):

    _snapshot_world(monkeypatch, tmp_path)

    # a saved MIX playlist exists for "sad"...
    yt.get_recommendations("sad", "match", 0.8, profile={"emotion": "sad"})

    # ...but YouTube is now out of quota and the person picked English
    yt._CACHE.clear()
    monkeypatch.setattr(yt, "_QUOTA_BLOCKED_UNTIL", 10 ** 12)

    english = yt.get_recommendations(
        "sad", "match", 0.8, profile={"emotion": "sad", "languages": ["english"]}
    )

    assert english["status"] == yt.STATUS_QUOTA
    assert english["songs"] == []



# ------------------------------------------------ pinned favourites

def _pin_world(monkeypatch, tmp_path):

    _snapshot_world(monkeypatch, tmp_path)

    calls = {"n": 0}
    pinned_upload = {"videoId": "lepadha0001", "title": "Le Padha Padhaa",
                     "artist": "Armaan Malik", "channel": "Sony Music South"}

    def fake_alternatives(song, artist, language):
        calls["n"] += 1
        return [dict(pinned_upload), {**pinned_upload, "videoId": "lepadha0002"}]

    monkeypatch.setattr(yt, "_search_alternatives", fake_alternatives)

    return calls


def test_pinned_song_leads_the_telugu_uplift_playlist(monkeypatch, tmp_path):

    calls = _pin_world(monkeypatch, tmp_path)

    result = yt.get_recommendations(
        "sad", "uplift", 0.8, profile={"emotion": "sad", "languages": ["telugu"]}
    )

    assert result["songs"][0]["videoId"] == "lepadha0001"
    assert result["songs"][0]["pinned"] is True

    # found once, then remembered: no second search
    yt.get_recommendations("angry", "uplift", 0.8,
                           profile={"emotion": "angry", "languages": ["telugu"]})
    assert calls["n"] == 1


def test_pinned_song_stays_out_of_other_playlists(monkeypatch, tmp_path):

    _pin_world(monkeypatch, tmp_path)

    match = yt.get_recommendations("sad", "match", 0.8,
                                   profile={"emotion": "sad", "languages": ["telugu"]})
    english = yt.get_recommendations("sad", "uplift", 0.8,
                                     profile={"emotion": "sad", "languages": ["english"]})

    for result in (match, english):
        assert "lepadha0001" not in {s["videoId"] for s in result["songs"]}


def test_a_failed_pinned_upload_falls_back_to_the_next_one(monkeypatch, tmp_path):

    _pin_world(monkeypatch, tmp_path)
    yt.get_recommendations("sad", "uplift", 0.8,
                           profile={"emotion": "sad", "languages": ["telugu"]})

    yt._BAD_IDS.add("lepadha0001")

    again = yt.get_recommendations("sad", "uplift", 0.8,
                                   profile={"emotion": "sad", "languages": ["telugu"]})
    assert again["songs"][0]["videoId"] == "lepadha0002"