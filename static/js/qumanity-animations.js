/**
 * Qumanity.in — Homepage & About redesign animations
 * Scroll reveals, counters, karma ticker, loader, navbar, elections tabs
 */
(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── Page loader (2s chakra spin) ── */
  function initLoader() {
    var loader = document.getElementById("qb-page-loader");
    if (!loader || sessionStorage.getItem("qb_loader_seen")) {
      if (loader) loader.remove();
      document.body.classList.remove("qb-loading");
      return;
    }
    document.body.classList.add("qb-loading");
    setTimeout(function () {
      loader.classList.add("is-done");
      document.body.classList.remove("qb-loading");
      sessionStorage.setItem("qb_loader_seen", "1");
      setTimeout(function () {
        loader.remove();
      }, 500);
    }, 2000);
  }

  /* ── Navbar glass + shrink on scroll ── */
  function initNavbar() {
    var header = document.querySelector(".qb-navbar");
    if (!header) return;
    var onScroll = function () {
      header.classList.toggle("qb-navbar--scrolled", window.scrollY > 24);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ── Chakra hover speed boost ── */
  function initChakraHover() {
    document.querySelectorAll(".logo-chakra-spin, .logo-chakra").forEach(function (el) {
      var parent = el.closest(".qb-chakra-logo__stage, .qb-chakra-logo, .qb-chakra-brand");
      if (!parent) return;
      parent.addEventListener("mouseenter", function () {
        el.style.animationDuration = "2s";
        clearTimeout(el._hoverTimer);
        el._hoverTimer = setTimeout(function () {
          el.style.animationDuration = "";
        }, 3000);
      });
    });
  }

  /* ── Scroll reveal (Intersection Observer) ── */
  function initReveal() {
    if (prefersReducedMotion) {
      document.querySelectorAll(".qr-reveal").forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    document.querySelectorAll(".qr-reveal").forEach(function (el) {
      observer.observe(el);
    });
  }

  /* ── Animated counters ── */
  function animateCounter(el) {
    var target = parseFloat(el.dataset.count || "0");
    var suffix = el.dataset.suffix || "";
    var prefix = el.dataset.prefix || "";
    var isInfinity = el.dataset.infinity === "true";
    if (isInfinity) {
      el.textContent = "∞";
      return;
    }
    var duration = 1800;
    var start = performance.now();
    function tick(now) {
      var t = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - t, 3);
      var val = Math.floor(target * eased);
      el.textContent = prefix + val.toLocaleString("en-IN") + suffix;
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function initCounters() {
    var counters = document.querySelectorAll("[data-count]");
    if (!counters.length) return;
    var obs = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            animateCounter(entry.target);
            obs.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );
    counters.forEach(function (el) {
      obs.observe(el);
    });
  }

  /* ── Elections tabs ── */
  function initElectionTabs() {
    var tabs = document.querySelectorAll("[data-election-tab]");
    var panels = document.querySelectorAll("[data-election-panel]");
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var id = tab.dataset.electionTab;
        tabs.forEach(function (t) {
          t.classList.toggle("is-active", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        panels.forEach(function (p) {
          var show = p.dataset.electionPanel === id;
          p.hidden = !show;
          p.classList.toggle("is-active", show);
        });
      });
    });
  }

  /* ── Timeline tab panels ── */
  function initTimelineSpy() {
    var items = document.querySelectorAll("[data-timeline-item]");
    var navBtns = document.querySelectorAll("[data-timeline-nav]");
    if (!items.length || !navBtns.length) return;

    function activate(id) {
      navBtns.forEach(function (btn) {
        var on = btn.dataset.timelineNav === id;
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
      items.forEach(function (item) {
        var on = item.id === id;
        item.classList.toggle("is-active", on);
        item.hidden = !on;
      });
    }

    navBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activate(btn.dataset.timelineNav);
      });
    });
    activate(navBtns[0].dataset.timelineNav);
  }

  /* ── Karma ledger ticker ── */
  var KARMA_TICKS = [
    "Sunita R. reported verified issue in Lucknow → ₹5 Karma",
    "Priya S. taught 2 hours in Rohini → ₹40 Karma",
    "Anil K. served on Village Council in Pune → ₹50 Karma",
    "Meera D. helped an elder in Kochi → ₹15 Karma",
    "Vikram S. cleaned village square in Jaipur → ₹10 Karma",
    "Arjun P. planted a tree in Bawana → ₹10 Karma",
  ];

  function initKarmaTicker() {
    var track = document.getElementById("qr-karma-ticker");
    if (!track) return;
    var idx = 0;
    function showNext() {
      track.classList.remove("is-visible");
      setTimeout(function () {
        track.textContent = KARMA_TICKS[idx % KARMA_TICKS.length];
        track.classList.add("is-visible");
        idx += 1;
      }, 400);
    }
    showNext();
    setInterval(showNext, 4000);
  }

  /* ── Hero particle canvas ── */
  function initParticles() {
    var canvas = document.getElementById("qr-hero-particles");
    if (!canvas || prefersReducedMotion) return;
    var ctx = canvas.getContext("2d");
    var particles = [];
    var count = 48;

    function resize() {
      canvas.width = canvas.offsetWidth * devicePixelRatio;
      canvas.height = canvas.offsetHeight * devicePixelRatio;
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    }

    function makeParticle() {
      return {
        x: Math.random() * canvas.offsetWidth,
        y: Math.random() * canvas.offsetHeight,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: 1 + Math.random() * 1.5,
      };
    }

    function init() {
      resize();
      particles = [];
      for (var i = 0; i < count; i++) particles.push(makeParticle());
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.offsetWidth, canvas.offsetHeight);
      particles.forEach(function (p, i) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > canvas.offsetWidth) p.vx *= -1;
        if (p.y < 0 || p.y > canvas.offsetHeight) p.vy *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255, 215, 0, 0.35)";
        ctx.fill();
        for (var j = i + 1; j < particles.length; j++) {
          var q = particles[j];
          var dx = p.x - q.x;
          var dy = p.y - q.y;
          var dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.strokeStyle = "rgba(255, 153, 51, " + (1 - dist / 120) * 0.2 + ")";
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
      });
      requestAnimationFrame(draw);
    }

    init();
    draw();
    window.addEventListener("resize", init);
  }

  /* ── Vision video lightbox ── */
  function initVideoLightbox() {
    var btn = document.getElementById("qr-watch-vision");
    var modal = document.getElementById("qr-video-modal");
    if (!btn || !modal) return;
    var close = modal.querySelector("[data-close-modal]");
    btn.addEventListener("click", function () {
      modal.hidden = false;
      document.body.style.overflow = "hidden";
    });
    function shut() {
      modal.hidden = true;
      document.body.style.overflow = "";
    }
    if (close) close.addEventListener("click", shut);
    modal.addEventListener("click", function (e) {
      if (e.target === modal) shut();
    });
  }

  /* ── 3D pillar tilt ── */
  function initPillarTilt() {
    if (prefersReducedMotion) return;
    document.querySelectorAll(".qr-pillar-card").forEach(function (card) {
      card.addEventListener("mousemove", function (e) {
        var rect = card.getBoundingClientRect();
        var x = (e.clientX - rect.left) / rect.width - 0.5;
        var y = (e.clientY - rect.top) / rect.height - 0.5;
        card.style.transform =
          "perspective(800px) rotateY(" + x * 8 + "deg) rotateX(" + -y * 8 + "deg)";
      });
      card.addEventListener("mouseleave", function () {
        card.style.transform = "";
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initLoader();
    initNavbar();
    initChakraHover();
    initReveal();
    initCounters();
    initElectionTabs();
    initTimelineSpy();
    initKarmaTicker();
    initParticles();
    initVideoLightbox();
    initPillarTilt();
  });
})();
