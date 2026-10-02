/* =========================================================
   AIMuse — INTERACTION EFFECTS
   =========================================================
   Loaded AFTER script.js. It never changes how AIMuse works,
   it only reacts to the person:

     E1. Moonlight cursor ring    — follows the pointer, swells
                                     over anything clickable
     E2. Confidence count-up      — 0% → 84% while the bar fills
     E3. Spotlight glow + tilt    — a pastel light under the
                                     pointer, cards lean toward it
     E4. Staggered float-ins      — songs / cards arrive one by one
     E5. Self-drawing timeline    — "How AIMuse hears you"
     E7. Butterflies              — a few pastel butterflies drift by

   Off on touch screens, with "prefers-reduced-motion", and
   while the "Reduce effects" button is on (checked live).
   ========================================================= */

(() => {

    "use strict";

    const REDUCED_MOTION =
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const TOUCH =
        window.matchMedia("(hover: none), (pointer: coarse)").matches;

    // "Reduce effects" can be switched on and off at any time.
    const effectsOff = () =>
        REDUCED_MOTION || document.body.classList.contains("reduce-effects");

    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));


    /* =====================================================
       E1. MOONLIGHT CURSOR RING
       ===================================================== */

    const CLICKABLE =
        "a, button, [role='tab'], [role='button'], label, select, " +
        ".song-item, .original-track-card";

    const TEXT_FIELDS =
        "textarea, input[type='text'], input[type='email'], input:not([type])";

    function setupCursorRing() {

        if (TOUCH || REDUCED_MOTION) return;

        const ring = document.createElement("div");
        const dot = document.createElement("div");

        ring.className = "cursor-ring";
        dot.className = "cursor-dot";

        ring.setAttribute("aria-hidden", "true");
        dot.setAttribute("aria-hidden", "true");

        document.body.append(ring, dot);

        let targetX = -100;
        let targetY = -100;
        let ringX = targetX;
        let ringY = targetY;

        document.addEventListener("mousemove", (event) => {

            targetX = event.clientX;
            targetY = event.clientY;

            // the dot is glued to the pointer, the ring drifts after it
            dot.style.transform = `translate3d(${targetX}px, ${targetY}px, 0)`;

            document.body.classList.add("has-cursor-ring");
            document.body.classList.remove("cursor-away");

        }, { passive: true });

        document.addEventListener("mouseover", (event) => {

            const target = event.target;

            // Over the YouTube player the page stops receiving
            // pointer events, so the ring would freeze — hide it.
            if (target.closest("iframe, .youtube-player-wrap")) {
                document.body.classList.add("cursor-away");
                return;
            }

            const isText = Boolean(target.closest(TEXT_FIELDS));
            const isHover = !isText && Boolean(target.closest(CLICKABLE));

            ring.classList.toggle("is-text", isText);
            ring.classList.toggle("is-hover", isHover);
            dot.classList.toggle("is-hover", isHover || isText);

        });

        document.documentElement.addEventListener("mouseleave", () => {
            document.body.classList.add("cursor-away");
        });

        document.addEventListener("mousedown", () => ring.classList.add("is-down"));
        document.addEventListener("mouseup", () => ring.classList.remove("is-down"));

        (function follow() {

            ringX += (targetX - ringX) * 0.2;
            ringY += (targetY - ringY) * 0.2;

            ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0)`;

            requestAnimationFrame(follow);

        })();

    }


    /* =====================================================
       E2. CONFIDENCE COUNT-UP
       =====================================================
       script.js writes e.g. "84%" into #confidence-value and,
       100 ms later, sets the bar's width. We notice the text
       change, empty the bar so it fills from zero, and count
       the number up at the same speed as the bar (1 s).
       ===================================================== */

    function setupConfidenceCountUp() {

        const value = document.getElementById("confidence-value");
        const fill = document.getElementById("confidence-fill");

        if (!value || !fill) return;

        // MutationObserver reports changes a moment later, so our
        // own count-up writes come back to us too. Remembering what
        // we last wrote lets us ignore those.
        let lastWritten = null;
        let frame = null;

        const easeOut = (t) => 1 - Math.pow(1 - t, 3);

        new MutationObserver(() => {

            const text = value.textContent.trim();

            if (text === lastWritten || effectsOff()) return;

            const target = parseInt(text, 10);

            if (!Number.isFinite(target)) return;

            // bar back to 0 instantly; script.js fills it shortly after
            fill.style.transition = "none";
            fill.style.width = "0%";
            void fill.offsetWidth;
            fill.style.transition = "";

            cancelAnimationFrame(frame);

            const start = performance.now();
            const duration = 1000;
            const delay = 100;     // matches script.js's setTimeout

            const step = (now) => {

                const t = clamp((now - start - delay) / duration, 0, 1);

                lastWritten = `${Math.round(easeOut(t) * target)}%`;
                value.textContent = lastWritten;

                if (t < 1) {
                    frame = requestAnimationFrame(step);
                }

            };

            frame = requestAnimationFrame(step);

        }).observe(value, { childList: true, characterData: true, subtree: true });

    }


    /* =====================================================
       E3. SPOTLIGHT GLOW + TILT
       =====================================================
       One listener for the whole page (event delegation), so
       it also works on songs and cards created later.
       ===================================================== */

    const GLOW =
        ".song-item, .original-track-card, .step-card, " +
        ".playlist-panel, .emotion-card";

    // how far each kind of card may lean (degrees)
    const TILT = {
        "original-track-card": 9,
        "emotion-card": 2.5
    };

    function tiltFor(el) {

        for (const [className, degrees] of Object.entries(TILT)) {
            if (el.classList.contains(className)) return degrees;
        }

        return 0;
    }

    function setupGlowAndTilt() {

        if (TOUCH) return;

        let current = null;
        let pending = null;

        function release() {

            if (!current) return;

            current.classList.remove("is-lit");

            if (tiltFor(current)) {
                current.style.transform = "";
            }

            current = null;
        }

        function update(event) {

            pending = null;

            if (effectsOff()) {
                release();
                return;
            }

            const el = event.target.closest(GLOW);

            if (el !== current) {
                release();
                current = el;
            }

            if (!el) return;

            el.classList.add("glow-surface", "is-lit");

            const rect = el.getBoundingClientRect();

            const px = (event.clientX - rect.left) / rect.width;
            const py = (event.clientY - rect.top) / rect.height;

            el.style.setProperty("--gx", `${(px * 100).toFixed(1)}%`);
            el.style.setProperty("--gy", `${(py * 100).toFixed(1)}%`);

            const degrees = tiltFor(el);

            if (degrees) {

                el.classList.add("fx-tilt");

                const rotateY = (px - 0.5) * degrees * 2;
                const rotateX = (0.5 - py) * degrees * 2;

                el.style.transform =
                    `perspective(900px) rotateX(${rotateX.toFixed(2)}deg) ` +
                    `rotateY(${rotateY.toFixed(2)}deg) translateY(-6px)`;
            }
        }

        document.addEventListener("pointermove", (event) => {

            // at most one update per frame
            if (pending) return;

            pending = requestAnimationFrame(() => update(event));

        }, { passive: true });

        document.documentElement.addEventListener("mouseleave", release);

    }


    /* =====================================================
       E4. STAGGERED FLOAT-INS + SCROLL REVEALS
       ===================================================== */

    const FLOAT_CONTAINERS = [
        "song-list",
        "sample-song-list",
        "mood-playlist-panel",
        "mood-tabs",
        "original-tracks-grid"
    ];

    const FLOAT_ITEMS = ".song-item, .mood-tab, .original-track-card";

    function floatIn(elements) {

        if (effectsOff()) return;

        elements.forEach((el, index) => {

            el.style.setProperty("--i", Math.min(index, 14));

            // restart the animation even if the class was already there
            el.classList.remove("fx-float-in");
            void el.offsetWidth;
            el.classList.add("fx-float-in");

            el.addEventListener(
                "animationend",
                () => el.classList.remove("fx-float-in"),
                { once: true }
            );
        });
    }

    function setupFloatIns() {

        FLOAT_CONTAINERS.forEach((id) => {

            const container = document.getElementById(id);

            if (!container) return;

            new MutationObserver((mutations) => {

                const added = [];

                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {

                        if (node.nodeType !== 1) return;

                        if (node.matches(FLOAT_ITEMS)) {
                            added.push(node);
                        }

                        added.push(...node.querySelectorAll(FLOAT_ITEMS));
                    });
                });

                if (added.length) {
                    floatIn(added);
                }

            }).observe(container, { childList: true, subtree: true });

            // items that were already there when the page loaded
            floatIn([...container.querySelectorAll(FLOAT_ITEMS)]);
        });

    }

    const REVEAL =
        ".section-heading, .subsection-label, .future-section > *:not(.future-glow)";

    function setupScrollReveals() {

        if (!("IntersectionObserver" in window)) return;

        const targets = [...document.querySelectorAll(REVEAL)];

        const observer = new IntersectionObserver((entries) => {

            entries.forEach((entry) => {

                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                }
            });

        }, { threshold: 0.15, rootMargin: "0px 0px -8% 0px" });

        targets.forEach((el, index) => {

            el.classList.add("fx-reveal");
            el.style.setProperty("--i", index % 3);
            observer.observe(el);
        });

    }


    /* =====================================================
       E5. SELF-DRAWING TIMELINE
       =====================================================
       The line grows with the scroll position. Each step
       lights up (and slides in) once the line reaches its
       dot, and stays lit. The line itself follows the scroll
       both ways, so scrolling back up "undraws" it.
       ===================================================== */

    function setupTimeline() {

        const timeline = document.getElementById("how-timeline");

        if (!timeline) return;

        const fill = timeline.querySelector(".timeline-fill");
        const steps = [...timeline.querySelectorAll(".timeline-step")];

        // alternate sides: left, right, left, right…
        steps.forEach((step, index) => {
            step.classList.toggle("is-right", index % 2 === 1);
        });

        let scheduled = false;

        function draw() {

            scheduled = false;

            const rect = timeline.getBoundingClientRect();
            const viewport = window.innerHeight;

            // the line's tip sits at 65% of the screen height
            const reach = viewport * 0.65 - rect.top;

            const progress = clamp(reach / rect.height, 0, 1);

            if (fill) {
                fill.style.setProperty("--progress", progress.toFixed(4));
            }

            steps.forEach((step) => {

                const node = step.querySelector(".timeline-node");

                const nodeTop = node
                    ? step.offsetTop + node.offsetTop
                    : step.offsetTop;

                if (reach >= nodeTop) {
                    step.classList.add("is-lit");
                }
            });
        }

        function schedule() {

            if (scheduled) return;

            scheduled = true;
            requestAnimationFrame(draw);
        }

        window.addEventListener("scroll", schedule, { passive: true });
        window.addEventListener("resize", schedule);

        draw();

    }


    /* =====================================================
       E7. BUTTERFLIES
       =====================================================
       A few pastel butterflies drift across the screen on
       slow, wandering paths, flapping their wings. They sit
       above the page but never block a tap (pointer-events:
       none), avoid nothing, and stay few so they feel like a
       surprise rather than decoration.
       ===================================================== */

    const BUTTERFLY_PALETTES = [
        ["#f6b8d8", "#c9b2f2"],     // blush -> lavender
        ["#b9d8f6", "#c7b6f4"],     // sky -> lavender
        ["#f7c6e0", "#f3dcb6"],     // pink -> peach
        ["#d6c4fa", "#a9cdf3"]      // lavender -> sky
    ];

    function butterflySVG(id, [a, b]) {

        return `
        <svg viewBox="-50 -50 100 100" aria-hidden="true">
            <defs>
                <linearGradient id="bf-${id}" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" stop-color="${a}"/>
                    <stop offset="1" stop-color="${b}"/>
                </linearGradient>
            </defs>
            <g class="bf-wing bf-left">
                <path d="M -2 -4 C -20 -38, -48 -30, -40 -6 C -36 4, -16 4, -2 0 Z"
                      fill="url(#bf-${id})" stroke="rgba(255,255,255,0.85)" stroke-width="1.6"/>
                <path d="M -2 2 C -16 8, -34 18, -26 32 C -18 40, -6 22, -2 6 Z"
                      fill="url(#bf-${id})" stroke="rgba(255,255,255,0.85)" stroke-width="1.6"/>
                <circle cx="-24" cy="-14" r="4" fill="rgba(255,255,255,0.75)"/>
            </g>
            <g class="bf-wing bf-right">
                <path d="M 2 -4 C 20 -38, 48 -30, 40 -6 C 36 4, 16 4, 2 0 Z"
                      fill="url(#bf-${id})" stroke="rgba(255,255,255,0.85)" stroke-width="1.6"/>
                <path d="M 2 2 C 16 8, 34 18, 26 32 C 18 40, 6 22, 2 6 Z"
                      fill="url(#bf-${id})" stroke="rgba(255,255,255,0.85)" stroke-width="1.6"/>
                <circle cx="24" cy="-14" r="4" fill="rgba(255,255,255,0.75)"/>
            </g>
            <ellipse cx="0" cy="2" rx="2.6" ry="15" fill="#8a76c4"/>
            <path d="M -1 -12 Q -6 -24 -10 -27 M 1 -12 Q 6 -24 10 -27"
                  stroke="#8a76c4" stroke-width="1.4" fill="none" stroke-linecap="round"/>
        </svg>`;
    }

    function setupButterflies() {

        if (REDUCED_MOTION) return;

        const layer = document.createElement("div");
        layer.className = "butterfly-layer";
        layer.setAttribute("aria-hidden", "true");
        document.body.appendChild(layer);

        const small = window.innerWidth < 600;
        const count = small ? 3 : 5;

        const flock = [];

        for (let i = 0; i < count; i++) {

            const el = document.createElement("div");
            el.className = "butterfly";
            el.innerHTML = butterflySVG(i, BUTTERFLY_PALETTES[i % BUTTERFLY_PALETTES.length]);

            const size = (small ? 36 : 44) + Math.random() * (small ? 12 : 18);
            el.style.width = el.style.height = `${size}px`;
            el.style.setProperty("--flap", `${0.32 + Math.random() * 0.22}s`);

            layer.appendChild(el);

            flock.push({
                el,
                x: Math.random() * window.innerWidth,
                y: Math.random() * window.innerHeight,
                heading: Math.random() * Math.PI * 2,
                speed: 26 + Math.random() * 24,          // px per second
                turn: 0.4 + Math.random() * 0.6,
                phase: Math.random() * 10,
                bob: 6 + Math.random() * 8
            });
        }

        let last = performance.now();

        function fly(now) {

            const dt = Math.min(0.05, (now - last) / 1000);
            last = now;

            const hidden = effectsOff() || document.hidden;
            layer.classList.toggle("is-off", hidden);

            if (!hidden) {

                const w = window.innerWidth;
                const h = window.innerHeight;
                const t = now / 1000;

                for (const b of flock) {

                    // gentle wandering, like the fairy dust but livelier
                    b.heading += Math.sin(t * b.turn + b.phase) * dt * 1.4;

                    b.x += Math.cos(b.heading) * b.speed * dt;
                    b.y += Math.sin(b.heading) * b.speed * dt;

                    // fluttery up-and-down bob
                    const bob = Math.sin(t * 3 + b.phase) * b.bob;

                    // wrap around the screen edges
                    const m = 60;
                    if (b.x < -m) b.x = w + m;
                    if (b.x > w + m) b.x = -m;
                    if (b.y < -m) b.y = h + m;
                    if (b.y > h + m) b.y = -m;

                    // face the way it flies (wings up = flying "up" on screen)
                    const angle = b.heading * 180 / Math.PI + 90;

                    b.el.style.transform =
                        `translate3d(${b.x}px, ${b.y + bob}px, 0) rotate(${angle.toFixed(1)}deg)`;
                }
            }

            requestAnimationFrame(fly);
        }

        requestAnimationFrame(fly);
    }


    /* =====================================================
       START
       ===================================================== */

    function start() {

        setupCursorRing();
        setupConfidenceCountUp();
        setupGlowAndTilt();
        setupFloatIns();
        setupScrollReveals();
        setupTimeline();
        setupButterflies();

    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }

})();