"""Hand-picked sample songs, played from YouTube (src/curated_samples.py)."""

from src import curated_samples as cs
from src import youtube_recommender as yt

import app


def _fake_found(video_ids):
    return {
        vid: {"videoId": vid, "channel": f"ch-{vid}", "duration_seconds": 200,
              "thumbnail": "", "_score": 10 - i}
        for i, vid in enumerate(video_ids)
    }


def test_warm_saves_uploads_and_skips_finished_songs(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES", {"happy": [("Song A", "Artist", "")]})

    calls = {"n": 0}

    def fake(*args):
        calls["n"] += 1
        return _fake_found(["aaaaaaaaaa1", "aaaaaaaaaa2"])

    monkeypatch.setattr(cs, "PAUSE_BETWEEN_SONGS", 0)
    monkeypatch.setattr(yt, "_alternatives_from_query", fake)

    cs.warm(print_line=lambda *_: None)
    cs.warm(print_line=lambda *_: None)          # second run: nothing to search

    assert calls["n"] == 1

    songs = cs.youtube_playlists()["happy"]
    assert songs[0]["videoId"] == "aaaaaaaaaa1"
    assert songs[0]["title"] == "Song A" and songs[0]["sample"] is True
    assert [a["videoId"] for a in songs[0]["alternates"]] == ["aaaaaaaaaa2"]


def test_quota_stops_warm_cleanly(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES", {"sad": [("Song B", "X", "")]})

    def boom(*args):
        raise yt._QuotaExceeded()

    monkeypatch.setattr(yt, "_alternatives_from_query", boom)

    cs.warm(print_line=lambda *_: None)          # must not raise

    assert cs.youtube_playlists()["sad"] == []


def test_failed_uploads_are_skipped(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES", {"calm": [("Song C", "Y", "")]})
    monkeypatch.setattr(yt, "_alternatives_from_query",
                        lambda *a: _fake_found(["cccccccccc1", "cccccccccc2"]))

    cs.warm(print_line=lambda *_: None)

    yt._BAD_IDS.add("cccccccccc1")
    try:
        song = cs.youtube_playlists()["calm"][0]
        assert song["videoId"] == "cccccccccc2"
    finally:
        yt._BAD_IDS.discard("cccccccccc1")


def test_api_samples_prefers_youtube_and_counts_songs(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES", {"happy": [("Song A", "Artist", "")]})
    monkeypatch.setattr(yt, "_alternatives_from_query",
                        lambda *a: _fake_found(["aaaaaaaaaa1"]))
    cs.warm(print_line=lambda *_: None)

    data = app.app.test_client().get("/api/samples").get_json()

    assert data["playlists"]["happy"][0]["videoId"] == "aaaaaaaaaa1"
    assert data["total"] >= 1



def test_flaky_network_is_retried(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES", {"happy": [("Song D", "Z", "")]})
    monkeypatch.setattr(cs, "RETRY_WAIT_SECONDS", 0)
    monkeypatch.setattr(cs, "PAUSE_BETWEEN_SONGS", 0)
    monkeypatch.setitem(yt.LAST_ERROR, "status", None)

    answers = [None, None, _fake_found(["dddddddddd1"])]
    monkeypatch.setattr(yt, "_alternatives_from_query", lambda *a: answers.pop(0))

    cs.warm(print_line=lambda *_: None)

    assert cs.youtube_playlists()["happy"][0]["videoId"] == "dddddddddd1"


def test_key_problems_stop_instead_of_wasting_quota(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES",
                        {"happy": [("Song E", "Z", ""), ("Song F", "Z", "")]})
    monkeypatch.setattr(cs, "RETRY_WAIT_SECONDS", 0)
    monkeypatch.setitem(yt.LAST_ERROR, "status", 403)
    monkeypatch.setitem(yt.LAST_ERROR, "text", "HTTP 403: blocked")

    calls = {"n": 0}

    def failing(*args):
        calls["n"] += 1
        return None

    monkeypatch.setattr(yt, "_alternatives_from_query", failing)

    lines = []
    cs.warm(print_line=lines.append)

    assert calls["n"] == 1                    # stopped at the first song
    assert any("403" in line for line in lines)



def test_slow_down_waits_and_retries(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES", {"happy": [("Song G", "Z", "")]})
    monkeypatch.setattr(cs, "RATE_LIMIT_WAIT_SECONDS", 0)
    monkeypatch.setattr(cs, "PAUSE_BETWEEN_SONGS", 0)

    answers = ["429", _fake_found(["gggggggggg1"])]

    def flaky(*args):
        answer = answers.pop(0)
        if answer == "429":
            raise yt._RateLimited()
        return answer

    monkeypatch.setattr(yt, "_alternatives_from_query", flaky)

    cs.warm(print_line=lambda *_: None)

    assert cs.youtube_playlists()["happy"][0]["videoId"] == "gggggggggg1"


def test_429_counts_as_quota_for_the_app():
    assert issubclass(yt._RateLimited, yt._QuotaExceeded)


def test_optional_match_title_is_used_for_matching(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "PAUSE_BETWEEN_SONGS", 0)
    monkeypatch.setattr(cs, "CURATED_SAMPLES",
                        {"neutral": [("Blossom (一路生花)", "温奕心", "", "一路生花")]})

    seen = {}

    def capture(query, music_only, language, song, artist, original, target):
        seen["target"] = target
        return _fake_found(["hhhhhhhhhh1"])

    monkeypatch.setattr(yt, "_alternatives_from_query", capture)

    cs.warm(print_line=lambda *_: None)

    assert seen["target"] == yt._norm("一路生花")
    assert cs.youtube_playlists()["neutral"][0]["title"] == "Blossom (一路生花)"



def test_a_hand_picked_video_needs_no_search(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES", {"happy": [("Song H", "Toma", "")]})
    monkeypatch.setattr(cs, "FIXED_VIDEOS", {("Song H", "Toma"): "y_udJSHQzjE"})
    monkeypatch.setattr(yt, "_alternatives_from_query",
                        lambda *a: (_ for _ in ()).throw(AssertionError("searched")))
    monkeypatch.setattr(yt, "_fetch_details", lambda ids: [])

    cs.warm(print_line=lambda *_: None)

    song = cs.youtube_playlists()["happy"][0]
    assert song["videoId"] == "y_udJSHQzjE" and song["artist"] == "Toma"



def test_search_uses_the_real_title_not_the_display_title(monkeypatch):

    monkeypatch.setattr(yt, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(cs, "CURATED_SAMPLES",
                        {"neutral": [("Road to Success (灿如繁星)", "林小玥", "", "灿如繁星")]})
    monkeypatch.setattr(cs, "FIXED_VIDEOS", {})     # force a real search

    seen = {}

    def capture(query, *args):
        seen["query"] = query
        return _fake_found(["iiiiiiiiii1"])

    monkeypatch.setattr(yt, "_alternatives_from_query", capture)

    cs.warm(print_line=lambda *_: None)

    assert seen["query"] == "林小玥 灿如繁星"