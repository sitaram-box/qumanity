/**
 * Qumanity — bottom "Oराम" marquee (scrolling poem ticker).
 *
 * Features:
 *  - Loads 237 poems from /static/poems.json (accepts a top-level array or a
 *    { "poems": [...] } wrapper).
 *  - Picks a random poem on first visit, then plays sequentially and wraps to 0.
 *  - Persists the current poem index in localStorage (resumes across reloads).
 *  - Seamless, gap-free transitions: the text swaps exactly on the animation
 *    iteration boundary, while the CSS animation keeps running.
 *  - Pause freezes the scroll exactly where it is; Play resumes from that same
 *    position (no jump to the beginning) — done purely via
 *    `animation-play-state`, never restarting the animation.
 *  - When paused, double-arrow buttons (⏪ ⏩) scrub backward/forward *within the
 *    current poem* relative to the paused position, clamped to the poem bounds.
 *  - Left "Oराम" button opens a dropdown (Vinaya Patrika / Weather / News).
 */
(function () {
  "use strict";

  var POEMS_URL = "/static/poems.json";
  var LS_INDEX = "marquee_index";

  // Fallback when the dynamic duration cannot be computed; keep in sync with
  // `.marquee-text` animation duration in style.css.
  var DURATION_MS = 75000;
  // Constant scroll speed in pixels/second — the same for every poem, so a
  // long poem simply takes longer rather than scrolling faster.
  // ~29% faster than the previous 70 px/s (moderate increase).
  var PX_PER_SECOND = 90;
  // Each arrow click scrubs this fraction of one poem's scroll.
  var STEP_FRACTION = 0.1;
  var SCRUB_TWEEN_MS = 250;

  // Shown when poems.json cannot be loaded.
  var FALLBACK = [{ id: 0, marker: "", text: "॥ श्रीराम ॥   Jai Shri Ram" }];

  var poems = [];
  var currentIndex = 0;
  var paused = false;
  var scrubRAF = null;
  var els = {};
  // Debounce so browsers that fire both `animationiteration` and the legacy
  // `webkitAnimationIteration` don't advance the poem twice per cycle.
  var lastAdvanceTs = 0;

  function qs(id) {
    return document.getElementById(id);
  }

  function cacheEls() {
    els.container = qs("qb-marquee");
    els.text = qs("qb-marquee-text");
    els.playBtn = qs("qb-marquee-playpause");
    els.prevBtn = qs("qb-marquee-prev");
    els.nextBtn = qs("qb-marquee-next");
    els.menuBtn = qs("sitaRamButton");
    els.menu = qs("qb-marquee-menu");
    return !!(els.container && els.text);
  }

  function notify(message, type) {
    if (typeof window.qbToast === "function") {
      window.qbToast(message, type || "info");
    } else {
      // eslint-disable-next-line no-console
      console.log(message);
    }
  }

  // Collapse the poem's internal line breaks into ticker-friendly separators.
  function formatPoem(poem) {
    if (!poem) return "";
    var body = String(poem.text || "")
      .replace(/\r/g, "")
      .replace(/\s*\n\s*/g, "   •   ")
      .trim();
    var marker = String(poem.marker || "").trim();
    return marker ? marker + "   —   " + body : body;
  }

  // --- Play / pause (resume from the exact same position) -------------------

  function setPausedState(p) {
    paused = !!p;
    if (els.container) els.container.classList.toggle("is-paused", paused);
    if (els.text) els.text.classList.toggle("paused", paused);
    if (els.playBtn) {
      els.playBtn.textContent = paused ? "\u25B6" : "\u275A\u275A"; // ▶  /  ❚❚
      els.playBtn.setAttribute("aria-label", paused ? "Play" : "Pause");
      els.playBtn.setAttribute("title", paused ? "Play" : "Pause");
      els.playBtn.setAttribute("aria-pressed", paused ? "true" : "false");
    }
  }

  // Pause/resume only toggle `animation-play-state` (via the .paused class), so
  // the current transform position is preserved and motion resumes in place.
  function play() {
    setPausedState(false);
  }
  function pause() {
    setPausedState(true);
  }
  function togglePlayPause() {
    if (paused) play();
    else pause();
  }

  // --- In-poem scrubbing (arrows, only while paused) ------------------------

  function getAnim() {
    if (!els.text || typeof els.text.getAnimations !== "function") return null;
    var list = els.text.getAnimations();
    return list && list.length ? list[0] : null;
  }

  function animDuration(anim) {
    try {
      var d = anim.effect.getComputedTiming().duration;
      if (typeof d === "number" && d > 0) return d;
    } catch (e) {
      /* ignore */
    }
    return DURATION_MS;
  }

  function tweenCurrentTime(anim, target, ms) {
    if (scrubRAF) {
      cancelAnimationFrame(scrubRAF);
      scrubRAF = null;
    }
    var start = Number(anim.currentTime) || 0;
    var delta = target - start;
    if (!delta) {
      try {
        anim.currentTime = target;
      } catch (e) {}
      return;
    }
    var t0 = null;
    function frame(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min(1, (ts - t0) / ms);
      var eased = 1 - Math.pow(1 - p, 2); // ease-out
      try {
        anim.currentTime = start + delta * eased;
      } catch (e) {}
      if (p < 1) scrubRAF = requestAnimationFrame(frame);
      else scrubRAF = null;
    }
    scrubRAF = requestAnimationFrame(frame);
  }

  // direction: -1 rewinds (text moves backward), +1 fast-forwards.
  function scrub(direction) {
    var anim = getAnim();
    if (!anim) return;
    var dur = animDuration(anim);
    var cur = Number(anim.currentTime) || 0;
    // Stay within the *current* poem's iteration window [iterBase, iterBase+dur].
    var iterBase = Math.floor(cur / dur) * dur;
    var within = cur - iterBase;
    var target = within + direction * dur * STEP_FRACTION;
    if (target < 0) target = 0; // beginning of poem — no further effect
    if (target > dur) target = dur; // end of poem — no further effect
    tweenCurrentTime(anim, iterBase + target, SCRUB_TWEEN_MS);
  }

  // --- Poem rotation --------------------------------------------------------

  // The CSS animation travels the element's full width (text + the 100%
  // padding lead-in) per cycle. Fixing the px/s speed means computing the
  // duration from the rendered width of each poem.
  function applyConstantSpeed() {
    if (!els.text) return;
    var distance = els.text.offsetWidth || els.text.scrollWidth || 0;
    if (!distance) return;
    var secs = distance / PX_PER_SECOND;
    // Clamp to something sane in case measurement misfires.
    if (secs < 10) secs = 10;
    if (secs > 600) secs = 600;
    els.text.style.animationDuration = secs.toFixed(2) + "s";
  }

  function updateMarqueeText(index) {
    if (!poems.length) return;
    var len = poems.length;
    // Wrap any index (forward or backward) into [0, len). This is what makes
    // poem 237 → poem 1 happen seamlessly and loop forever.
    currentIndex = ((index % len) + len) % len;
    els.text.textContent = formatPoem(poems[currentIndex]);
    // Measure after the new text has been laid out.
    requestAnimationFrame(applyConstantSpeed);
    try {
      localStorage.setItem(LS_INDEX, String(currentIndex));
    } catch (e) {
      /* ignore */
    }
  }

  // Move to the next poem, wrapping back to the first after the last one.
  function nextPoem() {
    if (!poems.length) return;
    var next = currentIndex + 1;
    if (next >= poems.length) next = 0; // infinite loop: 237 → 1
    updateMarqueeText(next);
  }

  // Fired on every animation-cycle boundary (the text has scrolled fully off
  // screen), so swapping the poem here is gap-free.
  function advance() {
    if (paused) return; // never auto-advance while frozen
    var now = Date.now();
    if (now - lastAdvanceTs < 1000) return; // debounce duplicate events
    lastAdvanceTs = now;
    nextPoem();
  }

  function getStartIndex(len) {
    var stored = null;
    try {
      stored = localStorage.getItem(LS_INDEX);
    } catch (e) {
      stored = null;
    }
    if (stored === null || stored === "") {
      return Math.floor(Math.random() * len);
    }
    var n = parseInt(stored, 10);
    if (isNaN(n) || n < 0 || n >= len) {
      return Math.floor(Math.random() * len);
    }
    return n;
  }

  function loadPoems() {
    return fetch(POEMS_URL, { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        var list = Array.isArray(data) ? data : data && data.poems;
        if (!Array.isArray(list) || !list.length) throw new Error("no poems");
        poems = list;
      })
      .catch(function () {
        poems = FALLBACK;
      });
  }

  function initMarquee() {
    if (!poems.length) poems = FALLBACK;

    currentIndex = getStartIndex(poems.length);
    updateMarqueeText(currentIndex);
    // Always start playing so the text is never frozen off-screen on load.
    setPausedState(false);

    // Swap to the next poem each time a full scroll cycle completes — this
    // fires when the text has wrapped off-screen, so there is no blank gap.
    // Listen for the standard event and the legacy WebKit/Safari name so the
    // loop keeps advancing on every engine; `advance()` debounces duplicates.
    els.text.addEventListener("animationiteration", advance);
    els.text.addEventListener("webkitAnimationIteration", advance);

    // The lead-in padding is 100% of the container, so the travel distance —
    // and therefore the constant-speed duration — changes with window width.
    var resizeT = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeT);
      resizeT = setTimeout(applyConstantSpeed, 200);
    });

    if (els.playBtn) {
      els.playBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        togglePlayPause();
      });
    }
    if (els.prevBtn) {
      els.prevBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (!paused) pause();
        scrub(-1);
      });
    }
    if (els.nextBtn) {
      els.nextBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (!paused) pause();
        scrub(1);
      });
    }
  }

  // --- Dropdown menu --------------------------------------------------------

  function setupDropdown() {
    if (!els.menuBtn || !els.menu) return;

    function closeMenu() {
      els.menu.classList.remove("show");
      els.menuBtn.setAttribute("aria-expanded", "false");
    }

    function openMenu() {
      els.menu.classList.add("show");
      els.menuBtn.setAttribute("aria-expanded", "true");
    }

    els.menuBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (els.menu.classList.contains("show")) closeMenu();
      else openMenu();
    });

    els.menu.addEventListener("click", function (e) {
      var item = e.target.closest("[data-marquee-action]");
      if (!item) return;
      e.preventDefault();
      var action = item.getAttribute("data-marquee-action");
      if (action === "weather") {
        notify(
          els.menu.getAttribute("data-weather-msg") || "Weather feature coming soon",
          "info"
        );
      } else if (action === "news") {
        notify(
          els.menu.getAttribute("data-news-msg") || "News feature coming soon",
          "info"
        );
      }
      // "vinaya" simply continues showing poems (no change).
      closeMenu();
    });

    document.addEventListener("click", function (e) {
      if (!els.menu.classList.contains("show")) return;
      if (els.menu.contains(e.target) || els.menuBtn.contains(e.target)) return;
      closeMenu();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && els.menu.classList.contains("show")) {
        closeMenu();
        els.menuBtn.focus();
      }
    });
  }

  function init() {
    if (!cacheEls()) return;
    setupDropdown();
    loadPoems().then(initMarquee);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
