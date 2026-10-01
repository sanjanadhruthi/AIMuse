"""Shared test setup: project root on the path, and a private snapshot file."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import youtube_recommender as yt  # noqa: E402
from src import curated_samples  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_snapshot(monkeypatch, tmp_path):
    """Tests must never read or write the real data/playlist_snapshot.json."""

    monkeypatch.setattr(yt, "_SNAPSHOT_FILE", str(tmp_path / "snapshot.json"))
    monkeypatch.setattr(yt, "_SNAPSHOT_LOADED", False)
    monkeypatch.setattr(yt, "_BAD_CHANNELS_FILE", str(tmp_path / "bad_channels.json"))
    monkeypatch.setattr(yt, "_BAD_CHANNELS", {})
    monkeypatch.setattr(yt, "_PINNED_FILE", str(tmp_path / "pinned.json"))
    monkeypatch.setattr(yt, "_PINNED", {})
    monkeypatch.setattr(yt, "_PINNED_LOADED", False)
    monkeypatch.setattr(curated_samples, "_FILE", str(tmp_path / "sample_videos.json"))
    monkeypatch.setattr(curated_samples, "PAUSE_BETWEEN_SONGS", 0)
    monkeypatch.setattr(curated_samples, "RETRY_WAIT_SECONDS", 0)
    monkeypatch.setattr(curated_samples, "RATE_LIMIT_WAIT_SECONDS", 0)
    yt._SNAPSHOTS.clear()
    yield
    yt._SNAPSHOTS.clear()