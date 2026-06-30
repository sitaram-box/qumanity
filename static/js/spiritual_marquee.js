/**
 * SpiritualMarquee — interactive Ramcharitmanas verse ticker (v2).
 * Extends base marquee.js behaviour with verse panel, speed, progress.
 */
(function () {
  "use strict";

  class SpiritualMarquee {
    constructor(root) {
      this.root = root;
      this.isPlaying = true;
      this.currentSpeed = 3;
      this.verses = [];
      this.currentVerseIndex = 0;
      this._progressRAF = null;
      this._els = {};
      this._bindEls();
      this._wireControls();
      this._createPanel();
    }

    _bindEls() {
      this._els.text = document.getElementById("qb-marquee-text");
      this._els.playBtn = document.getElementById("qb-marquee-playpause");
      this._els.prevBtn = document.getElementById("qb-marquee-prev");
      this._els.nextBtn = document.getElementById("qb-marquee-next");
      this._els.speed = document.getElementById("qb-marquee-speed");
      this._els.progress = document.getElementById("qb-marquee-progress-fill");
      this._els.scroll = this.root && this.root.querySelector(".marquee-scroll");
    }

    _wireControls() {
      var self = this;
      if (this._els.speed) {
        this._els.speed.addEventListener("input", function () {
          self.setSpeed(Number(self._els.speed.value));
        });
      }
      if (this._els.scroll) {
        this._els.scroll.addEventListener("mouseenter", function () {
          if (self.isPlaying) self._pauseAnim();
        });
        this._els.scroll.addEventListener("mouseleave", function () {
          if (self.isPlaying) self._playAnim();
        });
      }
      document.addEventListener("keydown", function (e) {
        if (!self.root || self.root.offsetParent === null) return;
        if (e.code === "Space" && !/input|textarea/i.test(e.target.tagName)) {
          e.preventDefault();
          self.togglePlay();
        }
        if (e.code === "ArrowLeft") self.prevVerse();
        if (e.code === "ArrowRight") self.nextVerse();
      });
    }

    _createPanel() {
      var backdrop = document.createElement("div");
      backdrop.id = "qb-verse-panel-backdrop";
      backdrop.className = "q-verse-panel-backdrop";
      backdrop.hidden = true;
      backdrop.innerHTML =
        '<div class="q-verse-panel" role="dialog" aria-modal="true" aria-labelledby="qb-verse-panel-title">' +
        '<div class="q-verse-panel__header">' +
        '<span class="q-verse-panel__number" id="qb-verse-panel-title">Verse</span>' +
        '<button type="button" class="qb-modal-close" id="qb-verse-panel-close" aria-label="Close">×</button>' +
        "</div>" +
        '<div class="q-verse-panel__hindi" id="qb-verse-panel-hindi"></div>' +
        '<div class="q-verse-panel__english" id="qb-verse-panel-english" hidden></div>' +
        '<div class="q-verse-panel__context" id="qb-verse-panel-context"></div>' +
        '<div class="q-verse-panel__actions">' +
        '<button type="button" class="q-btn q-btn-ghost btn-sm" id="qb-verse-toggle-en">Show English</button>' +
        '<button type="button" class="q-btn q-btn-ghost btn-sm" id="qb-verse-copy">Copy</button>' +
        '<button type="button" class="q-btn q-btn-ghost btn-sm" id="qb-verse-share">Share</button>' +
        "</div></div>";
      document.body.appendChild(backdrop);
      this._els.backdrop = backdrop;
      var self = this;
      backdrop.addEventListener("click", function (e) {
        if (e.target === backdrop) self.closePanel();
      });
      document.getElementById("qb-verse-panel-close").addEventListener("click", function () {
        self.closePanel();
      });
      document.getElementById("qb-verse-toggle-en").addEventListener("click", function () {
        var en = document.getElementById("qb-verse-panel-english");
        var btn = document.getElementById("qb-verse-toggle-en");
        if (!en) return;
        var show = en.hidden;
        en.hidden = !show;
        btn.textContent = show ? "Hide English" : "Show English";
      });
      document.getElementById("qb-verse-copy").addEventListener("click", function () {
        var text = document.getElementById("qb-verse-panel-hindi");
        if (text && navigator.clipboard) {
          navigator.clipboard.writeText(text.textContent || "");
          if (window.qbToast) window.qbToast("Verse copied", "success");
        }
      });
      document.getElementById("qb-verse-share").addEventListener("click", function () {
        var text = document.getElementById("qb-verse-panel-hindi");
        var body = (text && text.textContent) || "";
        if (navigator.share) {
          navigator.share({ title: "Ramcharitmanas", text: body }).catch(function () {});
        } else if (navigator.clipboard) {
          navigator.clipboard.writeText(body);
          if (window.qbToast) window.qbToast("Verse copied for sharing", "info");
        }
      });
    }

    setVerses(verses) {
      this.verses = verses || [];
    }

    togglePlay() {
      this.isPlaying = !this.isPlaying;
      if (this.isPlaying) {
        this._playAnim();
        if (this._els.playBtn) this._els.playBtn.innerHTML = "&#10074;&#10074;";
      } else {
        this._pauseAnim();
        if (this._els.playBtn) this._els.playBtn.innerHTML = "&#9654;";
      }
    }

    _playAnim() {
      if (this._els.text) this._els.text.style.animationPlayState = "running";
      this._startProgress();
    }

    _pauseAnim() {
      if (this._els.text) this._els.text.style.animationPlayState = "paused";
      this._stopProgress();
    }

    setSpeed(value) {
      this.currentSpeed = value;
      var base = 45;
      var duration = base / (value * 0.35 + 0.5);
      if (this._els.text) {
        this._els.text.style.animationDuration = duration + "s";
      }
    }

    prevVerse() {
      if (!this.verses.length) return;
      this.currentVerseIndex = (this.currentVerseIndex - 1 + this.verses.length) % this.verses.length;
      this.highlightVerse(this.currentVerseIndex);
    }

    nextVerse() {
      if (!this.verses.length) return;
      this.currentVerseIndex = (this.currentVerseIndex + 1) % this.verses.length;
      this.highlightVerse(this.currentVerseIndex);
    }

    highlightVerse(index) {
      this.currentVerseIndex = index;
      var links = this.root && this.root.querySelectorAll(".marquee-verse");
      if (links) {
        links.forEach(function (el, i) {
          el.classList.toggle("is-active", i === index);
        });
      }
    }

    showVerseDetail(id) {
      var verse = this.verses.find(function (v, i) {
        return String(v.id) === String(id) || i === Number(id);
      });
      if (!verse) return;
      var title = document.getElementById("qb-verse-panel-title");
      var hi = document.getElementById("qb-verse-panel-hindi");
      var en = document.getElementById("qb-verse-panel-english");
      var ctx = document.getElementById("qb-verse-panel-context");
      if (title) title.textContent = verse.marker || "Verse " + (verse.id || "");
      if (hi) hi.textContent = verse.text || "";
      if (en) {
        en.textContent = verse.translation || verse.english || "";
        en.hidden = true;
      }
      if (ctx) {
        ctx.textContent =
          verse.context ||
          "From Ramcharitmanas by Goswami Tulsidas — a devotional epic narrating the life of Lord Rama.";
      }
      document.getElementById("qb-verse-toggle-en").textContent = "Show English";
      if (this._els.backdrop) this._els.backdrop.hidden = false;
    }

    closePanel() {
      if (this._els.backdrop) this._els.backdrop.hidden = true;
    }

    _startProgress() {
      var self = this;
      this._stopProgress();
      var start = performance.now();
      function tick(now) {
        if (!self._els.text || !self._els.progress) return;
        var dur = parseFloat(getComputedStyle(self._els.text).animationDuration) * 1000 || 30000;
        var elapsed = (now - start) % dur;
        self._els.progress.style.width = (elapsed / dur) * 100 + "%";
        self._progressRAF = requestAnimationFrame(tick);
      }
      this._progressRAF = requestAnimationFrame(tick);
    }

    _stopProgress() {
      if (this._progressRAF) cancelAnimationFrame(this._progressRAF);
      this._progressRAF = null;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("qb-marquee");
    if (!root) return;
    var sm = new SpiritualMarquee(root);
    window.QumanitySpiritualMarquee = sm;
    sm.setSpeed(3);
    fetch("/static/poems.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var poems = Array.isArray(data) ? data : (data.poems || []);
        sm.setVerses(poems);
      })
      .catch(function () {});
    root.addEventListener("click", function (e) {
      var verse = e.target.closest(".marquee-verse");
      if (verse && verse.dataset.verseId != null) {
        sm.showVerseDetail(verse.dataset.verseId);
      }
    });
  });
})();
