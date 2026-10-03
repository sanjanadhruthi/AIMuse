/* =========================================================
   AIMuse — ACCOUNT POPUP (log in / sign up / log out)
   =========================================================
   The 👤 button in the settings dock opens a <dialog>.

     Logged out -> a form with two tabs: "Log in" / "Sign up"
     Logged in  -> "Signed in as …" and a Log out button

   It talks to the Flask API in src/auth.py:
     GET  /auth/me      who am I?
     POST /auth/login   POST /auth/signup   POST /auth/logout

   When the account changes, it fires an "aimuse:auth" event
   on window, so likes / history (next phases) can react.
   ========================================================= */

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


    /* ---------------------------------------------- on page load */

    render();

    api("/auth/me").then(({ ok, data }) => {
        if (ok && data.logged_in) setUser(data.username);
    });

})();