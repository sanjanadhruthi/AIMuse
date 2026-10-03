/* =========================================================
   AIMuse — ACCOUNT (login popup, login bubble, likes ❤️)
   =========================================================
   Two parts, each wrapped in its own (() => { ... })() so their
   variables never clash:

     PART 1 — LIKES: the ♡ on every song row
     PART 2 — ACCOUNT POPUP + LOGIN BUBBLE (the 👤 button)

   Talks to the Flask API in src/accounts.py.
   ========================================================= */


/* ---------------------------------------------------------
   PART 1 — LIKES
   --------------------------------------------------------- */


(() => {

    const HEART =
        '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">' +
        '<path d="M12 20.5s-7.5-4.6-9.3-9.2C1.4 8 3.4 4.5 7 4.5c2 0 3.6 1.1 5 3 1.4-1.9 3-3 5-3 3.6 0 5.6 3.5 4.3 6.8-1.8 4.6-9.3 9.2-9.3 9.2z"/>' +
        '</svg>';

    const liked = new Map();      // videoId -> like
    let signedIn = false;

    const likedList = document.getElementById("auth-liked");


    /* ---------------------------------------------- helpers */

    function moodFor(item) {

        // script.js keeps these as top-level variables
        if (item.closest("#sample-song-list")) {
            try { if (activeSampleMood) return activeSampleMood; } catch (error) { /* not defined */ }
        }

        try { if (latestEmotion) return latestEmotion; } catch (error) { /* not defined */ }

        return "neutral";
    }

    function languageFor(song) {

        if (song && song.language) return song.language;

        try {
            if (selectedLanguage && selectedLanguage !== "mix") return selectedLanguage;
        } catch (error) { /* not defined */ }

        return "";
    }

    function askToLogIn() {
        window.dispatchEvent(new CustomEvent("aimuse:open-login", {
            detail: { reason: "Log in to save the songs you love ❤️" }
        }));
    }


    /* ---------------------------------------------- the heart on each row */

    function sync(item, heart) {

        const on = liked.has(item.dataset.videoId);
        const title = (item._song && item._song.title) || "this song";

        heart.classList.toggle("is-liked", on);
        heart.setAttribute("aria-pressed", String(on));
        heart.setAttribute("aria-label", on ? `Unlike ${title}` : `Like ${title}`);
        heart.title = on ? "Unlike" : (signedIn ? "Like" : "Log in to like songs");

    }

    function decorate(item) {

        if (!item.dataset.videoId) return;

        let heart = item.querySelector(".like-button");

        if (!heart) {

            // A <span role="button">, because the row itself is already
            // a <button> and buttons can't be nested inside buttons.
            heart = document.createElement("span");
            heart.className = "like-button";
            heart.setAttribute("role", "button");
            heart.tabIndex = 0;
            heart.innerHTML = HEART;

            heart.addEventListener("click", (event) => {
                event.stopPropagation();     // don't also play the song
                event.preventDefault();
                toggle(item, heart);
            });

            heart.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    event.stopPropagation();
                    toggle(item, heart);
                }
            });

            item.appendChild(heart);
        }

        sync(item, heart);

    }

    function refreshAll() {
        document.querySelectorAll(".song-item[data-video-id]").forEach(decorate);
    }


    /* ---------------------------------------------- like / unlike */

    async function toggle(item, heart) {

        if (!signedIn) {
            askToLogIn();
            return;
        }

        const videoId = item.dataset.videoId;
        const song = item._song || {};
        const wasLiked = liked.has(videoId);

        // Show it straight away; undo if the server says no.
        const like = {
            videoId,
            title: song.title || "Untitled",
            artist: song.artist || song.channel || "",
            mood: moodFor(item),
            language: languageFor(song)
        };

        if (wasLiked) liked.delete(videoId);
        else liked.set(videoId, like);

        heart.classList.remove("pop");
        void heart.offsetWidth;               // restart the animation
        if (!wasLiked) heart.classList.add("pop");

        refreshAll();
        renderLikedList();

        try {

            const response = wasLiked
                ? await fetch(`/likes/${encodeURIComponent(videoId)}`, { method: "DELETE" })
                : await fetch("/likes", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(like)
                });

            if (response.status === 401) {
                signedIn = false;
                throw new Error("logged out");
            }

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

        } catch (error) {

            if (wasLiked) liked.set(videoId, like);
            else liked.delete(videoId);

            refreshAll();
            renderLikedList();

            if (!signedIn) askToLogIn();

        }

    }


    /* ---------------------------------------------- list in the account popup */

    function renderLikedList() {

        if (!likedList) return;

        likedList.textContent = "";

        if (!signedIn) return;

        const heading = document.createElement("p");
        heading.className = "liked-heading";
        heading.textContent = `❤️ Liked songs (${liked.size})`;
        likedList.appendChild(heading);

        if (!liked.size) {
            const empty = document.createElement("p");
            empty.className = "liked-empty";
            empty.textContent = "Nothing yet — tap ♡ on any song you love.";
            likedList.appendChild(empty);
            return;
        }

        const list = document.createElement("ul");
        list.className = "liked-list";

        // song titles come from YouTube: textContent only, never HTML
        [...liked.values()].slice(0, 30).forEach((song) => {

            const li = document.createElement("li");
            const link = document.createElement("a");

            link.href = `https://www.youtube.com/watch?v=${encodeURIComponent(song.videoId)}`;
            link.target = "_blank";
            link.rel = "noopener";

            const title = document.createElement("span");
            title.className = "liked-title";
            title.textContent = song.title;

            const meta = document.createElement("span");
            meta.className = "liked-meta";
            meta.textContent = [song.artist, song.mood].filter(Boolean).join(" · ");

            link.append(title, meta);
            li.appendChild(link);
            list.appendChild(li);

        });

        likedList.appendChild(list);

    }


    /* ---------------------------------------------- loading */

    async function load() {

        liked.clear();

        if (signedIn) {
            try {
                const response = await fetch("/likes");
                const data = await response.json();
                if (response.ok) {
                    // newest first from the server; keep that order
                    data.likes.forEach((like) => liked.set(like.videoId, like));
                }
            } catch (error) {
                /* offline: hearts just show as empty */
            }
        }

        refreshAll();
        renderLikedList();

    }

    window.addEventListener("aimuse:auth", (event) => {
        signedIn = Boolean(event.detail && event.detail.username);
        load();
    });


    /* ---------------------------------------------- new rows from script.js */

    let queued = false;

    new MutationObserver(() => {

        if (queued) return;
        queued = true;

        requestAnimationFrame(() => {
            queued = false;
            refreshAll();
        });

    }).observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["data-video-id"]   // a failed song swapped for another upload
    });

    refreshAll();

})();



/* ---------------------------------------------------------
   PART 2 — ACCOUNT POPUP + LOGIN BUBBLE
   --------------------------------------------------------- */


(() => {

    const button = document.getElementById("account-toggle");
    const dialog = document.getElementById("auth-dialog");

    if (!button || !dialog) return;

    const form = dialog.querySelector("#auth-form");
    const accountView = dialog.querySelector("#auth-account");
    const title = dialog.querySelector("#auth-title");
    const subtitle = dialog.querySelector("#auth-subtitle");
    const tabs = dialog.querySelectorAll(".auth-tab");
    const usernameInput = dialog.querySelector("#auth-username");
    const passwordInput = dialog.querySelector("#auth-password");
    const showPassword = dialog.querySelector("#auth-show-password");
    const submit = dialog.querySelector("#auth-submit");
    const message = dialog.querySelector("#auth-message");
    const accountName = dialog.querySelector("#auth-account-name");
    const logoutButton = dialog.querySelector("#auth-logout");
    const closeButton = dialog.querySelector("#auth-close");
    const label = button.querySelector(".dock-label");

    let mode = "login";      // "login" | "signup"
    let user = null;         // username, or null for guests
    let busy = false;

    const TEXT = {
        login: {
            title: "Welcome back",
            subtitle: "Log in so AIMuse remembers the songs you love.",
            submit: "Log in",
            autocomplete: "current-password"
        },
        signup: {
            title: "Join AIMuse",
            subtitle: "Pick a username — no email needed.",
            submit: "Create account",
            autocomplete: "new-password"
        }
    };


    /* ---------------------------------------------- talking to Flask */

    async function api(path, body) {

        // The free Render server sleeps; waking it can take ~50 s.
        const slowNote = setTimeout(() => {
            showMessage("Waking up the server… this can take a little while.", "info");
        }, 3000);

        try {

            const response = await fetch(path, {
                method: body ? "POST" : "GET",
                headers: body ? { "Content-Type": "application/json" } : {},
                body: body ? JSON.stringify(body) : undefined,
                credentials: "same-origin"
            });

            const data = await response.json().catch(() => ({}));

            return { ok: response.ok && data.success !== false, data };

        } catch (error) {

            return { ok: false, data: { error: "Can't reach AIMuse right now. Check your internet and try again." } };

        } finally {

            clearTimeout(slowNote);

        }

    }


    /* ---------------------------------------------- what's on screen */

    function showMessage(text, kind = "error") {
        message.textContent = text || "";
        message.dataset.kind = kind;
    }

    function setMode(next) {

        mode = next;

        const t = TEXT[mode];

        title.textContent = t.title;
        subtitle.textContent = t.subtitle;
        submit.textContent = t.submit;
        passwordInput.autocomplete = t.autocomplete;

        tabs.forEach((tab) => {
            const active = tab.dataset.mode === mode;
            tab.classList.toggle("is-active", active);
            tab.setAttribute("aria-selected", String(active));
        });

        showMessage("");

    }

    function render() {

        const signedIn = Boolean(user);

        button.classList.toggle("is-signed-in", signedIn);
        button.setAttribute("aria-label", signedIn ? `Account: ${user}` : "Log in or sign up");
        button.title = signedIn ? `Signed in as ${user}` : "Log in or sign up";
        if (label) label.textContent = signedIn ? user : "Log in";

        form.hidden = signedIn;
        accountView.hidden = !signedIn;

        if (signedIn) {
            title.textContent = "Your account";
            subtitle.textContent = "Likes and mood history are saved to this account.";
            accountName.textContent = user;
        } else {
            setMode(mode);
        }

    }

    function setUser(next) {

        const changed = next !== user;

        user = next;
        render();

        if (changed) {
            window.dispatchEvent(new CustomEvent("aimuse:auth", { detail: { username: user } }));
        }

    }

    function setBusy(state) {
        busy = state;
        submit.disabled = state;
        logoutButton.disabled = state;
        submit.classList.toggle("is-busy", state);
    }


    /* ---------------------------------------------- open / close */

    function open() {

        render();
        showMessage("");

        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "");

        if (!user) setTimeout(() => usernameInput.focus(), 50);

    }

    function close() {

        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");

    }

    button.addEventListener("click", open);
    closeButton.addEventListener("click", close);

    // Tapping the dark area outside the card closes it.
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) close();
    });

    tabs.forEach((tab) => {
        tab.addEventListener("click", () => setMode(tab.dataset.mode));
    });

    showPassword.addEventListener("change", () => {
        passwordInput.type = showPassword.checked ? "text" : "password";
    });


    /* ---------------------------------------------- log in / sign up */

    form.addEventListener("submit", async (event) => {

        event.preventDefault();

        if (busy) return;

        const username = usernameInput.value.trim();
        const password = passwordInput.value;

        setBusy(true);
        showMessage("");

        const { ok, data } = await api(`/auth/${mode}`, { username, password });

        setBusy(false);

        if (!ok) {
            showMessage(data.error || "Something went wrong. Please try again.");
            if (mode === "login") passwordInput.select();
            return;
        }

        passwordInput.value = "";
        showPassword.checked = false;
        passwordInput.type = "password";

        setUser(data.username);
        showMessage(mode === "signup" ? "Account created — welcome! 🌙" : "Welcome back! 🌙", "success");

        setTimeout(close, 1100);

    });


    /* ---------------------------------------------- log out */

    logoutButton.addEventListener("click", async () => {

        if (busy) return;

        setBusy(true);
        const { ok } = await api("/auth/logout", {});
        setBusy(false);

        if (!ok) {
            showMessage("Couldn't log out. Please try again.");
            return;
        }

        setMode("login");
        setUser(null);
        close();

    });


    /* ---------------------------------------------- the login nudge
       A small speech bubble under the 👤 button on the WELCOME
       screen: "Log in or sign up — for a better experience".

       Polite on purpose — a nudge that nags makes people leave:
         - guests only (never shown to someone logged in)
         - once per visit, for about 3 seconds
         - gone the moment you tap anything else (e.g. ENTER)
         - ✕ means "never show this again"
    */

    const NUDGE_KEY = "aimuseLoginNudge";       // localStorage: {shown, off}
    const NUDGE_SESSION = "aimuseLoginNudgeSeen";
    const NUDGE_DELAY = 1200;     // let the welcome screen settle first
    const NUDGE_STAYS = 3000;     // about 3 seconds on screen

    const nudge = document.getElementById("login-nudge");
    const nudgeOpen = document.getElementById("login-nudge-open");
    const nudgeClose = document.getElementById("login-nudge-close");

    let meChecked = false;
    let nudgeTimer = null;

    function readNudge() {
        try {
            return JSON.parse(localStorage.getItem(NUDGE_KEY)) || { shown: 0, off: false };
        } catch (error) {
            return { shown: 0, off: false };
        }
    }

    function writeNudge(state) {
        try { localStorage.setItem(NUDGE_KEY, JSON.stringify(state)); } catch (error) { /* blocked */ }
    }

    function seenThisVisit() {
        try { return sessionStorage.getItem(NUDGE_SESSION) === "1"; } catch (error) { return false; }
    }

    // Sits right under the button on phones (dock at the top) and
    // right above it on computers (dock at the bottom); the little
    // arrow always points at the 👤 icon.
    function placeNudge() {

        if (!nudge || nudge.hidden) return;

        const b = button.getBoundingClientRect();

        // offsetWidth/Height = the real size. (getBoundingClientRect
        // would include the 0.96 "pop-in" scale and come out too small.)
        const n = { width: nudge.offsetWidth, height: nudge.offsetHeight };
        const gap = 12;
        const margin = 10;

        const below = b.top + b.height / 2 < window.innerHeight / 2;

        let left = b.left + b.width / 2 - n.width / 2;
        // clientWidth = the width you can actually see (innerWidth can
        // be a few px wider if anything on the page pokes out sideways)
        const screenWidth = document.documentElement.clientWidth;

        left = Math.max(margin, Math.min(left, screenWidth - n.width - margin));

        const top = below ? b.bottom + gap : b.top - n.height - gap;

        nudge.style.left = `${left}px`;
        nudge.style.top = `${top}px`;
        nudge.style.setProperty("--arrow-x", `${b.left + b.width / 2 - left}px`);
        nudge.classList.toggle("is-below", below);

    }

    function hideOnOutsideTap(event) {
        if (!nudge.contains(event.target)) hideNudge();
    }

    function hideNudge() {

        clearTimeout(nudgeTimer);

        if (!nudge || nudge.hidden) return;

        nudge.classList.remove("is-visible");
        button.classList.remove("is-nudging");

        window.removeEventListener("scroll", hideNudge);
        document.removeEventListener("pointerdown", hideOnOutsideTap, true);
        window.removeEventListener("resize", placeNudge);

        setTimeout(() => { nudge.hidden = true; }, 300);

    }

    function maybeShowNudge() {

        if (!nudge || user || !meChecked) return;
        // not while the entry animation plays (the dock is hidden then)
        if (document.querySelector(".portal-transition.active")) return;
        if (seenThisVisit()) return;

        const state = readNudge();
        if (state.off) return;

        clearTimeout(nudgeTimer);

        nudgeTimer = setTimeout(() => {

            // things may have changed while we waited
            if (user || dialog.open || seenThisVisit()) return;
            if (document.querySelector(".portal-transition.active")) return;

            writeNudge({ ...state, shown: state.shown + 1 });
            try { sessionStorage.setItem(NUDGE_SESSION, "1"); } catch (error) { /* blocked */ }

            nudge.hidden = false;
            placeNudge();

            requestAnimationFrame(() => {
                nudge.classList.add("is-visible");
                button.classList.add("is-nudging");
            });

            window.addEventListener("scroll", hideNudge, { passive: true, once: true });

            // any tap outside the bubble (ENTER, the page…) hides it
            document.addEventListener("pointerdown", hideOnOutsideTap, true);
            window.addEventListener("resize", placeNudge);

            nudgeTimer = setTimeout(hideNudge, NUDGE_STAYS);

        }, NUDGE_DELAY);

    }

    if (nudge) {

        nudgeOpen.addEventListener("click", () => {
            hideNudge();
            setMode("login");
            open();
        });

        nudgeClose.addEventListener("click", () => {
            hideNudge();
            writeNudge({ ...readNudge(), off: true });
        });

        // Opening the popup yourself, or logging in, hides it too.
        button.addEventListener("click", hideNudge);
        window.addEventListener("aimuse:auth", hideNudge);

        // Pressing ENTER (script.js adds "entered" to <body>) hides it.
        new MutationObserver(() => {
            if (document.body.classList.contains("entered")) hideNudge();
        }).observe(document.body, { attributes: true, attributeFilter: ["class"] });

    }


    /* ---------------------------------------------- asked to log in
       Part 1 (likes) asks for this when a guest taps ♡ on a song.
    */

    window.addEventListener("aimuse:open-login", (event) => {

        hideNudge();

        if (user) return;

        setMode("login");
        open();

        const reason = event.detail && event.detail.reason;
        if (reason) showMessage(reason, "info");

    });


    /* ---------------------------------------------- on page load */

    render();

    api("/auth/me").then(({ ok, data }) => {
        if (ok && data.logged_in) setUser(data.username);
        meChecked = true;
        maybeShowNudge();
    });

})();