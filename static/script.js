/* =========================================================
   AIMUSE — INTERACTION ENGINE
   ========================================================= */


/* =========================================================
   01. ELEMENTS
   ========================================================= */

const entryScreen = document.getElementById("entry-screen");
const enterButton = document.getElementById("enter-button");
const mainExperience = document.getElementById("main-experience");

const entryMusic = document.getElementById("entry-music");
const musicStatus = document.getElementById("music-status");
const nowPlayingTrack = document.getElementById("now-playing-track");


const moodInput = document.getElementById("mood-input");
const characterCount = document.getElementById("character-count");
const analyzeButton = document.getElementById("analyze-button");
const moodError = document.getElementById("mood-error");

const emotionSection = document.getElementById("emotion-section");
const careCard = document.getElementById("care-card");
const musicStage = document.querySelector(".music-stage");
const aiPanel = document.querySelector(".ai-panel");
const samplePanel = document.querySelector(".sample-panel");
const moodPlaylistsBlock = document.getElementById("mood-playlists");
const scrollCue = document.getElementById("scroll-cue");
const playlistSection = document.getElementById("playlist-section");
const musicSection = document.getElementById("music-section");

const detectedEmotion = document.getElementById("detected-emotion");
const confidenceFill = document.getElementById("confidence-fill");
const confidenceValue = document.getElementById("confidence-value");

const playlistHeading = document.getElementById("playlist-heading");
const playlistContextNote = document.getElementById("playlist-context-note");
const playlistOptionsWrap = document.getElementById("playlist-options");
const matchOption = document.getElementById("match-option");
const upliftOption = document.getElementById("uplift-option");
const playlistOptions = document.querySelectorAll(".playlist-option");

const playlistMoodText = document.getElementById("playlist-mood-text");
const playerPlaceholder = document.getElementById("player-placeholder");
const playerPlaceholderTitle = document.getElementById("player-placeholder-title");
const playerPlaceholderSubtitle = document.getElementById("player-placeholder-subtitle");
const songList = document.getElementById("song-list");
const songCount = document.getElementById("song-count");
const playlistPanelNote = document.getElementById("playlist-panel-note");
const openOnYouTube = document.getElementById("open-on-youtube");

const sampleSongList = document.getElementById("sample-song-list");
const sampleSongCount = document.getElementById("sample-song-count");
const samplePanelNote = document.getElementById("sample-panel-note");
const samplePanelTitle = document.getElementById("sample-panel-title");

const understandingWrap = document.getElementById("understanding");
const understandingHeadline = document.getElementById("understanding-headline");
const understandingChips = document.getElementById("understanding-chips");

const youtubePlayerWrap = document.getElementById("youtube-player-wrap");
const youtubePlayerContainer = document.getElementById("youtube-player");
const sampleAudio = document.getElementById("sample-audio");

const originalTracksGrid = document.getElementById("original-tracks-grid");
const moodTabs = document.getElementById("mood-tabs");
const moodPlaylistPanel = document.getElementById("mood-playlist-panel");

const miniPlayer = document.getElementById("mini-player");
const miniPlayerLabel = document.getElementById("mini-player-label");
const miniPlayerTrack = document.getElementById("mini-player-track");
const miniPlayerToggle = document.getElementById("mini-player-toggle");
const sampleVisualizerCanvas = document.getElementById("sample-visualizer");

const themeToggle = document.getElementById("theme-toggle");


/* =========================================================
   02. AIMUSE ORIGINAL TRACKS
   ========================================================= */

/*
    Four original AIMUSE tracks, with the display metadata
    used everywhere a track name is shown: the entry
    indicator, the mini-player, and the discovery grid.
*/

const entryTracks = [
    { file: "Where Snow Meets the Sunlight.mp3", title: "Where Snow Meets the Sunlight" },
    { file: "Floating on Silver Mist.mp3", title: "Floating on Silver Mist" },
    { file: "Footsteps in the Falling Snow.mp3", title: "Footsteps in the Falling Snow" },
    { file: "Whispers in the Moonlight.mp3", title: "Whispers in the Moonlight" }
];

let currentTrackIndex = 0;


/*
    Which original opens the visit:
      - the very first visit: "Where Snow Meets the Sunlight",
      - every visit after that: the NEXT one in the list, so all
        four take turns (1 → 2 → 3 → 4 → 1 …).
    The browser remembers the last one in localStorage. If that
    isn't available (private mode, blocked storage) it simply
    starts with track 1, like before.
    Within a visit, each track still flows into the next.
*/

const ENTRY_TRACK_KEY = "aimuse:last-entry-track";

function chooseEntryTrack() {

    let index = 0;

    try {

        const last = parseInt(localStorage.getItem(ENTRY_TRACK_KEY), 10);

        if (Number.isInteger(last) && last >= 0) {
            index = (last + 1) % entryTracks.length;
        }

        localStorage.setItem(ENTRY_TRACK_KEY, String(index));

    } catch (error) {
        index = 0;
    }

    loadTrack(index, { autoplay: false });

}


/*
    Load a specific track by index without necessarily
    playing it. Used on first choice, and whenever the user
    picks a different original track from the discovery grid.
*/

function loadTrack(index, options = {}) {

    const track = entryTracks[index];

    if (!track) return;

    currentTrackIndex = index;

    entryMusic.src =
        `/static/${encodeURIComponent(track.file)}`;

    entryMusic.loop = false;
    entryMusic.volume = 1.0;

    updateNowPlayingDisplay();
    updateMiniPlayerTrack();
    highlightPlayingOriginalCard();

    if (options.autoplay) {
        startEntryMusic();
    }
}


function updateNowPlayingDisplay() {

    if (!nowPlayingTrack) return;

    const track = entryTracks[currentTrackIndex];

    if (track && !entryMusic.paused) {
        nowPlayingTrack.textContent = `♪ ${track.title}`;
        nowPlayingTrack.classList.add("visible");
    } else {
        nowPlayingTrack.classList.remove("visible");
    }
}


/*
    The title the mini-player shows: the current AIMuse
    original, or whichever sample / YouTube song is playing.
*/

function currentTitle() {

    if (activeSource === "entry") {

        const track = entryTracks[currentTrackIndex];

        return track ? track.title : "—";

    }

    return activeSongTitle || "—";

}


function updateMiniPlayerTrack() {

    if (!miniPlayerTrack) return;

    miniPlayerTrack.textContent = currentTitle();
}


/* =========================================================
   03. AUDIO ENGINE — AUTOPLAY, ORDER, ACTIVE SOURCE
   ========================================================= */

/*
    Three things can play: the AIMuse originals ("entry"), a
    local sample song ("sample"), or a YouTube pick
    ("youtube"). Only ever one at a time — whichever started
    last owns the mini-player (its title, play/pause button
    and progress bar).
*/

let activeSource = "entry";
let activeSongTitle = "";

let ytPlayer = null;
let ytApiReady = false;
let pendingVideoId = null;
let currentVideoId = null;

let entryTrackFailures = 0;


/*
    AUTOPLAY — WHAT BROWSERS ACTUALLY ALLOW

    Chrome, Edge, Safari and Firefox all refuse to play SOUND
    on a page until the person has interacted with it (a click,
    a key press or a tap). Moving the mouse or scrolling does
    not count. No website can get around this — so the best
    possible behaviour, and what this does, is:

      1. Try to play WITH sound the moment the page opens. This
         works when the browser already trusts the site (its
         "media engagement" score, or the site being allowed to
         autoplay in the browser's settings).
      2. If that is blocked, start playing MUTED. Muted playback
         is always allowed, so the first track is already
         running (progress bar moving) instead of silent.
      3. The first real gesture anywhere on the page (click, tap,
         key press) switches the sound on. If the browser still
         refuses, we simply wait for the NEXT gesture.
      4. ENTER is itself a click, so the music is audible as soon
         as the person steps inside.

    On top of that the engine retries when the audio becomes
    ready and when the tab becomes visible, and it always tells
    the person the true state instead of just saying "paused".
*/

// True while the AIMuse originals SHOULD be playing (until the
// person pauses them, or picks another song).
let entryWanted = true;

// True once audio has actually started at least once.
let entryStarted = false;

// A human-readable file problem, if the tracks can't load.
let entryFileProblem = "";


function isBenignPlayError(error) {

    // AbortError: another load replaced this one.
    // NotSupportedError: the file itself failed to load —
    // that's reported (and skipped) by the "error" listener.

    return Boolean(error) &&
        (error.name === "AbortError" || error.name === "NotSupportedError");

}


/*
    Every place that intentionally stops the originals goes
    through here, so the engine knows the silence is deliberate
    and doesn't fight the person by restarting it.
*/

function pauseEntryMusic() {

    entryWanted = false;

    entryMusic.pause();

}


async function playEntryMusic() {

    entryWanted = true;

    // Whatever else was playing hands over to the AIMuse track.
    endPlayback();

    // 1. With sound.

    try {

        entryMusic.muted = false;

        await entryMusic.play();

        return true;

    } catch (error) {

        if (isBenignPlayError(error)) return false;

        console.info(
            "AIMuse: sound autoplay was blocked by the browser (",
            error && error.name,
            ") — starting muted until the first click, tap or key press."
        );

    }

    // 2. Muted. Allowed on its own for <video> elements only — which is
    //    why #entry-music is a <video> (a muted <audio> is refused too).

    try {

        entryMusic.muted = true;

        await entryMusic.play();

        armSoundUnlock();

        updateEntryStatus();

        return true;

    } catch (error) {

        if (!isBenignPlayError(error)) {

            console.info(
                "AIMuse: even muted playback was blocked (",
                error && error.name,
                ") — waiting for the first click, tap or key press."
            );

            armSoundUnlock();

            updateEntryStatus();

        }

        return false;

    }

}


/* Kept as the names the rest of the file uses. */

function startEntryMusic() {

    return playEntryMusic();

}


function attemptMusicPlayback() {

    return playEntryMusic();

}



/*
    Un-mutes the entry music with a short fade-in (about 1.5 s), so
    the moment the first click "opens the sound" feels intentional.
*/

let entryFadeTimer = null;

function fadeInEntryMusic(duration = 1500) {

    clearInterval(entryFadeTimer);

    const target = 1;

    entryMusic.volume = 0;
    entryMusic.muted = false;

    const started = performance.now();

    entryFadeTimer = setInterval(() => {

        const progress = Math.min(1, (performance.now() - started) / duration);

        entryMusic.volume = target * progress;

        if (progress >= 1) clearInterval(entryFadeTimer);

    }, 50);

}

let soundUnlockArmed = false;

// Only genuine user-activation events. Never mousemove, wheel or
// scroll — the browser ignores those for sound. (touchstart and
// pointerdown are deliberately absent too: Chrome only counts a
// touch as activation once it ENDS.)
const SOUND_UNLOCK_EVENTS = ["pointerup", "mouseup", "click", "keydown", "touchend"];


function armSoundUnlock() {

    if (soundUnlockArmed) return;
    soundUnlockArmed = true;

    const unlock = () => {

        SOUND_UNLOCK_EVENTS.forEach(evt =>
            document.removeEventListener(evt, unlock, true)
        );

        soundUnlockArmed = false;

        if (activeSource !== "entry" || !entryWanted) return;

        // Bring the sound in gently instead of an abrupt jump.
        fadeInEntryMusic();

        if (entryMusic.paused) {

            // Still refused? Wait for the next gesture.
            entryMusic.play().catch(error => {

                if (!isBenignPlayError(error)) armSoundUnlock();

            });

        }

        updateEntryStatus();
        updateNowPlayingDisplay();

    };

    SOUND_UNLOCK_EVENTS.forEach(evt =>
        document.addEventListener(evt, unlock, true)
    );

}


function updateEntryStatus() {

    if (!musicStatus) return;

    if (entryFileProblem) {
        musicStatus.textContent = entryFileProblem;
        return;
    }

    if (entryMusic.paused) {

        // Browsers only allow sound after the first click/tap,
        // and pressing ENTER is that click — so say it softly.
        musicStatus.textContent =
            entryWanted && !entryStarted
                ? "Music begins when you enter"
                : "Music paused";

        return;

    }

    musicStatus.textContent =
        entryMusic.muted
            ? "Music begins when you enter"
            : "AIMuse is playing";

}


/*
    Retry hooks: if the first attempt came too early (audio not
    ready yet) or the tab was in the background, try again as
    soon as it makes sense. Each is a no-op unless the originals
    are supposed to be playing and aren't.
*/

function retryEntryPlaybackIfNeeded() {

    if (
        entryWanted &&
        activeSource === "entry" &&
        entryMusic.paused &&
        !entryFileProblem &&
        entryMusic.getAttribute("src")
    ) {
        playEntryMusic();
    }

}

document.addEventListener("visibilitychange", () => {

    if (document.visibilityState === "visible") {
        retryEntryPlaybackIfNeeded();
    }

});

window.addEventListener("load", retryEntryPlaybackIfNeeded);

entryMusic.addEventListener("canplay", retryEntryPlaybackIfNeeded);


entryMusic.addEventListener("play", () => {

    syncMiniPlayerState();

});


entryMusic.addEventListener("playing", () => {

    entryTrackFailures = 0;
    entryStarted = true;
    entryFileProblem = "";

    updateEntryStatus();
    updateNowPlayingDisplay();
    syncMiniPlayerState();

});


entryMusic.addEventListener("pause", () => {

    updateEntryStatus();
    syncMiniPlayerState();

});


entryMusic.addEventListener("volumechange", updateEntryStatus);


/*
    When a track finishes, the next one starts — in order,
    wrapping from the last back to the first.
*/

entryMusic.addEventListener("ended", () => {

    if (activeSource !== "entry") return;

    loadTrack(
        (currentTrackIndex + 1) % entryTracks.length,
        { autoplay: true }
    );

});


/*
    If a track file can't be loaded (missing file, wrong
    name), say exactly which one in the console and skip to
    the next instead of going silent.
*/

entryMusic.addEventListener("error", () => {

    // Clearing the source also raises "error" — ignore that.
    if (!entryMusic.getAttribute("src")) return;

    const failed = entryTracks[currentTrackIndex];

    console.warn(
        "AIMuse: couldn't load",
        failed ? failed.file : "the track",
        "— check that this exact file name exists in the static folder:",
        entryMusic.currentSrc
    );

    if (activeSource !== "entry") return;

    entryTrackFailures += 1;

    if (entryTrackFailures >= entryTracks.length) {

        entryFileProblem =
            "Couldn't load the AIMuse tracks — check the static folder";

        updateEntryStatus();

        return;

    }

    musicStatus.textContent =
        `Couldn't load "${failed ? failed.title : "a track"}" — skipping`;

    loadTrack(
        (currentTrackIndex + 1) % entryTracks.length,
        { autoplay: true }
    );

});


/*
    Prepare music immediately: load this visit's opening track
    (see chooseEntryTrack) and try to start it. The originals
    then play in order, one after another, forever.
*/

chooseEntryTrack();

attemptMusicPlayback();


/* =========================================================
   04. FAIRY DUST
   =========================================================
   A handful of glowing motes that drift slowly through the empty
   parts of the page. They never sit on text or boxes:

     - the canvas lives in the background layer, BEHIND all content,
     - and each mote also dissolves smoothly as it approaches any
       text block or card (the "avoid" list below), so it can never
       peek through the glass or between letters.

   Everything is one <canvas>, so it costs very little; it stops
   when the tab is hidden and when "Reduce effects" is on.
   ========================================================= */

const dustCanvas = document.getElementById("dust-canvas");

// People who asked their system for less motion get almost-still dust.
const dustPrefersStill =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const DUST_AVOID_SELECTORS = [
    // entry screen
    ".entry-eyebrow", ".entry-title", ".entry-description", ".portal-wrapper",
    ".entry-hint", ".music-indicator",
    // navigation
    ".navbar .brand", ".nav-links",
    // headings and copy
    ".main-experience h1", ".main-experience h2", ".main-experience h3",
    ".hero-description", ".section-heading", ".section-eyebrow",
    ".no-idea-subtitle", ".subsection-label", ".music-heading",
    ".playlist-context-note", ".understanding-headline",
    // boxes
    ".mood-card", ".emotion-card", ".scroll-cue", ".playlist-option",
    ".stage-player", ".ai-panel", ".sample-panel", ".playlist-panel",
    ".original-tracks-grid", ".mood-tabs", ".mood-playlist-panel",
    ".step-card", ".future-modes", ".footer",
    // floating controls
    ".mini-player", ".settings-dock"
].join(",");

const dust = {
    canvas: dustCanvas,
    ctx: dustCanvas ? dustCanvas.getContext("2d") : null,
    width: 0,
    height: 0,
    ratio: 1,
    motes: [],
    rects: [],
    rectsStale: true,
    lastRectTime: 0,
    lastFrame: 0,
    raf: 0,
    colors: ["217, 169, 189", "185, 172, 212", "169, 207, 197"],
    core: "255, 255, 255"
};

// Pixels around a text block / box that stay dust-free, and how wide the fade is.
const DUST_CLEARANCE = 10;
const DUST_FADE_BAND = 46;

function refreshDustColors() {

    const style = getComputedStyle(document.body);

    const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;

    dust.colors = [
        read("--dust-a", "217, 169, 189"),
        read("--dust-b", "185, 172, 212"),
        read("--dust-c", "169, 207, 197")
    ];

    dust.core = read("--dust-core", "255, 255, 255");

}

function sizeDustCanvas() {

    if (!dust.canvas) return;

    dust.ratio = Math.min(window.devicePixelRatio || 1, 2);

    dust.width = window.innerWidth;
    dust.height = window.innerHeight;

    dust.canvas.width = Math.round(dust.width * dust.ratio);
    dust.canvas.height = Math.round(dust.height * dust.ratio);

    dust.ctx.setTransform(dust.ratio, 0, 0, dust.ratio, 0, 0);

    // Enough to feel magical, never a blizzard: ~30 on a laptop
    // screen, ~14 on a phone.
    const wanted = Math.max(
        dust.width < 600 ? 22 : 14,
        Math.min(38, Math.round((dust.width * dust.height) / 58000))
    );

    while (dust.motes.length < wanted) dust.motes.push(newMote(true));
    dust.motes.length = wanted;

    dust.rectsStale = true;

}

function newMote(anywhere) {

    const angle = Math.random() * Math.PI * 2;

    return {
        x: Math.random() * dust.width,
        y: anywhere ? Math.random() * dust.height : dust.height + 20,
        heading: angle,
        speed: 6 + Math.random() * 12,               // pixels per second
        turn: 0.25 + Math.random() * 0.5,            // how windy its path is
        // phones: a little bigger so the dust is actually visible
        size: (1.6 + Math.random() * 2.2) * (dust.width < 600 ? 1.6 : 1),
        tint: Math.floor(Math.random() * 3),
        phase: Math.random() * Math.PI * 2,
        twinkle: 0.6 + Math.random() * 1.4,
        sparkle: Math.random() < (dust.width < 600 ? 0.5 : 0.32),   // 4-point glint
        age: 0
    };

}

/* Rectangles of every text block / box currently on screen. */

function updateDustRects() {

    const now = performance.now();

    dust.lastRectTime = now;
    dust.rectsStale = false;

    const rects = [];

    document.querySelectorAll(DUST_AVOID_SELECTORS).forEach(element => {

        const box = element.getBoundingClientRect();

        if (box.width < 2 || box.height < 2) return;
        if (box.bottom < -60 || box.top > dust.height + 60) return;
        if (box.right < -60 || box.left > dust.width + 60) return;

        const style = getComputedStyle(element);

        if (style.visibility === "hidden" || style.display === "none") return;

        rects.push([box.left, box.top, box.right, box.bottom]);

    });

    dust.rects = rects;

}

/* 0 = on / very near text or a box, 1 = out in the open. */

function dustOpenness(x, y) {

    /*
        Phones: the cards fill almost the whole width, so dust that
        strictly avoided every box was nearly never visible. There it
        drifts over boxes too, just softer (never below 55%).
    */
    const floor = dust.width < 600 ? 0.55 : 0;

    let nearest = Infinity;

    for (let i = 0; i < dust.rects.length; i++) {

        const r = dust.rects[i];

        const dx = Math.max(r[0] - x, 0, x - r[2]);
        const dy = Math.max(r[1] - y, 0, y - r[3]);

        const distance = Math.hypot(dx, dy);

        if (distance < nearest) nearest = distance;

        if (nearest === 0) return floor;

    }

    const t = Math.min(1, Math.max(0, (nearest - DUST_CLEARANCE) / DUST_FADE_BAND));

    return floor + (1 - floor) * t * t * (3 - 2 * t);      // smoothstep

}

function drawDustFrame(time) {

    dust.raf = requestAnimationFrame(drawDustFrame);

    if (!dust.ctx) return;

    const ctx = dust.ctx;

    if (document.body.classList.contains("reduce-effects")) {
        ctx.clearRect(0, 0, dust.width, dust.height);
        return;
    }

    const dt = Math.min(0.1, (time - (dust.lastFrame || time)) / 1000);

    dust.lastFrame = time;

    // Layout can change without a scroll (reveals, resizes, tab switches).
    if (dust.rectsStale || time - dust.lastRectTime > 400) {
        updateDustRects();
    }

    const calm = dustPrefersStill ? 0.25 : 1;
    const seconds = time / 1000;

    ctx.clearRect(0, 0, dust.width, dust.height);

    for (const mote of dust.motes) {

        // A slow, meandering path: heading wanders gently on two sine waves.
        mote.heading +=
            (Math.sin(seconds * mote.turn + mote.phase) +
             0.6 * Math.sin(seconds * mote.turn * 2.3 + mote.phase * 1.7)) * dt * 0.9;

        mote.x += Math.cos(mote.heading) * mote.speed * calm * dt;
        mote.y += Math.sin(mote.heading) * mote.speed * calm * dt - 1.5 * calm * dt;

        mote.age += dt;

        // Left the screen: reappear somewhere else, softly.
        if (mote.x < -30 || mote.x > dust.width + 30 || mote.y < -30 || mote.y > dust.height + 30) {

            Object.assign(mote, newMote(true));
            mote.age = 0;

            continue;

        }

        const fadeIn = Math.min(1, mote.age / 1.8);
        const glint = 0.55 + 0.45 * Math.sin(seconds * mote.twinkle + mote.phase);
        const open = dustOpenness(mote.x, mote.y);

        const alpha = fadeIn * glint * open;

        if (alpha < 0.015) continue;

        const tint = dust.colors[mote.tint];
        const radius = mote.size * 4.2;

        const glow = ctx.createRadialGradient(mote.x, mote.y, 0, mote.x, mote.y, radius);

        glow.addColorStop(0, `rgba(${tint}, ${(0.85 * alpha).toFixed(3)})`);
        glow.addColorStop(1, `rgba(${tint}, 0)`);

        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(mote.x, mote.y, radius, 0, Math.PI * 2);
        ctx.fill();

        // bright core
        ctx.fillStyle = `rgba(${dust.core}, ${(0.95 * alpha).toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(mote.x, mote.y, mote.size * 0.55, 0, Math.PI * 2);
        ctx.fill();

        // little 4-point glint on some of them
        if (mote.sparkle) {

            const arm = mote.size * 3.6 * (0.6 + 0.4 * glint);

            ctx.strokeStyle = `rgba(${dust.core}, ${(0.7 * alpha).toFixed(3)})`;
            ctx.lineWidth = 0.9;
            ctx.beginPath();
            ctx.moveTo(mote.x - arm, mote.y);
            ctx.lineTo(mote.x + arm, mote.y);
            ctx.moveTo(mote.x, mote.y - arm);
            ctx.lineTo(mote.x, mote.y + arm);
            ctx.stroke();

        }

    }

}

if (dustCanvas) {

    sizeDustCanvas();
    refreshDustColors();

    window.addEventListener("resize", sizeDustCanvas);

    // Scrolling moves every block, so the avoid-list must follow.
    window.addEventListener("scroll", () => { dust.rectsStale = true; }, { passive: true });

    dust.raf = requestAnimationFrame(drawDustFrame);

}


/* =========================================================
   05. ENTRY → MAIN WORLD
   ========================================================= */

/*
    The entry-animation video plays full-screen between the
    entry screen and the main experience. The AIMuse
    background track keeps playing the whole time — the clip
    has no audio of its own, so there's nothing to duck.
*/

const portalTransition = document.getElementById("portal-transition");
const portalVideo = document.getElementById("portal-video");


/*
    Browsers can block storage entirely (strict privacy settings,
    some embedded / private contexts) and then even READING
    localStorage throws. These wrappers make that harmless: the site
    simply forgets choices instead of crashing.
*/

function storageGet(key) {

    try {
        return localStorage.getItem(key);
    } catch (error) {
        return null;
    }

}

function storageSet(key, value) {

    try {
        localStorage.setItem(key, value);
    } catch (error) {
        /* not saved — fine */
    }

}


/*
    TWO ENTRY ANIMATIONS, TAKING TURNS
    ----------------------------------
    Every time the site is opened the OTHER animation plays:
    1, 2, 1, 2 ... The last one shown is remembered in the browser
    (localStorage), so each visitor gets their own alternation.

    To add a third animation, drop Entry_Animation_3.mp4 in /static
    and add its name to this list.
*/

const ENTRY_ANIMATIONS = [
    "Entry_Animation.mp4"
];

/*
    TRIMS (in seconds)
    ------------------
    Cuts time off an animation WITHOUT editing the video file:
      start: seconds skipped at the beginning
      end:   seconds cut off the end (the site then opens right away)

    Animation 1 is trimmed by half a second at the END.
    Prefer cutting the beginning instead? Use { start: 0.5, end: 0 }.
*/

/*
    stopAt: the second the animation is cut at (the site opens then).
    Leave it out to use "end" (seconds cut off the end) instead.
*/

const ENTRY_ANIMATION_TRIMS = {
    "Entry_Animation.mp4": { start: 0, end: 0, stopAt: 7 }
};

function entryTrim() {

    return ENTRY_ANIMATION_TRIMS[currentEntryAnimation] || { start: 0, end: 0 };

}

let entryTrimFrame = 0;

/* Opens the site as soon as the playing animation reaches its trimmed end. */

function watchEntryTrim() {

    cancelAnimationFrame(entryTrimFrame);

    const trim = entryTrim();

    if (!trim.end && !trim.stopAt) return;

    const check = () => {

        // Already finished or skipped.
        if (!portalTransition.classList.contains("active")) return;

        const length = portalVideo.duration;

        const cutAt = trim.stopAt
            ? trim.stopAt
            : (Number.isFinite(length) && length > trim.end ? length - trim.end : Infinity);

        if (portalVideo.currentTime >= cutAt) {
            finishEntry();
            return;
        }

        entryTrimFrame = requestAnimationFrame(check);

    };

    entryTrimFrame = requestAnimationFrame(check);

}

const ENTRY_ANIMATION_KEY = "aimuseLastEntryAnimation";

// Files that failed to load this visit (so a broken one is skipped).
const failedEntryAnimations = new Set();

function nextEntryAnimationIndex() {

    try {

        const last = parseInt(
            localStorage.getItem(ENTRY_ANIMATION_KEY),
            10
        );

        const next = Number.isInteger(last)
            ? (last + 1) % ENTRY_ANIMATIONS.length
            : 0;

        localStorage.setItem(ENTRY_ANIMATION_KEY, String(next));

        return next;

    } catch (error) {

        // Storage blocked (private mode?): fall back to a random pick.
        return Math.floor(Math.random() * ENTRY_ANIMATIONS.length);

    }

}

let currentEntryAnimation = ENTRY_ANIMATIONS[nextEntryAnimationIndex()];

function loadEntryAnimation(file) {

    currentEntryAnimation = file;

    portalVideo.src = `/static/${encodeURIComponent(file)}`;

    portalVideo.load();

}

loadEntryAnimation(currentEntryAnimation);
const portalSkip = document.getElementById("portal-skip");

let hasEntered = false;

let entryFinished = false;

/*
    The entry animation is over: open the site.

    - Runs ONCE (the video's "ended" event, the half-second trim and the
      Skip button may all ask for it).
    - The video is only paused, NOT rewound: it keeps showing its last
      frame while it fades away. (Rewinding at once flashed the first
      frame again, which looked like the animation playing twice.)
    - The site starts appearing in the same instant, so the page is
      "there" as the animation ends instead of a moment later.
*/

function finishEntry() {

    if (entryFinished) return;

    entryFinished = true;

    cancelAnimationFrame(entryTrimFrame);

    portalVideo.pause();

    mainExperience.classList.add("visible");

    entryScreen.classList.add("exit");

    document.body.classList.add("entered");

    portalTransition.classList.remove("active");

    showMiniPlayer();

    window.scrollTo({
        top: 0,
        behavior: "instant"
    });

    // Only rewind after the fade-out is completely over.
    setTimeout(() => {
        portalVideo.currentTime = 0;
    }, 1000);

}

enterButton.addEventListener("click", async () => {

    if (hasEntered) return;
    hasEntered = true;


    /* Keep the AIMuse track playing straight through. */

    await startEntryMusic();


    /* Hide the entry screen and start the portal video. */

    entryScreen.classList.add("exit");

    portalTransition.classList.add("active");

    portalVideo.currentTime = entryTrim().start;

    watchEntryTrim();

    portalVideo.play().catch(() => {

        /* If the video can't play for any reason, don't
           strand the user on a blank screen. */

        finishEntry();

    });

});


/* When the clip finishes, reveal the main experience. */

portalVideo.addEventListener("ended", finishEntry);


/*
    If the clip can't load at all (missing file, bad path,
    unsupported format), don't leave the user stuck on a
    black screen — log why, and move on to the main
    experience automatically.
*/

portalVideo.addEventListener("error", () => {

    failedEntryAnimations.add(currentEntryAnimation);

    // This one is missing or unplayable: try the other before giving up.
    const alternative = ENTRY_ANIMATIONS.find(
        file => !failedEntryAnimations.has(file)
    );

    if (alternative) {

        console.warn(
            "AIMuse: couldn't load", currentEntryAnimation,
            "— trying", alternative, "instead."
        );

        loadEntryAnimation(alternative);

        // Already mid-transition? Start the replacement straight away.
        if (portalTransition.classList.contains("active")) {
            portalVideo.currentTime = entryTrim().start;
            watchEntryTrim();
            portalVideo.play().catch(finishEntry);
        }

        return;

    }

    console.warn(
        "AIMuse: no entry animation could be loaded — check that",
        ENTRY_ANIMATIONS.join(" and "),
        "exist in /static:",
        portalVideo.currentSrc
    );

    if (portalTransition.classList.contains("active")) {
        finishEntry();
    }

});


/* Skip button — jump straight to the main experience. */

if (portalSkip) {

    portalSkip.addEventListener("click", finishEntry);

}


/* =========================================================
   06. TEXTAREA CHARACTER COUNTER
   ========================================================= */

if (moodInput) {

    moodInput.addEventListener("input", () => {

        characterCount.textContent =
            moodInput.value.length;

        // NEW:
        // If the user starts correcting their input,
        // remove the previous invalid-input warning.

        moodError.classList.remove("visible");

        moodInput.classList.remove("input-invalid");

    });

}

/* =========================================================
   MOOD INPUT VALIDATION
   ========================================================= */

function isLikelyGibberish(text) {

    const cleaned = text.trim();

    if (!cleaned) {
        return false;
    }

    /*
        Obvious keyboard/random input:
        examples:
        7t9y9iho
        12345678
        8x9q2z
    */

    const hasLetters = /[a-zA-Z]/.test(cleaned);
    const hasNumbers = /\d/.test(cleaned);

    if (!hasLetters) {
        return true;
    }

    /*
        If numbers are mixed heavily into a short string,
        treat it as accidental/random input.

        This still allows normal sentences such as:
        "I am 20 and feeling lonely"
    */

    const letters = (cleaned.match(/[a-zA-Z]/g) || []).length;
    const numbers = (cleaned.match(/\d/g) || []).length;

    if (
        cleaned.length <= 20 &&
        numbers >= 2 &&
        numbers >= letters * 0.3
    ) {
        return true;
    }

    /*
        Detect obvious keyboard-style gibberish such as:
        asdfgh
        qwertyui
        zxcvbn
    */

    const lower = cleaned.toLowerCase();

    const keyboardPatterns = [
        "asdfgh",
        "qwerty",
        "zxcvbn",
        "qazwsx",
        "wsxedc"
    ];

    if (
        keyboardPatterns.some(pattern =>
            lower.includes(pattern)
        )
    ) {
        return true;
    }

    /*
        Word-shape plausibility check.

        A word can contain vowels and still not be a real
        English word — "rtjulyi" has two vowels but no
        English word actually *starts* with "rt" or "rtj".
        Real English words only ever begin with a small,
        known set of consonant clusters (bl, ch, str, thr,
        and so on). If a word's opening consonants aren't in
        that set, or the word is unusually vowel-starved for
        its length, it's very likely accidental input rather
        than a real word AIMuse just doesn't recognise.
    */

    const VALID_INITIAL_CLUSTERS = new Set([
        "bl", "br", "ch", "ck", "cl", "cr", "dr", "dw",
        "fl", "fr", "gh", "gl", "gn", "gr", "kn", "ph",
        "pl", "pr", "ps", "pt", "qu", "rh", "sc", "sh",
        "sk", "sl", "sm", "sn", "sp", "st", "sw", "th",
        "tr", "tw", "wh", "wr",
        "sch", "scr", "shr", "spl", "spr", "squ", "str", "thr",
        // Romanised Hindi / Telugu ("bhot", "dhoka", "khush", "pyaar")
        "bh", "dh", "kh", "jh", "gy", "ky", "py", "ny", "ty", "by", "my",
        "chh"
    ]);

    const words = lower.split(/\s+/);

    for (const word of words) {

        const lettersOnly =
            word.replace(/[^a-z]/g, "");

        /*
            Very long words with no vowels at all are
            usually accidental/random input.
        */

        // "y" counts as a vowel: rhythm, myself, crying, system.
        if (
            lettersOnly.length >= 6 &&
            !/[aeiouy]/.test(lettersOnly)
        ) {
            return true;
        }

        if (lettersOnly.length < 4) {
            continue;
        }

        const leadingConsonants =
            lettersOnly.match(/^[^aeiouy]+/);

        if (leadingConsonants && leadingConsonants[0].length >= 2) {

            const twoLetter = leadingConsonants[0].slice(0, 2);
            const threeLetter = leadingConsonants[0].slice(0, 3);

            if (
                !VALID_INITIAL_CLUSTERS.has(twoLetter) &&
                !VALID_INITIAL_CLUSTERS.has(threeLetter)
            ) {
                return true;
            }
        }
    }

    return false;
}


/*
    A few playful ways to tell the person their input didn't
    look like a real feeling — picked at random so it doesn't
    feel like a robotic, repeated warning.
*/

const MOOD_ERROR_VARIANTS = [
    {
        title: "Haha, what did you just type?",
        message: "Try telling me how you're actually feeling — even a few words are enough."
    },
    {
        title: "Aiyyaaa, wrong format!",
        message: "That doesn't look like a feeling to me. Give it another go?"
    },
    {
        title: "Umm... come again?",
        message: "I couldn't find a real feeling in there. Try a word or two about how you feel."
    },
    {
        title: "That's not quite a mood, is it?",
        message: "Take another look at what you typed and describe your feeling in your own words."
    }
];

function showMoodError() {

    if (!moodError) return;

    const variant =
        MOOD_ERROR_VARIANTS[
            Math.floor(Math.random() * MOOD_ERROR_VARIANTS.length)
        ];

    const titleEl =
        document.getElementById("mood-error-title");

    const messageEl =
        document.getElementById("mood-error-message");

    if (titleEl) titleEl.textContent = variant.title;
    if (messageEl) messageEl.textContent = variant.message;

    moodError.classList.add("visible");

}


/* =========================================================
   07. BACKEND — EMOTION ANALYSIS
   ========================================================= */

let latestEmotion = null;
let latestConfidence = 0;
let latestValence = "neutral";
let latestText = "";


async function analyseMood() {

    const text =
        moodInput.value.trim();


    /* Empty input */

    if (!text) {

        moodInput.focus();

        moodInput.style.boxShadow =
            "0 0 0 5px rgba(217, 169, 189, 0.18)";

        setTimeout(() => {

            moodInput.style.boxShadow = "";

        }, 700);

        return;
    }


    /* Obvious gibberish / accidental input */

    if (isLikelyGibberish(text)) {

        showMoodError();

        moodInput.classList.add("input-invalid");

        moodInput.focus();

        return;
    }


    /* Valid input — remove previous warning */

    moodError.classList.remove("visible");

    moodInput.classList.remove("input-invalid");


    /* Loading state */

    analyzeButton.disabled = true;

    analyzeButton.querySelector(".button-text").textContent =
        "Understanding...";


    try {

        const response =
            await fetch("/analyze", {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    text: text
                })

            });


        const data =
            await response.json();


        if (!response.ok || !data.success) {

            throw new Error(
                data.error ||
                "Unable to analyse your mood."
            );

        }


        /*
            Backend-side safety net — if AIMuse's own emotion
            engine also couldn't find a real feeling in the
            text, show the same playful warning instead of
            pretending it understood.
        */

        if (data.invalid) {

            showMoodError();

            moodInput.classList.add("input-invalid");

            moodInput.focus();

            return;

        }


        /* Store result */

        latestEmotion = data.emotion;
        latestConfidence = data.confidence;
        latestValence = data.valence || "neutral";
        latestText = text;


        /* Show result */

        showEmotionResult(
            data.emotion,
            data.confidence,
            latestValence,
            data.understanding,
            Boolean(data.care)
        );


    } catch (error) {

        console.error(
            "AIMuse analysis error:",
            error
        );

        alert(
            "AIMuse couldn't connect to the backend. " +
            "Please make sure app.py is running."
        );

    } finally {

        analyzeButton.disabled = false;

        analyzeButton.querySelector(".button-text").textContent =
            "Discover my music";

    }

}


/* =========================================================
   08. DISPLAY EMOTION
   ========================================================= */

function formatEmotion(emotion) {

    if (!emotion) return "unknown";

    return emotion.charAt(0).toUpperCase() +
        emotion.slice(1);

}


const PLAYLIST_COPY = {

    negative: {
        heading: "What does your music need to do?",
        note: "You can stay with this feeling, or let AIMuse gently guide you somewhere brighter.",
    },

    neutral: {
        heading: "Let's build on this moment.",
        note: "Your mood doesn't need lifting — here's music that matches exactly where you are.",
    },

    positive: {
        heading: "Let's keep that feeling going.",
        note: "Your mood already feels good, so AIMuse only offers music to match it.",
    }

};


/*
    "What AIMuse understood" — the mood plus everything else it
    picked up (energy, situation, language, genre...). Built with
    textContent so nothing typed by the person is ever parsed as
    HTML.
*/

function renderUnderstanding(understanding) {

    if (!understandingWrap) return;

    const chips = understanding && Array.isArray(understanding.chips)
        ? understanding.chips
        : [];

    if (!chips.length) {
        understandingWrap.classList.add("hidden");
        return;
    }

    if (understandingHeadline) {
        understandingHeadline.textContent = understanding.headline || "";
    }

    understandingChips.innerHTML = "";

    chips.forEach(chip => {

        const el = document.createElement("span");

        el.className = `understanding-chip chip-${chip.kind || "mood"}`;
        el.textContent = chip.label;

        understandingChips.appendChild(el);

    });

    understandingWrap.classList.remove("hidden");

}


function showEmotionResult(emotion, confidence, valence, understanding, care = false) {

    renderUnderstanding(understanding);

    /*
        Real distress: a quiet card with a helpline, above the
        playlists. The backend has already made the mood "sad", so
        the gentle Mood-Uplifting playlist is offered as recommended.
    */

    if (careCard) {
        careCard.classList.toggle("hidden", !care);
    }

    detectedEmotion.textContent =
        formatEmotion(emotion);


    const percentage =
        Math.round(confidence * 100);

    confidenceValue.textContent =
        `${percentage}%`;


    emotionSection.classList.remove("hidden");


    setTimeout(() => {

        confidenceFill.style.width =
            `${percentage}%`;

    }, 100);


    /*
        Only negative emotions get the Mood-Uplifting
        option. Everything else only offers the Mood-Based
        playlist, since there's no moment to change.
    */

    const isNegative = valence === "negative";
    const copy = PLAYLIST_COPY[valence] || PLAYLIST_COPY.neutral;

    if (upliftOption) {
        upliftOption.classList.toggle("hidden", !isNegative);
    }

    if (playlistOptionsWrap) {
        playlistOptionsWrap.classList.toggle("single-option", !isNegative);
    }

    if (playlistHeading) {

        const parts = copy.heading.split(" ");
        const lastWord = parts.pop();

        playlistHeading.innerHTML =
            `${parts.join(" ")} <span data-depth="9">${lastWord}</span>`;

    }

    if (playlistContextNote) {
        playlistContextNote.textContent = copy.note;
    }

    playlistOptions.forEach(option => {
        option.classList.remove("selected");
    });

    playlistSection.classList.remove("hidden");


    // Tell the person the playlists are waiting below.
    showScrollCue();

    /*
        Scroll gently toward the result.
    */

    setTimeout(() => {

        emotionSection.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });

    }, 350);

}



/* =========================================================
   08B. "SCROLL DOWN" CUE UNDER THE MOOD RESULT
   =========================================================
   The playlist options sit below the mood card, but nothing
   says so. The cue appears once a result is shown, scrolls to
   the playlists when clicked, and goes away by itself as soon
   as the playlist section is on screen.
   ========================================================= */

let scrollCueTimer = null;

function showScrollCue() {

    if (!scrollCue) return;

    clearTimeout(scrollCueTimer);

    scrollCue.classList.remove("visible");

    // Wait for the smooth scroll to the card to settle first.
    scrollCueTimer = setTimeout(() => {

        const playlistTop = playlistSection
            ? playlistSection.getBoundingClientRect().top
            : Infinity;

        // Already looking at the playlists? No cue needed.
        if (playlistTop < window.innerHeight * 0.6) return;

        scrollCue.classList.add("visible");

    }, 1400);

}

function hideScrollCue() {

    if (!scrollCue) return;

    clearTimeout(scrollCueTimer);

    scrollCue.classList.remove("visible");

}

if (scrollCue) {

    scrollCue.addEventListener("click", () => {

        hideScrollCue();

        if (playlistSection) {
            scrollToElement(playlistSection, 40);
        }

    });

}

if (playlistSection && "IntersectionObserver" in window) {

    new IntersectionObserver((entries) => {

        entries.forEach(entry => {
            if (entry.isIntersecting) hideScrollCue();
        });

    }, { threshold: 0.3 }).observe(playlistSection);

}


/* =========================================================
   08C. LANGUAGE PICKER
   =========================================================
   Telugu / Hindi / English  -> the playlist has ONLY that language.
   Mix                       -> AIMuse's usual blend of languages.

   The choice is remembered. If a playlist is already on screen and
   the language changes, the AIMuse playlist is rebuilt straight away.
   ========================================================= */

const LANGUAGE_KEY = "aimuseLanguage";

const LANGUAGE_HINTS = {
    telugu: "Only Telugu songs.",
    hindi: "Only Hindi songs.",
    english: "Only English songs.",
    mix: "A blend of Hindi, Telugu, Korean, Japanese, Chinese, Spanish and English."
};

let selectedLanguage = "mix";

const languageOptions = document.getElementById("language-options");
const languageHint = document.getElementById("language-hint");

function languageLabel(choice) {

    return choice.charAt(0).toUpperCase() + choice.slice(1);

}

/* "Happy • Mood Match" — plus the language when it isn't the usual mix. */

function moodChipText(mode) {

    let text =
        `${formatEmotion(latestEmotion)} • ${
            mode === "uplift" ? "Mood Uplift" : "Mood Match"
        }`;

    if (selectedLanguage !== "mix") {
        text += ` • ${languageLabel(selectedLanguage)}`;
    }

    return text;

}

function applyLanguage(choice, { rebuild = false } = {}) {

    if (!Object.prototype.hasOwnProperty.call(LANGUAGE_HINTS, choice)) {
        choice = "mix";
    }

    const changed = choice !== selectedLanguage;

    selectedLanguage = choice;

    if (languageOptions) {

        languageOptions.querySelectorAll(".language-chip").forEach(chip => {

            const active = chip.dataset.language === choice;

            chip.classList.toggle("active", active);
            chip.setAttribute("aria-checked", String(active));

        });

    }

    if (languageHint) {
        languageHint.textContent = LANGUAGE_HINTS[choice];
    }

    storageSet(LANGUAGE_KEY, choice);

    // A playlist is already showing: rebuild it in the new language.
    if (rebuild && changed && currentMode && !musicSection.classList.contains("hidden")) {

        playlistMoodText.textContent = moodChipText(currentMode);

        if (activeSource === "youtube") endPlayback();

        renderAiLoading();

        fetchRealRecommendations(currentMode);

    }

}

if (languageOptions) {

    languageOptions.addEventListener("click", (event) => {

        const chip = event.target.closest(".language-chip");

        if (chip) applyLanguage(chip.dataset.language, { rebuild: true });

    });

    // Arrow keys move between the options, like a native radio group.
    languageOptions.addEventListener("keydown", (event) => {

        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;

        const chips = [...languageOptions.querySelectorAll(".language-chip")];

        const current = chips.findIndex(chip => chip.classList.contains("active"));

        const step = (event.key === "ArrowLeft" || event.key === "ArrowUp") ? -1 : 1;

        const next = chips[(current + step + chips.length) % chips.length];

        event.preventDefault();

        next.focus();

        applyLanguage(next.dataset.language, { rebuild: true });

    });

}

applyLanguage(storageGet(LANGUAGE_KEY) || "mix");


/* =========================================================
   09. ANALYSE BUTTON
   ========================================================= */

analyzeButton.addEventListener(
    "click",
    analyseMood
);


/*
    Ctrl + Enter also analyses the mood.
*/

moodInput.addEventListener(
    "keydown",
    (event) => {

        if (
            event.ctrlKey &&
            event.key === "Enter"
        ) {

            analyseMood();

        }

    }
);


/* =========================================================
   10. SAMPLE SONGS (real files from static/moods)
   ========================================================= */

/*
    The sample songs are NOT hard-coded here and are NOT from
    YouTube. The server scans the static/moods folder and
    returns whatever audio files are in each mood's sub-folder:

        static/moods/happy/*.mp3
        static/moods/sad/*.mp3
        ... calm, angry, romantic, energetic, neutral

    Add, rename or remove a file and the site follows — nothing
    to edit in this script.

        SAMPLE_PLAYLISTS = { mood: [ {title, artist, file, url} ] }
*/

let SAMPLE_PLAYLISTS = {};

let samplesLoaded = false;
let samplesFailed = false;

// The mood + mode currently shown in the music section.
let currentMode = null;
let activeMoodTab = "happy";
let activeSampleMood = null;   // set while the stage shows sample songs


function loadSamplePlaylists() {

    return fetch("/api/samples")

        .then(response => response.json())

        .then(data => {

            if (!data || !data.success) {
                throw new Error("Sample song list was not returned.");
            }

            SAMPLE_PLAYLISTS = data.playlists || {};

            samplesLoaded = true;
            samplesFailed = false;

            /*
                The deployed site ships without the sample MP3s
                (they are copyrighted). No files -> no "sample
                songs, by mood" block at all.
            */

            if (moodPlaylistsBlock) {
                moodPlaylistsBlock.classList.toggle("hidden", !data.total);
            }

            if (!data.total) {
                console.warn(
                    "AIMuse: /api/samples found no audio files — " +
                    "check that they are in static/moods/<mood>/ ."
                );
            }

        })

        .catch(error => {

            console.warn("AIMuse: couldn't load the sample songs —", error);

            samplesFailed = true;

        })

        .finally(refreshSampleUi);

}


/* Re-draw everything that shows sample songs. */

function refreshSampleUi() {

    // rebuild the tabs now that we know which moods have songs
    if (typeof buildMoodTabs === "function") {
        buildMoodTabs();
    }

    if (typeof renderMoodPlaylistPanel === "function") {
        renderMoodPlaylistPanel(activeMoodTab);
    }

    if (activeSampleMood && !document.querySelector("#sample-song-list .song-item.playing")) {
        renderSampleStage(activeSampleMood);
    }

}


/* =========================================================
   10B. SCROLL HELPER
   ========================================================= */

/*
    Scrolls so an element's own content sits a fixed distance
    from the top of the viewport — rather than
    scrollIntoView's default, which would also include the
    element's own top padding as visible blank space.
*/

function scrollToElement(el, offset = 96) {

    if (!el) return;

    const y =
        el.getBoundingClientRect().top +
        window.scrollY -
        offset;

    window.scrollTo({
        top: Math.max(y, 0),
        behavior: "smooth"
    });

}


/* =========================================================
   11. PLAYLIST MODE
   ========================================================= */

playlistOptions.forEach(option => {

    option.addEventListener(
        "click",
        () => {

            const mode =
                option.dataset.mode;

            handlePlaylistChoice(mode);

        }
    );

});


function handlePlaylistChoice(mode) {

    currentMode = mode;

    playlistSection.classList.remove("hidden");
    musicSection.classList.remove("hidden");


    playlistMoodText.textContent = moodChipText(mode);


    /*
        Highlight selected option (a class, not a transform,
        so it doesn't fight with the card's own tilt effect).
    */

    playlistOptions.forEach(option => {
        option.classList.remove("selected");
    });

    const selected =
        document.querySelector(
            `[data-mode="${mode}"]`
        );

    if (selected) {
        selected.classList.add("selected");
    }


    /*
        Reset the player back to its idle state — a fresh
        mood choice means whatever was playing no longer
        applies.
    */

    endPlayback();


    /*
        A mood was chosen: the list beside the player is the
        AIMuse (YouTube) playlist, not the sample songs.
    */

    setStageView("youtube");


    /*
        Box 2 — the AIMuse playlist from YouTube. Shows a loading
        state until the verified songs arrive; it never shows
        sample songs pretending to be YouTube results.
    */

    renderAiLoading();

    fetchRealRecommendations(mode);


    /*
        Scroll to the music player — targeting the heading itself
        (not the whole padded section) so it settles right near
        the top of the screen instead of leaving a gap above it.
    */

    setTimeout(() => {

        scrollToElement(
            document.querySelector(".music-heading"),
            96
        );

    }, 250);

}


/* ---- Which list sits beside the player -------------------- */

/*
    "youtube"  — after a mood was analysed and a playlist chosen
    "samples"  — after a sample song was picked in "Still deciding?"
    Only one list is shown at a time.
*/

function setStageView(view) {

    const showSamples = view === "samples";

    if (aiPanel) aiPanel.classList.toggle("hidden", showSamples);
    if (samplePanel) samplePanel.classList.toggle("hidden", !showSamples);

    if (!showSamples) {
        activeSampleMood = null;
    }

}


/* ---- The sample-song list beside the player ----------------- */

function renderSampleStage(mood) {

    if (!sampleSongList) return [];

    const songs = SAMPLE_PLAYLISTS[mood] || [];

    sampleSongList.innerHTML = "";

    const items = songs.map((song, index) => {
        const item = buildSongItem(song, index + 1, false);
        sampleSongList.appendChild(item);
        return item;
    });

    if (sampleSongCount) {
        sampleSongCount.textContent =
            `${songs.length} song${songs.length === 1 ? "" : "s"}`;
    }

    if (samplePanelTitle) {
        samplePanelTitle.textContent =
            `SAMPLE SONGS · ${String(mood).toUpperCase()}`;
    }

    if (samplePanelNote) {
        samplePanelNote.textContent =
            "Hand-picked songs for this mood, played from YouTube. " +
            "Tell AIMuse how you feel for a playlist made just for you.";
    }

    return items;

}


/*
    A sample song was picked in "Still deciding?": open the
    player, put that mood's list beside it, and play the song.
*/

function openSamplePlaylist(mood, index) {

    musicSection.classList.remove("hidden");

    setStageView("samples");

    activeSampleMood = mood;

    if (playlistMoodText) {
        playlistMoodText.textContent = `${formatEmotion(mood)} · sample songs`;
    }

    const items = renderSampleStage(mood);

    // Clicking the stage item plays it and marks it "playing"
    // in both lists (see buildSongItem).
    if (items[index]) {
        items[index].click();
    }

    setTimeout(() => {

        scrollToElement(
            document.querySelector(".music-heading"),
            96
        );

    }, 150);

}


/* ---- Box 2: the AIMuse (YouTube) playlist ------------------ */

function setAiNote(text) {

    if (playlistPanelNote) {
        playlistPanelNote.textContent = text;
    }

}


function setPlaylistLink(url) {

    if (!openOnYouTube) return;

    if (url) {
        openOnYouTube.href = url;
        openOnYouTube.classList.remove("hidden");
    } else {
        openOnYouTube.removeAttribute("href");
        openOnYouTube.classList.add("hidden");
    }

}


function renderAiLoading() {

    if (!songList) return;

    songList.innerHTML = "";

    for (let i = 0; i < 6; i++) {

        const row = document.createElement("div");

        row.className = "song-skeleton";
        row.setAttribute("aria-hidden", "true");

        songList.appendChild(row);

    }

    if (songCount) songCount.textContent = "…";

    setPlaylistLink("");

    setAiNote("Finding songs for this mood — and checking each one will play…");

}


function renderAiMessage(message, mode, { retry = true } = {}) {

    if (!songList) return;

    songList.innerHTML = "";

    const box = document.createElement("div");

    box.className = "panel-empty";

    const text = document.createElement("p");

    text.textContent = message;

    box.appendChild(text);

    if (retry) {

        const button = document.createElement("button");

        button.type = "button";
        button.className = "panel-retry";
        button.textContent = "Try again";

        button.addEventListener("click", () => {

            renderAiLoading();

            fetchRealRecommendations(mode);

        });

        box.appendChild(button);

    }

    songList.appendChild(box);

    if (songCount) songCount.textContent = "0 songs";

    setPlaylistLink("");

    setAiNote("The sample songs next to this box always work.");

}


function renderAiPlaylist(songs, meta) {

    if (!songList) return;

    songList.innerHTML = "";

    songs.forEach((song, index) => {
        songList.appendChild(buildSongItem(song, index + 1, true));
    });

    if (songCount) {
        songCount.textContent =
            `${songs.length} song${songs.length === 1 ? "" : "s"}`;
    }

    setPlaylistLink(meta && meta.playlist_url);

    if (!playlistPanelNote) return;

    const languages = [...new Set(
        songs.map(song => song.language).filter(Boolean)
    )].map(name => name.charAt(0).toUpperCase() + name.slice(1));

    let note =
        meta && meta.query
            ? `Searched YouTube for “${meta.query}”`
            : "Picked from YouTube for this mood";

    if (languages.length) {
        note += ` in ${languages.join(", ")}`;
    }

    note += ". Each song is checked before it's listed — and if one still won't play, AIMuse finds the same song from another video.";

    if (meta && meta.stale) {
        note = "YouTube couldn't be reached, so these are saved results. " + note;
    }

    setAiNote(note);

}


/*
    Guards against a slow /recommend response landing after
    the person has already picked a different mode — only the
    most recent request is allowed to update the list.
*/

let recommendationRequestId = 0;

async function fetchRealRecommendations(mode) {

    const requestId = ++recommendationRequestId;

    try {

        const response = await fetch("/recommend", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                text: latestText,
                emotion: latestEmotion,
                mode: mode,
                confidence: latestConfidence,
                language: selectedLanguage
            })

        });

        const data = await response.json();

        if (requestId !== recommendationRequestId) {
            return; // a newer request has since taken over
        }

        if (data.success && Array.isArray(data.songs) && data.songs.length) {

            renderAiPlaylist(data.songs, data);

        } else {

            renderAiMessage(
                data.message || "YouTube results aren't available right now.",
                mode,
                { retry: data.status !== "no_api_key" }
            );

        }

    } catch (error) {

        if (requestId !== recommendationRequestId) {
            return;
        }

        console.warn("AIMuse: /recommend request failed —", error);

        renderAiMessage(
            "Couldn't reach the recommendation service. Is app.py running?",
            mode
        );

    }

}


/*
    One song row. Text is always set with textContent — song
    titles come from YouTube, so they must never be parsed as
    HTML.
*/

function buildSongItem(song, number, real, onPick = null) {

    // Sample songs now come from YouTube too (they carry a videoId),
    // so they play in the YouTube player like any AIMuse song.
    if (!real && song.videoId) {
        real = true;
    }

    const item = document.createElement("button");

    item.type = "button";
    item.className = "song-item";

    if (real && song.videoId) {
        item.dataset.videoId = song.videoId;
    }

    if (!real && song.file) {
        item.dataset.file = song.file;
    }

    // Kept on the element so a failed song can be swapped for
    // another version of the same track (see replaceFailedSong).
    item._song = song;

    if (song.raw_title) {
        item.title = song.raw_title;
    }

    const numberEl = document.createElement("span");
    numberEl.className = "song-number";
    numberEl.textContent = String(number).padStart(2, "0");

    const info = document.createElement("span");
    info.className = "song-info";

    const title = document.createElement("span");
    title.className = "song-title";
    title.textContent = song.title || "Untitled";

    const artist = document.createElement("span");
    artist.className = "song-artist";

    if (real) {

        const languageLabel = song.language
            ? song.language.charAt(0).toUpperCase() + song.language.slice(1)
            : "";

        const length = song.duration_seconds
            ? formatTime(song.duration_seconds)
            : "";

        artist.textContent =
            [song.artist || song.channel, languageLabel, length]
                .filter(Boolean)
                .join(" · ");

    } else {

        artist.textContent = song.artist || "";

    }

    info.appendChild(title);
    info.appendChild(artist);

    item.appendChild(numberEl);
    item.appendChild(info);

    item.addEventListener("click", () => {

        // Some lists (the mood tabs) hand the song to the stage
        // instead of playing it themselves.
        if (onPick) {
            onPick();
            return;
        }

        document.querySelectorAll(".song-item.playing")
            .forEach(el => el.classList.remove("playing"));

        item.classList.add("playing");

        // The same sample song in the mood-tab list lights up too.
        if (!real && song.file) {
            document.querySelectorAll(".song-item[data-file]")
                .forEach(el => {
                    if (el !== item && el.dataset.file === song.file) {
                        el.classList.add("playing");
                    }
                });
        }

        if (song.sample && song.videoId) {
            document.querySelectorAll(".song-item[data-video-id]")
                .forEach(el => {
                    if (el !== item && el._song && el._song.sample &&
                        el.dataset.videoId === song.videoId) {
                        el.classList.add("playing");
                    }
                });
        }

        if (real) {
            playYouTubeSong(song);
        } else {
            previewSong(song);
        }

    });

    return item;

}


/*
    A YouTube song that turned out not to play: grey it out in
    the list so it isn't offered again this session.
*/

function markSongUnavailable(videoId) {

    if (!videoId) return;

    document.querySelectorAll(".song-item").forEach(item => {

        if (item.dataset.videoId === videoId) {

            item.classList.remove("playing");
            item.classList.add("unavailable");
            item.disabled = true;
            item.title = "This video can't be played here";

        }

    });

}


/*
    Tells the server a video failed in a real browser, so it's
    never recommended again (see report_bad_video in the
    recommender).
*/

function reportBadVideo(videoId, channel = "") {

    if (!videoId) return;

    // The channel is sent too: AIMuse learns which uploaders keep
    // blocking embeds and ranks them lower next time.
    fetch("/recommend/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ videoId, channel })
    }).catch(() => { /* best effort */ });

}


/*
    Real YouTube playback — this is where the background
    AIMuse track hands over to the song the person picked.

    Uses the real YouTube IFrame Player API (not a plain
    <iframe src="...">) so playback problems can be caught:
    if a video turns out not to be playable, the player moves
    straight on to the next song instead of sitting on a dead
    "This video is unavailable" screen.
*/

function loadYouTubeIframeApi() {

    if (window.YT && window.YT.Player) {
        ytApiReady = true;
        return;
    }

    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(script);

}


window.onYouTubeIframeAPIReady = function () {

    ytApiReady = true;

    if (pendingVideoId) {

        const videoId = pendingVideoId;
        pendingVideoId = null;

        createYouTubePlayer(videoId);

    }

};

loadYouTubeIframeApi();


function createYouTubePlayer(videoId) {

    if (!youtubePlayerContainer) return;

    const playerVars = {
        autoplay: 1,
        rel: 0,
        playsinline: 1
    };

    // YouTube wants to know which site is embedding it.
    if (window.location.origin && window.location.origin.startsWith("http")) {
        playerVars.origin = window.location.origin;
    }

    ytPlayer = new YT.Player(youtubePlayerContainer, {

        width: "640",
        height: "360",

        videoId: videoId,

        playerVars: playerVars,

        events: {
            onReady: handleYouTubeReady,
            onError: handleYouTubeError,
            onStateChange: handleYouTubeStateChange
        }

    });

}


function handleYouTubeReady(event) {

    if (activeSource !== "youtube") return;

    try {
        event.target.playVideo();
    } catch (error) {
        // The player will still show its own play button.
    }

    syncMiniPlayerState();

}


/*
    YouTube's player error codes:
      2    invalid video id            5    HTML5 player hiccup
      100  removed or private          101 / 150  owner disabled embedding

    100 / 101 / 150 are permanent, so the server blacklists the
    video. Either way, AIMuse now looks for the same song on
    another video before giving up on it (see replaceFailedSong).
*/

const PERMANENT_YT_ERRORS = new Set([100, 101, 150]);

/*
    SELF-HEALING PLAYLIST
    ---------------------
    A song that won't play is no longer crossed out and skipped.
    AIMuse asks the server for the SAME song (title + artist) from a
    different video, swaps it into the same row, and — if that row
    was the one being played — starts it straight away. Only when no
    other version exists is the row removed.
*/

const MAX_SWAPS_PER_ROW = 10;
const REPLACEMENT_TIMEOUT_MS = 15000;

// If the search for another version takes longer than this, the music
// moves on to the next song instead of sitting silent; the row is
// swapped quietly when the answer finally arrives.
const PATIENCE_MS = 6000;
const replacementsInFlight = new Set();

function aiSongRows() {

    return songList
        ? [...songList.querySelectorAll(".song-item")]
        : [];

}

/* Renumber rows, fix the count and the "Open on YouTube" link. */

function refreshAiListMeta() {

    const rows = aiSongRows();

    rows.forEach((row, index) => {

        const number = row.querySelector(".song-number");

        if (number) {
            number.textContent = String(index + 1).padStart(2, "0");
        }

    });

    if (songCount) {
        songCount.textContent =
            `${rows.length} song${rows.length === 1 ? "" : "s"}`;
    }

    const ids = rows
        .map(row => row.dataset.videoId)
        .filter(Boolean)
        .slice(0, 50);

    setPlaylistLink(
        ids.length
            ? "https://www.youtube.com/watch_videos?video_ids=" + ids.join(",")
            : ""
    );

}

/*
    Asks the server for a POOL of other uploads of the same song
    (different channels, best first). Always resolves — a slow or
    failed request gives [] instead of leaving the row stuck.
*/

async function requestReplacements(song, permanent) {

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REPLACEMENT_TIMEOUT_MS);

    try {

        const response = await fetch("/recommend/replace", {

            method: "POST",

            headers: { "Content-Type": "application/json" },

            signal: controller.signal,

            body: JSON.stringify({
                videoId: song.videoId,
                title: song.origTitle || song.title,
                artist: song.origArtist ?? (song.artist || song.channel || ""),
                language: song.language || "",
                channel: song.channel || "",
                permanent: permanent,
                exclude: aiSongRows()
                    .map(row => row.dataset.videoId)
                    .filter(Boolean)
            })

        });

        const data = await response.json();

        return data && Array.isArray(data.songs) ? data.songs : [];

    } catch (error) {

        console.warn("AIMuse: replacement request failed —", error);

        return [];

    } finally {

        clearTimeout(timer);

    }

}

/*
    Next candidate from the pool, preferring a DIFFERENT channel
    than the one that just failed — embedding is switched off per
    owner, so a label's other videos are almost certainly blocked too.
*/

function pickNextAlternate(pool, failedChannel) {

    if (!pool.length) return null;

    const failed = String(failedChannel || "").toLowerCase();

    const index = pool.findIndex(
        candidate => String(candidate.channel || "").toLowerCase() !== failed
    );

    return pool.splice(index >= 0 ? index : 0, 1)[0];

}

/*
    SELF-HEALING PLAYLIST
    ---------------------
    A song that won't play is swapped for ANOTHER UPLOAD of the same
    song, in the same row, and played straight away. The first failure
    fetches a pool of alternatives from the server; every later
    failure just takes the next one from that pool (instant, no
    server call) — so it keeps trying until something actually plays.
    Only when the pool is empty is the row removed.
*/

/*
    While AIMuse looks for another upload, YouTube's own "This video is
    unavailable" screen is replaced by the player card in a "searching"
    state — the vinyl spins and the card says what is happening.
*/

function showSearchingCard(song) {

    if (youtubePlayerWrap) {
        youtubePlayerWrap.classList.add("hidden");
    }

    if (!playerPlaceholder) return;

    playerPlaceholder.classList.remove("hidden");
    playerPlaceholder.classList.remove("playing");
    playerPlaceholder.classList.add("searching");

    if (playerPlaceholderTitle) {
        playerPlaceholderTitle.textContent = song.title;
    }

    if (playerPlaceholderSubtitle) {
        playerPlaceholderSubtitle.textContent =
            "Finding another version of this song…";
    }

}

/* Starts the next song after `item` (the one that failed), if there is one. */

function advancePast(item) {

    let next = item.nextElementSibling;

    while (
        next &&
        (next.classList.contains("unavailable") ||
         next.classList.contains("finding-alt"))
    ) {
        next = next.nextElementSibling;
    }

    if (next && next.classList.contains("song-item")) {
        next.click();
        return true;
    }

    return false;

}

/*
    A hand-picked sample song (beside the player) failed: switch to
    the next saved upload of the same song — instant, no server call.
    Returns true if it handled the failure.
*/

function swapSampleUpload(failedId, permanent) {

    const item = sampleSongList
        ? sampleSongList.querySelector(`.song-item[data-video-id="${failedId}"]`)
        : null;

    if (!item || !item._song) return false;

    const song = item._song;

    if (permanent) {
        reportBadVideo(failedId, song.channel || "");
    }

    const alternates = (song.alternates || []).filter(
        alt => alt.videoId && alt.videoId !== failedId
    );

    const next = alternates.shift();

    if (!next) {
        markSongUnavailable(failedId);
        skipToNextSong();
        return true;
    }

    const updated = { ...song, ...next, alternates, sample: true };

    // the same song in the mood-tab list follows along
    document.querySelectorAll(`.song-item[data-video-id="${failedId}"]`)
        .forEach(el => {
            el.dataset.videoId = next.videoId;
            el._song = updated;
        });

    playYouTubeSong(updated);

    return true;

}

async function replaceFailedSong(failedId, permanent, errorCode) {

    if (swapSampleUpload(failedId, permanent)) return;

    const item = songList
        ? songList.querySelector(`.song-item[data-video-id="${failedId}"]`)
        : null;

    const song = item && item._song;

    if (permanent) {
        reportBadVideo(failedId, song ? song.channel : "");
    }

    if (!item || !song) {
        markSongUnavailable(failedId);
        skipToNextSong();
        return;
    }

    if (replacementsInFlight.has(failedId)) return;

    replacementsInFlight.add(failedId);

    try {

        const swaps = song.swaps || 0;

        let pool = song.alternates || [];
        let next = null;
        let movedOn = false;

        if (swaps < MAX_SWAPS_PER_ROW) {
            next = pickNextAlternate(pool, song.channel);
        }

        // Pool empty and never searched: ask the server (once per song).
        if (!next && !song.searched && swaps < MAX_SWAPS_PER_ROW) {

            item.classList.add("finding-alt");

            setAiNote(
                `“${song.title}” can't be played here — looking for other uploads of the same song…`
            );

            if (activeSource === "youtube" && currentVideoId === failedId) {
                showSearchingCard(song);
            }

            const request = requestReplacements(song, permanent);

            const TOO_SLOW = Symbol("too slow");

            let found = await Promise.race([
                request,
                new Promise(resolve => setTimeout(() => resolve(TOO_SLOW), PATIENCE_MS))
            ]);

            if (found === TOO_SLOW) {

                // Don't leave the music stopped while we wait.
                movedOn = true;

                if (activeSource === "youtube" && currentVideoId === failedId) {

                    if (advancePast(item)) {
                        setAiNote(
                            `Still looking for another version of “${song.title}” — playing the next song meanwhile.`
                        );
                    }

                }

                found = await request;

            }

            song.searched = true;

            pool = found.filter(candidate => candidate.videoId !== failedId);

            next = pickNextAlternate(pool, song.channel);

        }

        // Did the person move on to a different song meanwhile?
        const stillCurrent =
            !movedOn && activeSource === "youtube" && currentVideoId === failedId;

        item.classList.remove("finding-alt");

        if (!next || !item.isConnected) {

            setAiNote(
                `No playable upload of “${song.title}” was found, so it was removed.`
            );

            if (item.isConnected) {
                dropFailedRow(item, stillCurrent);
            }

            return;

        }

        // The row keeps the ORIGINAL song name and artist; only the
        // video underneath changes.
        const originalTitle = song.origTitle || song.title;
        const originalArtist = song.origArtist ?? song.artist;

        next.origTitle = originalTitle;
        next.origArtist = originalArtist;
        next.title = originalTitle;
        next.artist = originalArtist;
        next.alternates = pool;
        next.swaps = swaps + 1;
        next.searched = true;

        const fresh = buildSongItem(next, 1, true);

        item.replaceWith(fresh);

        refreshAiListMeta();

        setAiNote(
            `“${originalTitle}” wasn't playable (error ${errorCode}) — ` +
            `trying another upload by ${next.channel || "another channel"}` +
            `${pool.length ? ` (${pool.length} more ready)` : ""}.`
        );

        if (stillCurrent) {
            fresh.click();   // same path as a person clicking it
        }

    } finally {

        replacementsInFlight.delete(failedId);

        item.classList.remove("finding-alt");

    }

}

/* Removes a dead row; if it was playing, moves on to the next one. */

function dropFailedRow(item, wasPlaying) {

    let next = item.nextElementSibling;

    while (next && next.classList.contains("unavailable")) {
        next = next.nextElementSibling;
    }

    item.remove();

    refreshAiListMeta();

    if (!wasPlaying) return;

    if (next && next.classList.contains("song-item")) {
        next.click();
    } else {
        endPlayback();
    }

}

function handleYouTubeError(event) {

    // Ignore anything from a song that's no longer current.
    if (activeSource !== "youtube") return;

    const failedId = currentVideoId;

    if (!failedId) return;

    const code = Number(event.data);

    console.warn(
        "AIMuse: YouTube couldn't play video",
        failedId,
        "(error code",
        code,
        ") — trying another upload of the same song."
    );

    replaceFailedSong(failedId, PERMANENT_YT_ERRORS.has(code), code);

}


function handleYouTubeStateChange(event) {

    if (activeSource !== "youtube") return;

    syncMiniPlayerState();

    // 0 = ended — move on to the next song in the list.
    if (event.data === 0) {
        skipToNextSong();
    }

}


function playYouTubeSong(song) {

    pauseEntryMusic();

    unloadSampleAudio();

    currentVideoId = song.videoId;

    setActiveSource("youtube", song.title);

    if (youtubePlayerWrap) {
        youtubePlayerWrap.classList.remove("hidden");
    }

    if (playerPlaceholder) {
        playerPlaceholder.classList.add("hidden");
        playerPlaceholder.classList.remove("searching");
    }

    if (!ytApiReady || !window.YT || !window.YT.Player) {

        // The player script is still loading (or was blocked).
        pendingVideoId = song.videoId;

        setTimeout(() => {

            if (ytApiReady || activeSource !== "youtube") return;

            if (youtubePlayerWrap) {
                youtubePlayerWrap.classList.add("hidden");
            }

            if (playerPlaceholder) {
                playerPlaceholder.classList.remove("hidden");
            }

            if (playerPlaceholderTitle) {
                playerPlaceholderTitle.textContent = song.title;
            }

            if (playerPlaceholderSubtitle) {
                playerPlaceholderSubtitle.textContent =
                    "Couldn't reach YouTube's player — check your connection.";
            }

        }, 8000);

        return;

    }

    if (ytPlayer && typeof ytPlayer.loadVideoById === "function") {
        ytPlayer.loadVideoById(song.videoId);
    } else {
        createYouTubePlayer(song.videoId);
    }

}


/*
    Moves on to the song after whichever one is currently
    marked "playing" — by clicking it, so it goes through the
    exact same path as a person clicking it. It looks at the
    list the playing song actually belongs to (the generated
    playlist OR one of the sample mood playlists), not just
    the main one. Used when a song ends, and when a song
    can't be played.
*/

function skipToNextSong() {

    const current = document.querySelector(".song-item.playing");

    let next = current ? current.nextElementSibling : null;

    // Skip anything already known not to play.
    while (next && next.classList.contains("unavailable")) {
        next = next.nextElementSibling;
    }

    if (next && next.classList.contains("song-item")) {
        next.click();
    } else {
        endPlayback();
    }

}


/* ---- small stop/reset helpers -------------------------------- */

function unloadSampleAudio() {

    if (!sampleAudio) return;

    sampleAudio.pause();
    sampleAudio.removeAttribute("src");
    sampleAudio.load();

}


function stopYouTube() {

    pendingVideoId = null;

    if (ytPlayer && typeof ytPlayer.stopVideo === "function") {

        try {
            ytPlayer.stopVideo();
        } catch (error) {
            // Player may already be torn down — safe to ignore.
        }

    }

    if (youtubePlayerWrap) {
        youtubePlayerWrap.classList.add("hidden");
    }

}


function resetPlayerCard() {

    if (playerPlaceholder) {

        playerPlaceholder.classList.remove("hidden");
        playerPlaceholder.classList.remove("playing");
        playerPlaceholder.classList.remove("searching");

    }

    if (playerPlaceholderTitle) {
        playerPlaceholderTitle.textContent = "Your music will appear here.";
    }

    if (playerPlaceholderSubtitle) {
        playerPlaceholderSubtitle.textContent = "Pick a song from either list to play it.";
    }

}


/*
    Stops any sample / YouTube song, returns the player card
    to idle, clears the "playing" highlight and gives the
    mini-player back to the AIMuse originals. Does NOT touch
    the AIMuse track itself.
*/

function endPlayback() {

    stopYouTube();

    unloadSampleAudio();

    resetPlayerCard();

    document.querySelectorAll(".song-item.playing")
        .forEach(el => el.classList.remove("playing"));

    setActiveSource("entry");

}


/*
    Builds a /static/... URL from a relative path, encoding
    each path segment individually — a plain encodeURIComponent
    on the whole string would turn "/" into "%2F" and break
    the path.
*/

function buildStaticUrl(relativePath) {

    return "/static/" +
        relativePath
            .split("/")
            .map(encodeURIComponent)
            .join("/");

}


/*
    Sample-song playback — real local audio files
    (static/Moods/...), played through their own audio
    element, with a progress bar in the player card.
*/

function previewSong(song) {

    pauseEntryMusic();

    stopYouTube();
    unloadSampleAudio();
    resetPlayerCard();

    setActiveSource("sample", song.title);

    if (playerPlaceholder) {
        playerPlaceholder.classList.add("playing");
    }

    if (playerPlaceholderTitle) {
        playerPlaceholderTitle.textContent = song.title;
    }

    if (playerPlaceholderSubtitle) {
        playerPlaceholderSubtitle.textContent = song.artist || "";
    }

    if (!song.file || !sampleAudio) {

        if (playerPlaceholderSubtitle) {
            playerPlaceholderSubtitle.textContent =
                `${song.artist || ""} — no audio file set for this song.`;
        }

        return;

    }

    sampleAudio.src = song.url || buildStaticUrl(song.file);

    sampleAudio.play().catch(error => {

        // A bad file is reported (and skipped) by the "error"
        // listener below; a quick song switch aborts harmlessly.
        if (isBenignPlayError(error)) return;

        console.warn(
            "AIMuse: couldn't play sample song —",
            song.file,
            error
        );

        if (playerPlaceholderSubtitle) {
            playerPlaceholderSubtitle.textContent =
                `${song.artist || ""} — couldn't play this file.`;
        }

    });

}


if (sampleAudio) {

    sampleAudio.addEventListener("play", syncMiniPlayerState);
    sampleAudio.addEventListener("pause", syncMiniPlayerState);

    // When a song finishes, the next one in its list starts.
    sampleAudio.addEventListener("ended", () => {

        skipToNextSong();

    });

    // A missing/broken file: say which, then move on.
    sampleAudio.addEventListener("error", () => {

        if (!sampleAudio.getAttribute("src")) return;

        console.warn(
            "AIMuse: couldn't load sample song file —",
            sampleAudio.currentSrc,
            "— check that the file exists in static/moods/ and is a valid audio file."
        );

        if (activeSource !== "sample") return;

        skipToNextSong();

    });

}




/* =========================================================
   11B. LIVE EQUALIZER (sample songs)
   =========================================================
   Real audio analysis: the sample <audio> element is routed
   through a Web Audio AnalyserNode. Its frequency spectrum
   drives (a) a spectrum analyzer on a canvas — 64 thin bars,
   bass on the left, treble on the right, each jumping with its
   own frequencies — and (b) a beat detector (kick drum vs. its
   own recent average) that punches the bars and pulses the
   glow behind the vinyl. Sample files are served from this same origin, so
   the browser allows the analysis. If Web Audio isn't
   available, a gentle simulated animation is used instead —
   the song itself always plays either way.
   ========================================================= */

const viz = {
    canvas: sampleVisualizerCanvas,
    ctx: null,
    audioCtx: null,
    analyser: null,
    data: null,
    bars: 64,
    levels: null,
    binLo: null,
    binHi: null,
    binCenter: null,
    raf: 0,
    failed: false,
    silentFrames: 0,
    bassAverage: 0,
    beat: 0,
    lastBeat: 0,
    lastTime: 0,
    width: 0,
    height: 0,
    rgb: "66, 58, 90"
};

const reducedMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (viz.canvas) {
    viz.ctx = viz.canvas.getContext("2d");
    viz.levels = new Float32Array(viz.bars);
}

function initAudioAnalyser() {

    if (viz.analyser || viz.failed || !sampleAudio) return;

    try {

        const AudioContextClass =
            window.AudioContext || window.webkitAudioContext;

        if (!AudioContextClass) throw new Error("No Web Audio support");

        viz.audioCtx = new AudioContextClass();

        const source = viz.audioCtx.createMediaElementSource(sampleAudio);

        viz.analyser = viz.audioCtx.createAnalyser();

        // 2048 samples = fine frequency detail (about 21 Hz per step),
        // low smoothing = the bars snap to every hit instead of blurring.
        viz.analyser.fftSize = 2048;
        viz.analyser.smoothingTimeConstant = 0.5;
        viz.analyser.minDecibels = -88;
        viz.analyser.maxDecibels = -18;

        source.connect(viz.analyser);
        viz.analyser.connect(viz.audioCtx.destination);

        viz.data = new Uint8Array(viz.analyser.frequencyBinCount);

        buildBinMap();

    } catch (error) {

        console.warn("AIMuse: live equalizer unavailable, using simulation —", error);

        viz.failed = true;
        viz.analyser = null;

    }

}

/*
    Each bar listens to its own slice of the spectrum, spaced
    logarithmically (like hearing): the left bars are the bass /
    kick drum, the middle bars are voices and melody, the right
    bars are hi-hats and shimmer.
*/

function buildBinMap() {

    const count = viz.bars;
    const nyquist = viz.audioCtx.sampleRate / 2;
    const binHz = nyquist / viz.data.length;

    const minHz = 55;
    const maxHz = Math.min(14000, nyquist * 0.92);

    viz.binLo = new Float32Array(count);
    viz.binHi = new Float32Array(count);
    viz.binCenter = new Float32Array(count);

    for (let i = 0; i < count; i++) {

        const f0 = minHz * Math.pow(maxHz / minHz, i / count);
        const f1 = minHz * Math.pow(maxHz / minHz, (i + 1) / count);

        viz.binLo[i] = f0 / binHz;
        viz.binHi[i] = f1 / binHz;
        viz.binCenter[i] = Math.sqrt(f0 * f1) / binHz;

    }

}

/* Reading between two FFT bins keeps neighbouring low bars from being identical. */

function spectrumAt(position) {

    const last = viz.data.length - 1;
    const index = Math.min(last, Math.max(0, position));

    const lower = Math.floor(index);
    const upper = Math.min(last, lower + 1);
    const mix = index - lower;

    return viz.data[lower] * (1 - mix) + viz.data[upper] * mix;

}

function sizeVisualizerCanvas() {

    if (!viz.canvas || !viz.ctx) return;

    const ratio = window.devicePixelRatio || 1;
    const rect = viz.canvas.getBoundingClientRect();

    if (!rect.width || !rect.height) return;

    viz.width = rect.width;
    viz.height = rect.height;

    viz.canvas.width = Math.round(rect.width * ratio);
    viz.canvas.height = Math.round(rect.height * ratio);

    viz.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

}

window.addEventListener("resize", sizeVisualizerCanvas);

function drawVisualizerFrame(time) {

    viz.raf = 0;

    if (!viz.ctx) return;

    if (!viz.width) sizeVisualizerCanvas();

    const now = time || performance.now();

    const playing =
        activeSource === "sample" && sampleAudio && !sampleAudio.paused;

    const count = viz.bars;

    // Frame-rate independent timing (same feel on slow and fast machines).
    const dt = Math.min(100, Math.max(6, now - (viz.lastTime || now - 16.7)));

    viz.lastTime = now;

    const frames = dt / 16.7;

    let usingAnalyser = false;

    if (playing && viz.analyser && viz.data) {

        viz.analyser.getByteFrequencyData(viz.data);

        // All-zero data for a while means the browser isn't giving
        // us audio to analyse — fall back to the simulation.
        let sum = 0;
        for (let i = 0; i < 48; i++) sum += viz.data[i];

        viz.silentFrames = sum === 0 ? viz.silentFrames + 1 : 0;
        usingAnalyser = viz.silentFrames < 90;

    }

    // ---- BEAT DETECTION -----------------------------------------
    // A beat = the bass (kick drum, ~40–180 Hz) suddenly louder than
    // its own recent average. Works on any song, no tempo needed.

    let bassNow = 0;

    if (playing && usingAnalyser) {

        for (let i = 2; i <= 9; i++) bassNow += viz.data[i];

        bassNow = bassNow / (8 * 255);

        viz.bassAverage += (bassNow - viz.bassAverage) * (1 - Math.pow(0.94, frames));

        if (
            bassNow > 0.22 &&
            bassNow > viz.bassAverage * 1.16 + 0.03 &&
            now - viz.lastBeat > 170
        ) {

            viz.beat = 1;
            viz.lastBeat = now;

        }

    } else if (playing) {

        // Simulation: a steady pulse so the animation still feels alive.
        if (now - viz.lastBeat > 480) {
            viz.beat = 1;
            viz.lastBeat = now;
        }

        bassNow = 0.4;

    }

    viz.beat *= Math.pow(0.86, frames);

    // ---- BAR HEIGHTS ---------------------------------------------

    const fall = 1 - Math.pow(1 - 0.3, frames);      // bars drop quickly

    for (let i = 0; i < count; i++) {

        const position = i / (count - 1);

        let target = 0;

        if (playing && usingAnalyser) {

            const centre = spectrumAt(viz.binCenter[i]);

            let strongest = centre;

            const lo = Math.floor(viz.binLo[i]);
            const hi = Math.min(viz.data.length - 1, Math.ceil(viz.binHi[i]));

            for (let bin = lo; bin <= hi; bin++) {
                if (viz.data[bin] > strongest) strongest = viz.data[bin];
            }

            const raw = strongest / 255;

            // Highs are naturally quieter in music — tilt so the whole
            // width moves. The power curve keeps quiet bars low and
            // lets real hits stand tall, like the reference.
            const tilt = 0.85 + 1.35 * Math.pow(position, 1.15);

            target = Math.pow(raw, 1.75) * tilt;

        } else if (playing) {

            const t = now / 1000;
            const body = Math.exp(-position * 2.2);

            target =
                body * (0.15 + 0.35 * Math.abs(Math.sin(t * 5.1 + i * 1.7))) +
                (Math.sin(t * 9.3 + i * 12.9) > 0.94 ? 0.5 : 0) * body;

        }

        // A beat gives every bar an extra kick.
        target = Math.min(1, target * (1 + 0.22 * viz.beat));

        if (target > viz.levels[i]) {
            viz.levels[i] = target;                            // instant attack
        } else {
            viz.levels[i] += (target - viz.levels[i]) * fall;  // quick release
        }

    }

    // Glow behind the vinyl follows the kick.

    if (playerPlaceholder) {

        const glow = playing
            ? Math.max(viz.beat, Math.min(1, bassNow * 1.4))
            : 0;

        playerPlaceholder.style.setProperty(
            "--bass",
            (reducedMotion ? 0 : glow).toFixed(3)
        );

    }

    // ---- DRAW: thin bars standing on a baseline ------------------

    const ctx = viz.ctx;
    const width = viz.width;
    const height = viz.height;

    ctx.clearRect(0, 0, width, height);

    const step = width / count;
    const barWidth = Math.max(2, Math.min(3.4, step * 0.46));
    const baseline = height - 6;
    const usableHeight = baseline - 4;

    let alive = false;

    for (let i = 0; i < count; i++) {

        const level = viz.levels[i];

        if (level > 0.012) alive = true;

        const barHeight = 2.4 + level * usableHeight;
        const x = i * step + (step - barWidth) / 2;

        // taller bars glow a touch warmer, resting bars stay soft
        const strength = 0.55 + 0.45 * Math.min(1, level * 1.6);

        ctx.fillStyle = `rgba(${viz.rgb}, ${strength.toFixed(3)})`;

        ctx.beginPath();

        if (ctx.roundRect) {
            ctx.roundRect(x, baseline - barHeight, barWidth, barHeight, barWidth / 2);
        } else {
            ctx.rect(x, baseline - barHeight, barWidth, barHeight);
        }

        ctx.fill();

    }

    // Keep animating while playing, or until every bar has dropped.
    if (playing || alive) {
        viz.raf = requestAnimationFrame(drawVisualizerFrame);
    } else {
        viz.lastTime = 0;
        viz.beat = 0;
    }

}

function startVisualizer() {

    if (!viz.canvas || viz.raf) return;

    sizeVisualizerCanvas();

    viz.raf = requestAnimationFrame(drawVisualizerFrame);

}

if (sampleAudio) {

    sampleAudio.addEventListener("play", () => {

        initAudioAnalyser();

        // A suspended context would mute the song once it's routed
        // through Web Audio, so always make sure it's running.
        if (viz.audioCtx && viz.audioCtx.state === "suspended") {
            viz.audioCtx.resume().catch(() => {});
        }

        startVisualizer();

    });

    // On pause / end the loop lets the bars settle, then stops.
    sampleAudio.addEventListener("pause", startVisualizer);
    sampleAudio.addEventListener("ended", startVisualizer);

}


/* =========================================================
   12. DISCOVERY SECTION — "DON'T KNOW WHAT TO LISTEN TO?"
   ========================================================= */

const MOOD_ORDER = [
    "happy", "sad", "calm", "angry", "romantic", "energetic", "neutral"
];


function buildOriginalTracksGrid() {

    if (!originalTracksGrid) return;

    originalTracksGrid.innerHTML = "";

    entryTracks.forEach((track, index) => {

        const card = document.createElement("button");

        card.type = "button";
        card.className = "original-track-card";
        card.dataset.trackIndex = String(index);

        card.innerHTML = `
            <span class="track-card-icon">♪</span>
            <span class="track-card-title">${track.title}</span>
            <span class="track-card-subtitle">AIMUSE ORIGINAL</span>
        `;

        card.addEventListener("click", () => {

            if (currentTrackIndex === index && !entryMusic.paused) {
                pauseEntryMusic();
                showMiniPlayer();
                return;
            }

            loadTrack(index, { autoplay: true });
            showMiniPlayer();

        });

        originalTracksGrid.appendChild(card);

    });

    highlightPlayingOriginalCard();

}


function highlightPlayingOriginalCard() {

    if (!originalTracksGrid) return;

    originalTracksGrid.querySelectorAll(".original-track-card")
        .forEach(card => {

            const isCurrent =
                Number(card.dataset.trackIndex) === currentTrackIndex &&
                activeSource === "entry" &&
                !entryMusic.paused;

            card.classList.toggle("playing", isCurrent);

        });

}


function buildMoodTabs() {

    if (!moodTabs) return;

    moodTabs.innerHTML = "";

    /*
        Only moods that actually have songs get a tab — while the
        YouTube sample songs are still being saved, a half-filled
        set shouldn't show empty tabs. (Before the songs have
        loaded, every mood is shown as usual.)
    */

    const moods = samplesLoaded
        ? MOOD_ORDER.filter(mood => (SAMPLE_PLAYLISTS[mood] || []).length)
        : MOOD_ORDER;

    if (moods.length && !moods.includes(activeMoodTab)) {
        activeMoodTab = moods[0];
    }

    moods.forEach((mood) => {

        const tab = document.createElement("button");

        tab.type = "button";
        tab.className = "mood-tab";
        tab.textContent = formatEmotion(mood);
        tab.dataset.mood = mood;
        tab.setAttribute("role", "tab");

        if (mood === activeMoodTab) {
            tab.classList.add("active");
        }

        tab.addEventListener("click", () => {

            moodTabs.querySelectorAll(".mood-tab")
                .forEach(t => t.classList.remove("active"));

            tab.classList.add("active");

            activeMoodTab = mood;

            renderMoodPlaylistPanel(mood);

        });

        moodTabs.appendChild(tab);

    });

}


function renderMoodPlaylistPanel(mood) {

    if (!moodPlaylistPanel) return;

    const songs = SAMPLE_PLAYLISTS[mood] || [];

    moodPlaylistPanel.innerHTML = `
        <div class="mood-playlist-heading">
            ${formatEmotion(mood)} playlist
            <span class="mood-playlist-count"></span>
        </div>
        <div class="mood-playlist-list"></div>
    `;

    const count = moodPlaylistPanel.querySelector(".mood-playlist-count");

    count.textContent =
        samplesFailed
            ? "couldn't load"
            : !samplesLoaded
                ? "loading…"
                : `${songs.length} song${songs.length === 1 ? "" : "s"} · sample`;

    const list = moodPlaylistPanel.querySelector(".mood-playlist-list");

    songs.forEach((song, index) => {

        const item = buildSongItem(
            song, index + 1, false,
            () => openSamplePlaylist(mood, index)
        );
        list.appendChild(item);

    });

    if (samplesLoaded && !songs.length) {

        const empty = document.createElement("p");

        empty.className = "panel-empty-note";
        empty.textContent =
            `No audio files found in static/moods/${mood}/ yet.`;

        list.appendChild(empty);

    }

}


buildOriginalTracksGrid();
buildMoodTabs();
renderMoodPlaylistPanel(MOOD_ORDER[0]);

// Fetch the sample songs (scanned from static/moods by the server).
loadSamplePlaylists();


/* =========================================================
   13. PERSISTENT MINI PLAYER + PROGRESS BARS
   ========================================================= */

/*
    The mini-player always reflects whatever is playing right
    now — an AIMuse original, a sample song or a YouTube pick
    — with its title, a play/pause button and a progress bar
    showing how much of the song has played.
*/

function showMiniPlayer() {

    if (!miniPlayer) return;

    miniPlayer.classList.add("visible");
    miniPlayer.setAttribute("aria-hidden", "false");

    document.body.classList.add("player-active");

    syncMiniPlayerState();

}


/* Which source owns the mini-player, and its own title. */

function setActiveSource(source, title = "") {

    activeSource = source;
    activeSongTitle = title;

    syncMiniPlayerState();

}


/*
    A uniform read of the active source's playback state, so
    the mini-player doesn't care which kind of audio it is.
*/

function getPlayback() {

    if (activeSource === "sample" && sampleAudio) {

        return {
            paused: sampleAudio.paused,
            current: sampleAudio.currentTime || 0,
            duration: sampleAudio.duration
        };

    }

    if (activeSource === "youtube") {

        if (ytPlayer && typeof ytPlayer.getPlayerState === "function") {

            let state = -1;
            let current = 0;
            let duration = 0;

            try {
                state = ytPlayer.getPlayerState();
                current = ytPlayer.getCurrentTime();
                duration = ytPlayer.getDuration();
            } catch (error) {
                // Player not ready yet — treat as starting up.
            }

            // 1 = playing, 3 = buffering.
            return {
                paused: !(state === 1 || state === 3),
                current: current || 0,
                duration: duration || 0
            };

        }

        // Still loading the player.
        return { paused: false, current: 0, duration: 0 };

    }

    return {
        paused: entryMusic.paused,
        current: entryMusic.currentTime || 0,
        duration: entryMusic.duration
    };

}


function formatTime(totalSeconds) {

    if (!isFinite(totalSeconds) || totalSeconds < 0) {
        totalSeconds = 0;
    }

    const minutes = Math.floor(totalSeconds / 60);
    const seconds = Math.floor(totalSeconds % 60);

    return `${minutes}:${String(seconds).padStart(2, "0")}`;

}


function syncMiniPlayerState() {

    if (!miniPlayer) return;

    const { paused } = getPlayback();

    miniPlayer.classList.toggle("paused", paused);

    if (miniPlayerLabel) {
        miniPlayerLabel.textContent = paused ? "Paused" : "Playing";
    }

    if (miniPlayerToggle) {

        miniPlayerToggle.textContent = paused ? "▶" : "❙❙";

        miniPlayerToggle.setAttribute(
            "aria-label",
            paused ? "Resume music" : "Pause music"
        );

    }

    updateMiniPlayerTrack();
    updateNowPlayingDisplay();
    highlightPlayingOriginalCard();

    // Lets the vinyl stop spinning when a sample song is paused.
    if (playerPlaceholder) {
        playerPlaceholder.classList.toggle(
            "paused",
            activeSource === "sample" && paused
        );
    }

}


function toggleActivePlayback() {

    if (activeSource === "sample" && sampleAudio) {

        if (sampleAudio.paused) {
            sampleAudio.play().catch(() => {});
        } else {
            sampleAudio.pause();
        }

        return;

    }

    if (activeSource === "youtube") {

        if (!ytPlayer || typeof ytPlayer.getPlayerState !== "function") return;

        const state = ytPlayer.getPlayerState();

        if (state === 1 || state === 3) {
            ytPlayer.pauseVideo();
        } else {
            ytPlayer.playVideo();
        }

        return;

    }

    if (entryMusic.paused) {
        playEntryMusic();
    } else {
        pauseEntryMusic();
    }

}


if (miniPlayerToggle) {

    miniPlayerToggle.addEventListener("click", toggleActivePlayback);

}


/* =========================================================
   14. THEME SYSTEM (light / dark)
   =========================================================
   The choice is remembered. With no saved choice, AIMuse follows
   the device's own light/dark setting — and keeps following it
   until the person presses the toggle once.

   The page itself is themed in style.css (body.dark-theme).
   An inline script at the top of <body> applies the saved theme
   before the first paint, so there is no flash of light mode.
   ========================================================= */

const ICON_MOON =
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

const ICON_SUN =
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="12" cy="12" r="4"/>' +
    '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';

const ICON_SPARKLE =
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9z"/>' +
    '<path d="M19 15v4M17 17h4"/></svg>';

/* Sets the icon and the text label of a settings-dock button. */

function setDockButton(button, iconSvg, label) {

    if (!button) return;

    const icon = button.querySelector(".dock-icon");
    const text = button.querySelector(".dock-label");

    if (icon) icon.innerHTML = iconSvg;
    if (text) text.textContent = label;

}

const THEME_KEY = "aimuseDarkMode";

const systemDarkQuery = window.matchMedia("(prefers-color-scheme: dark)");

let darkMode = false;
let themeTransitionTimer = null;

/* The equalizer is drawn on a canvas, so it reads its colour from CSS. */

function refreshVizColor() {

    const value = getComputedStyle(document.body)
        .getPropertyValue("--viz-rgb")
        .trim();

    viz.rgb = value || "66, 58, 90";

}

function applyTheme(dark, { animate = false } = {}) {

    darkMode = dark;

    if (animate) {

        document.body.classList.add("theme-transition");

        clearTimeout(themeTransitionTimer);

        themeTransitionTimer = setTimeout(() => {
            document.body.classList.remove("theme-transition");
        }, 650);

    }

    document.body.classList.toggle("dark-theme", dark);

    // The icon and label show what a click will switch TO.
    setDockButton(themeToggle, dark ? ICON_SUN : ICON_MOON, dark ? "Light mode" : "Dark mode");

    themeToggle.setAttribute("aria-pressed", String(dark));

    themeToggle.setAttribute(
        "aria-label",
        dark ? "Switch to light theme" : "Switch to dark theme"
    );

    const themeColor = document.querySelector('meta[name="theme-color"]');

    if (themeColor) {
        themeColor.setAttribute("content", dark ? "#0a0714" : "#f4eefb");
    }

    refreshVizColor();
    refreshDustColors();

}

themeToggle.addEventListener("click", () => {

    applyTheme(!darkMode, { animate: true });

    // From now on the person's choice wins over the system setting.
    storageSet(THEME_KEY, String(darkMode));

});

const savedTheme = storageGet(THEME_KEY);

applyTheme(
    savedTheme === null ? systemDarkQuery.matches : savedTheme === "true"
);

// Follow the device setting live, but only if nobody has chosen yet.
systemDarkQuery.addEventListener("change", (event) => {

    if (storageGet(THEME_KEY) === null) {
        applyTheme(event.matches, { animate: true });
    }

});


/* =========================================================
   14B. REDUCED EFFECTS (performance switch)
   ========================================================= */

const EFFECTS_KEY = "aimuseReduceEffects";

const effectsToggle = document.getElementById("effects-toggle");

function applyReducedEffects(reduce) {

    document.body.classList.toggle("reduce-effects", reduce);

    if (!effectsToggle) return;

    effectsToggle.setAttribute("aria-pressed", String(reduce));

    setDockButton(
        effectsToggle,
        ICON_SPARKLE,
        reduce ? "Restore effects" : "Reduce effects"
    );

    effectsToggle.setAttribute(
        "aria-label",
        reduce ? "Turn visual effects back on" : "Reduce visual effects"
    );

    effectsToggle.title = reduce
        ? "Visual effects are reduced — click to turn them back on"
        : "Reduce visual effects (smoother on slower computers)";

}

if (effectsToggle) {

    effectsToggle.addEventListener("click", () => {

        const reduce = !document.body.classList.contains("reduce-effects");

        applyReducedEffects(reduce);

        storageSet(EFFECTS_KEY, String(reduce));

    });

    applyReducedEffects(storageGet(EFFECTS_KEY) === "true");

}


/*
    DOCK HINT
    ---------
    For the first few seconds of every visit the two buttons show
    their text labels, so people can see what they are. Once either
    has been used, the labels only appear on hover.
*/

const settingsDock = document.getElementById("settings-dock");

if (settingsDock) {

    const DOCK_USED_KEY = "aimuseDockUsed";

    if (storageGet(DOCK_USED_KEY) === "true") {

        settingsDock.classList.remove("hint");

    } else {

        setTimeout(() => settingsDock.classList.remove("hint"), 7000);

    }

    settingsDock.addEventListener("click", () => {

        storageSet(DOCK_USED_KEY, "true");

        settingsDock.classList.remove("hint");

    });

}


/* =========================================================
   15. CURSOR GLOW
   ========================================================= */

let cursorGlow = null;
let rawCursorX = window.innerWidth / 2;
let rawCursorY = window.innerHeight / 2;
let cursorGlowX = rawCursorX;
let cursorGlowY = rawCursorY;

const prefersReducedMotion =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const isTouchDevice =
    window.matchMedia("(hover: none), (pointer: coarse)").matches;

if (!prefersReducedMotion && !isTouchDevice) {

    cursorGlow = document.createElement("div");
    cursorGlow.className = "cursor-glow";
    document.body.appendChild(cursorGlow);

    document.addEventListener("mousemove", (event) => {

        rawCursorX = event.clientX;
        rawCursorY = event.clientY;

    });

}


/* =========================================================
   16. PARALLAX
   ========================================================= */

let mouseX = 0;
let mouseY = 0;

let targetX = 0;
let targetY = 0;


document.addEventListener(
    "mousemove",
    (event) => {

        mouseX =
            (event.clientX /
                window.innerWidth -
                0.5);

        mouseY =
            (event.clientY /
                window.innerHeight -
                0.5);

    }
);


function animateParallax() {

    if (!prefersReducedMotion) {

        targetX +=
            (mouseX - targetX) * 0.035;

        targetY +=
            (mouseY - targetY) * 0.035;


        /*
            Auroras get a direct transform, matching their
            original behaviour.
        */

        const auroras =
            document.querySelectorAll(".aurora");

        auroras.forEach((aurora, index) => {

            const strength =
                (index + 1) * 8;

            aurora.style.transform =
                `translate3d(
                    ${targetX * strength}px,
                    ${targetY * strength}px,
                    0
                )`;

        });


        /*
            Everything else with a data-depth attribute gets
            a margin-based nudge instead of a transform, so
            it doesn't fight with its own CSS keyframe
            animation (floating notes, sparkles, orbits and
            drifting dots all already animate their own
            transform).
        */

        const depthElements =
            document.querySelectorAll("[data-depth]:not(.aurora)");

        depthElements.forEach((el) => {

            const depth =
                parseFloat(el.dataset.depth) || 5;

            el.style.marginLeft =
                `${targetX * depth}px`;

            el.style.marginTop =
                `${targetY * depth}px`;

        });


        /*
            A soft light drifts toward the cursor for extra
            depth.
        */

        if (cursorGlow) {

            cursorGlowX += (rawCursorX - cursorGlowX) * 0.08;
            cursorGlowY += (rawCursorY - cursorGlowY) * 0.08;

            cursorGlow.style.transform =
                `translate3d(${cursorGlowX}px, ${cursorGlowY}px, 0)`;

        }

    }

    requestAnimationFrame(
        animateParallax
    );

}

animateParallax();


/* =========================================================
   17. TILT CARDS
   ========================================================= */

/*
    Feature cards (the mood input card, the playlist option
    cards, and the how-it-works steps) tilt gently toward the
    cursor. This is user-triggered motion — it only runs
    while the cursor is actually over the card.
*/

function enableTilt(selector, maxTilt = 7, lift = -6) {

    if (prefersReducedMotion || isTouchDevice) return;

    document.querySelectorAll(selector).forEach((card) => {

        card.addEventListener("mousemove", (event) => {

            const rect = card.getBoundingClientRect();

            const px = (event.clientX - rect.left) / rect.width;
            const py = (event.clientY - rect.top) / rect.height;

            const rotateY = (px - 0.5) * (maxTilt * 2);
            const rotateX = (0.5 - py) * (maxTilt * 2);

            card.style.transform =
                `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(${lift}px)`;

        });

        card.addEventListener("mouseleave", () => {
            card.style.transform = "";
        });

    });

}

enableTilt(".tilt-card");


/* =========================================================
   MOOD CARD — SAFE INTERNAL PARALLAX
   ========================================================= */

const moodCard = document.querySelector(".mood-card");

if (moodCard && !prefersReducedMotion && !isTouchDevice) {

    moodCard.addEventListener("pointermove", (event) => {

        const rect =
            moodCard.getBoundingClientRect();

        const x =
            ((event.clientX - rect.left) / rect.width - 0.5) * 2;

        const y =
            ((event.clientY - rect.top) / rect.height - 0.5) * 2;

        /*
            Only move the decorative layers.
            The actual card never moves.
        */

        moodCard.style.setProperty(
            "--parallax-x",
            `${x * 12}px`
        );

        moodCard.style.setProperty(
            "--parallax-y",
            `${y * 12}px`
        );

        moodCard.style.setProperty(
            "--parallax-x-soft",
            `${x * -7}px`
        );

        moodCard.style.setProperty(
            "--parallax-y-soft",
            `${y * -7}px`
        );
    });


    moodCard.addEventListener("pointerleave", () => {

        moodCard.style.setProperty(
            "--parallax-x",
            "0px"
        );

        moodCard.style.setProperty(
            "--parallax-y",
            "0px"
        );

        moodCard.style.setProperty(
            "--parallax-x-soft",
            "0px"
        );

        moodCard.style.setProperty(
            "--parallax-y-soft",
            "0px"
        );
    });
}

/* =========================================================
   18. SCROLL PARALLAX + SCROLL PROGRESS
   ========================================================= */

const scrollProgressBar = document.getElementById("scroll-progress-bar");

window.addEventListener(
    "scroll",
    () => {

        const scrollY =
            window.scrollY;

        const silkLayers =
            document.querySelectorAll(
                ".silk-layer"
            );

        silkLayers.forEach(
            (layer, index) => {

                const speed =
                    index === 0
                        ? 0.08
                        : 0.12;

                layer.style.marginTop =
                    `${scrollY * speed}px`;

            }
        );




        /*
            Fill the top progress bar based on how far the
            visitor has scrolled through the page.
        */

        if (scrollProgressBar) {

            const scrollable =
                document.documentElement.scrollHeight -
                window.innerHeight;

            const progress =
                scrollable > 0
                    ? (scrollY / scrollable) * 100
                    : 0;

            scrollProgressBar.style.width =
                `${Math.min(100, Math.max(0, progress))}%`;

        }

    },
    { passive: true }
);


/* =========================================================
   19. KEYBOARD ENTRY
   ========================================================= */

document.addEventListener(
    "keydown",
    async (event) => {

        /*
            Space / Enter can enter the world
            while the entry page is active.
        */

        if (
            !hasEntered &&
            (
                event.key === "Enter" ||
                event.key === " "
            )
        ) {

            event.preventDefault();

            enterButton.click();

        }

    }
);


/* =========================================================
   20. INITIAL STATE
   ========================================================= */

emotionSection.classList.add("hidden");
playlistSection.classList.add("hidden");
musicSection.classList.add("hidden");


console.log(
    "AIMuse frontend initialized."
);