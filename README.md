# AIMuse

**Tell it how you feel — it builds you a playlist.**
AIMuse reads a sentence about your mood, works out what you're feeling (mood, energy,
situation, language, artist), and turns that into a playlist of songs that actually play.

> Screenshot / demo GIF: add one at `docs/demo.gif` and it will show up here.
> `![AIMuse demo](docs/demo.gif)`

## Features

- **Understands more than a mood word.** Detects one of 7 core moods (happy, sad, calm, angry,
  romantic, energetic, neutral) plus a secondary mood, energy level, context ("nostalgic"),
  activity ("night drive"), genre, a requested language ("play some telugu songs") and a named
  artist ("songs like Arijit Singh"). Handles negation ("not feeling good" → sad), emoji,
  mixed feelings, and the way people actually type in India — Hinglish ("mood off yaar") and
  Telugu-English ("chala badhaga undi").
- **Notices when someone needs more than music.** Phrases of real distress never read as
  "neutral": the mood becomes sad, the gentle uplift playlist is recommended, and a calm card
  shows the Tele-MANAS helpline (14416). This check is rule-based and always runs.
- **Two playlist modes.** *Mood-based* matches how you feel; *Mood-uplifting* starts where you are
  and gently moves you toward something brighter.
- **Songs that really play.** Every YouTube candidate passes three checks before it is listed
  (search filters → `videos.list` playability → a free oEmbed probe).
- **Self-healing playlists.** If a song still fails in the browser, AIMuse finds *other uploads of
  the same song* on different channels and tries them until one plays. Embedding is disabled per
  owner, so the next attempt deliberately comes from a different channel.
- **Learns which channels block embeds.** Every failed video counts against its channel
  (`src/bad_channels.json`); channels that keep failing sink in future rankings, which also saves
  API quota.
- **Never an empty playlist.** The last good playlist per mood and language is saved to
  `data/playlist_snapshot.json` and served when YouTube's daily quota runs out. It never crosses
  languages: an English request never gets a Hindi mix.
- **Clean song names.** Messy YouTube titles (`NiziU 『Make you happy』 M/V`) become
  *Make you happy — NiziU*.
- **Live audio visualizer** for the built-in sample songs: a 64-bar spectrum analyzer driven by the
  Web Audio API, with kick-drum beat detection that also pulses the glow behind the vinyl.
- **Interaction design:** a moonlight cursor ring, pointer-following glow and tilt, staggered
  float-ins, a confidence count-up and a self-drawing "How AIMuse hears you" timeline
  (`static/effects.js`). All of it switches off on touch screens, with reduced-motion settings and
  with the **Reduce effects** button.
- **Light and dark themes** (follows your device until you choose; no flash on load).

## Quick start (Windows PowerShell)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
$env:YOUTUBE_API_KEY = "your-key"     # or set it once in Windows "Environment Variables"
python app.py
```

Open <http://127.0.0.1:5000>. macOS / Linux: `source venv/bin/activate` and
`export YOUTUBE_API_KEY=your-key`. A `.env` file with the same variable also works.

Without a YouTube key the app still runs; the YouTube box explains what is missing and the
built-in sample songs keep working. `http://127.0.0.1:5000/health` shows what is configured.

### Configuration

| Variable          | Default | Meaning                                                            |
|-------------------|---------|--------------------------------------------------------------------|
| `YOUTUBE_API_KEY` | —       | YouTube Data API v3 key. Environment variable (or `.env`).         |
| `YOUTUBE_REGION`  | `IN`    | Country code used to skip region-blocked videos. Empty = no filter. |

### Sample songs

Put audio files in `static/Moods/<mood>/` (`happy`, `sad`, `calm`, `angry`, `romantic`,
`energetic`, `neutral`). The server scans the folders, so adding or renaming a file needs no code
change. To fix a wrongly-labelled title/artist, edit `SAMPLE_METADATA` in `src/sample_names.py`.
The folder is git-ignored (the files are copyrighted), so the deployed site simply hides the
"sample songs, by mood" block.

### Demo snapshot (run once after the daily quota resets)

```powershell
flask --app app warm-cache
```

Builds one playlist per mood and saves it to `data/playlist_snapshot.json`. Commit that file:
the deployed site falls back to it when the quota is used up.

## Project layout

```
app.py                      Flask app: routes + the emotion-understanding engine
index.html                  Single-page front-end (served as a template)
Procfile                    Start command for hosting (gunicorn)
static/
  script.js                 UI logic, YouTube player, self-healing swaps, visualizer, themes
  style.css                 Design system, light + dark themes
  effects.js / effects.css  Cursor ring, glow + tilt, float-ins, timeline
  Moods/<mood>/*.mp3        Sample songs (local only, git-ignored)
data/
  playlist_snapshot.json    Saved playlists for when the quota runs out
src/
  youtube_recommender.py    Query building, search, verification, ranking, replacement engine
  sample_names.py           File name -> (title, artist) for the sample songs
  preprocessing.py          Text pre-processing
  test_mood.py              Golden set for the mood engine
  test_recommender.py       Recommender, replacement engine, snapshot, channel learning
  conftest.py               Test isolation (never touches real data files)
```

## How a playlist is made

```
text ──► analyze_text() ──► emotional profile ──► search query ──► YouTube search (per language)
        mood, energy,        (mood, energy,        "sad emotional     │
        context, language,    context, activity,    songs telugu"     ▼
        artist                genre, language,     3-layer playability check ──► rank + de-duplicate
                              artist)                                                │
                                                                                     ▼
                       browser plays it ◄── playlist ◄── one song per artist, languages interleaved
                              │
                              └─ error 100/101/150? ─► /recommend/replace ─► other uploads of the
                                                        same song, different channels first
```

Ranking combines YouTube's relevance, log-scaled popularity, like ratio, song-like duration
(compilations over 10 minutes are rejected), mood words in the title, native-script titles for
the requested language, a large boost for a requested artist, and a learned penalty for channels
whose videos keep refusing to embed. Remixes, covers, edits and "best of" mixes are penalised.

## API

| Method | Route                | Purpose                                                        |
|--------|----------------------|----------------------------------------------------------------|
| GET    | `/`                  | The app                                                        |
| POST   | `/analyze`           | `{text}` → detected mood, confidence, understanding chips      |
| POST   | `/recommend`         | `{text, emotion, mode, confidence}` → verified YouTube songs   |
| POST   | `/recommend/replace` | A song failed → pool of other uploads of the same song         |
| POST   | `/recommend/report`  | A video failed in a real browser → blacklisted permanently     |
| GET    | `/api/samples`       | Sample songs found in `static/moods/`                          |
| GET    | `/health`            | Diagnostics                                                    |

## Tests

```powershell
python -m pytest -q src
```

93 tests. `test_mood.py` is a golden set of real sentences (negation, Hinglish, Telugu-English,
distress, gibberish); `test_recommender.py` covers query building, channel-diversity ordering,
the replacement engine (quota back-off, blacklisting), the demo snapshot and channel learning.
YouTube calls are replaced with in-memory fakes, so it runs offline in under a second.

## Design notes and known limits

- **Quota.** A YouTube search costs 100 of the 10,000 daily units. A fresh 7-language "Mix"
  playlist is about 700 units, a single-language one about 100; results are cached for an hour,
  then served from the snapshot if YouTube can't answer. A failed song costs up to 300 units for
  its replacement search; the pool is cached.
- **Embedding blocks are invisible to the API.** Some uploaders (often big labels) block playback
  outside youtube.com; only the real player finds out. AIMuse heals around it and learns from it.
- **The visualizer only exists for the sample songs.** YouTube plays inside its own iframe, and
  browsers do not let a page analyse that audio.
- **Beat detection** looks for kick-drum energy jumping above its recent average; songs with a
  very quiet or absent kick show softer bars.
- `src/bad_videos.json` and `src/bad_channels.json` are created at runtime and are git-ignored.

## Roadmap

- [ ] Understand mood with a free LLM API (Groq) for sarcasm and unusual phrasing, keeping the
      rule engine as fallback and the distress check rule-based
- [ ] Like / skip signals and "more like this"; uplift playlists ordered as an emotional journey
- [ ] Mood-tinted theme, beat-reactive particles, Media Session (media keys)
- [ ] Anonymised analytics dashboard (moods, languages, skip and failure rates)
- [ ] Labelled test set + accuracy report for the mood classifier
- [ ] Deployment