(function () {
  // Translation loading indicator. The global implementation lives in i18n.js
  // (loaded on every page); these delegate to it so dashboard code can show a
  // "Translating… please wait" overlay while a language change is in flight.
  function showTranslationLoader() {
    if (typeof window.showTranslationLoader === "function") {
      window.showTranslationLoader();
      return;
    }
    var el = document.getElementById("qb-translation-loader");
    if (el) el.hidden = false;
  }

  function hideTranslationLoader() {
    if (typeof window.hideTranslationLoader === "function") {
      window.hideTranslationLoader();
      return;
    }
    var el = document.getElementById("qb-translation-loader");
    if (el) el.hidden = true;
  }

  function text(el, value) {
    if (el) el.textContent = value;
  }

  function escHtml(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function escAttr(s) {
    return escHtml(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  /** Copy text to clipboard; show brief feedback on btn or feedbackEl. */
  function qbCopyText(textValue, feedbackEl) {
    var value = String(textValue || "");
    function showCopied() {
      if (!feedbackEl) return;
      feedbackEl.textContent = "Copied!";
      feedbackEl.hidden = false;
      window.setTimeout(function () {
        feedbackEl.hidden = true;
      }, 1800);
    }
    function fallbackCopy() {
      var ta = document.createElement("textarea");
      ta.value = value;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        showCopied();
      } catch (_e) {}
      document.body.removeChild(ta);
    }
    if (!value) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(showCopied).catch(fallbackCopy);
    } else {
      fallbackCopy();
    }
  }

  function qbInitCopyButtons(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-qb-copy-target]").forEach(function (btn) {
      if (btn.getAttribute("data-qb-copy-bound") === "1") return;
      btn.setAttribute("data-qb-copy-bound", "1");
      btn.addEventListener("click", function () {
        var targetId = btn.getAttribute("data-qb-copy-target");
        var target = targetId ? document.getElementById(targetId) : null;
        var value = target ? (target.textContent || target.value || "").trim() : "";
        var feedbackId = btn.getAttribute("data-qb-copy-feedback");
        var feedbackEl = feedbackId ? document.getElementById(feedbackId) : null;
        qbCopyText(value, feedbackEl);
      });
    });
  }

  window.QBCopyText = qbCopyText;
  window.QBInitCopyButtons = qbInitCopyButtons;

  /** Parse fetch responses safely — never assume JSON when the server returns HTML. */
  function fetchJson(url, options) {
    options = options || {};
    options.credentials = options.credentials || "same-origin";
    options.headers = Object.assign({ Accept: "application/json" }, options.headers || {});
    return fetch(url, options).then(function (r) {
      return r.text().then(function (text) {
        var ct = (r.headers.get("content-type") || "").toLowerCase();
        var body = null;
        var trimmed = (text || "").trim();
        if (
          trimmed &&
          (ct.indexOf("application/json") !== -1 ||
            trimmed.charAt(0) === "{" ||
            trimmed.charAt(0) === "[")
        ) {
          try {
            body = JSON.parse(trimmed);
          } catch (_parseErr) {
            throw new Error("Invalid JSON response (HTTP " + r.status + ")");
          }
        } else if (trimmed && trimmed.charAt(0) === "<") {
          throw new Error("Server returned HTML instead of JSON (HTTP " + r.status + ")");
        } else if (trimmed) {
          throw new Error(trimmed.slice(0, 160) || "Unexpected response");
        } else {
          body = {};
        }
        return { ok: r.ok, status: r.status, body: body, b: body };
      });
    });
  }

  function buildLocationStatsUrl(scope, locationId) {
    if (!scope || !locationId) return "#";
    return (
      "/location/" +
      scope +
      "/" +
      String(locationId)
        .split("/")
        .map(function (part) {
          return encodeURIComponent(part);
        })
        .join("/")
    );
  }

  var dashCfg = {
    userHierarchy: [],
    defaultVillageId: "",
    showPublicLocationStatistics: false,
    showGlobalEarthStatistics: false,
    showGlobalContinentStatistics: false,
    showGlobalZoneStatistics: false,
    showGlobalCountryStatistics: false,
    showGlobalLocationStatistics: false,
    postFormLocationId: "",
    quantumPunchVillageId: "",
    userContinentId: "",
    userContinentName: "",
    userCountryId: "",
    userCountryName: "",
    userShowZoneTab: false,
    showPublicAccount: true,
    commerceEnabled: false,
    isAdmin: false,
  };
  try {
    var cfgEl = document.getElementById("qb-dash-config-json");
    if (cfgEl && cfgEl.textContent) {
      dashCfg = JSON.parse(cfgEl.textContent);
    }
  } catch (_e) {}

  function loadAccountStatusBanner() {
    var bannerEl = document.getElementById("qb-account-status-banner");
    if (!bannerEl) return;
    fetch("/api/user/dashboard-status", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (b) {
        var status = String(b.account_status || "active");
        if (status === "active") {
          bannerEl.hidden = true;
          bannerEl.innerHTML = "";
          return;
        }
        bannerEl.hidden = false;
        if (status === "pending_verification") {
          bannerEl.className = "qb-account-status-banner qb-alert qb-alert-warning mb-3";
          bannerEl.innerHTML =
            "<strong>Account Pending Verification</strong>" +
            "<p class=" + '"small mb-1 mt-1"' + ">Your donation is being verified by our admin team.</p>" +
            (b.txn_reference
              ? "<p class=" +
                '"small mb-1"' +
                ">Transaction ID: <strong class=" +
                '"font-monospace"' +
                ">" +
                escHtml(b.txn_reference) +
                "</strong></p>"
              : "") +
            "<p class=" + '"small mb-0"' + ">You'll receive a notification once verified. Some features are limited.</p>";
        } else if (status === "verification_failed") {
          bannerEl.className = "qb-account-status-banner qb-alert qb-alert-error mb-3";
          bannerEl.innerHTML =
            "<strong>Verification Failed</strong>" +
            "<p class=" + '"small mb-1 mt-1"' + ">We couldn't verify your transaction.</p>" +
            (b.failure_reason
              ? "<p class=" +
                '"small mb-2"' +
                ">Reason: " +
                escHtml(b.failure_reason) +
                "</p>"
              : "") +
            "<div class=" +
            '"d-flex flex-wrap gap-2"' +
            ">" +
            "<button type=" +
            '"button"' +
            " class=" +
            '"qb-btn qb-btn-primary btn-sm"' +
            " id=" +
            '"qb-retry-donation-btn"' +
            ">Retry Payment</button>" +
            "<a href=" +
            '"mailto:support@qumanity.org"' +
            " class=" +
            '"qb-btn qb-btn-neutral btn-sm"' +
            ">Contact Support</a>" +
            "</div>";
          var retryBtn = document.getElementById("qb-retry-donation-btn");
          if (retryBtn) {
            retryBtn.addEventListener("click", showRetryDonationModal);
          }
        }
      })
      .catch(function () {});
  }

  function showRetryDonationModal() {
    var backdrop = document.createElement("div");
    backdrop.className = "qb-id-modal-backdrop";
    backdrop.innerHTML =
      "<div class=" +
      '"qb-id-modal"' +
      ">" +
      "<h2 class=" +
      '"h5 mb-2"' +
      ">Retry Donation</h2>" +
      "<p class=" +
      '"small mb-3"' +
      ">Choose how you want to activate your account.</p>" +
      "<button type=" +
      '"button"' +
      " class=" +
      '"qb-btn qb-btn-secondary btn-sm mb-2 w-100"' +
      " data-retry-zero>Zero Amount Donation (₹0)</button>" +
      "<button type=" +
      '"button"' +
      " class=" +
      '"qb-btn qb-btn-primary btn-sm w-100"' +
      " data-retry-pay>Pay Again via QR</button>" +
      "<button type=" +
      '"button"' +
      " class=" +
      '"qb-btn qb-btn-neutral btn-sm mt-2 w-100"' +
      " data-retry-close>Cancel</button>" +
      "</div>";
    document.body.appendChild(backdrop);
    backdrop.querySelector("[data-retry-close]").addEventListener("click", function () {
      backdrop.remove();
    });
    backdrop.querySelector("[data-retry-zero]").addEventListener("click", function () {
      backdrop.remove();
      if (window.qbToast) {
        window.qbToast(
          "Zero-amount activation requires admin approval. Contact support.",
          "info"
        );
      }
    });
    backdrop.querySelector("[data-retry-pay]").addEventListener("click", function () {
      backdrop.remove();
      fetch("/api/donation/retry", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ amount: 50 }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (b) {
          if (!b.success) throw new Error(b.error || "Retry failed");
          if (window.qbToast) {
            window.qbToast(
              "New donation started. Pay via QR and contact support with your txn reference.",
              "info"
            );
          }
          loadAccountStatusBanner();
        })
        .catch(function (err) {
          if (window.qbToast) window.qbToast(err.message || "Retry failed", "error");
        });
    });
  }

  loadAccountStatusBanner();

  /* preferredLanguage + uiStrings come from server on each full page load (no client cache). */
  var uiLang = String((dashCfg && dashCfg.preferredLanguage) || "en").toLowerCase();
  var uiS = (dashCfg && dashCfg.uiStrings) || {};

  function uiTr(key) {
    if (uiS && uiS[key]) return uiS[key];
    return key;
  }

  function uiTrLabel(enLabel) {
    var m = {
      Male: "male",
      Female: "female",
      Fire: "fire",
      Earth: "earth",
      Air: "air",
      Water: "water",
      Balak: "balak",
      Yuvak: "yuvak",
      Vridh: "vridh",
      Sanyas: "sanyas",
    };
    var k = m[enLabel];
    return k ? uiTr(k) : enLabel;
  }

  var fneMemberSnapshot = null;

  var FAMILY_SLOT_PRESET_REL = {
    paternal_grandfather: "Paternal GrandFather",
    paternal_grandmother: "Paternal GrandMother",
    maternal_grandfather: "Maternal GrandFather",
    maternal_grandmother: "Maternal GrandMother",
    father: "Father",
    mother: "Mother",
  };

  /** Nested relationship menu (display labels = stored values). */
  var RELATIONSHIP_NESTED_GROUPS = [
    { label: "GrandParents · Paternal", options: ["Paternal GrandFather", "Paternal GrandMother"] },
    { label: "GrandParents · Maternal", options: ["Maternal GrandFather", "Maternal GrandMother"] },
    {
      label: "Parents",
      options: ["Self", "Father", "Mother", "Spouse", "Spouse-Father", "Spouse-Mother"],
    },
    { label: "Siblings", options: ["Brother", "Sister"] },
    { label: "Children", options: ["Son", "Daughter"] },
    { label: "Grandchild", options: ["Grandson", "Granddaughter"] },
  ];

  function fillNestedRelationshipSelect(sel, opts) {
    opts = opts || {};
    var includeSelf = !!opts.includeSelf;
    var preset = opts.presetValue || "";
    if (!sel) return;
    var keep = preset || sel.value || "";
    sel.innerHTML = '<option value="">— Select relationship —</option>';
    RELATIONSHIP_NESTED_GROUPS.forEach(function (grp) {
      var og = document.createElement("optgroup");
      og.label = grp.label;
      (grp.options || []).forEach(function (val) {
        if (!includeSelf && val === "Self") return;
        var o = document.createElement("option");
        o.value = val;
        o.textContent = val;
        og.appendChild(o);
      });
      if (og.children.length) sel.appendChild(og);
    });
    if (keep && [].some.call(sel.options, function (opt) { return opt.value === keep; })) {
      sel.value = keep;
    } else {
      sel.value = "";
    }
  }

  var NUCLEAR_TREE_REL_OPTIONS = [
    "Father",
    "Mother",
    "Spouse",
    "Son",
    "Daughter",
    "Brother",
    "Sister",
    "Grandfather (Paternal)",
    "Grandfather (Maternal)",
    "Grandmother (Paternal)",
    "Grandmother (Maternal)",
  ];

  function fillNuclearTreeRelationshipSelect(sel, preset) {
    var keep = preset || (sel && sel.value) || "";
    if (!sel) return;
    sel.innerHTML = '<option value="">— Select relationship —</option>';
    NUCLEAR_TREE_REL_OPTIONS.forEach(function (val) {
      var o = document.createElement("option");
      o.value = val;
      o.textContent = val;
      sel.appendChild(o);
    });
    if (keep && [].some.call(sel.options, function (opt) { return opt.value === keep; })) {
      sel.value = keep;
    } else {
      sel.value = "";
    }
  }

  /* --- Advanced time box --- */
  var timePayload = null;
  var calMode = "gregorian";
  var dropdownOpen = false;

  try {
    calMode = localStorage.getItem("qbDashCalMode") || "gregorian";
  } catch (_e) {}

  function applyCalModeButtons() {
    document.querySelectorAll(".qb-segmented-btn").forEach(function (btn) {
      var m = btn.getAttribute("data-cal-mode");
      btn.classList.toggle("is-active", m === calMode);
    });
  }

  function renderTimebox() {
    var mainEl = document.getElementById("qb-timebox-line-main");
    var l2 = document.getElementById("qb-timebox-line2");
    var l3 = document.getElementById("qb-timebox-line3");
    if (!timePayload || !mainEl) return;

    var t = timePayload.time_hms || "";
    var dateU = timePayload.date_display_upper || "";

    if (calMode === "gregorian") {
      text(mainEl, dateU + "  " + t);
      text(
        l2,
        (timePayload.weekday_en || "") +
          "   ☉ " +
          (timePayload.sun_sign_tropical_en || "") +
          "   ☾ " +
          (timePayload.moon_sign_tropical_en || "")
      );
      text(l3, "");
      if (l3) l3.hidden = true;
    } else {
      var lm = timePayload.lunar_month_sa || "";
      var pk = timePayload.paksha_sa || "";
      var ti = timePayload.tithi_name_sa || "";
      text(
        mainEl,
        t +
          ", चन्द्रमासाः ☾ " +
          lm +
          " पक्षः-" +
          pk +
          " तिथि-" +
          ti
      );
      text(
        l2,
        (timePayload.weekday_sa || "") +
          ", राशयः ☉ " +
          (timePayload.sun_sign_sidereal_sa || "") +
          ", नक्षत्रम् ☆ " +
          (timePayload.moon_nakshatra_sa || "")
      );
      var vs = timePayload.vikram_samvat_sa || "";
      text(l3, vs);
      if (l3) l3.hidden = false;
    }

    var extra = document.getElementById("qb-timebox-extra");
    if (extra) extra.hidden = !dropdownOpen;
    var btn = document.getElementById("qb-timebox-dropdown-btn");
    if (btn) btn.setAttribute("aria-expanded", dropdownOpen ? "true" : "false");
  }

  function fetchAdvancedTime() {
    fetch("/api/advanced_time", { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error(x.body.error || "advanced_time failed");
        timePayload = x.body;
        applyCalModeButtons();
        renderTimebox();
      })
      .catch(function () {
        var mainEl = document.getElementById("qb-timebox-line-main");
        text(mainEl, "Time unavailable");
      });
  }

  document.querySelectorAll(".qb-segmented-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var m = btn.getAttribute("data-cal-mode");
      if (!m) return;
      calMode = m;
      try {
        localStorage.setItem("qbDashCalMode", calMode);
      } catch (_e) {}
      applyCalModeButtons();
      renderTimebox();
    });
  });

  var dropBtn = document.getElementById("qb-timebox-dropdown-btn");
  if (dropBtn) {
    dropBtn.addEventListener("click", function () {
      dropdownOpen = !dropdownOpen;
      renderTimebox();
    });
  }

  applyCalModeButtons();
  fetchAdvancedTime();
  setInterval(fetchAdvancedTime, 60 * 1000);

  /* --- Resizable sidebar --- */
  var shell = document.getElementById("qb-dash-shell");
  var rail = document.getElementById("qb-sidebar-rail");
  var resizer = document.getElementById("qb-dash-resizer");
  if (shell && rail && resizer) {
    try {
      var saved = localStorage.getItem("qbSidebarWidthPct");
      if (saved) {
        var p = parseFloat(saved);
        if (p >= 18 && p <= 50) {
          rail.style.width = p + "%";
          document.documentElement.style.setProperty("--qb-sidebar-width", p + "%");
        }
      }
    } catch (_e) {}

    var dragging = false;
    var startX = 0;
    var startW = 0;
    var shellW = 0;

    function clamp(n, lo, hi) {
      return Math.max(lo, Math.min(hi, n));
    }

    resizer.addEventListener("mousedown", function (e) {
      dragging = true;
      resizer.classList.add("is-dragging");
      startX = e.clientX;
      startW = rail.getBoundingClientRect().width;
      shellW = shell.getBoundingClientRect().width;
      e.preventDefault();
    });

    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      var dx = e.clientX - startX;
      var nw = clamp(startW + dx, shellW * 0.18, shellW * 0.5);
      var pct = (nw / shellW) * 100;
      rail.style.width = pct + "%";
      document.documentElement.style.setProperty("--qb-sidebar-width", pct + "%");
    });

    window.addEventListener("mouseup", function () {
      if (!dragging) return;
      dragging = false;
      resizer.classList.remove("is-dragging");
      try {
        var pct = (rail.getBoundingClientRect().width / shell.getBoundingClientRect().width) * 100;
        localStorage.setItem("qbSidebarWidthPct", String(Math.round(pct * 10) / 10));
      } catch (_e) {}
    });
  }

  /* --- Nav + explorers --- */
  var exPublic = document.getElementById("qb-explorer-public");
  var exGlobal = document.getElementById("qb-explorer-global");

  function setExplorerMode(mode) {
    if (exPublic) exPublic.hidden = mode !== "public";
    if (exGlobal) exGlobal.hidden = mode !== "global";
  }

  document.querySelectorAll(".qb-dash-nav-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var tab = btn.getAttribute("data-dash-tab");
      try {
        localStorage.setItem("qbDashTab", tab);
      } catch (_e) {}
      try {
        var u = new URL(window.location.href);
        u.searchParams.set("tab", tab);
        history.replaceState(null, "", u.toString());
      } catch (_e) {}
      document.querySelectorAll(".qb-dash-nav-btn").forEach(function (b) {
        var on = b === btn;
        b.classList.toggle("is-active", on);
        b.classList.toggle("active", on);
      });
      document.querySelectorAll(".qb-dash-panel").forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-dash-panel") !== tab;
      });
      if (tab === "public" || tab === "global") {
        setExplorerMode(tab);
        if (tab === "global") {
          initGlobalTreeOnce();
          loadGlobalPanel();
        }
      } else {
        if (exPublic) exPublic.hidden = true;
        if (exGlobal) exGlobal.hidden = true;
        if (tab === "personal") refreshPersonalData();
        if (tab === "private") {
          loadUserPrivateInfo();
          loadPrivateElectionAdminPanel();
        }
      }
      if (window.qbPlanetary && window.qbPlanetary.onMainTabChange) {
        window.qbPlanetary.onMainTabChange(tab);
      }
    });
  });

  var activeNav = document.querySelector(".qb-dash-nav-btn.is-active");
  if (activeNav) {
    var t0 = activeNav.getAttribute("data-dash-tab");
    document.querySelectorAll(".qb-dash-panel").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-dash-panel") !== t0;
    });
    if (t0 === "public" || t0 === "global") setExplorerMode(t0);
    if (t0 === "personal") refreshPersonalData();
    if (t0 === "private") {
      loadUserPrivateInfo();
      loadPrivateElectionAdminPanel();
    }
    if (t0 === "global") {
      initGlobalTreeOnce();
      loadGlobalPanel();
    }
  }

  /* --- Restore last active tab from URL (?tab=) or localStorage --- */
  (function restoreDashTab() {
    var want = null;
    try {
      want = new URL(window.location.href).searchParams.get("tab");
    } catch (_e) {}
    if (!want) {
      try {
        want = localStorage.getItem("qbDashTab");
      } catch (_e) {}
    }
    if (!want) return;
    var target = document.querySelector(
      '.qb-dash-nav-btn[data-dash-tab="' + want + '"]'
    );
    var current = document.querySelector(".qb-dash-nav-btn.is-active");
    if (target && target !== current) target.click();
  })();

  /* --- Row 4 element selector (visual highlight only for now) --- */
  (function elementRow() {
    var row = document.getElementById("qb-element-row");
    if (!row) return;
    var btns = row.querySelectorAll(".qb-element-btn");
    var LS_EL = "qbDashElement";
    function setActive(el) {
      btns.forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-element") === el);
      });
    }
    var stored = null;
    try {
      stored = localStorage.getItem(LS_EL);
    } catch (_e) {}
    setActive(stored || row.getAttribute("data-user-element") || "Fire");
    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        var el = b.getAttribute("data-element");
        setActive(el);
        try {
          localStorage.setItem(LS_EL, el);
        } catch (_e) {}
      });
    });
  })();

  function timeAgo(value) {
    if (!value) return "";
    var raw = String(value);
    if (raw.indexOf("T") === -1) raw = raw.replace(" ", "T") + "Z";
    var parsed = Date.parse(raw);
    if (isNaN(parsed)) return String(value);
    var seconds = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
    if (seconds < 60) return "just now";
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + "m ago";
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + "h ago";
    var days = Math.floor(hours / 24);
    if (days < 30) return days + "d ago";
    var months = Math.floor(days / 30);
    if (months < 12) return months + "mo ago";
    return Math.floor(months / 12) + "y ago";
  }

  var boardNames = {
    village: uiTr("collective_village_board"),
    tehsil: uiTr("collective_tehsil_board"),
    district: uiTr("collective_district_board"),
    state: uiTr("collective_state_board"),
    zone: uiTr("collective_zone_board"),
    country: uiTr("collective_country_board"),
    continent: uiTr("collective_continent_board"),
    earth: uiTr("collective_earth_board"),
  };
  var activeBoardState = "live";
  var activeBoardScope = "village";
  var activeBoardLocationId = "";
  var activePersonalBoardState = "live";
  var selectedConnectionUser = null;
  var notificationItems = [];
  var notificationLinkRequests = [];

  function formatBoardDate(value) {
    if (!value) return "—";
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function voteButtonClass(vote, activeVote) {
    if (vote === 1) return activeVote === 1 ? "btn-success" : "btn-outline-success";
    if (vote === -1) return activeVote === -1 ? "btn-danger" : "btn-outline-danger";
    return activeVote === 0 ? "btn-secondary" : "btn-outline-secondary";
  }

  function voteCountsHtml(p) {
    return (
      '<div class="qb-board-vote-counts" aria-label="Vote counts">' +
      '<strong>Total Score: <span class="js-qb-post-score" data-post-id="' +
      escHtml(String(p.id)) +
      '">' +
      escHtml(String(p.total_score == null ? 0 : p.total_score)) +
      "</span></strong>" +
      "</div>"
    );
  }

  function progressHtml(p, boardState) {
    var progress = p.progress || {};
    var pct = Math.max(0, Math.min(100, parseFloat(progress.percent || 0)));
    var remaining =
      boardState === "live"
        ? escHtml(String(progress.remaining_days == null ? 0 : progress.remaining_days)) + " day(s) left"
        : "Completed at this level";
    return (
      '<div class="qb-board-progress">' +
      '<div class="qb-board-progress-meta">' +
      "<span>Start: " +
      escHtml(formatBoardDate(progress.start_date)) +
      "</span>" +
      "<span>End: " +
      escHtml(formatBoardDate(progress.end_date)) +
      "</span>" +
      "</div>" +
      '<div class="qb-board-progress-track" aria-label="Level progress">' +
      '<span class="qb-board-progress-fill" style="width: ' +
      pct +
      '%"></span>' +
      '<span class="qb-board-progress-needle" style="left: ' +
      pct +
      '%"></span>' +
      "</div>" +
      '<div class="qb-board-progress-foot"><span>' +
      escHtml(String(pct)) +
      "%</span><span>" +
      remaining +
      "</span></div>" +
      "</div>"
    );
  }

  function frozenMetaHtml(p) {
    var progress = p.progress || {};
    var label = p.escalation_label || "Frozen";
    return (
      '<div class="qb-board-frozen-meta">' +
      '<span class="badge bg-info text-dark">' +
      escHtml(label) +
      "</span>" +
      '<div class="qb-board-frozen-dates text-muted small mt-1">' +
      "<span>Live: " +
      escHtml(formatBoardDate(progress.start_date || p.level_start_time)) +
      " – " +
      escHtml(formatBoardDate(progress.end_date || p.level_end_time)) +
      "</span>" +
      "</div>" +
      "</div>"
    );
  }

  function renderPreviousPost(p) {
    var li = document.createElement("li");
    li.className = "qb-board-post qb-my-post-previous";
    li.innerHTML =
      '<article class="qb-board-post-card">' +
      '<header class="qb-board-post-head">' +
      '<span class="qb-board-post-time">' +
      escHtml(formatBoardDate(p.level_end_time || p.created_at)) +
      "</span>" +
      '<span class="badge bg-secondary ms-2">' +
      escHtml(p.archive_label || "Previous post") +
      "</span>" +
      "</header>" +
      '<p class="qb-board-post-content">' +
      escHtml(p.content || "") +
      "</p>" +
      '<div class="qb-board-vote-row">' +
      voteCountsHtml(p) +
      "</div>" +
      "</article>";
    return li;
  }

  function renderPost(p, boardState) {
    var li = document.createElement("li");
    li.className = "qb-board-post";
    li.setAttribute("data-post-id", String(p.id));
    var pid = escHtml(String(p.id));
    var currentVote = p.current_user_vote;
    var voteHint = p.is_own_post
      ? '<span class="qb-board-vote-note">Your post</span>'
      : p.has_voted
        ? '<span class="qb-board-vote-note">You have voted</span>'
        : "";
    var voteControls = "";
    if (boardState === "live") {
      var buttons = "";
      if (p.can_vote && !p.has_voted) {
        buttons =
          '<div class="btn-group btn-group-sm" role="group" aria-label="Vote on post">' +
          '<button type="button" class="btn ' +
          voteButtonClass(1, currentVote) +
          ' js-qb-vote" data-post-id="' +
          pid +
          '" data-vote="1">+1</button>' +
          '<button type="button" class="btn ' +
          voteButtonClass(0, currentVote) +
          ' js-qb-vote" data-post-id="' +
          pid +
          '" data-vote="0">0</button>' +
          '<button type="button" class="btn ' +
          voteButtonClass(-1, currentVote) +
          ' js-qb-vote" data-post-id="' +
          pid +
          '" data-vote="-1">-1</button>' +
          "</div>";
      }
      voteControls =
        '<div class="qb-board-vote-row">' +
        buttons +
        voteCountsHtml(p) +
        voteHint +
        "</div>";
    } else {
      voteControls = '<div class="qb-board-vote-row">' + voteCountsHtml(p) + "</div>";
    }
    var deleteBtn = "";
    if (boardState === "live") {
      if (p.can_author_delete) {
        deleteBtn =
          '<button type="button" class="qb-post-delete-btn qb-js-post-delete" ' +
          'data-post-id="' +
          pid +
          '" data-mode="author" title="Delete your post (within 24 hours)">' +
          "Delete</button>";
      } else if (p.can_admin_delete) {
        deleteBtn =
          '<button type="button" class="qb-post-delete-btn qb-post-delete-btn--admin qb-js-post-delete" ' +
          'data-post-id="' +
          pid +
          '" data-mode="admin" title="Delete this post (admin)">' +
          "Delete (Admin)</button>";
      }
    }
    var bodyExtra =
      boardState === "frozen"
        ? frozenMetaHtml(p)
        : progressHtml(p, boardState);
    li.innerHTML =
      '<article class="qb-board-post-card">' +
      '<header class="qb-board-post-head">' +
      '<button type="button" class="qb-board-author js-qb-author" data-author-private-id="' +
      escAttr(p.author_private_id || "") +
      '" data-author-name="' +
      escAttr(p.author_full_name || p.author_display_name || "") +
      '" data-author-age="' +
      escAttr(p.author_age == null ? "" : p.author_age) +
      '" data-author-gender="' +
      escAttr(p.author_gender || "") +
      '" data-author-location="' +
      escAttr(p.author_location_name || "") +
      '">' +
      escHtml(p.author_display_name || [p.author_first, p.author_last].filter(Boolean).join(" ")) +
      "</button>" +
      '<span class="qb-board-post-time">' +
      escHtml(timeAgo(p.created_at)) +
      " · " +
      escHtml(formatBoardDate(p.created_at)) +
      "</span>" +
      deleteBtn +
      "</header>" +
      '<p class="qb-board-post-content">' +
      escHtml(p.content) +
      "</p>" +
      bodyExtra +
      voteControls +
      "</article>";
    return li;
  }

  function setBoardHeading(scope) {
    var title = document.getElementById("qb-collective-board-title");
    var subtitle = document.getElementById("qb-collective-board-subtitle");
    if (title) text(title, boardNames[scope] || "Collective Board");
    if (subtitle) {
      text(
        subtitle,
        activeBoardState === "live"
          ? uiTr("board_subtitle_live_voting")
          : uiTr("board_subtitle_frozen")
      );
    }
  }

  function updatePostFormVisibility() {
    var btn = document.getElementById("qb-new-post-open");
    if (!btn) return;
    btn.hidden = false;
  }

  function prependPost(p) {
    var ul = document.getElementById("qb-personal-feed");
    var empty = document.getElementById("qb-personal-feed-empty");
    if (!ul || !p) return;
    if (empty) empty.hidden = true;
    ul.insertBefore(renderPost(p, "live"), ul.firstChild);
  }

  function loadPersonalBoard() {
    var ul = document.getElementById("qb-personal-feed");
    var empty = document.getElementById("qb-personal-feed-empty");
    if (!ul) return;
    fetchJson("/api/personal_board?state=" + encodeURIComponent(activePersonalBoardState))
      .then(function (x) {
        if (!x.ok) throw new Error(x.body.error || "personal board failed");
        var posts = x.body.posts || [];
        ul.innerHTML = "";
        if (!posts.length) {
          if (empty) {
            empty.hidden = false;
            text(empty, activePersonalBoardState === "live" ? "No live personal posts yet." : "No frozen personal posts yet.");
          }
          return;
        }
        if (empty) empty.hidden = true;
        posts.forEach(function (p) {
          ul.appendChild(renderPost(p, activePersonalBoardState));
        });
      })
      .catch(function (err) {
        ul.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          text(empty, err.message || "Could not load Personal Collective Board posts.");
        }
        console.error("PCB load failed:", err);
      });
  }

  function setPersonalAccountView(view) {
    view = view || "pcb";
    var pcb = document.getElementById("qb-personal-stack-pcb");
    var fam = document.getElementById("qb-personal-stack-family");
    var soc = document.getElementById("qb-personal-stack-social");
    if (pcb) pcb.hidden = view !== "pcb";
    if (fam) fam.hidden = view !== "family";
    if (soc) soc.hidden = view !== "social";
    if (view === "pcb") {
      loadPersonalBoard();
    } else if (view === "family") {
      loadConnections("family");
    } else if (view === "social") {
      loadConnections("social");
    }
  }

  var openFamBtn = document.getElementById("qb-open-family-tree-btn");
  if (openFamBtn) {
    openFamBtn.addEventListener("click", function () {
      setPersonalAccountView("family");
    });
  }
  var openSocBtn = document.getElementById("qb-open-social-circle-btn");
  if (openSocBtn) {
    openSocBtn.addEventListener("click", function () {
      setPersonalAccountView("social");
    });
  }
  var backPcbFam = document.getElementById("qb-back-to-pcb-from-family");
  if (backPcbFam) {
    backPcbFam.addEventListener("click", function () {
      setPersonalAccountView("pcb");
    });
  }
  var backPcbSoc = document.getElementById("qb-back-to-pcb-from-social");
  if (backPcbSoc) {
    backPcbSoc.addEventListener("click", function () {
      setPersonalAccountView("pcb");
    });
  }

  function connectionTypeLabel(type) {
    return type === "family" ? "Family member" : "Social Circle";
  }

  function renderConnectionItem(item, opts) {
    opts = opts || {};
    var li = document.createElement("li");
    li.className = "qb-connection-row";
    var rel = item.relationship ? " · " + item.relationship : "";
    var actions = "";
    if (opts.removable) {
      actions =
        '<div class="qb-connection-row-actions mt-1">' +
        '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-social-remove" data-request-id="' +
        escAttr(String(item.id || item.request_id || "")) +
        '">Remove</button>' +
        "</div>";
    }
    li.innerHTML =
      '<div><strong>' +
      escHtml(item.name || item.member_name || "") +
      "</strong> <span class='font-monospace text-muted'>" +
      escHtml(item.public_id || item.account_public_id || "") +
      "</span><span class='qb-rel-tag'>" +
      escHtml(rel) +
      "</span></div>" +
      '<div class="text-muted">' +
      escHtml([item.age ? "Age " + item.age : "", item.gender || "", item.location_name || ""].filter(Boolean).join(" · ")) +
      "</div>" +
      actions;
    return li;
  }

  /* --- Family form / tree / list --- */

  var familyProfileState = {
    form_completed: false,
    relationship_status: "",
    form_data: {},
  };
  function familyFlash(msg, kind) {
    var el = document.getElementById("qb-family-flash");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.remove("text-info", "text-danger", "text-success");
    el.classList.add(kind === "error" ? "text-danger" : kind === "ok" ? "text-success" : "text-info");
  }

  function makeSiblingRow(values) {
    values = values || {};
    var row = document.createElement("div");
    row.className = "qb-family-dynamic-row";
    row.innerHTML =
      '<input type="text" class="form-control form-control-sm" placeholder="Name" data-family-key="name" />' +
      '<select class="form-select form-select-sm" data-family-key="gender">' +
      '<option value="">Gender</option>' +
      '<option value="Male">Male</option>' +
      '<option value="Female">Female</option>' +
      "</select>" +
      '<input type="number" min="0" class="form-control form-control-sm" placeholder="Age" data-family-key="age" />' +
      '<select class="form-select form-select-sm" data-family-key="age_modifier">' +
      '<option value="">Older / Younger</option>' +
      '<option value="older">Older</option>' +
      '<option value="younger">Younger</option>' +
      "</select>" +
      '<label class="qb-family-inline-check"><input type="checkbox" data-family-key="is_dead" /> Deceased</label>' +
      '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-family-remove-row">×</button>';
    Object.keys(values).forEach(function (k) {
      var el = row.querySelector('[data-family-key="' + k + '"]');
      if (!el) return;
      if (el.type === "checkbox") el.checked = !!values[k];
      else el.value = values[k] == null ? "" : String(values[k]);
    });
    return row;
  }

  function makeGrandchildRow(values) {
    values = values || {};
    var row = document.createElement("div");
    row.className = "qb-family-dynamic-row qb-family-grandchild-row";
    row.innerHTML =
      '<input type="text" class="form-control form-control-sm" placeholder="Grandchild name" data-grandchild-key="name" />' +
      '<select class="form-select form-select-sm" data-grandchild-key="gender">' +
      '<option value="">Gender</option>' +
      '<option value="Male">Male</option>' +
      '<option value="Female">Female</option>' +
      "</select>" +
      '<input type="number" min="0" class="form-control form-control-sm" placeholder="Age" data-grandchild-key="age" />' +
      '<label class="qb-family-inline-check"><input type="checkbox" data-grandchild-key="is_dead" /> Deceased</label>' +
      '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-family-remove-grandchild">×</button>';
    Object.keys(values).forEach(function (k) {
      var el = row.querySelector('[data-grandchild-key="' + k + '"]');
      if (!el) return;
      if (el.type === "checkbox") el.checked = !!values[k];
      else el.value = values[k] == null ? "" : String(values[k]);
    });
    return row;
  }

  function makeChildRow(values) {
    values = values || {};
    var row = document.createElement("div");
    row.className = "qb-family-dynamic-block";
    row.innerHTML =
      '<div class="qb-family-dynamic-row">' +
      '<input type="text" class="form-control form-control-sm" placeholder="Child name" data-family-key="name" />' +
      '<select class="form-select form-select-sm" data-family-key="gender">' +
      '<option value="">Gender</option>' +
      '<option value="Male">Male</option>' +
      '<option value="Female">Female</option>' +
      "</select>" +
      '<input type="number" min="0" class="form-control form-control-sm" placeholder="Age" data-family-key="age" />' +
      '<label class="qb-family-inline-check"><input type="checkbox" data-family-key="is_dead" /> Deceased</label>' +
      '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-family-remove-row" title="Remove child">×</button>' +
      "</div>" +
      '<div class="qb-family-subrow qb-family-child-married-toggle">' +
      '<span class="small text-muted me-2">Is this child married?</span>' +
      '<label class="qb-family-inline-check"><input type="radio" data-child-married="no" checked /> No</label>' +
      '<label class="qb-family-inline-check"><input type="radio" data-child-married="yes" /> Yes</label>' +
      "</div>" +
      '<div class="qb-family-subrow qb-family-child-spouse" hidden>' +
      '<input type="text" class="form-control form-control-sm" placeholder="Spouse name" data-child-spouse-key="name" />' +
      '<select class="form-select form-select-sm" data-child-spouse-key="gender">' +
      '<option value="">Gender</option>' +
      '<option value="Male">Male</option>' +
      '<option value="Female">Female</option>' +
      "</select>" +
      '<input type="number" min="0" class="form-control form-control-sm" placeholder="Age" data-child-spouse-key="age" />' +
      '<label class="qb-family-inline-check"><input type="checkbox" data-child-spouse-key="is_dead" /> Deceased</label>' +
      "</div>" +
      '<div class="qb-family-subgroup">' +
      '<div class="d-flex justify-content-between align-items-center mb-1">' +
      '<span class="small text-muted">Grandchildren (children of this child)</span>' +
      '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-family-add-grandchild">+ Add grandchild</button>' +
      "</div>" +
      '<div class="qb-family-grandchildren"></div>' +
      "</div>";

    // Hook up married toggle and grandchild button on this child block.
    var marriedRadios = row.querySelectorAll("[data-child-married]");
    var spouseBox = row.querySelector(".qb-family-child-spouse");
    function applyMarriedState() {
      var yes = false;
      marriedRadios.forEach(function (rb) {
        if (rb.checked && rb.getAttribute("data-child-married") === "yes") yes = true;
      });
      if (spouseBox) spouseBox.hidden = !yes;
    }
    marriedRadios.forEach(function (rb) {
      rb.addEventListener("change", applyMarriedState);
    });

    var addGrandBtn = row.querySelector(".qb-js-family-add-grandchild");
    var grandBox = row.querySelector(".qb-family-grandchildren");
    if (addGrandBtn && grandBox) {
      addGrandBtn.addEventListener("click", function () {
        grandBox.appendChild(makeGrandchildRow());
      });
    }
    row.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".qb-js-family-remove-grandchild");
      if (!btn) return;
      var rowEl = btn.closest(".qb-family-grandchild-row");
      if (rowEl) rowEl.remove();
    });

    // Initial fill if we ever rehydrate from a saved blob (admin reset case).
    Object.keys(values).forEach(function (k) {
      if (k === "spouse" || k === "grandchildren" || k === "is_married") return;
      var el = row.querySelector('[data-family-key="' + k + '"]');
      if (!el) return;
      if (el.type === "checkbox") el.checked = !!values[k];
      else el.value = values[k] == null ? "" : String(values[k]);
    });
    if (values.is_married) {
      marriedRadios.forEach(function (rb) {
        rb.checked = rb.getAttribute("data-child-married") === "yes";
      });
      applyMarriedState();
    }
    if (values.spouse) {
      Object.keys(values.spouse).forEach(function (k) {
        var el = row.querySelector('[data-child-spouse-key="' + k + '"]');
        if (!el) return;
        if (el.type === "checkbox") el.checked = !!values.spouse[k];
        else el.value = values.spouse[k] == null ? "" : String(values.spouse[k]);
      });
    }
    if (Array.isArray(values.grandchildren) && grandBox) {
      values.grandchildren.forEach(function (gc) {
        grandBox.appendChild(makeGrandchildRow(gc));
      });
    }
    return row;
  }

  function readDynamicRows(container) {
    var out = [];
    if (!container) return out;
    container.querySelectorAll(".qb-family-dynamic-row").forEach(function (row) {
      if (row.classList.contains("qb-family-grandchild-row")) return; // handled per-child
      var entry = {};
      row.querySelectorAll("[data-family-key]").forEach(function (el) {
        var k = el.getAttribute("data-family-key");
        if (el.type === "checkbox") entry[k] = el.checked;
        else entry[k] = el.value;
      });
      if ((entry.name || "").trim()) out.push(entry);
    });
    return out;
  }

  function readChildBlocks(container) {
    var out = [];
    if (!container) return out;
    container.querySelectorAll(".qb-family-dynamic-block").forEach(function (block) {
      var entry = {};
      block.querySelectorAll("[data-family-key]").forEach(function (el) {
        var k = el.getAttribute("data-family-key");
        if (el.type === "checkbox") entry[k] = el.checked;
        else entry[k] = el.value;
      });
      if (!(entry.name || "").trim()) return;
      var marriedYes = false;
      block.querySelectorAll("[data-child-married]").forEach(function (rb) {
        if (rb.checked && rb.getAttribute("data-child-married") === "yes") {
          marriedYes = true;
        }
      });
      entry.is_married = marriedYes;
      if (marriedYes) {
        var spouse = {};
        block.querySelectorAll("[data-child-spouse-key]").forEach(function (el) {
          var k = el.getAttribute("data-child-spouse-key");
          if (el.type === "checkbox") spouse[k] = el.checked;
          else spouse[k] = el.value;
        });
        if ((spouse.name || "").trim()) entry.spouse = spouse;
      }
      var grand = [];
      var grandBox = block.querySelector(".qb-family-grandchildren");
      if (grandBox) {
        grandBox.querySelectorAll(".qb-family-grandchild-row").forEach(function (gr) {
          var g = {};
          gr.querySelectorAll("[data-grandchild-key]").forEach(function (el) {
            var k = el.getAttribute("data-grandchild-key");
            if (el.type === "checkbox") g[k] = el.checked;
            else g[k] = el.value;
          });
          if ((g.name || "").trim()) grand.push(g);
        });
      }
      entry.grandchildren = grand;
      out.push(entry);
    });
    return out;
  }

  function setSimpleField(form, key, value) {
    var el = form.querySelector('[data-family-field="' + key + '"]');
    if (!el) return;
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value == null ? "" : String(value);
  }

  function readSimpleField(form, key) {
    var el = form.querySelector('[data-family-field="' + key + '"]');
    if (!el) return "";
    if (el.type === "checkbox") return el.checked;
    return el.value || "";
  }

  function updateFamilyFormFieldsForStatus(status) {
    var spouseFs = document.getElementById("qb-family-spouse-fieldset");
    var spouseParents = document.getElementById(
      "qb-family-spouse-parents-fieldset"
    );
    var hasKidsFs = document.getElementById("qb-family-has-children-fieldset");
    var kidsFs = document.getElementById("qb-family-children-fieldset");

    if (spouseFs) spouseFs.hidden = status !== "married";
    if (spouseParents) {
      spouseParents.hidden = status !== "married" && status !== "single-parent";
    }
    var showHasChildren =
      status === "married" || status === "widowed" || status === "divorced";
    if (hasKidsFs) hasKidsFs.hidden = !showHasChildren;
    if (kidsFs) {
      if (status === "single-parent") {
        kidsFs.hidden = false;
      } else if (showHasChildren) {
        var yes = false;
        document
          .querySelectorAll('input[name="has_children"]')
          .forEach(function (r) {
            if (r.checked && r.value === "yes") yes = true;
          });
        kidsFs.hidden = !yes;
      } else {
        kidsFs.hidden = true;
      }
    }
  }

  function showFamilyTreeContent(show) {
    var content = document.getElementById("qb-family-content");
    if (content) content.hidden = !show;
  }

  function showFamilyInitialSetup(show) {
    var wrap = document.getElementById("qb-family-initial-setup-wrap");
    if (wrap) wrap.hidden = !show;
  }

  function showFamilyForm(showForm) {
    var formWrap = document.getElementById("qb-family-form-wrap");
    var optionsDetails = document.getElementById("qb-family-options-details");
    if (formWrap) formWrap.hidden = !showForm;
    if (optionsDetails) optionsDetails.hidden = true;
  }

  function loadFamilyProfile() {
    return fetchJson("/api/family/profile")
      .then(function (x) {
        if (!x.ok) throw new Error((x.body && x.body.error) || "family profile failed");
        familyProfileState = x.body || familyProfileState;
        var needs = !!familyProfileState.needs_initial_setup;
        if (needs) {
          showFamilyInitialSetup(true);
          showFamilyForm(false);
          showFamilyTreeContent(false);
          return;
        }
        showFamilyInitialSetup(false);
        showFamilyTreeContent(true);
        var initialDone = !!(familyProfileState.initial_setup && familyProfileState.initial_setup.completed);
        if (familyProfileState.form_completed || initialDone) {
          showFamilyForm(false);
          loadFamilyTree();
          loadFamilyAllMembers();
        } else {
          showFamilyForm(true);
          loadFamilyTree();
          var form = document.getElementById("qb-family-form");
          if (form) {
            updateFamilyFormFieldsForStatus(
              familyProfileState.relationship_status || "unmarried"
            );
            var radios = form.querySelectorAll('[name="relationship_status"]');
            radios.forEach(function (r) {
              r.checked = r.value === (familyProfileState.relationship_status || "unmarried");
            });
          }
        }
      })
      .catch(function (err) {
        familyFlash(err.message || "Could not load family profile", "error");
      });
  }

  function gatherFamilyForm() {
    var form = document.getElementById("qb-family-form");
    if (!form) return null;
    var status = "unmarried";
    var radios = form.querySelectorAll('[name="relationship_status"]');
    radios.forEach(function (r) {
      if (r.checked) status = r.value;
    });
    var siblings = readDynamicRows(document.getElementById("qb-family-siblings"));
    var children = readChildBlocks(
      document.getElementById("qb-family-children")
    );

    var hasChildren = false;
    if (status === "married" || status === "widowed" || status === "divorced") {
      form.querySelectorAll('input[name="has_children"]').forEach(function (r) {
        if (r.checked && r.value === "yes") hasChildren = true;
      });
    } else if (status === "single-parent") {
      hasChildren = true;
    }

    var spouse = {};
    var spouseFather = {};
    var spouseMother = {};
    if (status === "married") {
      spouse = {
        name: readSimpleField(form, "spouse.name"),
        gender: readSimpleField(form, "spouse.gender"),
        age: readSimpleField(form, "spouse.age"),
        is_dead: readSimpleField(form, "spouse.is_dead"),
      };
    }
    if (status === "married" || status === "single-parent") {
      spouseFather = {
        name: readSimpleField(form, "spouse_father.name"),
        is_dead: readSimpleField(form, "spouse_father.is_dead"),
      };
      spouseMother = {
        name: readSimpleField(form, "spouse_mother.name"),
        is_dead: readSimpleField(form, "spouse_mother.is_dead"),
      };
    }

    return {
      relationship_status: status,
      father: {
        name: readSimpleField(form, "father.name"),
        is_dead: readSimpleField(form, "father.is_dead"),
      },
      mother: {
        name: readSimpleField(form, "mother.name"),
        is_dead: readSimpleField(form, "mother.is_dead"),
      },
      siblings: siblings,
      spouse: spouse,
      spouse_father: spouseFather,
      spouse_mother: spouseMother,
      has_children: hasChildren,
      children: hasChildren ? children : [],
    };
  }

  function submitFamilyForm() {
    var payload = gatherFamilyForm();
    if (!payload) return;
    familyFlash("Saving family details…", "info");
    fetch("/api/family/submit_form", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "submit failed");
        familyFlash("Family details saved.", "ok");
        familyProfileState = x.b.profile || familyProfileState;
        showFamilyForm(false);
        loadFamilyTree();
        loadFamilyAllMembers();
      })
      .catch(function (err) {
        familyFlash(err.message || "Could not save form", "error");
      });
  }

  function syncIfsChildrenVisibility() {
    var fs = document.getElementById("qb-ifs-children-fieldset");
    var wrap = document.getElementById("qb-ifs-children-count-wrap");
    var rs = "unmarried";
    document.querySelectorAll('input[name="ifs_relationship_status"]').forEach(function (r) {
      if (r.checked) rs = r.value;
    });
    var show = rs === "married" || rs === "single-parent" || rs === "widowed";
    if (fs) fs.hidden = !show;
    if (!show) {
      document.querySelectorAll('input[name="ifs_has_children"]').forEach(function (r) {
        r.checked = r.value === "no";
      });
    }
    var hasCh = false;
    document.querySelectorAll('input[name="ifs_has_children"]').forEach(function (r) {
      if (r.checked && r.value === "yes") hasCh = true;
    });
    if (wrap) wrap.hidden = !show || !hasCh;
  }

  function renderIfsSiblingNameFields() {
    var container = document.getElementById("qb-ifs-sibling-name-fields");
    if (!container) return;
    var yes = false;
    document.querySelectorAll('input[name="ifs_has_siblings"]').forEach(function (r) {
      if (r.checked && r.value === "yes") yes = true;
    });
    if (!yes) {
      container.innerHTML = "";
      return;
    }
    var nb = parseInt((document.getElementById("qb-ifs-brothers") || {}).value || "0", 10);
    var ns = parseInt((document.getElementById("qb-ifs-sisters") || {}).value || "0", 10);
    if (isNaN(nb)) nb = 0;
    if (isNaN(ns)) ns = 0;
    nb = Math.max(0, Math.min(20, nb));
    ns = Math.max(0, Math.min(20, ns));
    var html = "";
    var i;
    for (i = 0; i < nb; i++) {
      html +=
        '<div class="mb-2"><label class="form-label small" for="qb-ifs-bro-name-' +
        i +
        '">Brother ' +
        (i + 1) +
        " name (optional)</label>" +
        '<input type="text" class="form-control form-control-sm qb-ifs-bro-name" id="qb-ifs-bro-name-' +
        i +
        '" maxlength="160" /></div>';
    }
    for (i = 0; i < ns; i++) {
      html +=
        '<div class="mb-2"><label class="form-label small" for="qb-ifs-sis-name-' +
        i +
        '">Sister ' +
        (i + 1) +
        " name (optional)</label>" +
        '<input type="text" class="form-control form-control-sm qb-ifs-sis-name" id="qb-ifs-sis-name-' +
        i +
        '" maxlength="160" /></div>';
    }
    container.innerHTML = html;
  }

  function syncIfsSiblingsVisibility() {
    var wrap = document.getElementById("qb-ifs-siblings-count-wrap");
    if (!wrap) return;
    var yes = false;
    document.querySelectorAll('input[name="ifs_has_siblings"]').forEach(function (r) {
      if (r.checked && r.value === "yes") yes = true;
    });
    wrap.hidden = !yes;
    renderIfsSiblingNameFields();
  }

  document.querySelectorAll('input[name="ifs_relationship_status"]').forEach(function (r) {
    r.addEventListener("change", syncIfsChildrenVisibility);
  });
  document.querySelectorAll('input[name="ifs_has_children"]').forEach(function (r) {
    r.addEventListener("change", syncIfsChildrenVisibility);
  });
  document.querySelectorAll('input[name="ifs_has_siblings"]').forEach(function (r) {
    r.addEventListener("change", syncIfsSiblingsVisibility);
  });
  syncIfsChildrenVisibility();
  syncIfsSiblingsVisibility();
  var broInp = document.getElementById("qb-ifs-brothers");
  var sisInp = document.getElementById("qb-ifs-sisters");
  if (broInp) broInp.addEventListener("input", renderIfsSiblingNameFields);
  if (sisInp) sisInp.addEventListener("input", renderIfsSiblingNameFields);

  var ifsForm = document.getElementById("qb-family-initial-setup-form");
  if (ifsForm) {
    ifsForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var stEl = document.getElementById("qb-ifs-status");
      var rs = "unmarried";
      document.querySelectorAll('input[name="ifs_relationship_status"]').forEach(function (r) {
        if (r.checked) rs = r.value;
      });
      var hasCh = false;
      document.querySelectorAll('input[name="ifs_has_children"]').forEach(function (r) {
        if (r.checked && r.value === "yes") hasCh = true;
      });
      var nChild = parseInt((document.getElementById("qb-ifs-children-count") || {}).value || "0", 10);
      if (hasCh && (isNaN(nChild) || nChild < 1 || nChild > 10)) {
        text(stEl, "Enter number of children (1–10).");
        return;
      }
      var hasSib = false;
      document.querySelectorAll('input[name="ifs_has_siblings"]').forEach(function (r) {
        if (r.checked && r.value === "yes") hasSib = true;
      });
      var nBro = parseInt((document.getElementById("qb-ifs-brothers") || {}).value || "0", 10);
      var nSis = parseInt((document.getElementById("qb-ifs-sisters") || {}).value || "0", 10);
      var brother_names = [];
      var sister_names = [];
      var bi, si;
      for (bi = 0; bi < nBro; bi++) {
        var bel = document.getElementById("qb-ifs-bro-name-" + bi);
        brother_names.push(bel ? (bel.value || "").trim() : "");
      }
      for (si = 0; si < nSis; si++) {
        var seln = document.getElementById("qb-ifs-sis-name-" + si);
        sister_names.push(seln ? (seln.value || "").trim() : "");
      }
      if (hasSib && nBro + nSis < 1) {
        text(stEl, "Enter at least one brother or sister.");
        return;
      }
      text(stEl, "Saving…");
      fetch("/api/family/initial_setup", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          relationship_status: rs,
          has_children: hasCh,
          children_count: hasCh ? nChild : 0,
          father_name: ((document.getElementById("qb-ifs-father-name") || {}).value || "").trim(),
          mother_name: ((document.getElementById("qb-ifs-mother-name") || {}).value || "").trim(),
          has_siblings: hasSib,
          brothers_count: hasSib ? nBro : 0,
          sisters_count: hasSib ? nSis : 0,
          brother_names: hasSib ? brother_names : [],
          sister_names: hasSib ? sister_names : [],
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Setup failed");
          text(stEl, "");
          familyFlash("Family tree created.", "ok");
          loadFamilyProfile();
        })
        .catch(function (err) {
          text(stEl, err.message || "Could not save.");
        });
    });
  }

  var privateInfoLifeStage = "";
  var cachedEducation = null;
  var cachedWork = null;
  var selectedDonateAmount = 0;
  var selectedDonateMethod = "upi";
  var upiPaymentAcknowledged = false;

  var DONATION_PREVIEW = {
    1: "You receive: 1 Karma Point (₹1). Village: none.",
    2: "You receive: 1 Karma Point (₹1). Village: 1 Karma Point (₹1).",
    5: "You receive: 2 Karma Points (₹2 each). Village: 1 Karma Point (₹1).",
    10: "You receive: 3 Karma Points (₹5, ₹3, ₹1). Village: 1 Karma Point (₹2).",
    20: "You receive: 3 Karma Points (₹5 each). Village: 1 Karma Point (₹5).",
    50: "You receive: 2 Karma Points (₹20 each). Village: 1 Karma Point (₹10).",
    100: "You receive: 3 Karma Points (₹50, ₹20, ₹10). Village: 1 Karma Point (₹20).",
    200: "You receive: 2 Karma Points (₹100, ₹50). Village: 1 Karma Point (₹50).",
    500: "You receive: 2 Karma Points (₹200 each). Village: 1 Karma Point (₹100).",
  };

  function educationHasData(edu) {
    if (!edu) return false;
    var lvl = (edu.education_level || "Uneducated").trim();
    if (lvl === "School" || lvl === "College") return true;
    return false;
  }

  function workHasData(wrk) {
    if (!wrk) return false;
    return !!(wrk.work_status && wrk.work_status !== "Unemployed") || !!(wrk.unemployed_sub || "").trim();
  }

  function renderEducationView(edu) {
    var view = document.getElementById("qb-edu-view");
    var actions = document.getElementById("qb-edu-view-actions");
    var form = document.getElementById("qb-private-education-form");
    if (!view) return;
    edu = edu || {};
    var lvl = edu.education_level || "Uneducated";
    var html = "<p class='mb-1'><strong>Level:</strong> " + escHtml(lvl) + "</p>";
    if (lvl === "School") {
      html +=
        "<p class='mb-1'><strong>Class passed:</strong> " +
        escHtml(edu.school_class_passed || "—") +
        "</p>" +
        "<p class='mb-1'><strong>Year:</strong> " +
        escHtml(edu.school_year != null ? String(edu.school_year) : "—") +
        "</p>" +
        "<p class='mb-0'><strong>Institution:</strong> " +
        escHtml(edu.school_institution || "—") +
        "</p>";
    } else if (lvl === "College") {
      var st = [];
      if (edu.college_status_passed) st.push("Passed");
      if (edu.college_status_dropout) st.push("Drop-out");
      html +=
        "<p class='mb-1'><strong>Degree:</strong> " +
        escHtml(edu.college_degree_type || "—") +
        "</p>" +
        "<p class='mb-1'><strong>Status:</strong> " +
        escHtml(st.join(", ") || "—") +
        "</p>" +
        "<p class='mb-1'><strong>Year:</strong> " +
        escHtml(edu.college_year != null ? String(edu.college_year) : "—") +
        "</p>" +
        "<p class='mb-0'><strong>Institution:</strong> " +
        escHtml(edu.college_institution || "—") +
        "</p>";
    }
    view.innerHTML = html;
    if (educationHasData(edu)) {
      view.hidden = false;
      if (actions) actions.hidden = false;
      if (form) form.hidden = true;
    } else {
      view.hidden = true;
      if (actions) actions.hidden = true;
      if (form) form.hidden = false;
    }
  }

  function renderWorkView(wrk) {
    var view = document.getElementById("qb-work-view");
    var actions = document.getElementById("qb-work-view-actions");
    var form = document.getElementById("qb-private-work-form");
    if (!view) return;
    wrk = wrk || {};
    var st = wrk.work_status || "Unemployed";
    var html = "<p class='mb-1'><strong>Status:</strong> " + escHtml(st) + "</p>";
    if (st === "Unemployed") {
      html += "<p class='mb-0'><strong>Note:</strong> " + escHtml(wrk.unemployed_sub || "—") + "</p>";
    } else if (st === "Employee") {
      html +=
        "<p class='mb-1'><strong>Workplace:</strong> " +
        escHtml(wrk.employee_workplace || "—") +
        "</p><p class='mb-0'><strong>Experience:</strong> " +
        escHtml(wrk.employee_experience || "—") +
        "</p>";
    } else if (st === "Employer") {
      html +=
        "<p class='mb-1'><strong>Firm type:</strong> " +
        escHtml(wrk.employer_org_type || "—") +
        "</p>";
      if (wrk.employer_org_type === "Organised") {
        html +=
          "<p class='mb-1'><strong>Company:</strong> " +
          escHtml(wrk.employer_company_name || "—") +
          "</p><p class='mb-1'><strong>Location:</strong> " +
          escHtml(wrk.employer_location || "—") +
          "</p><p class='mb-0'><strong>Incorporated:</strong> " +
          escHtml(wrk.employer_years != null ? String(wrk.employer_years) : "0") +
          " y " +
          escHtml(wrk.employer_months != null ? String(wrk.employer_months) : "0") +
          " m</p>";
      } else {
        html += "<p class='mb-0'><strong>Business:</strong> " + escHtml(wrk.employer_business_name || "—") + "</p>";
      }
    } else if (st === "Retired") {
      html += "<p class='mb-0 text-muted'>Retired</p>";
    }
    view.innerHTML = html;
    if (workHasData(wrk) || st !== "Unemployed") {
      view.hidden = false;
      if (actions) actions.hidden = false;
      if (form) form.hidden = true;
    } else if (st === "Unemployed" && (wrk.unemployed_sub || "").trim()) {
      view.hidden = false;
      if (actions) actions.hidden = false;
      if (form) form.hidden = true;
    } else {
      view.hidden = true;
      if (actions) actions.hidden = true;
      if (form) form.hidden = false;
    }
  }

  function fillEducationForm(edu) {
    edu = edu || {};
    var el = document.getElementById("qb-edu-level");
    if (el) el.value = edu.education_level || "Uneducated";
    var sc = document.getElementById("qb-edu-school-class");
    if (sc) sc.value = edu.school_class_passed || "";
    var sy = document.getElementById("qb-edu-school-year");
    if (sy) sy.value = edu.school_year != null ? String(edu.school_year) : "";
    var si = document.getElementById("qb-edu-school-inst");
    if (si) si.value = edu.school_institution || "";
    var cd = document.getElementById("qb-edu-college-degree");
    if (cd) cd.value = edu.college_degree_type || "Graduation";
    var cp = document.getElementById("qb-edu-college-passed");
    if (cp) cp.checked = !!edu.college_status_passed;
    var cdr = document.getElementById("qb-edu-college-dropout");
    if (cdr) cdr.checked = !!edu.college_status_dropout;
    var cy = document.getElementById("qb-edu-college-year");
    if (cy) cy.value = edu.college_year != null ? String(edu.college_year) : "";
    var ci = document.getElementById("qb-edu-college-inst");
    if (ci) ci.value = edu.college_institution || "";
    syncPrivateEducationBlocks();
  }

  function fillWorkForm(wrk) {
    wrk = wrk || {};
    var ws = document.getElementById("qb-work-status");
    if (ws) ws.value = wrk.work_status || "Unemployed";
    var us = document.getElementById("qb-work-unemployed-sub");
    if (us) us.value = wrk.unemployed_sub || "";
    var wp = document.getElementById("qb-work-emp-place");
    if (wp) wp.value = wrk.employee_workplace || "";
    var wx = document.getElementById("qb-work-emp-exp");
    if (wx) wx.value = wrk.employee_experience || "";
    var ot = document.getElementById("qb-work-org-type");
    if (ot) ot.value = wrk.employer_org_type || "";
    var cn = document.getElementById("qb-work-co-name");
    if (cn) cn.value = wrk.employer_company_name || "";
    var cl = document.getElementById("qb-work-co-loc");
    if (cl) cl.value = wrk.employer_location || "";
    var cyy = document.getElementById("qb-work-co-y");
    if (cyy) cyy.value = wrk.employer_years != null ? String(wrk.employer_years) : "";
    var cmm = document.getElementById("qb-work-co-m");
    if (cmm) cmm.value = wrk.employer_months != null ? String(wrk.employer_months) : "";
    var bn = document.getElementById("qb-work-biz-name");
    if (bn) bn.value = wrk.employer_business_name || "";
    syncPrivateWorkBlocks();
  }

  function syncPrivateEducationBlocks() {
    var lvl = ((document.getElementById("qb-edu-level") || {}).value || "Uneducated").trim();
    var sb = document.getElementById("qb-edu-school-block");
    var cb = document.getElementById("qb-edu-college-block");
    if (sb) sb.hidden = lvl !== "School";
    if (cb) cb.hidden = lvl !== "College";
  }

  function syncPrivateWorkBlocks() {
    var st = ((document.getElementById("qb-work-status") || {}).value || "Unemployed").trim();
    var u = document.getElementById("qb-work-unemployed-block");
    var e = document.getElementById("qb-work-employee-block");
    var er = document.getElementById("qb-work-employer-block");
    var ret = document.getElementById("qb-work-opt-retired");
    if (ret) {
      var allowRet = privateInfoLifeStage === "Vridh" || privateInfoLifeStage === "Sanyas";
      ret.hidden = !allowRet;
      if (!allowRet && st === "Retired") {
        var sel = document.getElementById("qb-work-status");
        if (sel) sel.value = "Unemployed";
        st = "Unemployed";
      }
    }
    if (u) u.hidden = st !== "Unemployed";
    if (e) e.hidden = st !== "Employee";
    if (er) er.hidden = st !== "Employer";
    var org = ((document.getElementById("qb-work-org-type") || {}).value || "").trim();
    var oreg = document.getElementById("qb-work-employer-organised");
    var oung = document.getElementById("qb-work-employer-unorganised");
    if (oreg) oreg.hidden = st !== "Employer" || org !== "Organised";
    if (oung) oung.hidden = st !== "Employer" || org !== "Unorganised";
  }

  function loadUserPrivateInfo() {
    fetch("/api/user/private_info", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        cachedEducation = (x.b && x.b.education) || {};
        cachedWork = (x.b && x.b.work) || {};
        privateInfoLifeStage = (x.b && x.b.life_stage) || "";
        fillEducationForm(cachedEducation);
        fillWorkForm(cachedWork);
        renderEducationView(cachedEducation);
        renderWorkView(cachedWork);
      })
      .catch(function () {});
  }

  function reloadEducation() {
    return fetch("/api/user/education", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
        cachedEducation = x.b.education || {};
        fillEducationForm(cachedEducation);
        renderEducationView(cachedEducation);
      });
  }

  function reloadWork() {
    return fetch("/api/user/work", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
        cachedWork = x.b.work || {};
        fillWorkForm(cachedWork);
        renderWorkView(cachedWork);
      });
  }

  var eduEditBtn = document.getElementById("qb-edu-edit-btn");
  if (eduEditBtn) {
    eduEditBtn.addEventListener("click", function () {
      var form = document.getElementById("qb-private-education-form");
      var view = document.getElementById("qb-edu-view");
      var actions = document.getElementById("qb-edu-view-actions");
      if (form) form.hidden = false;
      if (view) view.hidden = true;
      if (actions) actions.hidden = true;
    });
  }
  var workEditBtn = document.getElementById("qb-work-edit-btn");
  if (workEditBtn) {
    workEditBtn.addEventListener("click", function () {
      var form = document.getElementById("qb-private-work-form");
      var view = document.getElementById("qb-work-view");
      var actions = document.getElementById("qb-work-view-actions");
      if (form) form.hidden = false;
      if (view) view.hidden = true;
      if (actions) actions.hidden = true;
    });
  }

  var eduLevelEl = document.getElementById("qb-edu-level");
  if (eduLevelEl) eduLevelEl.addEventListener("change", syncPrivateEducationBlocks);
  var eduForm = document.getElementById("qb-private-education-form");
  if (eduForm) {
    eduForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var st = document.getElementById("qb-edu-save-status");
      text(st, "Saving…");
      var lvl = ((document.getElementById("qb-edu-level") || {}).value || "Uneducated").trim();
      var body = { education_level: lvl };
      if (lvl === "School") {
        body.school_class_passed = (document.getElementById("qb-edu-school-class") || {}).value || "";
        var syRaw = (document.getElementById("qb-edu-school-year") || {}).value || "";
        var syN = parseInt(String(syRaw), 10);
        body.school_year = isNaN(syN) ? null : syN;
        body.school_institution = (document.getElementById("qb-edu-school-inst") || {}).value || "";
      }
      if (lvl === "College") {
        body.college_degree_type = (document.getElementById("qb-edu-college-degree") || {}).value || "";
        body.college_status_passed = !!(document.getElementById("qb-edu-college-passed") || {}).checked;
        body.college_status_dropout = !!(document.getElementById("qb-edu-college-dropout") || {}).checked;
        var cyRaw = (document.getElementById("qb-edu-college-year") || {}).value || "";
        var cyN = parseInt(String(cyRaw), 10);
        body.college_year = isNaN(cyN) ? null : cyN;
        body.college_institution = (document.getElementById("qb-edu-college-inst") || {}).value || "";
      }
      fetch("/api/user/education", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          text(st, "Saved.");
          cachedEducation = (x.b && x.b.education) || cachedEducation;
          renderEducationView(cachedEducation);
        })
        .catch(function (err) {
          text(st, err.message || "Error");
        });
    });
  }

  var workStatusEl = document.getElementById("qb-work-status");
  if (workStatusEl) workStatusEl.addEventListener("change", syncPrivateWorkBlocks);
  var workOrgEl = document.getElementById("qb-work-org-type");
  if (workOrgEl) workOrgEl.addEventListener("change", syncPrivateWorkBlocks);
  var workForm = document.getElementById("qb-private-work-form");
  if (workForm) {
    workForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var st = document.getElementById("qb-work-save-status");
      text(st, "Saving…");
      var ws = ((document.getElementById("qb-work-status") || {}).value || "Unemployed").trim();
      var body = { work_status: ws };
      if (ws === "Unemployed") {
        body.unemployed_sub = (document.getElementById("qb-work-unemployed-sub") || {}).value || "";
      }
      if (ws === "Employee") {
        body.employee_workplace = (document.getElementById("qb-work-emp-place") || {}).value || "";
        body.employee_experience = (document.getElementById("qb-work-emp-exp") || {}).value || "";
      }
      if (ws === "Employer") {
        body.employer_org_type = (document.getElementById("qb-work-org-type") || {}).value || "";
        body.employer_company_name = (document.getElementById("qb-work-co-name") || {}).value || "";
        body.employer_location = (document.getElementById("qb-work-co-loc") || {}).value || "";
        var eyRaw = (document.getElementById("qb-work-co-y") || {}).value || "";
        var emRaw = (document.getElementById("qb-work-co-m") || {}).value || "";
        var eyN = parseInt(String(eyRaw), 10);
        var emN = parseInt(String(emRaw), 10);
        body.employer_years = isNaN(eyN) ? null : eyN;
        body.employer_months = isNaN(emN) ? null : emN;
        body.employer_business_name = (document.getElementById("qb-work-biz-name") || {}).value || "";
      }
      fetch("/api/user/work", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          text(st, "Saved.");
          cachedWork = (x.b && x.b.work) || cachedWork;
          renderWorkView(cachedWork);
        })
        .catch(function (err) {
          text(st, err.message || "Error");
        });
    });
  }

  function getSelectedDonateMethod() {
    var picked = document.querySelector('input[name="qb-donate-method"]:checked');
    return picked ? String(picked.value || "upi").toLowerCase() : "upi";
  }

  function syncDonateMethodUi() {
    selectedDonateMethod = getSelectedDonateMethod();
    var cash = document.getElementById("qb-donate-cash-fields");
    var upi = document.getElementById("qb-donate-upi-fields");
    if (cash) cash.hidden = selectedDonateMethod !== "cash";
    if (upi) upi.hidden = selectedDonateMethod !== "upi";
    if (selectedDonateMethod === "upi") upiPaymentAcknowledged = false;
  }

  document.querySelectorAll(".qb-donate-method-radio").forEach(function (radio) {
    radio.addEventListener("change", syncDonateMethodUi);
  });
  var upiDoneBtn = document.getElementById("qb-donate-upi-done");
  if (upiDoneBtn) {
    upiDoneBtn.addEventListener("click", function () {
      upiPaymentAcknowledged = true;
      text(document.getElementById("qb-donate-flash"), "Payment marked complete. You may donate now.");
    });
  }

  function renderKarmaChips(container, coins) {
    if (!container) return;
    container.innerHTML = "";
    (coins || []).forEach(function (c) {
      var span = document.createElement("span");
      span.className = "qb-karma-chip";
      span.textContent = "₹" + c.rupee_value + "×" + c.count;
      container.appendChild(span);
    });
    if (!coins || !coins.length) {
      var empty = document.createElement("span");
      empty.className = "qb-stmt-muted";
      empty.textContent = "No Karma Points yet";
      container.appendChild(empty);
    }
  }

  function loadWeeklyStatements() {
    var flash = document.getElementById("qb-wallet-txn-flash");
    var weeksUl = document.getElementById("qb-wallet-stmt-weeks");
    var weeksEmpty = document.getElementById("qb-wallet-stmt-weeks-empty");
    var detail = document.getElementById("qb-wallet-stmt-detail");
    var hint = document.getElementById("qb-wallet-stmt-pick-hint");
    var iframe = document.getElementById("qb-wallet-stmt-iframe");
    if (flash) text(flash, "Loading…");
    if (weeksUl) weeksUl.innerHTML = "";
    return fetch("/api/karma/statements", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
        if (flash) text(flash, "");
        var rows = (x.b && x.b.statements) || [];
        if (!weeksUl) return;
        if (!rows.length) {
          if (weeksEmpty) weeksEmpty.hidden = false;
          if (detail) detail.hidden = true;
          if (hint) hint.hidden = false;
          return;
        }
        if (weeksEmpty) weeksEmpty.hidden = true;
        rows.forEach(function (s) {
          var li = document.createElement("li");
          li.className = "mb-2";
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "qb-btn qb-btn-outline btn-sm w-100 text-start";
          btn.textContent = s.week_start + " → " + s.week_end;
          btn.addEventListener("click", function () {
            if (hint) hint.hidden = true;
            if (detail) detail.hidden = false;
            if (iframe) iframe.src = "/api/karma/statements/" + s.id + "/html";
          });
          li.appendChild(btn);
          weeksUl.appendChild(li);
        });
      })
      .catch(function (err) {
        if (flash) text(flash, err.message || "Could not load statements");
      });
  }

  var walletTxnBtn = document.getElementById("qb-wallet-txn-btn");
  if (walletTxnBtn) {
    walletTxnBtn.addEventListener("click", function () {
      openModal("qb-wallet-txn-modal");
      loadWeeklyStatements();
    });
  }

  function loadWalletModal() {
    fetch("/api/wallet/balance", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
        text(document.getElementById("qb-wallet-balance-qoins"), String(x.b.balance_qoins || 0));
        text(document.getElementById("qb-wallet-balance-rupees"), String(x.b.total_rupees || 0));
        renderKarmaChips(document.getElementById("qb-wallet-coin-chips"), x.b.coins || []);
        return fetch("/api/karma/pending", {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        }).then(function (r2) {
          return r2.json().then(function (p) {
            return { pending: p };
          });
        });
      })
      .then(function (wrap) {
        var line = document.getElementById("qb-wallet-pending-line");
        if (!line || !wrap || !wrap.pending) return;
        var p = wrap.pending;
        var n = p.pending_count || 0;
        var k = (p.karma_pending || []).length;
        if (n || k) {
          line.hidden = false;
          line.textContent =
            "Pending this week: " +
            n +
            " transaction(s) (₹" +
            (p.pending_rupees || 0) +
            ")" +
            (k ? " · " + k + " karma action(s)" : "");
        } else {
          line.hidden = true;
        }
      })
      .catch(function (err) {
        text(document.getElementById("qb-donate-flash"), err.message || "Could not load wallet");
      });
  }

  var activeMyPostTab = "active";

  function loadMyPostModal() {
    var ul = document.getElementById("qb-my-post-list");
    var empty = document.getElementById("qb-my-post-empty");
    if (!ul) return;
    var url =
      activeMyPostTab === "previous"
        ? "/api/my_posts/previous"
        : "/api/my_posts/active";
    fetchJson(url)
      .then(function (x) {
        if (!x.ok) throw new Error(x.body.error || "Could not load posts");
        var posts = x.body.posts || [];
        ul.innerHTML = "";
        if (!posts.length) {
          if (empty) {
            empty.hidden = false;
            text(
              empty,
              activeMyPostTab === "previous"
                ? "No previous posts yet."
                : "No current personal posts yet."
            );
          }
          return;
        }
        if (empty) empty.hidden = true;
        posts.forEach(function (p) {
          if (activeMyPostTab === "previous") {
            ul.appendChild(renderPreviousPost(p));
          } else {
            ul.appendChild(renderPost(p, "live"));
          }
        });
      })
      .catch(function () {
        ul.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          text(empty, "Could not load posts.");
        }
      });
  }

  function setMyPostTab(tab) {
    activeMyPostTab = tab === "previous" ? "previous" : "active";
    document.querySelectorAll(".qb-js-my-post-tab").forEach(function (btn) {
      var on = btn.getAttribute("data-my-post-tab") === activeMyPostTab;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    loadMyPostModal();
  }

  var myPostBtn = document.getElementById("qb-my-post-btn");
  if (myPostBtn) {
    myPostBtn.addEventListener("click", function () {
      setMyPostTab("active");
      openModal("qb-my-post-modal");
    });
  }
  document.querySelectorAll(".qb-js-my-post-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setMyPostTab(btn.getAttribute("data-my-post-tab"));
    });
  });

  var karmaWalletBtn = document.getElementById("qb-karma-wallet-btn");
  if (karmaWalletBtn) {
    karmaWalletBtn.addEventListener("click", function () {
      selectedDonateAmount = 0;
      text(document.getElementById("qb-donate-preview"), "");
      text(document.getElementById("qb-donate-flash"), "");
      var sub = document.getElementById("qb-donate-submit");
      if (sub) sub.disabled = true;
      document.querySelectorAll(".qb-donate-amt").forEach(function (b) {
        b.classList.remove("qb-btn-primary");
        b.classList.add("qb-btn-outline");
      });
      openModal("qb-karma-wallet-modal");
      syncDonateMethodUi();
      loadWalletModal();
    });
  }
  document.querySelectorAll(".qb-donate-amt").forEach(function (btn) {
    btn.addEventListener("click", function () {
      selectedDonateAmount = parseInt(btn.getAttribute("data-amount"), 10) || 0;
      document.querySelectorAll(".qb-donate-amt").forEach(function (b) {
        b.classList.toggle("qb-btn-primary", b === btn);
        b.classList.toggle("qb-btn-outline", b !== btn);
      });
      text(
        document.getElementById("qb-donate-preview"),
        DONATION_PREVIEW[selectedDonateAmount] || ""
      );
      var sub = document.getElementById("qb-donate-submit");
      if (sub) sub.disabled = !selectedDonateAmount;
    });
  });
  var donateSubmit = document.getElementById("qb-donate-submit");
  if (donateSubmit) {
    donateSubmit.addEventListener("click", function () {
      if (!selectedDonateAmount) return;
      var method = getSelectedDonateMethod();
      var agentId = ((document.getElementById("qb-donate-agent-id") || {}).value || "").trim();
      if (method === "cash" && !agentId) {
        text(document.getElementById("qb-donate-flash"), "Agent Account ID is required for cash donations.");
        return;
      }
      if (method === "upi" && !upiPaymentAcknowledged) {
        text(document.getElementById("qb-donate-flash"), "Confirm payment with Payment Completed first.");
        return;
      }
      text(document.getElementById("qb-donate-flash"), "Processing…");
      var body = { amount: selectedDonateAmount, method: method };
      if (method === "cash") body.agent_id = agentId;
      fetch("/api/karma/donate", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Donation failed");
          text(document.getElementById("qb-donate-flash"), "Donation successful. Wallet updated.");
          loadWalletModal();
        })
        .catch(function (err) {
          text(document.getElementById("qb-donate-flash"), err.message || "Donation failed");
        });
    });
  }

  var adminVillageSearch = document.getElementById("qb-admin-village-search");
  var adminVillageSuggest = document.getElementById("qb-admin-village-suggest");
  var adminSelectedVillageId = "";
  var adminSearchTimer = null;
  if (adminVillageSearch) {
    adminVillageSearch.addEventListener("input", function () {
      adminSelectedVillageId = "";
      var q = (adminVillageSearch.value || "").trim();
      clearTimeout(adminSearchTimer);
      if (!q) {
        if (adminVillageSuggest) {
          adminVillageSuggest.hidden = true;
          adminVillageSuggest.innerHTML = "";
        }
        return;
      }
      adminSearchTimer = setTimeout(function () {
        fetch("/api/admin/villages/search?q=" + encodeURIComponent(q), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
          .then(function (x) {
            if (!adminVillageSuggest) return;
            adminVillageSuggest.innerHTML = "";
            (x.b.villages || []).forEach(function (v) {
              var li = document.createElement("li");
              var btn = document.createElement("button");
              btn.type = "button";
              btn.className = "qb-btn qb-btn-outline btn-sm w-100 text-start mb-1";
              btn.textContent = (v.name || v.id) + " · " + v.id;
              btn.addEventListener("click", function () {
                adminSelectedVillageId = v.id;
                adminVillageSearch.value = v.id;
                adminVillageSuggest.hidden = true;
              });
              li.appendChild(btn);
              adminVillageSuggest.appendChild(li);
            });
            adminVillageSuggest.hidden = !(x.b.villages && x.b.villages.length);
          });
      }, 250);
    });
  }
  var adminReportBtn = document.getElementById("qb-admin-donation-report-btn");
  if (adminReportBtn) {
    adminReportBtn.addEventListener("click", function () {
      var vid = adminSelectedVillageId || (adminVillageSearch && adminVillageSearch.value.trim()) || "";
      var flash = document.getElementById("qb-admin-donation-report-flash");
      if (!vid) {
        if (flash) text(flash, "Enter or select a village ID.");
        return;
      }
      if (flash) text(flash, "Loading…");
      fetch("/api/admin/village_donations?village_id=" + encodeURIComponent(vid), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Report failed");
          if (flash) text(flash, "");
          var out = document.getElementById("qb-admin-donation-report-out");
          if (out) out.hidden = false;
          text(document.getElementById("qb-admin-report-village-label"), x.b.village_id || vid);
          text(document.getElementById("qb-admin-report-total-qoins"), String(x.b.total_qoins || 0));
          text(document.getElementById("qb-admin-report-total-rupees"), String(x.b.total_rupees || 0));
          var recent = document.getElementById("qb-admin-report-recent");
          if (recent) {
            recent.innerHTML = "";
            (x.b.recent || []).forEach(function (t) {
              var li = document.createElement("li");
              li.className = "mb-1";
              li.textContent =
                "₹" +
                t.rupee_value +
                " from " +
                (t.donor_private_id || "—") +
                " · " +
                (t.created_at || "");
              recent.appendChild(li);
            });
            if (!(x.b.recent || []).length) {
              recent.innerHTML = "<li class='text-muted'>No village donations yet.</li>";
            }
          }
        })
        .catch(function (err) {
          if (flash) text(flash, err.message || "Report failed");
        });
    });
  }

  function fillConnectionRelationshipSelect(memberType, ro) {
    ro = ro || {};
    var relSelect = document.getElementById("qb-relationship-select");
    var custom = document.getElementById("qb-relationship-custom");
    if (!relSelect) return;
    fillNestedRelationshipSelect(relSelect, {
      includeSelf: false,
      presetValue: ro.presetValue || "",
    });
    if (custom) {
      custom.hidden = true;
      custom.value = "";
    }
  }

  function parseParentLinkSelect(val) {
    var s = String(val || "").trim();
    if (!s) return { member: null, connection: null };
    if (s.indexOf("m:") === 0) {
      var mid = parseInt(s.slice(2), 10);
      return { member: isNaN(mid) ? null : mid, connection: null };
    }
    if (s.indexOf("c:") === 0) {
      var cid = parseInt(s.slice(2), 10);
      return { member: null, connection: isNaN(cid) ? null : cid };
    }
    return { member: null, connection: null };
  }

  function otherPersonSelectValueFromMember(m) {
    if (!m) return "";
    if (m.tree_child_of_member_id != null && m.tree_child_of_member_id !== "") {
      return "m:" + m.tree_child_of_member_id;
    }
    if (m.tree_child_of_connection_request_id != null && m.tree_child_of_connection_request_id !== "") {
      return "c:" + m.tree_child_of_connection_request_id;
    }
    return "";
  }

  function populateNuclearParentSelect(sel, candidates, excludeMemberId, currentVal, namesOnly) {
    if (!sel) return;
    namesOnly = !!namesOnly;
    sel.innerHTML = '<option value="">— None —</option>';
    (candidates || []).forEach(function (c) {
      if (c.kind === "member") {
        if (String(c.member_id) === String(excludeMemberId)) return;
        var o = document.createElement("option");
        o.value = "m:" + c.member_id;
        o.textContent = namesOnly ? String(c.member_name || "") : (c.member_name || "") + " · " + (c.relationship || "");
        sel.appendChild(o);
      } else if (c.kind === "connection") {
        var o2 = document.createElement("option");
        o2.value = "c:" + c.connection_request_id;
        o2.textContent = namesOnly
          ? String(c.member_name || "")
          : (c.member_name || "") + " · " + (c.relationship || "") + " (account)";
        sel.appendChild(o2);
      }
    });
    if (currentVal && [].some.call(sel.options, function (opt) { return opt.value === currentVal; })) {
      sel.value = currentVal;
    }
  }

  function renderFamilyMemberNode(slotLabel, member, opts) {
    opts = opts || {};
    var node = document.createElement("div");
    node.className = "qb-family-node";
    if (!member) {
      var slotKey = opts.slotKey || "";
      var preset = FAMILY_SLOT_PRESET_REL[slotKey];
      if (preset) {
        var addBtn =
          '<button type="button" class="qb-family-slot-add qb-js-family-slot-add" data-preset-relationship="' +
          escAttr(preset) +
          '" data-slot-label="' +
          escAttr(slotLabel) +
          '" aria-label="Add ' +
          escAttr(slotLabel) +
          '">+</button>';
        var isGp =
          slotKey.indexOf("grandfather") >= 0 || slotKey.indexOf("grandmother") >= 0;
        if (isGp) {
          node.innerHTML = escHtml(slotLabel) + '<div class="qb-family-empty-slot-line">' + addBtn + "</div>";
        } else {
          node.innerHTML =
            escHtml(slotLabel) +
            '<br /><span class="qb-family-empty-slot">Not added</span>' +
            '<div class="qb-family-empty-slot-line">' +
            addBtn +
            "</div>";
        }
      } else {
        node.innerHTML =
          escHtml(slotLabel) + '<br /><span class="qb-family-empty-slot">Not added</span>';
      }
      return node;
    }
    node.classList.add("is-filled");
    if (member.is_dead) node.classList.add("is-deceased");
    if (member.is_self) node.classList.add("qb-family-node--self");
    var name = member.name || member.member_name || "—";
    var publicId = member.account_public_id || member.public_id || "";
    var mt = (member.member_type || "nuclear").toLowerCase();
    var canEditLinks =
      !member.is_self &&
      !member.is_placeholder &&
      mt === "nuclear" &&
      (member.source === "form" || member.source === "manual");
    var nameInner = '<span class="qb-family-name">' + escHtml(name) + "</span>";
    if (canEditLinks) {
      nameInner =
        '<span class="qb-family-name-row"><span class="qb-family-name">' +
        escHtml(name) +
        '</span><button type="button" class="qb-family-node-edit qb-js-family-member-edit" title="Edit member" aria-label="Edit member" data-member-id="' +
        escAttr(String(member.id)) +
        '" data-source="' +
        escAttr(member.source || "manual") +
        '" data-member-type="nuclear">✎</button></span>';
    }
    if (publicId) {
      nameInner += " <span class='font-monospace text-muted small'>" + escHtml(publicId) + "</span>";
    }
    var deadBadge = member.is_dead ? '<span class="qb-family-dead-badge">deceased</span>' : "";
    var inner =
      escHtml(slotLabel) +
      '<br /><span class="qb-family-name-wrap">' +
      nameInner +
      "</span>" +
      deadBadge;
    if (member.linked_mother_name || member.linked_father_name) {
      var bits = [];
      if (member.linked_mother_name) {
        bits.push("Mother: " + escHtml(member.linked_mother_name));
      }
      if (member.linked_father_name) {
        bits.push("Father: " + escHtml(member.linked_father_name));
      }
      inner += '<div class="qb-family-linked-parents">' + bits.join(" · ") + "</div>";
    }
    if (member.natural_lineage_phrase) {
      inner +=
        '<div class="qb-family-linked-parents">' + escHtml(member.natural_lineage_phrase) + "</div>";
    }
    node.innerHTML = inner;
    return node;
  }

  function loadFamilyTree() {
    if (window.qbReloadFamilyGraph) {
      window.qbReloadFamilyGraph();
    }
  }

  function loadFamilyAllMembers() {
    var ul = document.getElementById("qb-family-all-list-modal");
    if (!ul) {
      if (window.qbReloadFamilyGraph) window.qbReloadFamilyGraph();
      return;
    }
    var empty = document.getElementById("qb-family-all-empty-modal");
    fetch("/api/family/all_members", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "members failed");
        var rows = x.b.members || [];
        ul.innerHTML = "";
        if (empty) empty.hidden = rows.length > 0;
        rows.forEach(function (m) {
          var li = document.createElement("li");
          li.className = "qb-family-all-row" + (m.is_dead ? " is-deceased" : "");
          var mt = (m.member_type || (m.family_member_type === "general" ? "general" : "nuclear") || "nuclear").toLowerCase();
          var publicTag = m.account_public_id
            ? "<span class='font-monospace text-muted small'>" + escHtml(m.account_public_id) + "</span>"
            : "";

          var isSelf = !!m.is_self || (m.source || "") === "self";
          var isAdmin = !!dashCfg.isAdmin;
          var actionHtml = "";
          if (m.removal_pending) {
            actionHtml =
              '<span class="qb-rel-tag qb-rel-tag--pending">Removal pending admin review</span>';
          } else if (!isSelf) {
            var removeMode = m.can_remove_directly || isAdmin ? "instant" : "request";
            actionHtml =
              '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-family-icon-btn qb-js-family-remove" title="Remove" aria-label="Remove" data-remove-mode="' +
              escAttr(removeMode) +
              '" data-source="' +
              escAttr(m.source || "") +
              '" data-id="' +
              escAttr(String(m.id)) +
              '" data-name="' +
              escAttr(m.member_name || "") +
              '" data-relationship="' +
              escAttr(m.relationship_label || m.relationship || "") +
              '">🗑</button>';
          }

          var linkBtn = "";
          var canLink =
            !isSelf &&
            mt === "nuclear" &&
            (m.source === "form" || m.source === "manual") &&
            !m.account_public_id;
          if (canLink) {
            linkBtn =
              '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-family-icon-btn qb-js-family-link-account" title="Link account" aria-label="Link account" data-source="' +
              escAttr(m.source || "") +
              '" data-id="' +
              escAttr(String(m.id)) +
              '" data-name="' +
              escAttr(m.member_name || "") +
              '" data-relationship="' +
              escAttr(m.relationship_label || m.relationship || "") +
              '">🔗</button>';
          }

          var editBtn = "";
          if (!isSelf) {
            editBtn =
              '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-family-icon-btn qb-js-family-member-edit" title="Edit" aria-label="Edit" data-id="' +
              escAttr(String(m.id)) +
              '" data-source="' +
              escAttr(m.source || "") +
              '" data-member-type="' +
              escAttr(mt) +
              '">✎</button>';
          }

          var kindLabel = "Nuclear (tree)";
          if (mt === "general") kindLabel = "General (list only)";
          else if (m.source === "connection") kindLabel = "Connected (account)";
          else if (m.source === "manual") kindLabel = "Nuclear (manual)";
          else if (m.source === "form") kindLabel = "Nuclear (activation form)";
          var deadTag = m.is_dead
            ? '<span class="qb-family-dead-badge">deceased</span>'
            : "";
          li.innerHTML =
            "<div class='qb-family-all-main'>" +
            "<strong>" +
            escHtml(m.member_name || "") +
            "</strong> " +
            publicTag +
            " <span class='qb-rel-tag'>" +
            escHtml(m.relationship_label || m.relationship || "") +
            "</span>" +
            "<span class='qb-family-source small text-muted'> · " +
            kindLabel +
            "</span>" +
            (deadTag ? " " + deadTag : "") +
            "</div>" +
            "<div class='qb-family-all-actions qb-family-all-actions--icons mt-1'>" +
            editBtn +
            (actionHtml ? " " + actionHtml : "") +
            (linkBtn ? " " + linkBtn : "") +
            "</div>";
          ul.appendChild(li);
        });
      })
      .catch(function (err) {
        if (ul) ul.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          text(empty, err.message || "Could not load family members.");
        }
      });
  }

  function openFamilyMemberEditModal(m) {
    if (!m || m.is_self) return;
    fmeSnapshot = m;
    text(document.getElementById("qb-fme-status"), "");
    var idEl = document.getElementById("qb-fme-id");
    var srcEl = document.getElementById("qb-fme-source");
    var mtEl = document.getElementById("qb-fme-member-type");
    var genPanel = document.getElementById("qb-fme-general-panel");
    var nucPanel = document.getElementById("qb-fme-nuclear-panel");
    var linkPanel = document.getElementById("qb-fme-link-panel");
    var linkHint = document.getElementById("qb-fme-link-hint");
    var saveBtn = document.getElementById("qb-fme-save");
    var unlinkBtn = document.getElementById("qb-fme-unlink");
    if (!idEl || !srcEl || !mtEl) return;

    var src = String(m.source || "form");
    var mt = String(
      m.member_type || (m.family_member_type === "general" ? "general" : "nuclear") || "nuclear"
    ).toLowerCase();
    idEl.value = String(m.id);
    srcEl.value = src;
    mtEl.value = mt;

    var linkPid = document.getElementById("qb-fme-link-pid");
    var linkSug = document.getElementById("qb-fme-link-suggestion");
    if (linkPid) linkPid.value = "";
    if (linkSug) linkSug.innerHTML = "";

    if (src === "connection") {
      if (genPanel) genPanel.hidden = false;
      if (nucPanel) nucPanel.hidden = true;
      if (linkPanel) linkPanel.hidden = true;
      if (saveBtn) saveBtn.hidden = true;
      if (unlinkBtn) unlinkBtn.hidden = true;
      text(document.getElementById("qb-fme-gen-name"), m.member_name || "—");
      text(document.getElementById("qb-fme-gen-pub"), m.account_public_id || "");
      text(
        document.getElementById("qb-fme-gen-rel"),
        m.relationship_label || m.relationship || "Family"
      );
    } else if (mt === "general") {
      if (genPanel) genPanel.hidden = false;
      if (nucPanel) nucPanel.hidden = true;
      if (linkPanel) linkPanel.hidden = true;
      if (saveBtn) saveBtn.hidden = true;
      if (unlinkBtn) {
        unlinkBtn.hidden = false;
        unlinkBtn.textContent = "Unlink (remove connection)";
      }
      text(document.getElementById("qb-fme-gen-name"), m.member_name || "—");
      text(document.getElementById("qb-fme-gen-pub"), m.account_public_id || "");
      text(
        document.getElementById("qb-fme-gen-rel"),
        m.relationship_label || m.relationship || "Family"
      );
    } else {
      if (genPanel) genPanel.hidden = true;
      if (nucPanel) nucPanel.hidden = false;
      if (saveBtn) saveBtn.hidden = false;
      var linked = !!(m.account_public_id && String(m.account_public_id).trim());
      if (unlinkBtn) {
        unlinkBtn.hidden = !linked;
        unlinkBtn.textContent = "Unlink account";
      }
      if (linkPanel) {
        linkPanel.hidden = linked;
        if (linkHint) {
          text(
            linkHint,
            linked
              ? "This member is linked to " + String(m.account_public_id) + "."
              : "Send a link request so the other user can approve connecting their Account ID to this tree member."
          );
        }
      }
      var nm = document.getElementById("qb-fme-name");
      var ag = document.getElementById("qb-fme-age");
      var ge = document.getElementById("qb-fme-gender");
      if (nm) nm.value = m.member_name || "";
      if (ag) ag.value = m.age != null && m.age !== "" ? String(m.age) : "";
      if (ge) ge.value = m.gender || "";
    }
    openModal("qb-family-member-edit-modal");
  }

  function openFamilyMemberEditFromButton(btn) {
    var id = parseInt(btn.getAttribute("data-id") || "0", 10);
    if (!id) return;
    var src = btn.getAttribute("data-source") || "";
    var mt = btn.getAttribute("data-member-type") || "";
    fetch("/api/family/all_members", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "load failed");
        var rows = x.b.members || [];
        var m = rows.find(function (row) {
          return parseInt(String(row.id), 10) === id && (!src || row.source === src);
        });
        if (!m) m = rows.find(function (row) { return parseInt(String(row.id), 10) === id; });
        if (!m) throw new Error("Member not found");
        if (mt) m.member_type = mt;
        openFamilyMemberEditModal(m);
      })
      .catch(function (err) {
        familyFlash(err.message || "Could not open editor", "error");
      });
  }

  var fmeSnapshot = null;

  function populateFamilyMemberSelect(sel, members, excludeId, currentVal) {
    if (!sel) return;
    sel.innerHTML = '<option value="">— None —</option>';
    (members || []).forEach(function (m) {
      if (String(m.id) === String(excludeId)) return;
      var o = document.createElement("option");
      o.value = String(m.id);
      o.textContent =
        (m.member_name || "") + " · " + (m.relationship_label || m.relationship || "");
      sel.appendChild(o);
    });
    if (currentVal != null && currentVal !== "" && String(currentVal) !== "0") {
      sel.value = String(currentVal);
    }
  }

  function renderEditTreeEditor(members) {
    var box = document.getElementById("qb-family-edit-tree-body");
    if (!box) return;
    box.innerHTML = "";
    (members || []).forEach(function (m) {
      var row = document.createElement("div");
      row.className = "qb-family-edit-tree-row";
      row.setAttribute("data-member-id", String(m.id));
      var label = document.createElement("div");
      label.textContent = (m.member_name || "") + " (" + (m.relationship || "") + ")";
      row.appendChild(label);
      [
        ["tree_mother_member_id", "Mother"],
        ["tree_father_member_id", "Father"],
        ["tree_spouse_member_id", "Spouse"],
        ["tree_child_of_member_id", "Child of"],
      ].forEach(function (pair) {
        var sel = document.createElement("select");
        sel.className = "form-select form-select-sm";
        sel.setAttribute("data-tree-field", pair[0]);
        populateFamilyMemberSelect(sel, members, m.id, m[pair[0]]);
        row.appendChild(sel);
      });
      box.appendChild(row);
    });
  }

  function closeAllFamilyNodeMenus() {
    document.querySelectorAll(".qb-family-node.is-menu-open").forEach(function (n) {
      n.classList.remove("is-menu-open");
      var m = n.querySelector(".qb-family-node-menu");
      if (m) m.hidden = true;
      var kb = n.querySelector(".qb-family-node-kebab");
      if (kb) kb.setAttribute("aria-expanded", "false");
    });
  }

  function closeFamilyOptionsDetails() {
    var d = document.getElementById("qb-family-options-details");
    if (d) d.open = false;
  }

  function resetAndOpenConnectionModal(type, opts) {
    opts = opts || {};
    var typeStr = type || "social";
    var typeEl = document.getElementById("qb-connection-type");
    var search = document.getElementById("qb-connection-search");
    var suggestions = document.getElementById("qb-connection-suggestions");
    var relationshipWrap = document.getElementById("qb-relationship-wrap");
    var customRel = document.getElementById("qb-relationship-custom");
    var selected = document.getElementById("qb-connection-selected");
    var actions = document.getElementById("qb-connection-actions");
    var memberTypeWrap = document.getElementById("qb-connection-member-type-wrap");
    var memberTypeSel = document.getElementById("qb-connection-member-type");
    var relSelect = document.getElementById("qb-relationship-select");
    var profileWrap = document.getElementById("qb-connection-family-profile-wrap");
    var nm = document.getElementById("qb-conn-member-name");
    var ag = document.getElementById("qb-conn-member-age");
    var genEl = document.getElementById("qb-conn-member-gender");
    var searchLbl = document.getElementById("qb-connection-search-label");
    selectedConnectionUser = null;
    if (typeEl) typeEl.value = typeStr;
    if (search) search.value = "";
    if (suggestions) suggestions.innerHTML = "";
    if (memberTypeWrap) memberTypeWrap.hidden = typeStr !== "family";
    if (profileWrap) profileWrap.hidden = typeStr !== "family";
    if (nm) nm.value = "";
    if (ag) ag.value = "";
    if (genEl) genEl.value = "";
    if (searchLbl) {
      searchLbl.textContent =
        typeStr === "family"
          ? "Account ID (Public ID) — optional for Nuclear Family, required for General Family"
          : "Enter Account ID (Public ID)";
    }
    if (memberTypeSel) {
      if (typeStr === "family") {
        memberTypeSel.value = opts.familyMemberType || "";
      } else {
        memberTypeSel.value = "";
      }
    }
    if (relationshipWrap) relationshipWrap.hidden = typeStr !== "family";
    if (customRel) {
      customRel.value = "";
      customRel.hidden = true;
    }
    if (typeStr === "family") {
      var mt = opts.familyMemberType || (memberTypeSel && memberTypeSel.value) || "";
      fillConnectionRelationshipSelect(mt, { presetValue: opts.presetRelationship || "" });
    } else if (relSelect) {
      fillConnectionRelationshipSelect("", {});
    }
    if (selected) {
      selected.hidden = true;
      selected.innerHTML = "";
    }
    if (actions) actions.hidden = true;
    var sendBtnInit = document.getElementById("qb-connection-send-btn");
    if (sendBtnInit) {
      sendBtnInit.disabled = false;
      sendBtnInit.classList.remove("is-disabled");
    }
    text(document.getElementById("qb-connection-modal-title"), "Add " + connectionTypeLabel(typeStr));
    text(document.getElementById("qb-connection-status"), "");
    openModal("qb-connection-modal");
  }

  function syncAddFamilyTypeUI() {
    var gen = document.querySelector('input[name="qb-add-family-type"][value="general"]');
    var isGen = gen && gen.checked;
    var nuclear = document.getElementById("qb-family-add-close-nuclear-block");
    var genPanel = document.getElementById("qb-family-add-close-general-panel");
    var subBtn = document.getElementById("qb-family-add-close-submit-btn");
    if (nuclear) nuclear.hidden = isGen;
    if (genPanel) genPanel.hidden = !isGen;
    if (subBtn) subBtn.hidden = isGen;
    var nameEl = document.getElementById("qb-family-add-close-name");
    if (nameEl) nameEl.required = !isGen;
  }

  function openNuclearFamilyAddModal(ctx) {
    ctx = ctx || {};
    closeAllFamilyNodeMenus();
    closeFamilyOptionsDetails();
    var form = document.getElementById("qb-family-add-close-form");
    if (form) form.reset();
    var nRadio = document.querySelector('input[name="qb-add-family-type"][value="nuclear"]');
    if (nRadio) nRadio.checked = true;
    syncAddFamilyTypeUI();
    text(document.getElementById("qb-family-add-close-status"), "");
    var sel = document.getElementById("qb-family-add-close-connect");
    fetch("/api/family/tree_links", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Failed");
        populateFamilyMemberSelect(sel, x.b.members || [], "", "");
        if (ctx.connectMemberId && sel) {
          var cv = String(ctx.connectMemberId);
          if ([].some.call(sel.options, function (o) { return o.value === cv; })) sel.value = cv;
        }
        openModal("qb-family-add-close-modal");
      })
      .catch(function () {
        if (sel) populateFamilyMemberSelect(sel, [], "", "");
        openModal("qb-family-add-close-modal");
      });
  }

  function openEditTreeConnectionsModal() {
    closeAllFamilyNodeMenus();
    closeFamilyOptionsDetails();
    text(document.getElementById("qb-family-edit-tree-status"), "");
    fetch("/api/family/tree_links", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Failed");
        renderEditTreeEditor(x.b.members || []);
        openModal("qb-family-edit-tree-modal");
      })
      .catch(function (err) {
        familyFlash(err.message || "Could not load tree data", "error");
      });
  }

  function openFamilyNaturalEditor(memberId) {
    if (!memberId || isNaN(memberId)) return;
    closeFamilyOptionsDetails();
    text(document.getElementById("qb-fne-status"), "");
    fetch("/api/family/tree_links", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Failed");
        var members = x.b.members || [];
        var candidates = x.b.nuclear_parent_candidates || [];
        var m = members.find(function (row) {
          return parseInt(String(row.id), 10) === memberId;
        });
        if (!m) throw new Error("Member not found");
        fneMemberSnapshot = m;
        var idEl = document.getElementById("qb-fne-member-id");
        if (idEl) idEl.value = String(memberId);
        text(document.getElementById("qb-fne-member-name"), m.member_name || "—");
        var relSel = document.getElementById("qb-fne-relationship");
        fillNestedRelationshipSelect(relSel, {
          includeSelf: true,
          presetValue: (m.reference_relation && String(m.reference_relation)) || "",
        });
        if (relSel && !relSel.value && m.relationship) {
          if ([].some.call(relSel.options, function (o) { return o.value === m.relationship; })) {
            relSel.value = m.relationship;
          }
        }
        var otherSel = document.getElementById("qb-fne-other");
        populateNuclearParentSelect(
          otherSel,
          candidates,
          memberId,
          otherPersonSelectValueFromMember(m),
          true
        );
        openModal("qb-family-edit-parents-modal");
      })
      .catch(function (err) {
        familyFlash(err.message || "Could not open editor", "error");
      });
  }

  function openFamilyTreeAddModal(presetRelationship, slotLabel, placeholderMemberId) {
    closeFamilyOptionsDetails();
    var form = document.getElementById("qb-family-tree-add-form");
    if (form) form.reset();
    var prEl = document.getElementById("qb-fta-preset-relationship");
    if (prEl) prEl.value = presetRelationship || "";
    var phEl = document.getElementById("qb-fta-placeholder-id");
    if (phEl) phEl.value = placeholderMemberId != null && placeholderMemberId !== "" ? String(placeholderMemberId) : "";
    text(
      document.getElementById("qb-fta-slot-hint"),
      slotLabel ? "Adding to tree: " + slotLabel : ""
    );
    var relSel = document.getElementById("qb-fta-relationship");
    fillNuclearTreeRelationshipSelect(relSel, presetRelationship || "");
    text(document.getElementById("qb-fta-status"), "");
    openModal("qb-family-tree-add-modal");
  }

  function loadConnections(type) {
    if (type === "family") {
      // Family panel is driven by /api/family/* endpoints — only initialise here.
      loadFamilyProfile();
      return;
    }
    var ul = document.getElementById("qb-social-list");
    var empty = document.getElementById("qb-social-empty");
    if (!ul) return;
    fetch("/api/connections?type=" + encodeURIComponent(type), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error(x.b.error || "connections failed");
        var rows = x.b.connections || [];
        ul.innerHTML = "";
        if (empty) empty.hidden = rows.length > 0;
        rows.forEach(function (item) {
          // The social tab supports removing a connection. Surface request_id
          // so the Remove button below can target the right row.
          var entry = Object.assign({}, item, { id: item.request_id || item.id });
          ul.appendChild(renderConnectionItem(entry, { removable: true }));
        });
      })
      .catch(function () {
        ul.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          text(empty, "Could not load " + connectionTypeLabel(type).toLowerCase() + " connections.");
        }
      });
  }

  function loadIncomingRequests() {
    var ul = document.getElementById("qb-requests-list");
    var empty = document.getElementById("qb-requests-empty");
    if (!ul) return;
    fetch("/api/requests/incoming", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error(x.b.error || "requests failed");
        var rows = x.b.requests || [];
        ul.innerHTML = "";
        if (empty) empty.hidden = rows.length > 0;
        rows.forEach(function (item) {
          var li = renderConnectionItem(item);
          li.insertAdjacentHTML(
            "beforeend",
            '<div class="qb-request-actions">' +
              '<button type="button" class="qb-btn qb-btn-primary btn-sm qb-js-request-action" data-action="accept" data-request-id="' +
              escAttr(item.request_id) +
              '">Accept</button>' +
              '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-request-action" data-action="reject" data-request-id="' +
              escAttr(item.request_id) +
              '">Reject</button>' +
              "</div>"
          );
          ul.appendChild(li);
        });
      })
      .catch(function () {
        ul.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          text(empty, "Could not load incoming requests.");
        }
      });
  }

  function refreshPersonalData() {
    loadPersonalBoard();
    loadIncomingRequests();
    var fam = document.getElementById("qb-personal-stack-family");
    var soc = document.getElementById("qb-personal-stack-social");
    if (fam && !fam.hidden) loadConnections("family");
    if (soc && !soc.hidden) loadConnections("social");
  }

  var notificationMessages = [];

  function renderNotificationMenu() {
    var list = document.getElementById("qb-notification-list");
    var empty = document.getElementById("qb-notification-empty");
    if (!list) return;
    list.innerHTML = "";
    var totalCount =
      notificationItems.length + notificationMessages.length + notificationLinkRequests.length;
    if (empty) empty.hidden = totalCount > 0;
    notificationItems.forEach(function (item) {
      var li = document.createElement("li");
      li.className = "qb-notification-item";
      li.innerHTML =
        '<div><strong>' +
        escHtml(item.name || "") +
        "</strong></div>" +
        '<div class="small text-muted">' +
        escHtml(connectionTypeLabel(item.request_type)) +
        (item.relationship ? " · " + escHtml(item.relationship) : "") +
        "</div>" +
        '<div class="qb-notification-actions">' +
        '<button type="button" class="qb-btn qb-btn-primary btn-sm qb-js-notification-action" data-action="accept" data-request-id="' +
        escAttr(item.request_id) +
        '">Accept</button>' +
        '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-notification-action" data-action="reject" data-request-id="' +
        escAttr(item.request_id) +
        '">Reject</button>' +
        "</div>";
      list.appendChild(li);
    });
    notificationLinkRequests.forEach(function (lr) {
      var li = document.createElement("li");
      li.className = "qb-notification-item qb-notification-item--link";
      li.innerHTML =
        '<div><strong>Family account link</strong></div>' +
        '<div class="small text-muted">' +
        escHtml(lr.from_name || lr.from_public_id || "") +
        " wants to link you as " +
        escHtml(lr.relationship_label || "family") +
        "</div>" +
        '<div class="qb-notification-actions">' +
        '<button type="button" class="qb-btn qb-btn-primary btn-sm qb-js-link-request-action" data-action="accept" data-link-request-id="' +
        escAttr(String(lr.link_request_id)) +
        '">Accept</button>' +
        '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-link-request-action" data-action="reject" data-link-request-id="' +
        escAttr(String(lr.link_request_id)) +
        '">Reject</button>' +
        "</div>";
      list.appendChild(li);
    });
    notificationMessages.forEach(function (m) {
      var li = document.createElement("li");
      li.className = "qb-notification-item qb-notification-item--message" +
        (m.is_system ? " qb-notification-item--system" : "");
      li.innerHTML =
        '<div><strong>' +
        escHtml(m.subject || "(no subject)") +
        "</strong></div>" +
        '<div class="small text-muted">From ' +
        escHtml(m.sender_name || "Qumanity") +
        "</div>" +
        '<div class="qb-notification-msg-preview small">' +
        escHtml((m.preview || "").slice(0, 220)) +
        (m.preview && m.preview.length > 220 ? "…" : "") +
        "</div>" +
        '<div class="qb-notification-actions">' +
        '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-notification-msg-read" data-message-id="' +
        escAttr(m.message_id) +
        '">Mark as read</button>' +
        "</div>";
      list.appendChild(li);
    });
  }

  function updateNotificationBadge() {
    var badge = document.getElementById("qb-notification-badge");
    if (!badge) return;
    var count =
      notificationItems.length + notificationMessages.length + notificationLinkRequests.length;
    badge.hidden = count === 0;
    badge.textContent = count > 9 ? "+9" : String(count);
  }

  function fetchNotifications() {
    return fetch("/api/notifications/unread", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error(x.b.error || "notifications failed");
        notificationItems = (x.b && x.b.requests) || [];
        notificationMessages = (x.b && x.b.messages) || [];
        notificationLinkRequests = (x.b && x.b.link_requests) || [];
        updateNotificationBadge();
        renderNotificationMenu();
      })
      .catch(function () {
        notificationItems = [];
        notificationMessages = [];
        notificationLinkRequests = [];
        updateNotificationBadge();
        renderNotificationMenu();
      });
  }

  function setNotificationMenu(open) {
    var menu = document.getElementById("qb-notification-menu");
    var btn = document.getElementById("qb-notification-btn");
    if (!menu || !btn) return;
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) fetchNotifications();
  }

  function loadCollectiveBoard(locationId, scope) {
    var ul = document.getElementById("qb-public-feed");
    var empty = document.getElementById("qb-public-feed-empty");
    if (!locationId || !scope || !ul) return;
    activeBoardLocationId = locationId;
    activeBoardScope = scope;
    setBoardHeading(scope);
    updatePostFormVisibility();
    fetchJson(
      "/api/collective_board?level=" +
        encodeURIComponent(scope) +
        "&location_id=" +
        encodeURIComponent(locationId) +
        "&state=" +
        encodeURIComponent(activeBoardState)
    )
      .then(function (x) {
        if (!x.ok) throw new Error(x.body.error || "feed failed");
        var posts = x.body.posts || [];
        ul.innerHTML = "";
        if (!posts.length) {
          if (empty) empty.hidden = false;
          return;
        }
        if (empty) empty.hidden = true;
        posts.forEach(function (p) {
          ul.appendChild(renderPost(p, activeBoardState));
        });
      })
      .catch(function (err) {
        if (ul) ul.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          text(empty, err.message || "Could not load Collective Board posts for this level.");
        }
        console.error("CVB load failed:", err);
      });
  }

  document.querySelectorAll(".qb-board-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      if (tab.classList.contains("qb-js-personal-board-tab")) return;
      activeBoardState = tab.getAttribute("data-board-state") || "live";
      document.querySelectorAll(".qb-board-tab").forEach(function (t) {
        if (t.classList.contains("qb-js-personal-board-tab")) return;
        var on = t === tab;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      loadCollectiveBoard(activeBoardLocationId, activeBoardScope);
    });
  });

  document.querySelectorAll(".qb-js-personal-board-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      activePersonalBoardState = tab.getAttribute("data-personal-board-state") || "live";
      document.querySelectorAll(".qb-js-personal-board-tab").forEach(function (t) {
        var on = t === tab;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      loadPersonalBoard();
    });
  });

  var qpVillageId = String((dashCfg && dashCfg.quantumPunchVillageId) || "").trim();
  var electionsEnabled = !!(dashCfg && dashCfg.electionsEnabled);
  var electionPanel = document.getElementById("qb-election-panel");
  var electionCouncilCard = document.getElementById("qb-election-council-card");
  var electionPausedBanner = document.getElementById("qb-election-paused-banner");

  function renderLeadershipSlots(panelId, payload) {
    var container = document.getElementById("qb-leadership-slots-" + panelId);
    var subtitle = document.getElementById("qb-leadership-subtitle-" + panelId);
    if (!container || !payload) return;
    if (subtitle) {
      text(subtitle, uiTr("quantum_punch_council_sub"));
    }
    container.innerHTML = "";
    var levelKey = String(payload.level_type || payload.level_label || "").toLowerCase();
    (payload.slots || []).forEach(function (slot) {
      var item = document.createElement("div");
      item.className = "qb-leadership-slot";
      item.setAttribute("role", "listitem");
      item.setAttribute("data-slot-rank", String(slot.hierarchy_rank || ""));
      var holderClass =
        slot.display_name === "Admin" ? "qb-leadership-slot-holder is-admin" : "qb-leadership-slot-holder";
      var appointHtml = "";
      if (payload.is_admin && slot.can_appoint && slot.display_name === "Vacant") {
        appointHtml =
          '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-leadership-appoint-btn" disabled title="Coming soon">' +
          escHtml(uiTr("appoint")) +
          "</button>";
      }
      var desig = String(slot.designation || "").toLowerCase();
      var roleLabel = uiTr(desig) || desig;
      var levelLabel = uiTr(levelKey) || payload.level_label || levelKey;
      var holderName =
        slot.display_name === "Admin"
          ? uiTr("admin")
          : slot.display_name === "Vacant"
            ? uiTr("vacant")
            : slot.display_name;
      item.innerHTML =
        '<span class="qb-leadership-slot-title">' +
        escHtml(levelLabel + " " + roleLabel) +
        "</span>" +
        '<span class="' +
        holderClass +
        '">' +
        escHtml(holderName) +
        "</span>" +
        appointHtml;
      container.appendChild(item);
    });
  }

  function loadLeadershipCouncil(panelId, levelType, locationId) {
    var lt = String(levelType || "").trim().toLowerCase();
    var lid = String(locationId || "").trim();
    if (!lt || !lid) return;
    var container = document.getElementById("qb-leadership-slots-" + panelId);
    if (container) {
      container.querySelectorAll(".qb-leadership-slot").forEach(function (el) {
        el.classList.add("qb-leadership-slot--loading");
      });
    }
    fetchJson("/api/leadership/" + encodeURIComponent(lt) + "/" + encodeURIComponent(lid))
      .then(function (x) {
        if (!x.ok) throw new Error((x.body && x.body.error) || "Leadership load failed");
        renderLeadershipSlots(panelId, x.body);
      })
      .catch(function (err) {
        if (container) {
          container.innerHTML =
            '<p class="small text-muted mb-0">' + escHtml(err.message || "Could not load council") + "</p>";
        }
      });
  }

  function manifestLines(m) {
    m = m || {};
    var parts = [];
    if (m.why_stand) parts.push("Why stand: " + m.why_stand);
    if (m.changes) parts.push("Changes: " + m.changes);
    if (m.text) parts.push(m.text);
    return parts.join("\n\n");
  }

  function electionPhaseLabel(ph) {
    var labels = {
      nomination: "Nomination open",
      voting: "Voting open",
      closed: "Results announced",
      upcoming: "Upcoming",
    };
    return labels[ph] || ph || "—";
  }

  function openElectionHistoryModal() {
    var nom = document.getElementById("qb-election-history-nominations");
    var vot = document.getElementById("qb-election-history-votes");
    var win = document.getElementById("qb-election-history-winners");
    fetch("/api/election/history", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        var empty = "No data available";
        if (nom) {
          text(
            nom,
            x.b && x.b.past_nominations && x.b.past_nominations.length
              ? "Records will appear here."
              : empty
          );
        }
        if (vot) {
          text(
            vot,
            x.b && x.b.past_voting_results && x.b.past_voting_results.length
              ? "Records will appear here."
              : empty
          );
        }
        if (win) {
          text(
            win,
            x.b && x.b.past_winners && x.b.past_winners.length
              ? "Records will appear here."
              : empty
          );
        }
        openModal("qb-election-history-modal");
      })
      .catch(function () {
        if (nom) text(nom, "No data available");
        if (vot) text(vot, "No data available");
        if (win) text(win, "No data available");
        openModal("qb-election-history-modal");
      });
  }

  function renderElectionCandidateProfiles(cands) {
    var wrap = document.getElementById("qb-election-candidate-profiles");
    var ul = document.getElementById("qb-election-candidate-profiles-list");
    if (!wrap || !ul) return;
    ul.innerHTML = "";
    var list = cands || [];
    if (!list.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    list.forEach(function (c) {
      var li = document.createElement("li");
      li.className = "qb-election-profile-card mb-3 pb-3 border-bottom border-secondary";
      var nm = escHtml(((c.first_name || "") + " " + (c.last_name || "")).trim());
      var body = manifestLines(c.manifest);
      li.innerHTML =
        "<div><strong>" +
        nm +
        "</strong> <span class='badge bg-secondary'>" +
        escHtml(c.gender || "") +
        "</span></div>" +
        "<div class='small text-muted mt-1'>Age: " +
        escHtml(c.age == null ? "—" : String(c.age)) +
        " · " +
        escHtml(c.age_group || "") +
        " · Karma: " +
        escHtml(c.karma_index == null ? "0" : String(c.karma_index)) +
        " · Wallet: " +
        escHtml(c.wallet_balance == null ? "0" : String(c.wallet_balance)) +
        " Karma Points</div>" +
        "<div class='small mt-1 text-muted'>" +
        escHtml(body).replace(/\n/g, "<br/>") +
        "</div>";
      ul.appendChild(li);
    });
  }

  function loadPrivateElectionAdminPanel() {
    if (!dashCfg.isAdmin) return;
    var cycleLine = document.getElementById("qb-private-election-cycle-line");
    var phaseLine = document.getElementById("qb-private-election-phase-line");
    var nomBtn = document.getElementById("qb-admin-manage-nominations-btn");
    fetchJson("/api/election/status")
      .then(function (x) {
        if (!x.ok) throw new Error((x.body && x.body.error) || "Load failed");
        var disp = x.body.election_display || {};
        var ap = x.body.active_period;
        var zodiac =
          (disp.zodiac_sign || (ap && ap.zodiac_sign) || (x.body.cycle && x.body.cycle.zodiac_sign) || "—");
        var ph = disp.phase || (x.body.cycle && x.body.cycle.status) || x.body.phase || "—";
        if (cycleLine) {
          text(cycleLine, "Current zodiac cycle: " + zodiac);
        }
        if (phaseLine) {
          phaseLine.textContent =
            "Phase: " +
            (disp.status_label || electionPhaseLabel(ph)) +
            (disp.current_phase_window ? " · " + disp.current_phase_window : "");
        }
        if (nomBtn) {
          nomBtn.hidden = !x.body.user_in_target_village;
        }
      })
      .catch(function (err) {
        if (cycleLine) text(cycleLine, err.message || "Could not load election status");
        if (phaseLine) text(phaseLine, "");
        console.error("Election admin status failed:", err);
      });
  }

  function renderElectionCouncil(data) {
    var kingEl = document.getElementById("qb-election-king-line");
    var queenEl = document.getElementById("qb-election-queen-line");
    var upEl = document.getElementById("qb-election-upcoming-line");
    var listEl = document.getElementById("qb-election-council-zodiac-list");
    if (!kingEl || !data) return;
    if (data.paused) {
      kingEl.innerHTML = "";
      queenEl.innerHTML = "";
      if (upEl) text(upEl, data.message || "");
      if (listEl) listEl.innerHTML = "";
      return;
    }
    var k = data.nayak || data.king;
    var q = data.nayika || data.queen;
    kingEl.innerHTML = k
      ? "<strong>Nayak</strong> (current sign, male leader): " +
        escHtml(k.name || "") +
        " — " +
        escHtml(k.zodiac_sign || "")
      : "<strong>Nayak</strong>: —";
    queenEl.innerHTML = q
      ? "<strong>Nayika</strong> (current sign, female leader): " +
        escHtml(q.name || "") +
        " — " +
        escHtml(q.zodiac_sign || "")
      : "<strong>Nayika</strong>: —";
    var up = data.upcoming_election;
    upEl.innerHTML = up
      ? "Upcoming: <strong>" +
        escHtml(up.zodiac_sign || "") +
        "</strong> — starts in " +
        String(up.days_until != null ? up.days_until : "—") +
        " day(s)."
      : "";
    if (listEl) {
      listEl.innerHTML = "";
      (data.members || []).forEach(function (row) {
        var li = document.createElement("li");
        li.className = "qb-election-council-zodiac-item";
        var hl = row.is_current_king || row.is_current_queen ? " is-active-zodiac" : "";
        var m = row.male;
        var f = row.female;
        var mn = m ? escHtml(m.name) + " <span class='font-monospace'>" + escHtml(m.public_id || "") + "</span>" : "—";
        var fn = f ? escHtml(f.name) + " <span class='font-monospace'>" + escHtml(f.public_id || "") + "</span>" : "—";
        li.innerHTML =
          "<div class='qb-election-council-row" +
          hl +
          "'><strong>" +
          escHtml(row.zodiac_sign || "") +
          "</strong><span class='qb-election-council-pair'><span class='text-muted'>M</span> " +
          mn +
          "</span><span class='qb-election-council-pair'><span class='text-muted'>F</span> " +
          fn +
          "</span></div>";
        listEl.appendChild(li);
      });
    }
  }

  function renderElectionStatus(payload) {
    var stEl = document.getElementById("qb-election-status-line");
    var phaseWin = document.getElementById("qb-election-phase-window");
    var nextPh = document.getElementById("qb-election-next-phase");
    var histBtn = document.getElementById("qb-election-history-btn");
    var profWrap = document.getElementById("qb-election-candidate-profiles");
    var nom = document.getElementById("qb-election-nomination-block");
    var vot = document.getElementById("qb-election-voting-block");
    var post = document.getElementById("qb-election-postvote-block");
    var postTxt = document.getElementById("qb-election-postvote-text");
    var closedB = document.getElementById("qb-election-closed-block");
    var closedTxt = document.getElementById("qb-election-closed-text");
    var bad = document.getElementById("qb-election-ineligible");
    if (!stEl) return;
    if (payload && (payload.paused || payload.elections_enabled === false)) {
      if (electionPanel) electionPanel.hidden = true;
      if (electionCouncilCard) electionCouncilCard.hidden = true;
      if (electionPausedBanner) electionPausedBanner.hidden = false;
      text(
        stEl,
        payload.message ||
          "Elections are currently paused. They will resume during the Gemini month. Please check back later."
      );
      return;
    }
    if (electionPausedBanner) electionPausedBanner.hidden = true;
    if (electionPanel) electionPanel.hidden = false;
    if (nom) nom.hidden = true;
    if (vot) vot.hidden = true;
    if (post) post.hidden = true;
    if (closedB) closedB.hidden = true;
    if (bad) bad.hidden = true;
    if (profWrap) profWrap.hidden = true;
    var ap = payload.active_period;
    var ph = (payload.cycle && payload.cycle.status) || payload.phase || "";
    var disp = payload.election_display || {};
    var zodiac =
      (disp.zodiac_sign || (ap && ap.zodiac_sign) || (payload.cycle && payload.cycle.zodiac_sign) || "");
    var statusLabel = disp.status_label || electionPhaseLabel(ph);
    var line = zodiac
      ? "Status: <strong>" +
        escHtml(statusLabel) +
        "</strong> · Zodiac: <strong>" +
        escHtml(zodiac) +
        "</strong>"
      : "No active zodiac cycle for the prototype calendar (outside 2026 windows).";
    stEl.innerHTML = line;
    if (phaseWin) {
      if (disp.current_phase_window) {
        phaseWin.hidden = false;
        text(phaseWin, disp.current_phase_window);
      } else {
        phaseWin.hidden = true;
        text(phaseWin, "");
      }
    }
    if (nextPh) {
      if (disp.next_phase_label && disp.next_phase_start_display) {
        nextPh.hidden = false;
        text(
          nextPh,
          disp.next_phase_label +
            " opens: " +
            disp.next_phase_start_display
        );
      } else {
        nextPh.hidden = true;
        text(nextPh, "");
      }
    }
    if (histBtn) {
      histBtn.hidden = !payload.user_in_target_village;
    }
    if (!payload.user_in_target_village) {
      if (bad) {
        bad.hidden = false;
        text(bad, "Elections apply to residents of Rohini Sector‑24 only.");
      }
      return;
    }
    if (ph === "closed" && payload.cycle) {
      if (closedB) closedB.hidden = false;
      var mw = payload.cycle.male_winner_private_id || "—";
      var fw = payload.cycle.female_winner_private_id || "—";
      if (closedTxt) {
        text(closedTxt, "Results: Male head: " + mw + " · Female head: " + fw);
      }
    } else {
      var canVote = !!payload.eligible_to_vote;
      var canNom = !!payload.eligible_to_nominate;
      if (!canVote && !canNom && bad) {
        bad.hidden = false;
        var ag = payload.user_age_group || "";
        if (ph === "nomination" && ag && ag !== "Yuvak") {
          text(
            bad,
            "Only Yuvak residents (ages 25–49) may stand for election. Your life stage: " + ag + "."
          );
        } else if (ph === "voting" && payload.user_age != null && payload.user_age < 13) {
          text(bad, "You must be at least 13 years old to vote in village elections.");
        } else if (payload.voting_ineligible_message) {
          text(bad, payload.voting_ineligible_message);
        } else {
          text(
            bad,
            "Voting is open only to " +
              (payload.cycle_element || "matching") +
              " sign members for this election."
          );
        }
      }
    }
    var nomDone = document.getElementById("qb-election-nomination-done");
    if (nomDone) nomDone.hidden = true;
    if (ph === "nomination" && payload.eligible_to_nominate && !payload.user_is_candidate) {
      if (nom) nom.hidden = false;
    } else if (ph === "nomination" && payload.user_is_candidate) {
      if (nomDone) nomDone.hidden = false;
      if (nomDone) {
        text(
          nomDone,
          payload.cycle && String(payload.cycle.status || "") === "nomination"
            ? "Your nomination is pending admin approval for this zodiac cycle."
            : "Your nomination has been submitted for this zodiac cycle."
        );
      }
    }
    if (ph === "voting" && payload.user_in_target_village) {
      renderElectionCandidateProfiles(payload.candidates || []);
    }
    if (ph === "voting" && payload.eligible_to_vote) {
      if (vot) vot.hidden = false;
      var vm = document.getElementById("qb-election-male-list");
      var vf = document.getElementById("qb-election-female-list");
      var vmSel = payload.votes_for_user && payload.votes_for_user.Male;
      var vfSel = payload.votes_for_user && payload.votes_for_user.Female;
      function fillList(ul, gender, selPid, cands) {
        if (!ul) return;
        ul.innerHTML = "";
        var list = (cands || []).filter(function (c) { return c.gender === gender; });
        if (!list.length) {
          ul.innerHTML = "<li class='text-muted'>No candidates yet.</li>";
          return;
        }
        list.forEach(function (c) {
          var li = document.createElement("li");
          li.className = "qb-election-cand";
          var id = "qb-ev-" + gender + "-" + escAttr(c.candidate_private_id);
          var checked = selPid === c.candidate_private_id ? " checked" : "";
          var dis = selPid ? " disabled" : "";
          var body = manifestLines(c.manifest);
          li.innerHTML =
            "<label class='qb-election-cand-label'>" +
            "<input type='radio' name='qb-vote-" +
            gender +
            "' value='" +
            escAttr(c.candidate_private_id) +
            "' class='qb-election-radio' data-gender='" +
            escAttr(gender) +
            "'" +
            checked +
            dis +
            " />" +
            "<span class='qb-election-cand-name'>" +
            escHtml((c.first_name || "") + " " + (c.last_name || "")).trim() +
            "</span>" +
            "<span class='small text-muted d-block'>Age " +
            escHtml(c.age == null ? "—" : String(c.age)) +
            " · " +
            escHtml(c.gender || "") +
            " · Karma " +
            escHtml(c.karma_index == null ? "0" : String(c.karma_index)) +
            " · " +
            escHtml(c.wallet_balance == null ? "0" : String(c.wallet_balance)) +
            " Karma Points</span>" +
            "<div class='qb-election-manifest small text-muted'>" +
            escHtml(body).replace(/\n/g, "<br/>") +
            "</div></label>";
          ul.appendChild(li);
        });
      }
      fillList(vm, "Male", vmSel, payload.candidates);
      fillList(vf, "Female", vfSel, payload.candidates);
      var vsub = document.getElementById("qb-election-vote-submit");
      var hasM = document.querySelectorAll("input.qb-election-radio[name='qb-vote-Male']").length > 0;
      var hasF = document.querySelectorAll("input.qb-election-radio[name='qb-vote-Female']").length > 0;
      if (vsub) {
        vsub.hidden = !!(vmSel && vfSel);
        if (!vsub.hidden) {
          var hm0 = document.querySelector("input[name='qb-vote-Male']:checked");
          var hf0 = document.querySelector("input[name='qb-vote-Female']:checked");
          var needM = hasM && !vmSel;
          var needF = hasF && !vfSel;
          vsub.disabled = (needM && !hm0) || (needF && !hf0);
        }
      }
      if (vmSel || vfSel) {
        if (post) post.hidden = false;
        if (postTxt) {
          postTxt.innerHTML =
            "You have voted" +
            (vmSel ? " · Male" : "") +
            (vfSel ? " · Female" : "") +
            ".";
        }
      }
      document.querySelectorAll(".qb-election-radio").forEach(function (r) {
        r.addEventListener("change", function () {
          var vsub2 = document.getElementById("qb-election-vote-submit");
          if (!vsub2 || vsub2.hidden) return;
          var hm = document.querySelector("input[name='qb-vote-Male']:checked");
          var hf = document.querySelector("input[name='qb-vote-Female']:checked");
          var hmCount = document.querySelectorAll("input.qb-election-radio[name='qb-vote-Male']").length;
          var hfCount = document.querySelectorAll("input.qb-election-radio[name='qb-vote-Female']").length;
          var needM = hmCount > 0 && !vmSel;
          var needF = hfCount > 0 && !vfSel;
          vsub2.disabled = (needM && !hm) || (needF && !hf);
        });
      });
    }
  }

  function syncVillageHubPanel(locationId, scope) {
    var hub = document.getElementById("qb-village-hub-panel");
    if (!hub) return;
    var show =
      !!dashCfg.commerceEnabled &&
      scope === "village" &&
      qpVillageId &&
      String(locationId || "").trim() === qpVillageId;
    hub.hidden = !show;
    if (show) {
      loadVillageHubStatus();
      loadKarmaTypes();
      loadKarmaPending();
    }
  }

  function loadVillageHubStatus() {
    fetch("/api/village/hub-status", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var councilPanel = document.getElementById("qb-village-council-approvals");
        if (councilPanel) {
          councilPanel.hidden = !x.b.is_council;
          if (x.b.is_council) {
            loadCouncilKarmaClaims();
            loadCouncilBusinessPending();
          }
        }
      })
      .catch(function () {});
  }

  function loadCouncilKarmaClaims() {
    fetch("/api/karma/claims/pending", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var ul = document.getElementById("qb-council-karma-list");
        if (!ul) return;
        ul.innerHTML = "";
        (x.b.claims || []).forEach(function (c) {
          var li = document.createElement("li");
          li.className = "mb-2 pb-2 border-bottom border-secondary";
          li.innerHTML =
            "<strong>" +
            escHtml(c.action_label || c.action_code) +
            "</strong> · " +
            escHtml(c.first_name + " " + c.last_name) +
            " <button type='button' class='qb-btn qb-btn-outline btn-sm ms-1' data-karma-approve='" +
            c.id +
            "'>Approve</button> <button type='button' class='qb-btn qb-btn-link btn-sm' data-karma-reject='" +
            c.id +
            "'>Reject</button>";
          ul.appendChild(li);
        });
        ul.querySelectorAll("[data-karma-approve]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            reviewKarmaClaim(btn.getAttribute("data-karma-approve"), "approved");
          });
        });
        ul.querySelectorAll("[data-karma-reject]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            reviewKarmaClaim(btn.getAttribute("data-karma-reject"), "rejected");
          });
        });
      });
  }

  function reviewKarmaClaim(id, status) {
    fetch("/api/karma/claims/" + id + "/review", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ status: status }),
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Review failed");
        loadCouncilKarmaClaims();
        loadKarmaPending();
      })
      .catch(function (err) {
        alert(err.message || "Review failed");
      });
  }

  function loadCouncilBusinessPending() {
    fetch("/api/businesses/pending", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var ul = document.getElementById("qb-council-business-list");
        if (!ul) return;
        ul.innerHTML = "";
        (x.b.businesses || []).forEach(function (b) {
          var li = document.createElement("li");
          li.className = "mb-2 pb-2 border-bottom border-secondary";
          li.innerHTML =
            "<strong>" +
            escHtml(b.business_name) +
            "</strong> (" +
            escHtml(b.business_type) +
            ") · " +
            escHtml(b.first_name + " " + b.last_name) +
            " <button type='button' class='qb-btn qb-btn-outline btn-sm ms-1' data-biz-approve='" +
            b.id +
            "'>Approve</button>";
          ul.appendChild(li);
        });
        ul.querySelectorAll("[data-biz-approve]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            fetch("/api/businesses/" + btn.getAttribute("data-biz-approve") + "/review", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({ status: "approved" }),
            }).then(function () {
              loadCouncilBusinessPending();
            });
          });
        });
      });
  }

  function openVillageServicesModal() {
    var activeTab = document.querySelector(".qb-js-public-tab.is-active");
    var lid = activeTab ? activeTab.getAttribute("data-location-id") || "" : "";
    var sc = activeTab ? activeTab.getAttribute("data-scope") || "" : "";
    syncVillageHubPanel(lid, sc);
    openModal("qb-village-services-modal");
  }

  function openElectionsModal() {
    if (!electionsEnabled) {
      if (electionPausedBanner) electionPausedBanner.hidden = false;
      if (electionPanel) electionPanel.hidden = true;
      if (electionCouncilCard) electionCouncilCard.hidden = true;
      openModal("qb-elections-modal");
      return;
    }
    var activeTab = document.querySelector(".qb-js-public-tab.is-active");
    var lid = activeTab ? activeTab.getAttribute("data-location-id") || "" : qpVillageId;
    var sc = activeTab ? activeTab.getAttribute("data-scope") || "village" : "village";
    loadQuantumElectionUi(lid, sc);
    openModal("qb-elections-modal");
  }

  function loadQuantumElectionUi(locationId, scope) {
    if (!electionPanel) return;
    if (!electionsEnabled) {
      if (electionPausedBanner) electionPausedBanner.hidden = false;
      electionPanel.hidden = true;
      if (electionCouncilCard) electionCouncilCard.hidden = true;
      fetchJson("/api/election/status")
        .then(function (x) {
          if (x.ok && x.body) renderElectionStatus(x.body);
        })
        .catch(function () {});
      return;
    }
    if (electionPausedBanner) electionPausedBanner.hidden = true;
    if (!qpVillageId) return;
    if (scope !== "village" || String(locationId || "").trim() !== qpVillageId) {
      electionPanel.hidden = true;
      if (electionCouncilCard) electionCouncilCard.hidden = true;
      return;
    }
    electionPanel.hidden = false;
    if (electionCouncilCard) electionCouncilCard.hidden = false;
    fetchJson("/api/election/status")
      .then(function (x) {
        if (!x.ok) throw new Error((x.body && x.body.error) || "Election status failed");
        renderElectionStatus(x.body);
        if (dashCfg.isAdmin) loadPrivateElectionAdminPanel();
      })
      .catch(function (err) {
        text(document.getElementById("qb-election-status-line"), err.message || "Could not load election status");
        console.error("Election status failed:", err);
      });
    fetchJson("/api/election/council")
      .then(function (x) {
        if (!x.ok) return;
        renderElectionCouncil(x.body);
      })
      .catch(function () {});
  }

  var nomForm = document.getElementById("qb-election-nominate-form");
  if (nomForm) {
    nomForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var why = ((document.getElementById("qb-election-why") || {}).value || "").trim();
      var ch = ((document.getElementById("qb-election-changes") || {}).value || "").trim();
      var msg = document.getElementById("qb-election-nominate-msg");
      text(msg, "Saving…");
      fetch("/api/election/nominate", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ why_stand: why, changes: ch }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Nomination failed");
          var nomBlock = document.getElementById("qb-election-nomination-block");
          var nomDoneEl = document.getElementById("qb-election-nomination-done");
          alert(
            "Your nomination has been submitted successfully and is pending admin approval. You cannot submit again for this zodiac cycle."
          );
          if (nomBlock) nomBlock.hidden = true;
          if (nomDoneEl) nomDoneEl.hidden = false;
          text(msg, "");
          loadQuantumElectionUi(qpVillageId, "village");
        })
        .catch(function (err) {
          var errMsg = err.message || "Error";
          alert(errMsg);
          text(msg, errMsg);
        });
    });
  }

  var voteBtn = document.getElementById("qb-election-vote-submit");
  if (voteBtn) {
    voteBtn.addEventListener("click", function () {
      var msg = document.getElementById("qb-election-vote-msg");
      text(msg, "Submitting…");
      var hm = document.querySelector("input[name='qb-vote-Male']:checked");
      var hf = document.querySelector("input[name='qb-vote-Female']:checked");
      var jobs = [];
      if (hm) {
        jobs.push(
          fetch("/api/election/vote", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({
              candidate_private_id: hm.value,
              gender: "Male",
            }),
          }).then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
        );
      }
      if (hf) {
        jobs.push(
          fetch("/api/election/vote", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({
              candidate_private_id: hf.value,
              gender: "Female",
            }),
          }).then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
        );
      }
      Promise.all(jobs)
        .then(function (results) {
          for (var i = 0; i < results.length; i++) {
            if (!results[i].ok) throw new Error((results[i].b && results[i].b.error) || "Vote failed");
          }
          text(msg, "Votes recorded.");
          loadQuantumElectionUi(qpVillageId, "village");
        })
        .catch(function (err) {
          text(msg, err.message || "Error");
        });
    });
  }

  var publicTabs = document.querySelectorAll(".qb-js-public-tab");
  if (publicTabs.length) {
    function activatePublicTab(tab) {
      publicTabs.forEach(function (t) {
        var on = t === tab;
        t.classList.toggle("is-active", on);
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      var lid = tab.getAttribute("data-location-id") || "";
      var sc = tab.getAttribute("data-scope") || "";
      var statsBtn = document.getElementById("qb-public-location-stats-link");
      if (statsBtn) {
        var showStats =
          dashCfg.showPublicLocationStatistics &&
          (sc === "village" ||
            sc === "tehsil" ||
            sc === "district" ||
            sc === "state") &&
          lid;
        statsBtn.hidden = !showStats;
        if (showStats) {
          statsBtn.href = buildLocationStatsUrl(sc, lid);
        }
      }
      var svcBtn = document.getElementById("qb-village-services-btn");
      if (svcBtn) {
        var scopeKey = tab.getAttribute("data-scope") || "";
        var svcWord = uiTr("services");
        svcBtn.textContent = scopeKey ? uiTr(scopeKey) + " " + svcWord : svcWord;
      }
      loadCollectiveBoard(lid, sc);
      loadLeadershipCouncil("public", sc, lid);
      if (window.qbPlanetary && window.qbPlanetary.onLocationTabChange) {
        window.qbPlanetary.onLocationTabChange(lid, sc, "public");
      }
    }
    publicTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activatePublicTab(tab);
      });
    });
    var first =
      Array.prototype.find.call(publicTabs, function (t) {
        return t.classList.contains("is-active");
      }) || publicTabs[0];
    activatePublicTab(first);
  }

  var postForm = document.querySelector(".qb-js-post-form");
  var postLocationInput = document.querySelector(".qb-js-post-location-id");
  var postContent = document.querySelector(".qb-js-post-content");
  var postStatus = document.querySelector(".qb-js-post-status");

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.hidden = false;
    var focusEl = modal.querySelector("textarea, button, input");
    if (focusEl) focusEl.focus();
  }

  function closeModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.hidden = true;
  }

  document.querySelectorAll("[data-qb-close-modal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      closeModal(btn.getAttribute("data-qb-close-modal"));
    });
  });

  document.querySelectorAll(".qb-modal-backdrop").forEach(function (modal) {
    modal.addEventListener("click", function (ev) {
      if (ev.target === modal) closeModal(modal.id);
    });
  });

  var notificationBtn = document.getElementById("qb-notification-btn");
  if (notificationBtn) {
    notificationBtn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var menu = document.getElementById("qb-notification-menu");
      setNotificationMenu(menu ? menu.hidden : true);
    });
  }
  document.addEventListener("click", function (ev) {
    var wrap = ev.target.closest(".qb-notification-wrap");
    if (!wrap) setNotificationMenu(false);
  });
  fetchNotifications();
  window.setInterval(fetchNotifications, 30000);

  var newPostOpen = document.getElementById("qb-new-post-open");
  if (newPostOpen) {
    newPostOpen.addEventListener("click", function () {
      text(postStatus, "");
      openModal("qb-new-post-modal");
    });
  }

  document.querySelectorAll(".qb-js-connection-open").forEach(function (btn) {
    btn.addEventListener("click", function () {
      resetAndOpenConnectionModal(btn.getAttribute("data-connection-type") || "social", {});
    });
  });

  function checkConnectionStatusForSelected() {
    if (!selectedConnectionUser) return;
    var type = (document.getElementById("qb-connection-type") || {}).value || "social";
    var status = document.getElementById("qb-connection-status");
    var sendBtn = document.getElementById("qb-connection-send-btn");
    text(status, "Checking existing requests…");
    if (sendBtn) sendBtn.disabled = true;
    fetch(
      "/api/connection/status?target_public_id=" +
        encodeURIComponent(selectedConnectionUser.public_id || "") +
        "&type=" +
        encodeURIComponent(type),
      { credentials: "same-origin", headers: { Accept: "application/json" } }
    )
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "status check failed");
        var canSend = !!x.b.can_send;
        if (sendBtn) {
          sendBtn.disabled = !canSend;
          sendBtn.classList.toggle("is-disabled", !canSend);
        }
        text(status, x.b.message || "");
      })
      .catch(function (err) {
        if (sendBtn) sendBtn.disabled = false;
        text(status, err.message || "Could not verify request status");
      });
  }

  function selectConnectionTarget(u) {
    selectedConnectionUser = u;
    var selected = document.getElementById("qb-connection-selected");
    var actions = document.getElementById("qb-connection-actions");
    if (selected) {
      selected.hidden = false;
      selected.innerHTML =
        "<strong>Selected:</strong> " +
        escHtml(u.name || "") +
        " <span class='font-monospace'>" +
        escHtml(u.public_id || "") +
        "</span>";
    }
    if (actions) actions.hidden = false;
    checkConnectionStatusForSelected();
  }

  function searchConnectionUsers() {
    var type = (document.getElementById("qb-connection-type") || {}).value || "social";
    var q = ((document.getElementById("qb-connection-search") || {}).value || "").trim();
    var box = document.getElementById("qb-connection-suggestions");
    var status = document.getElementById("qb-connection-status");
    if (!box) return;
    if (q.length < 2) {
      box.innerHTML = "";
      text(status, "Enter at least 2 characters.");
      return;
    }
    text(status, "Searching...");
    fetch("/api/users/suggest?public_id_prefix=" + encodeURIComponent(q), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error(x.b.error || "Search failed");
        var users = x.b.users || [];
        box.innerHTML = "";
        text(status, users.length ? "Select a user to send a request." : "No matching users.");
        users.forEach(function (u) {
          var item = document.createElement("button");
          item.type = "button";
          item.className = "qb-connection-suggestion";
          item.setAttribute("data-public-id", u.public_id || "");
          item.innerHTML =
            "<strong>" +
            escHtml(u.name || "") +
            "</strong><span class='font-monospace'>" +
            escHtml(u.public_id || "") +
            "</span><small>" +
            escHtml([u.age ? "Age " + u.age : "", u.gender || "", u.location_name || ""].filter(Boolean).join(" · ")) +
            "</small>";
          item.addEventListener("click", function () {
            selectConnectionTarget(u);
          });
          box.appendChild(item);
        });
      })
      .catch(function (err) {
        box.innerHTML = "";
        text(status, err.message || "Search failed");
      });
  }

  var connSearchBtn = document.getElementById("qb-connection-search-btn");
  if (connSearchBtn) connSearchBtn.addEventListener("click", searchConnectionUsers);
  var connSearchInput = document.getElementById("qb-connection-search");
  if (connSearchInput) {
    var searchTimer = null;
    connSearchInput.addEventListener("input", function () {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(searchConnectionUsers, 250);
    });
    connSearchInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        searchConnectionUsers();
      }
    });
  }
  var relSelect = document.getElementById("qb-relationship-select");
  if (relSelect) {
    relSelect.addEventListener("change", function () {
      checkConnectionStatusForSelected();
    });
  }
  var connMemberTypeSel = document.getElementById("qb-connection-member-type");
  if (connMemberTypeSel) {
    connMemberTypeSel.addEventListener("change", function () {
      var ctype = (document.getElementById("qb-connection-type") || {}).value || "social";
      if (ctype === "family") {
        fillConnectionRelationshipSelect(connMemberTypeSel.value || "", {});
        var sendBtn = document.getElementById("qb-connection-send-btn");
        if (sendBtn && connMemberTypeSel.value === "nuclear") {
          sendBtn.disabled = false;
          sendBtn.classList.remove("is-disabled");
        }
        checkConnectionStatusForSelected();
      }
    });
  }
  var connSendBtn = document.getElementById("qb-connection-send-btn");
  if (connSendBtn) {
    connSendBtn.addEventListener("click", function () {
      var status = document.getElementById("qb-connection-status");
      var type = (document.getElementById("qb-connection-type") || {}).value || "social";
      var name = ((document.getElementById("qb-conn-member-name") || {}).value || "").trim();
      var ageRaw = (document.getElementById("qb-conn-member-age") || {}).value || "";
      var ageNum = ageRaw === "" || ageRaw == null ? null : parseInt(String(ageRaw), 10);
      if (ageNum != null && isNaN(ageNum)) ageNum = null;
      var genderVal = ((document.getElementById("qb-conn-member-gender") || {}).value || "").trim();
      var searchVal = ((document.getElementById("qb-connection-search") || {}).value || "").trim();

      if (type === "social") {
        if (!selectedConnectionUser) {
          text(status, "Select a user first.");
          return;
        }
        text(status, "Sending request...");
        fetch("/api/connection/request", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            public_id: selectedConnectionUser.public_id,
            request_type: "social",
            relationship: null,
          }),
        })
          .then(function (res) {
            return res.json().then(function (payload) {
              return { ok: res.ok, payload: payload };
            });
          })
          .then(function (result) {
            if (!result.ok) throw new Error(result.payload.error || "Request failed");
            text(status, "Connection request sent.");
            closeModal("qb-connection-modal");
          })
          .catch(function (err) {
            text(status, err.message || "Request failed");
          });
        return;
      }

      var mtEl = document.getElementById("qb-connection-member-type");
      var familyMemberType = (mtEl && mtEl.value) || "";
      if (!familyMemberType || (familyMemberType !== "nuclear" && familyMemberType !== "general")) {
        text(status, "Choose Family Member Type (Nuclear or General).");
        return;
      }
      if (!name) {
        text(status, "Name is required.");
        return;
      }
      var selectedRel = (document.getElementById("qb-relationship-select") || {}).value || "";
      if (!selectedRel) {
        text(status, "Choose a relationship.");
        return;
      }
      if (familyMemberType === "general") {
        if (!searchVal) {
          text(status, "Account ID is required for General Family.");
          return;
        }
        if (!selectedConnectionUser) {
          text(status, "Search and select a user with that Account ID.");
          return;
        }
      }
      if (familyMemberType === "nuclear" && !selectedConnectionUser) {
        text(status, "Saving…");
        fetch("/api/family/dashboard_add", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            member_name: name,
            age: ageNum,
            gender: genderVal,
            relationship: selectedRel,
            family_member_type: "nuclear",
            public_id: "",
          }),
        })
          .then(function (res) {
            return res.json().then(function (payload) {
              return { ok: res.ok, payload: payload };
            });
          })
          .then(function (result) {
            if (!result.ok) throw new Error(result.payload.error || "Save failed");
            text(status, "Family member added.");
            closeModal("qb-connection-modal");
            loadFamilyTree();
            loadFamilyAllMembers();
          })
          .catch(function (err) {
            text(status, err.message || "Save failed");
          });
        return;
      }
      if (!selectedConnectionUser) {
        text(status, "Search and select a user.");
        return;
      }
      text(status, "Sending request...");
      fetch("/api/connection/request", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          public_id: selectedConnectionUser.public_id,
          request_type: "family",
          relationship: selectedRel,
          family_member_type: familyMemberType,
          member_name: name,
          age: ageNum,
          gender: genderVal || null,
        }),
      })
        .then(function (res) {
          return res.json().then(function (payload) {
            return { ok: res.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok) throw new Error(result.payload.error || "Request failed");
          text(status, "Connection request sent.");
          closeModal("qb-connection-modal");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(status, err.message || "Request failed");
        });
    });
  }

  // --- Family form interactions ---

  var familyForm = document.getElementById("qb-family-form");
  if (familyForm) {
    familyForm.querySelectorAll('[name="relationship_status"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (radio.checked) updateFamilyFormFieldsForStatus(radio.value);
      });
    });
    familyForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      submitFamilyForm();
    });
  }

  var addSibBtn = document.getElementById("qb-family-add-sibling");
  if (addSibBtn) {
    addSibBtn.addEventListener("click", function () {
      var box = document.getElementById("qb-family-siblings");
      if (box) box.appendChild(makeSiblingRow());
    });
  }
  var addChildBtn = document.getElementById("qb-family-add-child");
  if (addChildBtn) {
    addChildBtn.addEventListener("click", function () {
      var box = document.getElementById("qb-family-children");
      if (box) box.appendChild(makeChildRow());
    });
  }

  // "Do you have children?" toggle (Married users) — show/hide the children list.
  document.addEventListener("change", function (ev) {
    if (
      ev.target &&
      ev.target.name === "has_children" &&
      ev.target.type === "radio"
    ) {
      var status = "unmarried";
      var radios = document.querySelectorAll('[name="relationship_status"]');
      radios.forEach(function (r) {
        if (r.checked) status = r.value;
      });
      updateFamilyFormFieldsForStatus(status);
    }
  });

  document.addEventListener("click", function (ev) {
    var famEditParents = ev.target.closest(".qb-js-family-edit-parents");
    if (famEditParents) {
      ev.preventDefault();
      ev.stopPropagation();
      var mid = famEditParents.getAttribute("data-member-id") || "";
      if (!mid) return;
      openFamilyNaturalEditor(parseInt(mid, 10));
      return;
    }
    var famMemEdit = ev.target.closest(".qb-js-family-member-edit");
    if (famMemEdit) {
      ev.preventDefault();
      openFamilyMemberEditFromButton(famMemEdit);
      return;
    }
    var slotAdd = ev.target.closest(".qb-js-family-slot-add");
    if (slotAdd) {
      ev.preventDefault();
      var preset = slotAdd.getAttribute("data-preset-relationship") || "";
      var sl = slotAdd.getAttribute("data-slot-label") || "";
      openFamilyTreeAddModal(preset, sl);
      return;
    }

    if (!ev.target.closest(".qb-family-node")) {
      closeAllFamilyNodeMenus();
    }

    var removeRowBtn = ev.target.closest(".qb-js-family-remove-row");
    if (removeRowBtn) {
      // Child rows are wrapped in a .qb-family-dynamic-block (carries the
      // spouse/grandchildren sub-rows). Sibling/etc. rows live in a plain
      // .qb-family-dynamic-row. Prefer the block so we tear the whole child
      // out, not just the name row.
      var block =
        removeRowBtn.closest(".qb-family-dynamic-block") ||
        removeRowBtn.closest(".qb-family-dynamic-row");
      if (block && block.parentElement) block.parentElement.removeChild(block);
      return;
    }
    var markDead = ev.target.closest(".qb-js-mark-dead");
    if (markDead) {
      ev.preventDefault();
      if (!window.confirm("Mark this person as deceased? Only an admin can reverse this.")) return;
      var src = markDead.getAttribute("data-source") || "form";
      var mid = markDead.getAttribute("data-id") || "";
      if (!mid) return;
      fetch("/api/family/mark_dead", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ id: parseInt(mid, 10), source: src }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Could not mark");
          familyFlash("Member marked as deceased.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) { familyFlash(err.message || "Could not mark", "error"); });
      return;
    }
    var removeFam = ev.target.closest(".qb-js-family-remove");
    if (removeFam) {
      ev.preventDefault();
      var src2 = removeFam.getAttribute("data-source") || "form";
      var mid2 = removeFam.getAttribute("data-id") || "";
      var name2 = removeFam.getAttribute("data-name") || "this family member";
      if (!mid2) return;
      var modeRm = removeFam.getAttribute("data-remove-mode") || "instant";
      if (modeRm === "request") {
        openFamilyRemovalRequestModal({
          source: src2,
          id: mid2,
          name: name2,
          relationship: removeFam.getAttribute("data-relationship") || "",
        });
        return;
      }
      if (!window.confirm("Remove " + name2 + "? This cannot be undone.")) return;
      fetch("/api/family/remove_member", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ id: parseInt(mid2, 10), source: src2 }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b, status: r.status }; }); })
        .then(function (x) {
          if (!x.ok) {
            if (x.status === 409 && x.b && x.b.requires_admin_approval) {
              openFamilyRemovalRequestModal({
                source: src2,
                id: mid2,
                name: name2,
                relationship: removeFam.getAttribute("data-relationship") || "",
              });
              return;
            }
            throw new Error((x.b && x.b.error) || "Could not remove");
          }
          familyFlash("Family member removed.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) { familyFlash(err.message || "Could not remove", "error"); });
      return;
    }

    var linkAccount = ev.target.closest(".qb-js-family-link-account");
    if (linkAccount) {
      ev.preventDefault();
      openFamilyLinkAccountModal({
        source: linkAccount.getAttribute("data-source") || "form",
        id: linkAccount.getAttribute("data-id") || "",
        name: linkAccount.getAttribute("data-name") || "",
        relationship: linkAccount.getAttribute("data-relationship") || "",
      });
      return;
    }

    var postDelete = ev.target.closest(".qb-js-post-delete");
    if (postDelete) {
      ev.preventDefault();
      handlePostDeleteClick(postDelete);
      return;
    }
    var socialRemove = ev.target.closest(".qb-js-social-remove");
    if (socialRemove) {
      ev.preventDefault();
      if (!window.confirm("Remove this social connection?")) return;
      var sid = socialRemove.getAttribute("data-request-id") || "";
      if (!sid) return;
      fetch("/api/connection/remove", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ connection_id: parseInt(sid, 10) }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Could not remove");
          loadConnections("social");
        })
        .catch(function (err) {
          window.alert(err.message || "Could not remove connection");
        });
      return;
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    var addBtn = ev.target.closest && ev.target.closest(".qb-js-family-slot-add");
    if (!addBtn) return;
    ev.preventDefault();
    var preset = addBtn.getAttribute("data-preset-relationship") || "";
    var sl = addBtn.getAttribute("data-slot-label") || "";
    openFamilyTreeAddModal(preset, sl);
  });

  // --- Add Grandparent modal ---
  // --- Post deletion (author 24h, or admin anytime) ---
  function handlePostDeleteClick(btn) {
    var postId = btn.getAttribute("data-post-id") || "";
    var mode = btn.getAttribute("data-mode") || "author";
    if (!postId) return;
    if (mode === "author") {
      if (!window.confirm(
        "Delete this post permanently? You can only delete your own post within 24 hours of posting."
      )) return;
      submitPostDeletion(postId, "");
    } else {
      openAdminPostDeleteModal(postId);
    }
  }

  function openAdminPostDeleteModal(postId) {
    var reasonEl = document.getElementById("qb-admin-delete-reason");
    var statusEl = document.getElementById("qb-admin-delete-status");
    var idEl = document.getElementById("qb-admin-delete-post-id");
    if (reasonEl) reasonEl.value = "";
    if (statusEl) text(statusEl, "");
    if (idEl) idEl.value = String(postId);
    openModal("qb-admin-delete-modal");
  }

  function submitPostDeletion(postId, reason) {
    var statusEl = document.getElementById("qb-admin-delete-status");
    fetch("/api/post/delete/" + encodeURIComponent(postId), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ reason: reason || "" }),
    })
      .then(function (r) {
        return r.json().then(function (b) { return { ok: r.ok, b: b }; });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Could not delete post");
        // Remove the post node from any board it appears in.
        document
          .querySelectorAll('[data-post-id="' + postId + '"]')
          .forEach(function (n) {
            if (n.parentElement) n.parentElement.removeChild(n);
          });
        closeModal("qb-admin-delete-modal");
        if (statusEl) text(statusEl, "");
      })
      .catch(function (err) {
        if (statusEl) text(statusEl, err.message || "Delete failed.");
        else window.alert(err.message || "Delete failed.");
      });
  }

  // --- Family removal request (after 2-day direct window) ---
  function openFamilyRemovalRequestModal(opts) {
    opts = opts || {};
    var idEl = document.getElementById("qb-family-removal-target-id");
    var srcEl = document.getElementById("qb-family-removal-target-source");
    var labelEl = document.getElementById("qb-family-removal-target-label");
    var reasonEl = document.getElementById("qb-family-removal-reason");
    var statusEl = document.getElementById("qb-family-removal-status");
    if (idEl) idEl.value = opts.id || "";
    if (srcEl) srcEl.value = opts.source || "";
    if (labelEl) {
      text(
        labelEl,
        (opts.name || "this family member") +
          (opts.relationship ? " (" + opts.relationship + ")" : "")
      );
    }
    if (reasonEl) reasonEl.value = "";
    if (statusEl) text(statusEl, "");
    openModal("qb-family-removal-request-modal");
  }

  // --- Link family member to an account via public_id ---
  var linkAccountContext = null;
  var linkAccountSuggestion = null;
  function openFamilyLinkAccountModal(opts) {
    opts = opts || {};
    linkAccountContext = {
      source: opts.source || "form",
      id: opts.id || "",
      name: opts.name || "",
      relationship: opts.relationship || "",
    };
    linkAccountSuggestion = null;
    var nameEl = document.getElementById("qb-family-link-target-name");
    var searchEl = document.getElementById("qb-family-link-public-id");
    var suggestionEl = document.getElementById("qb-family-link-suggestion");
    var sendBtn = document.getElementById("qb-family-link-send-btn");
    var statusEl = document.getElementById("qb-family-link-status");
    if (nameEl) text(nameEl, opts.name || "—");
    if (searchEl) searchEl.value = "";
    if (suggestionEl) suggestionEl.innerHTML = "";
    if (sendBtn) sendBtn.disabled = true;
    if (statusEl) text(statusEl, "");
    openModal("qb-family-link-modal");
  }

  function searchFamilyLinkTarget(prefix) {
    var suggestionEl = document.getElementById("qb-family-link-suggestion");
    var sendBtn = document.getElementById("qb-family-link-send-btn");
    if (sendBtn) sendBtn.disabled = true;
    linkAccountSuggestion = null;
    if (!suggestionEl) return;
    suggestionEl.innerHTML = "";
    if (!prefix || prefix.length < 2) return;
    fetch("/api/users/suggest?public_id_prefix=" + encodeURIComponent(prefix), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "search failed");
        var users = (x.b && x.b.users) || [];
        if (!users.length) {
          suggestionEl.innerHTML = '<div class="small text-muted">No matching accounts.</div>';
          return;
        }
        users.slice(0, 6).forEach(function (u) {
          var item = document.createElement("button");
          item.type = "button";
          item.className = "qb-connection-suggestion qb-js-link-suggestion";
          item.setAttribute("data-public-id", u.public_id || "");
          item.setAttribute("data-name", u.name || "");
          item.setAttribute("data-age", String(u.age == null ? "" : u.age));
          item.setAttribute("data-gender", u.gender || "");
          item.setAttribute("data-location", u.location_name || "");
          item.innerHTML =
            "<strong>" + escHtml(u.public_id || "") + "</strong>" +
            " · " + escHtml(u.name || "") +
            ' <span class="small text-muted">' +
            escHtml((u.age == null ? "" : String(u.age))) +
            " · " + escHtml(u.gender || "") + " · " +
            escHtml(u.location_name || "") +
            "</span>";
          suggestionEl.appendChild(item);
        });
      })
      .catch(function () {
        suggestionEl.innerHTML = '<div class="small text-danger">Search failed.</div>';
      });
  }

  function selectFamilyLinkSuggestion(btn) {
    linkAccountSuggestion = {
      public_id: btn.getAttribute("data-public-id") || "",
      name: btn.getAttribute("data-name") || "",
      age: btn.getAttribute("data-age") || "",
      gender: btn.getAttribute("data-gender") || "",
      location: btn.getAttribute("data-location") || "",
    };
    var suggestionEl = document.getElementById("qb-family-link-suggestion");
    if (suggestionEl) {
      suggestionEl
        .querySelectorAll(".qb-js-link-suggestion")
        .forEach(function (s) { s.classList.remove("is-active"); });
      btn.classList.add("is-active");
    }
    var statusEl = document.getElementById("qb-family-link-status");
    if (statusEl) {
      text(
        statusEl,
        "Selected " + (linkAccountSuggestion.name || linkAccountSuggestion.public_id) + "."
      );
    }
    var sendBtn = document.getElementById("qb-family-link-send-btn");
    if (sendBtn) sendBtn.disabled = false;
    var le = document.getElementById("qb-family-link-public-id");
    if (le && linkAccountSuggestion) le.value = linkAccountSuggestion.public_id || "";
  }

  // --- Admin: family removal request queue ---
  function loadAdminFamilyRemovals() {
    var list = document.getElementById("qb-admin-removal-list");
    var empty = document.getElementById("qb-admin-removal-empty");
    if (!list) return;
    text(document.getElementById("qb-admin-removal-status"), "Loading…");
    fetch("/api/admin/family_removal_requests?status=pending", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "queue failed");
        var rows = (x.b && x.b.requests) || [];
        list.innerHTML = "";
        if (empty) empty.hidden = rows.length > 0;
        rows.forEach(function (req) {
          var li = document.createElement("li");
          li.className = "qb-admin-removal-item";
          li.innerHTML =
            "<div class='qb-admin-removal-main'>" +
            "<strong>" +
            escHtml(req.user_name || req.user_public_id || "Unknown user") +
            "</strong>" +
            " <span class='font-monospace small text-muted'>" +
            escHtml(req.user_public_id || "") +
            "</span>" +
            "<div class='small text-muted'>requests removal of <strong>" +
            escHtml(req.target_member_name || "—") +
            "</strong> (" +
            escHtml(req.target_relationship || "relative") +
            ")</div>" +
            "<div class='small mt-1'><em>Reason:</em> " +
            escHtml(req.reason || "") +
            "</div>" +
            "<div class='small text-muted mt-1'>Submitted " +
            escHtml(req.created_at || "") +
            "</div>" +
            "</div>" +
            "<div class='qb-admin-removal-actions'>" +
            '<input type="text" class="form-control form-control-sm qb-admin-removal-comment" placeholder="Admin note (optional)" />' +
            '<button type="button" class="qb-btn qb-btn-primary btn-sm qb-js-admin-removal-action" data-action="approve" data-request-id="' +
            escAttr(req.id) +
            '">Approve</button>' +
            '<button type="button" class="qb-btn qb-btn-outline btn-sm qb-js-admin-removal-action" data-action="reject" data-request-id="' +
            escAttr(req.id) +
            '">Reject</button>' +
            "</div>";
          list.appendChild(li);
        });
        text(
          document.getElementById("qb-admin-removal-status"),
          rows.length ? "" : "No pending removal requests."
        );
      })
      .catch(function (err) {
        list.innerHTML = "";
        text(
          document.getElementById("qb-admin-removal-status"),
          err.message || "Could not load queue."
        );
      });
  }

  function openAdminRemovalsModal() {
    openModal("qb-admin-removals-modal");
    loadAdminFamilyRemovals();
  }

  function openAddGrandparentModal(slotKey, slotLabel) {
    var rel = slotLabel || "";
    if (!rel) {
      rel = (slotKey || "")
        .split("_")
        .map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); })
        .join(" ");
    }
    var nameInput = document.getElementById("qb-grandparent-name");
    var genderInput = document.getElementById("qb-grandparent-gender");
    var deadInput = document.getElementById("qb-grandparent-dead");
    var relInput = document.getElementById("qb-grandparent-relationship");
    var sub = document.getElementById("qb-grandparent-subtitle");
    if (nameInput) nameInput.value = "";
    if (deadInput) deadInput.checked = false;
    if (relInput) relInput.value = rel;
    if (genderInput) {
      genderInput.value = /grandfather/i.test(rel) ? "Male" : "Female";
    }
    if (sub) sub.textContent = "Add " + rel + " details.";
    text(document.getElementById("qb-grandparent-status"), "");
    openModal("qb-add-grandparent-modal");
  }

  // Admin: delete-with-reason modal submission
  var adminDeleteForm = document.getElementById("qb-admin-delete-form");
  if (adminDeleteForm) {
    adminDeleteForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var postId = (document.getElementById("qb-admin-delete-post-id") || {}).value || "";
      var reason = ((document.getElementById("qb-admin-delete-reason") || {}).value || "").trim();
      var statusEl = document.getElementById("qb-admin-delete-status");
      if (!postId) return;
      if (!reason) {
        if (statusEl) text(statusEl, "Reason is required.");
        return;
      }
      if (statusEl) text(statusEl, "Deleting…");
      submitPostDeletion(postId, reason);
    });
  }

  // Family removal-request modal submission
  var removalReqForm = document.getElementById("qb-family-removal-request-form");
  if (removalReqForm) {
    removalReqForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var idEl = document.getElementById("qb-family-removal-target-id");
      var srcEl = document.getElementById("qb-family-removal-target-source");
      var reasonEl = document.getElementById("qb-family-removal-reason");
      var statusEl = document.getElementById("qb-family-removal-status");
      var id = (idEl || {}).value || "";
      var source = (srcEl || {}).value || "";
      var reason = ((reasonEl || {}).value || "").trim();
      if (!id || !source) return;
      if (!reason) {
        if (statusEl) text(statusEl, "Reason is required.");
        return;
      }
      if (statusEl) text(statusEl, "Submitting…");
      fetch("/api/family/request_removal", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          id: parseInt(id, 10),
          source: source,
          reason: reason,
        }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Could not submit");
          closeModal("qb-family-removal-request-modal");
          familyFlash("Removal request submitted. An admin will review it.", "ok");
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          if (statusEl) text(statusEl, err.message || "Could not submit.");
        });
    });
  }

  function linkModalResolvePublicId() {
    if (linkAccountSuggestion && linkAccountSuggestion.public_id) {
      return String(linkAccountSuggestion.public_id || "").trim();
    }
    var el = document.getElementById("qb-family-link-public-id");
    return el ? String(el.value || "").trim() : "";
  }

  // Link family member modal: search
  var linkSearch = document.getElementById("qb-family-link-public-id");
  var linkSearchBtn = document.getElementById("qb-family-link-search-btn");
  if (linkSearch) {
    var linkSearchTimer = null;
    linkSearch.addEventListener("input", function () {
      var sendBtn = document.getElementById("qb-family-link-send-btn");
      if (sendBtn) sendBtn.disabled = linkModalResolvePublicId().length < 3;
      var val = (linkSearch.value || "").trim();
      if (linkSearchTimer) window.clearTimeout(linkSearchTimer);
      linkSearchTimer = window.setTimeout(function () {
        if (val.length >= 2) searchFamilyLinkTarget(val);
      }, 220);
    });
  }
  if (linkSearchBtn && linkSearch) {
    linkSearchBtn.addEventListener("click", function () {
      searchFamilyLinkTarget((linkSearch.value || "").trim());
    });
  }
  document.addEventListener("click", function (ev) {
    var sug = ev.target.closest(".qb-js-link-suggestion");
    if (sug) selectFamilyLinkSuggestion(sug);
  });

  // Link family member modal: direct link (sets account_public_id on row)
  var linkSendBtn = document.getElementById("qb-family-link-send-btn");
  if (linkSendBtn) {
    linkSendBtn.addEventListener("click", function () {
      var statusEl = document.getElementById("qb-family-link-status");
      var pidStr = linkModalResolvePublicId();
      if (!linkAccountContext || !pidStr) {
        if (statusEl) text(statusEl, "Enter or select an Account ID.");
        return;
      }
      var mid = parseInt(linkAccountContext.id || "0", 10);
      if (!mid) {
        if (statusEl) text(statusEl, "Missing member reference.");
        return;
      }
      if (statusEl) text(statusEl, "Linking…");
      fetch("/api/family/link_account", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          public_id: pidStr,
          member_id: mid,
        }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Could not link account");
          closeModal("qb-family-link-modal");
          openModal("qb-family-link-sent-modal");
          loadFamilyAllMembers();
          loadFamilyTree();
        })
        .catch(function (err) {
          if (statusEl) text(statusEl, err.message || "Could not link.");
        });
    });
  }

  document.querySelectorAll(".qb-js-add-family-type").forEach(function (r) {
    r.addEventListener("change", syncAddFamilyTypeUI);
  });

  var generalGo = document.getElementById("qb-family-add-close-general-go");
  if (generalGo) {
    generalGo.addEventListener("click", function () {
      closeModal("qb-family-add-close-modal");
      resetAndOpenConnectionModal("family", { familyMemberType: "general" });
    });
  }

  var addCloseForm = document.getElementById("qb-family-add-close-form");
  if (addCloseForm) {
    addCloseForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var genPick = document.querySelector('input[name="qb-add-family-type"][value="general"]');
      if (genPick && genPick.checked) return;
      var st = document.getElementById("qb-family-add-close-status");
      var nm = ((document.getElementById("qb-family-add-close-name") || {}).value || "").trim();
      var rel = (document.getElementById("qb-family-add-close-rel") || {}).value || "";
      var gender = (document.getElementById("qb-family-add-close-gender") || {}).value || "";
      var ageRaw = (document.getElementById("qb-family-add-close-age") || {}).value || "";
      var connectRaw = (document.getElementById("qb-family-add-close-connect") || {}).value || "";
      if (!nm) {
        text(st, "Name is required.");
        return;
      }
      if (!rel) {
        text(st, "Choose a relationship.");
        return;
      }
      text(st, "Saving…");
      var body = {
        name: nm,
        relationship: rel,
        gender: gender,
        age: ageRaw ? parseInt(ageRaw, 10) : null,
      };
      if (connectRaw) body.connect_to_member_id = parseInt(connectRaw, 10);
      fetch("/api/family/add_close_manual", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Could not add");
          addCloseForm.reset();
          var nRadio = document.querySelector('input[name="qb-add-family-type"][value="nuclear"]');
          if (nRadio) nRadio.checked = true;
          syncAddFamilyTypeUI();
          text(st, "");
          closeModal("qb-family-add-close-modal");
          familyFlash("Nuclear family member added.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Could not add");
        });
    });
  }

  function _numOrNull(v) {
    if (v == null || v === "") return null;
    var n = parseInt(String(v), 10);
    return isNaN(n) ? null : n;
  }

  var editTreeSave = document.getElementById("qb-family-edit-tree-save");
  if (editTreeSave) {
    editTreeSave.addEventListener("click", function () {
      var box = document.getElementById("qb-family-edit-tree-body");
      var st = document.getElementById("qb-family-edit-tree-status");
      if (!box) return;
      var updates = [];
      box.querySelectorAll(".qb-family-edit-tree-row").forEach(function (rowEl) {
        var mid = rowEl.getAttribute("data-member-id");
        if (!mid) return;
        var up = { id: parseInt(mid, 10) };
        rowEl.querySelectorAll("select[data-tree-field]").forEach(function (sel) {
          var k = sel.getAttribute("data-tree-field");
          if (k) up[k] = _numOrNull(sel.value);
        });
        updates.push(up);
      });
      text(st, "Saving…");
      fetch("/api/family/tree_links/save", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ updates: updates }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          text(st, "");
          closeModal("qb-family-edit-tree-modal");
          familyFlash("Tree connections updated.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Save failed");
        });
    });
  }

  var fneForm = document.getElementById("qb-family-natural-edit-form");
  if (fneForm) {
    fneForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var st = document.getElementById("qb-fne-status");
      var m = fneMemberSnapshot;
      if (!m || m.id == null) {
        text(st, "Nothing to save.");
        return;
      }
      var relSel = document.getElementById("qb-fne-relationship");
      var otherSel = document.getElementById("qb-fne-other");
      var refRel = (relSel && relSel.value) || "";
      var parsed = parseParentLinkSelect(otherSel && otherSel.value);
      text(st, "Saving…");
      fetch("/api/family/member_sentence_save", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          member_id: m.id,
          reference_relation: refRel,
          other_member_id: parsed.member,
          other_connection_request_id: parsed.connection,
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          text(st, "");
          closeModal("qb-family-edit-parents-modal");
          familyFlash("Relationship updated.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Save failed");
        });
    });
  }

  var ftaForm = document.getElementById("qb-family-tree-add-form");
  if (ftaForm) {
    ftaForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var st = document.getElementById("qb-fta-status");
      var nm = ((document.getElementById("qb-fta-name") || {}).value || "").trim();
      var ageRaw = (document.getElementById("qb-fta-age") || {}).value || "";
      var ageNum = ageRaw === "" ? null : parseInt(String(ageRaw), 10);
      if (ageNum != null && isNaN(ageNum)) ageNum = null;
      var genderVal = ((document.getElementById("qb-fta-gender") || {}).value || "").trim();
      var rel = (document.getElementById("qb-fta-relationship") || {}).value || "";
      var pub = ((document.getElementById("qb-fta-public-id") || {}).value || "").trim();
      if (!nm) {
        text(st, "Name is required.");
        return;
      }
      if (!rel) {
        text(st, "Choose a relationship.");
        return;
      }
      text(st, "Saving…");
      var phId = ((document.getElementById("qb-fta-placeholder-id") || {}).value || "").trim();
      var body = {
        member_name: nm,
        age: ageNum,
        gender: genderVal,
        relationship: rel,
        relationship_to_user: rel,
      };
      if (phId) {
        body.replace_placeholder_id = parseInt(phId, 10);
        if (isNaN(body.replace_placeholder_id)) {
          text(st, "Invalid placeholder.");
          return;
        }
      }
      if (pub) body.public_id = pub;
      fetch("/api/family/add_nuclear", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          text(st, "");
          closeModal("qb-family-tree-add-modal");
          familyFlash("Family member added.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Save failed");
        });
    });
  }

  function runPublicIdSuggest(prefix, container, itemClass) {
    if (!container) return;
    container.innerHTML = "";
    if (!prefix || prefix.length < 2) return;
    fetch("/api/users/suggest?public_id_prefix=" + encodeURIComponent(prefix), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "search failed");
        var users = (x.b && x.b.users) || [];
        if (!users.length) {
          container.innerHTML = '<div class="small text-muted">No matching accounts.</div>';
          return;
        }
        users.slice(0, 6).forEach(function (u) {
          var item = document.createElement("button");
          item.type = "button";
          item.className = "qb-connection-suggestion " + itemClass;
          item.setAttribute("data-public-id", u.public_id || "");
          item.innerHTML =
            "<strong>" + escHtml(u.public_id || "") + "</strong>" +
            " · " + escHtml(u.name || "") +
            ' <span class="small text-muted">' +
            escHtml(u.age == null ? "" : String(u.age)) +
            " · " + escHtml(u.gender || "") +
            "</span>";
          container.appendChild(item);
        });
      })
      .catch(function () {
        container.innerHTML = '<div class="small text-danger">Search failed.</div>';
      });
  }

  var ftaSearchBtn = document.getElementById("qb-fta-public-search");
  if (ftaSearchBtn) {
    ftaSearchBtn.addEventListener("click", function () {
      var inp = document.getElementById("qb-fta-public-id");
      var box = document.getElementById("qb-fta-suggestion");
      runPublicIdSuggest((inp && inp.value) || "", box, "qb-js-fta-suggest");
    });
  }

  document.addEventListener("click", function (ev) {
    var ftaPick = ev.target.closest(".qb-js-fta-suggest");
    if (!ftaPick) return;
    var inp = document.getElementById("qb-fta-public-id");
    if (inp) inp.value = ftaPick.getAttribute("data-public-id") || "";
  });

  var genFamPick = null;
  function fillGeneralFamilyLookupFromServer(pub) {
    var st = document.getElementById("qb-fam-gen-status");
    var nameEl = document.getElementById("qb-fam-gen-name");
    var genEl = document.getElementById("qb-fam-gen-gender");
    var lifeEl = document.getElementById("qb-fam-gen-life-stage");
    if (!pub) {
      if (nameEl) nameEl.value = "";
      if (genEl) {
        genEl.disabled = false;
        genEl.value = "";
        genEl.disabled = true;
      }
      if (lifeEl) {
        lifeEl.disabled = false;
        lifeEl.value = "";
        lifeEl.disabled = true;
      }
      return;
    }
    text(st, "Loading profile…");
    fetch("/api/users/lookup?public_id=" + encodeURIComponent(pub), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Lookup failed");
        if (!x.b || !x.b.found) {
          if (nameEl) nameEl.value = "";
          if (genEl) {
            genEl.disabled = false;
            genEl.value = "";
            genEl.disabled = true;
          }
          if (lifeEl) {
            lifeEl.disabled = false;
            lifeEl.value = "";
            lifeEl.disabled = true;
          }
          text(st, "Account ID not found.");
          return;
        }
        if (nameEl) nameEl.value = x.b.name || "";
        if (genEl) {
          genEl.disabled = false;
          genEl.value = x.b.gender || "";
          genEl.disabled = true;
        }
        if (lifeEl) {
          lifeEl.disabled = false;
          lifeEl.value = x.b.life_stage || "";
          lifeEl.disabled = true;
        }
        text(st, "Profile loaded.");
      })
      .catch(function () {
        text(st, "Lookup failed.");
      });
  }

  function openFamilyAddGeneralModal() {
    var f = document.getElementById("qb-family-add-general-form");
    if (f) f.reset();
    genFamPick = null;
    var cw = document.getElementById("qb-fam-gen-custom-wrap");
    if (cw) cw.hidden = true;
    text(document.getElementById("qb-fam-gen-status"), "");
    fillGeneralFamilyLookupFromServer("");
    openModal("qb-family-add-general-modal");
  }

  var genTypeSel = document.getElementById("qb-fam-gen-type");
  if (genTypeSel) {
    genTypeSel.addEventListener("change", function () {
      var cw = document.getElementById("qb-fam-gen-custom-wrap");
      if (cw) cw.hidden = (genTypeSel.value || "").toLowerCase() !== "other";
    });
  }

  var genSearchBtn = document.getElementById("qb-fam-gen-search");
  if (genSearchBtn) {
    genSearchBtn.addEventListener("click", function () {
      var inp = document.getElementById("qb-fam-gen-public-id");
      var box = document.getElementById("qb-fam-gen-suggestion");
      var raw = ((inp && inp.value) || "").trim();
      runPublicIdSuggest(raw, box, "qb-js-fam-gen-suggest");
      if (raw.length >= 3) fillGeneralFamilyLookupFromServer(raw);
    });
  }

  document.addEventListener("click", function (ev) {
    var g = ev.target.closest(".qb-js-fam-gen-suggest");
    if (!g) return;
    genFamPick = { public_id: g.getAttribute("data-public-id") || "" };
    var inp = document.getElementById("qb-fam-gen-public-id");
    if (inp) inp.value = genFamPick.public_id;
    g.parentElement.querySelectorAll(".qb-js-fam-gen-suggest").forEach(function (b) {
      b.classList.remove("is-active");
    });
    g.classList.add("is-active");
    fillGeneralFamilyLookupFromServer(genFamPick.public_id);
  });

  var genForm = document.getElementById("qb-family-add-general-form");
  if (genForm) {
    genForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var st = document.getElementById("qb-fam-gen-status");
      var typ = (document.getElementById("qb-fam-gen-type") || {}).value || "";
      var cust = ((document.getElementById("qb-fam-gen-custom") || {}).value || "").trim();
      var pub = genFamPick && genFamPick.public_id
        ? genFamPick.public_id
        : (((document.getElementById("qb-fam-gen-public-id") || {}).value || "").trim());
      var memberName = ((document.getElementById("qb-fam-gen-name") || {}).value || "").trim();
      var genderEl = document.getElementById("qb-fam-gen-gender");
      var lifeEl = document.getElementById("qb-fam-gen-life-stage");
      var gender = "";
      var lifeStage = "";
      if (genderEl) {
        genderEl.disabled = false;
        gender = (genderEl.value || "").trim();
        genderEl.disabled = true;
      }
      if (lifeEl) {
        lifeEl.disabled = false;
        lifeStage = (lifeEl.value || "").trim();
        lifeEl.disabled = true;
      }
      if (!typ) {
        text(st, "Choose a family member type.");
        return;
      }
      if (typ.toLowerCase() === "other" && !cust) {
        text(st, "Enter a custom relationship for Other.");
        return;
      }
      if (!pub) {
        text(st, "Account ID is required.");
        return;
      }
      if (!memberName) {
        text(st, "Search and load the account profile first (name is required).");
        return;
      }
      if (!gender || !lifeStage) {
        text(st, "Profile must include gender and age group — use Search after entering Account ID.");
        return;
      }
      text(st, "Sending…");
      fetch("/api/family/add_general", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          public_id: pub,
          family_member_kind: typ,
          custom_relationship: cust,
          member_name: memberName,
          gender: gender,
          life_stage: lifeStage,
        }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b, code: r.status }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Request failed");
          text(st, "");
          closeModal("qb-family-add-general-modal");
          familyFlash("Family connection request sent.", "ok");
        })
        .catch(function (err) {
          text(st, err.message || "Could not send.");
        });
    });
  }

  var viewAllBtn = document.getElementById("qb-family-view-all-btn");
  if (viewAllBtn) {
    viewAllBtn.addEventListener("click", function () {
      loadFamilyAllMembers();
      openModal("qb-family-all-members-modal");
    });
  }

  var addGenBtn = document.getElementById("qb-family-add-general-btn");
  if (addGenBtn) {
    addGenBtn.addEventListener("click", function () {
      openFamilyAddGeneralModal();
    });
  }

  var fmeSave = document.getElementById("qb-fme-save");
  if (fmeSave) {
    fmeSave.addEventListener("click", function () {
      var st = document.getElementById("qb-fme-status");
      var mt = ((document.getElementById("qb-fme-member-type") || {}).value || "").toLowerCase();
      var src = (document.getElementById("qb-fme-source") || {}).value || "";
      if (src === "connection" || mt === "general") return;
      var mid = parseInt((document.getElementById("qb-fme-id") || {}).value || "0", 10);
      var nm = ((document.getElementById("qb-fme-name") || {}).value || "").trim();
      if (!mid || !nm) {
        text(st, "Name is required.");
        return;
      }
      text(st, "Saving…");
      fetch("/api/family/update_member", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          member_id: mid,
          member_name: nm,
          gender: ((document.getElementById("qb-fme-gender") || {}).value || "").trim(),
          age: (function (v) {
            if (!v || v === "") return null;
            var n = parseInt(String(v), 10);
            return isNaN(n) ? null : n;
          })((document.getElementById("qb-fme-age") || {}).value),
        }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          text(st, "");
          closeModal("qb-family-member-edit-modal");
          familyFlash("Member updated.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Save failed");
        });
    });
  }

  var fmeUnlink = document.getElementById("qb-fme-unlink");
  if (fmeUnlink) {
    fmeUnlink.addEventListener("click", function () {
      var st = document.getElementById("qb-fme-status");
      var mid = parseInt((document.getElementById("qb-fme-id") || {}).value || "0", 10);
      if (!mid) return;
      if (!window.confirm("Unlink this family member from the account?")) return;
      text(st, "Working…");
      fetch("/api/family/unlink_account", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ member_id: mid }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Unlink failed");
          text(st, "");
          closeModal("qb-family-member-edit-modal");
          familyFlash("Updated.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Unlink failed");
        });
    });
  }

  var fmeLinkSearch = document.getElementById("qb-fme-link-search");
  if (fmeLinkSearch) {
    fmeLinkSearch.addEventListener("click", function () {
      var inp = document.getElementById("qb-fme-link-pid");
      var box = document.getElementById("qb-fme-link-suggestion");
      runPublicIdSuggest((inp && inp.value) || "", box, "qb-js-fme-suggest");
    });
  }

  document.addEventListener("click", function (ev) {
    var z = ev.target.closest(".qb-js-fme-suggest");
    if (!z) return;
    var inp = document.getElementById("qb-fme-link-pid");
    if (inp) inp.value = z.getAttribute("data-public-id") || "";
  });

  var fmeLinkApply = document.getElementById("qb-fme-link-apply");
  if (fmeLinkApply) {
    fmeLinkApply.addEventListener("click", function () {
      var st = document.getElementById("qb-fme-status");
      var mid = parseInt((document.getElementById("qb-fme-id") || {}).value || "0", 10);
      var pub = ((document.getElementById("qb-fme-link-pid") || {}).value || "").trim();
      if (!mid || !pub) {
        text(st, "Enter an Account ID.");
        return;
      }
      text(st, "Linking…");
      fetch("/api/family/link_account", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ member_id: mid, public_id: pub }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Link failed");
          text(st, "");
          closeModal("qb-family-member-edit-modal");
          openModal("qb-family-link-sent-modal");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Link failed");
        });
    });
  }

  var fmeRemove = document.getElementById("qb-fme-remove");
  if (fmeRemove) {
    fmeRemove.addEventListener("click", function () {
      var st = document.getElementById("qb-fme-status");
      var mid = parseInt((document.getElementById("qb-fme-id") || {}).value || "0", 10);
      var src = (document.getElementById("qb-fme-source") || {}).value || "form";
      if (!mid) return;
      if (!window.confirm("Remove this family member?")) return;
      text(st, "Removing…");
      fetch("/api/family/remove_member", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ id: mid, source: src }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b, status: r.status }; }); })
        .then(function (x) {
          if (x.status === 409 && x.b && x.b.requires_admin_approval) {
            text(st, "");
            closeModal("qb-family-member-edit-modal");
            openFamilyRemovalRequestModal({
              id: mid,
              source: src,
              name: (fmeSnapshot && fmeSnapshot.member_name) || "",
              relationship: (fmeSnapshot && (fmeSnapshot.relationship_label || fmeSnapshot.relationship)) || "",
            });
            return;
          }
          if (!x.ok) throw new Error((x.b && x.b.error) || "Remove failed");
          text(st, "");
          closeModal("qb-family-member-edit-modal");
          familyFlash("Member removed.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(st, err.message || "Remove failed");
        });
    });
  }

  // Admin removal queue: open button + Approve / Reject buttons inside list
  var adminQueueOpenBtn = document.getElementById("qb-admin-removals-open");
  if (adminQueueOpenBtn) {
    adminQueueOpenBtn.addEventListener("click", function () {
      openAdminRemovalsModal();
    });
  }
  document.addEventListener("click", function (ev) {
    var act = ev.target.closest(".qb-js-admin-removal-action");
    if (!act) return;
    ev.preventDefault();
    var action = act.getAttribute("data-action") || "";
    var rid = act.getAttribute("data-request-id") || "";
    if (!rid) return;
    var item = act.closest(".qb-admin-removal-item");
    var commentEl = item && item.querySelector(".qb-admin-removal-comment");
    var comment = (commentEl && commentEl.value) || "";
    fetch(
      "/api/admin/family_removal_requests/" + encodeURIComponent(rid) + "/" + action,
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ admin_comment: comment }),
      }
    )
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Action failed");
        loadAdminFamilyRemovals();
      })
      .catch(function (err) {
        text(document.getElementById("qb-admin-removal-status"), err.message || "Action failed");
      });
  });

  var grandparentForm = document.getElementById("qb-add-grandparent-form");
  if (grandparentForm) {
    grandparentForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var rel = (document.getElementById("qb-grandparent-relationship") || {}).value || "";
      var name = (document.getElementById("qb-grandparent-name") || {}).value || "";
      var gender = (document.getElementById("qb-grandparent-gender") || {}).value || "";
      var isDead = (document.getElementById("qb-grandparent-dead") || {}).checked || false;
      var statusEl = document.getElementById("qb-grandparent-status");
      if (!name.trim()) {
        text(statusEl, "Name is required.");
        return;
      }
      text(statusEl, "Saving…");
      fetch("/api/family/add_grandparent", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          relationship: rel,
          name: name.trim(),
          gender: gender,
          is_dead: isDead,
        }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Could not save");
          closeModal("qb-add-grandparent-modal");
          familyFlash("Grandparent added.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(statusEl, err.message || "Could not save");
        });
    });
  }

  // --- Bulk Mark Deceased modal ---
  function openMarkDeceasedModal() {
    var list = document.getElementById("qb-mark-deceased-list");
    var empty = document.getElementById("qb-mark-deceased-empty");
    var submit = document.getElementById("qb-mark-deceased-submit");
    if (list) list.innerHTML = "";
    if (empty) empty.hidden = true;
    if (submit) submit.disabled = true;
    text(document.getElementById("qb-mark-deceased-status"), "Loading family members…");
    openModal("qb-mark-deceased-modal");

    fetch("/api/family/alive_members", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Could not load");
        var members = x.b.members || [];
        if (!members.length) {
          if (empty) empty.hidden = false;
          text(document.getElementById("qb-mark-deceased-status"), "");
          return;
        }
        members.forEach(function (m) {
          var li = document.createElement("li");
          li.className = "qb-mark-deceased-item";
          var srcLabel = m.source === "connection" ? "connection" : m.source || "form";
          li.innerHTML =
            '<label class="qb-mark-deceased-row">' +
            '<input type="checkbox" class="qb-js-mark-deceased-check" data-source="' +
            escAttr(m.source || "form") +
            '" data-id="' +
            escAttr(String(m.id)) +
            '" />' +
            "<span class='qb-mark-deceased-name'><strong>" +
            escHtml(m.member_name || "") +
            "</strong> <span class='qb-rel-tag'>" +
            escHtml(m.relationship_label || m.relationship || "") +
            "</span> <span class='small text-muted'>(" + srcLabel + ")</span></span>" +
            "</label>";
          if (list) list.appendChild(li);
        });
        if (submit) submit.disabled = false;
        text(
          document.getElementById("qb-mark-deceased-status"),
          "Select members and click Mark as Deceased."
        );
      })
      .catch(function (err) {
        text(document.getElementById("qb-mark-deceased-status"), err.message || "Could not load");
      });
  }

  var markDeadSubmit = document.getElementById("qb-mark-deceased-submit");
  if (markDeadSubmit) {
    markDeadSubmit.addEventListener("click", function () {
      var statusEl = document.getElementById("qb-mark-deceased-status");
      var picked = [];
      document
        .querySelectorAll(".qb-js-mark-deceased-check:checked")
        .forEach(function (cb) {
          picked.push({
            id: parseInt(cb.getAttribute("data-id") || "0", 10),
            source: cb.getAttribute("data-source") || "form",
          });
        });
      if (!picked.length) {
        text(statusEl, "Select at least one member.");
        return;
      }
      if (!window.confirm("Mark " + picked.length + " family member(s) as deceased? Only an admin can reverse this.")) {
        return;
      }
      text(statusEl, "Saving…");
      fetch("/api/family/mark_deceased", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ members: picked }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Could not save");
          var updated = (x.b && x.b.updated) || 0;
          closeModal("qb-mark-deceased-modal");
          familyFlash("Marked " + updated + " member(s) as deceased.", "ok");
          loadFamilyTree();
          loadFamilyAllMembers();
        })
        .catch(function (err) {
          text(statusEl, err.message || "Could not save");
        });
    });
  }

  if (postForm && (dashCfg.defaultVillageId || dashCfg.postFormLocationId)) {
    postForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var locationId = dashCfg.postFormLocationId || dashCfg.defaultVillageId;
      if (postLocationInput) postLocationInput.value = locationId;
      var content = (postContent && postContent.value) || "";
      text(postStatus, "Saving...");
      fetch("/api/post/create", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ location_id: locationId, content: content }),
      })
        .then(function (res) {
          return res.json().then(function (body) {
            return { ok: res.ok, body: body };
          });
        })
        .then(function (payload) {
          if (!payload.ok) throw new Error(payload.body.error || "Unable to save post");
          if (postContent) postContent.value = "";
          text(postStatus, payload.body.message || "Post saved.");
          closeModal("qb-new-post-modal");
          if (activePersonalBoardState === "live" && payload.body.post) {
            prependPost(payload.body.post);
          } else {
            activePersonalBoardState = "live";
            document.querySelectorAll(".qb-js-personal-board-tab").forEach(function (t) {
              var on = (t.getAttribute("data-personal-board-state") || "") === "live";
              t.classList.toggle("is-active", on);
              t.setAttribute("aria-selected", on ? "true" : "false");
            });
            loadPersonalBoard();
          }
        })
        .catch(function (err) {
          text(postStatus, err.message || "Failed to save post");
        });
    });
  }

  document.addEventListener("click", function (ev) {
    var linkReqAct = ev.target.closest(".qb-js-link-request-action");
    if (linkReqAct) {
      ev.stopPropagation();
      var lid = linkReqAct.getAttribute("data-link-request-id");
      var lact = linkReqAct.getAttribute("data-action");
      if (!lid || (lact !== "accept" && lact !== "reject")) return;
      var url =
        lact === "accept"
          ? "/api/family/link_accept"
          : "/api/family/link_reject";
      var body = { link_request_id: parseInt(lid, 10) };
      if (lact === "reject") {
        var msg = window.prompt("Optional message to the requester (or leave blank):", "") || "";
        body.message = msg;
      }
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (res) {
          return res.json().then(function (payload) {
            return { ok: res.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok) throw new Error(result.payload.error || "Update failed");
          fetchNotifications();
          refreshPersonalData();
          loadFamilyProfile();
        })
        .catch(function (err) {
          text(
            document.getElementById("qb-personal-placeholder-status"),
            err.message || "Link request update failed"
          );
        });
      return;
    }
    var notificationAction = ev.target.closest(".qb-js-notification-action");
    if (notificationAction) {
      ev.stopPropagation();
      var nrid = notificationAction.getAttribute("data-request-id");
      var nact = notificationAction.getAttribute("data-action");
      if (!nrid || (nact !== "accept" && nact !== "reject")) return;
      fetch("/api/notifications/" + nact + "/" + encodeURIComponent(nrid), {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json().then(function (payload) {
            return { ok: res.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok) throw new Error(result.payload.error || "Notification update failed");
          fetchNotifications();
          refreshPersonalData();
        })
        .catch(function (err) {
          text(document.getElementById("qb-personal-placeholder-status"), err.message || "Notification update failed");
        });
      return;
    }
    var notificationMsgRead = ev.target.closest(".qb-js-notification-msg-read");
    if (notificationMsgRead) {
      ev.stopPropagation();
      var mid = notificationMsgRead.getAttribute("data-message-id") || "";
      if (!mid) return;
      fetch(
        "/api/notifications/read_message/" + encodeURIComponent(mid),
        {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        }
      )
        .then(function (res) {
          return res.json().then(function (payload) {
            return { ok: res.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok) throw new Error(result.payload.error || "Could not mark read");
          fetchNotifications();
        })
        .catch(function () {});
      return;
    }

    var reqBtn = ev.target.closest(".qb-js-request-action");
    if (reqBtn) {
      var rid = reqBtn.getAttribute("data-request-id");
      var action = reqBtn.getAttribute("data-action");
      if (!rid || (action !== "accept" && action !== "reject")) return;
      fetch("/api/request/" + action + "/" + encodeURIComponent(rid), {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json().then(function (payload) {
            return { ok: res.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok) throw new Error(result.payload.error || "Request update failed");
          refreshPersonalData();
        })
        .catch(function (err) {
          text(document.getElementById("qb-personal-placeholder-status"), err.message || "Request update failed");
        });
      return;
    }

    var btn = ev.target.closest(".js-qb-vote");
    if (!btn || btn.disabled) return;
    var postId = btn.getAttribute("data-post-id");
    var vote = parseInt(btn.getAttribute("data-vote"), 10);
    if (!postId || isNaN(vote)) return;
    fetch("/api/post/vote", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ post_id: parseInt(postId, 10), vote_value: vote }),
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (payload) {
        if (!payload.ok) throw new Error(payload.body.error || "Vote failed");
        var scoreEl = document.querySelector(
          ".js-qb-post-score[data-post-id='" + postId + "']"
        );
        if (scoreEl) scoreEl.textContent = String(payload.body.total_score || 0);
        var card = document.querySelector(".qb-board-post[data-post-id='" + postId + "']");
        document.querySelectorAll(".js-qb-vote[data-post-id='" + postId + "']").forEach(function (b) {
          var v = parseInt(b.getAttribute("data-vote"), 10);
          b.classList.remove(
            "btn-success",
            "btn-outline-success",
            "btn-secondary",
            "btn-outline-secondary",
            "btn-danger",
            "btn-outline-danger"
          );
          b.classList.add(voteButtonClass(v, payload.body.current_user_vote));
          b.disabled = true;
        });
        if (card && !card.querySelector(".qb-board-vote-note")) {
          var row = card.querySelector(".qb-board-vote-row");
          if (row) row.insertAdjacentHTML("beforeend", '<span class="qb-board-vote-note">You have voted</span>');
        }
        if (card) {
          var group = card.querySelector(".btn-group");
          if (group) group.remove();
        }
      })
      .catch(function (err) {
        text(postStatus, err.message || "Vote failed");
      });
  });

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".js-qb-author");
    if (!btn) return;
    text(document.getElementById("qb-author-name"), btn.getAttribute("data-author-name") || "—");
    text(document.getElementById("qb-author-age"), btn.getAttribute("data-author-age") || "—");
    text(document.getElementById("qb-author-gender"), btn.getAttribute("data-author-gender") || "—");
    text(document.getElementById("qb-author-location"), btn.getAttribute("data-author-location") || "—");
    var rid = document.getElementById("qb-author-recipient-id");
    var rname = document.getElementById("qb-author-recipient-name");
    var body = document.getElementById("qb-author-message-body");
    if (rid) rid.value = btn.getAttribute("data-author-private-id") || "";
    if (rname) rname.value = btn.getAttribute("data-author-name") || "";
    if (body) body.value = "";
    text(document.getElementById("qb-author-message-status"), "");
    openModal("qb-author-modal");
  });

  var authorMsgForm = document.getElementById("qb-author-message-form");
  if (authorMsgForm) {
    authorMsgForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var recipient = (document.getElementById("qb-author-recipient-id") || {}).value || "";
      var recipientName = (document.getElementById("qb-author-recipient-name") || {}).value || "this post";
      var body = (document.getElementById("qb-author-message-body") || {}).value || "";
      var status = document.getElementById("qb-author-message-status");
      text(status, "Sending...");
      fetch("/api/messages/send", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          recipient_id: recipient,
          subject: "Message regarding " + recipientName + "'s post",
          body: body,
          is_draft: false,
        }),
      })
        .then(function (res) {
          return res.json().then(function (payload) {
            return { ok: res.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok) throw new Error(result.payload.error || "Message failed");
          text(status, "Message sent.");
          authorMsgForm.reset();
          closeModal("qb-author-modal");
        })
        .catch(function (err) {
          text(status, err.message || "Message failed");
        });
    });
  }

  /* --- India tree (public explorer) --- */
  var selectedPublicLabels = [];

  function clearPublicSelection() {
    selectedPublicLabels.forEach(function (el) {
      el.classList.remove("is-selected");
    });
    selectedPublicLabels = [];
  }

  function fetchIndiaChildren(parentId) {
    return fetch(
      "/api/locations/children?parent_id=" + encodeURIComponent(parentId),
      { credentials: "same-origin", headers: { Accept: "application/json" } }
    ).then(function (r) {
      if (!r.ok) throw new Error("children");
      return r.json();
    });
  }

  function appendIndiaNode(container, label, id, rowKind) {
    var wrap = document.createElement("div");
    wrap.className = "qb-tree-node";
    var row = document.createElement("div");
    row.className = "qb-tree-row";
    var chev = document.createElement("button");
    chev.type = "button";
    chev.className = "qb-tree-chev";
    chev.setAttribute("aria-label", "Expand");
    chev.textContent = "▸";
    var lab = document.createElement("button");
    lab.type = "button";
    lab.className = "qb-tree-label";
    lab.textContent = label;
    lab.setAttribute("data-geo-id", id);
    var kids = document.createElement("div");
    kids.className = "qb-tree-children";
    kids.hidden = true;
    row.appendChild(chev);
    row.appendChild(lab);
    wrap.appendChild(row);
    wrap.appendChild(kids);
    container.appendChild(wrap);

    chev.addEventListener("click", function (e) {
      e.stopPropagation();
      if (kids.getAttribute("data-loaded") === "1") {
        kids.hidden = !kids.hidden;
        chev.textContent = kids.hidden ? "▸" : "▾";
        return;
      }
      if (rowKind === "village") return;
      fetchIndiaChildren(id).then(function (rows) {
        kids.innerHTML = "";
        var nextKind =
          rowKind === "root"
            ? "state"
            : rowKind === "state"
              ? "district"
              : rowKind === "district"
                ? "tehsil"
                : "village";
        rows.forEach(function (r) {
          appendIndiaNode(kids, r.name, r.id, nextKind);
        });
        kids.setAttribute("data-loaded", "1");
        kids.hidden = false;
        chev.textContent = "▾";
      });
    });

    lab.addEventListener("click", function (e) {
      e.preventDefault();
      clearPublicSelection();
      lab.classList.add("is-selected");
      selectedPublicLabels.push(lab);
    });
  }

  var pubRoot = document.getElementById("qb-tree-public-root");
  if (pubRoot) {
    appendIndiaNode(pubRoot, "India", "IND", "root");
  }

  /* --- Global tree + stats --- */
  var globalSel = { continent: null, country: null, zone: null };
  var globalTreeInited = false;
  var activeGlobalBoardState = "live";
  var activeGlobalScope = "earth";
  var activeGlobalGeoId = "0";

  function fetchGlobalChildren(parentId) {
    return fetch(
      "/api/locations/global_children?parent_id=" + encodeURIComponent(parentId),
      { credentials: "same-origin", headers: { Accept: "application/json" } }
    ).then(function (r) {
      if (!r.ok) throw new Error("global children");
      return r.json();
    });
  }

  function userDefaultContinent() {
    if (dashCfg.userContinentId)
      return {
        id: dashCfg.userContinentId,
        name: dashCfg.userContinentName || dashCfg.userContinentId,
      };
    return null;
  }

  function userDefaultCountry() {
    if (dashCfg.userCountryId)
      return { id: dashCfg.userCountryId, name: dashCfg.userCountryName || dashCfg.userCountryId };
    return null;
  }

  function updateGlobalTabsFromSelection() {
    var tabs = document.querySelectorAll(".qb-js-global-tab");
    var earth = tabs[0];
    var cont = tabs[1];
    var cou = tabs[2];
    var zone = document.getElementById("qb-global-tab-zone");
    var contSrc = globalSel.continent || userDefaultContinent();
    var couSrc = globalSel.country || userDefaultCountry();
    if (earth) {
      earth.querySelector(".qb-location-tab-name").textContent = "Planet Earth";
      earth.setAttribute("data-global-id", "0");
    }
    if (cont) {
      if (contSrc) {
        cont.querySelector(".qb-location-tab-name").textContent = contSrc.name;
        cont.setAttribute("data-global-id", contSrc.id);
      } else {
        cont.querySelector(".qb-location-tab-name").textContent = "—";
        cont.setAttribute("data-global-id", "");
      }
    }
    if (cou) {
      if (couSrc) {
        cou.querySelector(".qb-location-tab-name").textContent = couSrc.name;
        cou.setAttribute("data-global-id", couSrc.id);
      } else {
        cou.querySelector(".qb-location-tab-name").textContent = "—";
        cou.setAttribute("data-global-id", "");
      }
    }
    if (zone) {
      if (dashCfg.userShowZoneTab) {
        zone.hidden = false;
        if (globalSel.zone) {
          zone.querySelector(".qb-location-tab-name").textContent = globalSel.zone.name;
          zone.setAttribute("data-global-id", globalSel.zone.id);
        } else if (dashCfg.userZoneId) {
          zone.querySelector(".qb-location-tab-name").textContent =
            dashCfg.userZoneName || "Zone";
          zone.setAttribute("data-global-id", dashCfg.userZoneId);
        } else {
          zone.querySelector(".qb-location-tab-name").textContent = "Zone";
          zone.setAttribute("data-global-id", "");
        }
      } else {
        zone.hidden = true;
        globalSel.zone = null;
        if (activeGlobalScope === "zone") {
          activeGlobalScope = "earth";
          activeGlobalGeoId = "0";
          if (earth) {
            document.querySelectorAll(".qb-js-global-tab").forEach(function (t) {
              var on = t === earth;
              t.classList.toggle("is-active", on);
              t.setAttribute("aria-selected", on ? "true" : "false");
            });
          }
        }
      }
    }
  }

  function loadGlobalCollectiveBoard() {
    var ul = document.getElementById("qb-global-feed");
    var empty = document.getElementById("qb-global-feed-empty");
    if (!ul) return;
    var level = activeGlobalScope || "earth";
    var lid = activeGlobalGeoId || "0";
    if (level === "earth") lid = lid || "0";
    if (level !== "earth" && !lid) {
      ul.innerHTML = "";
      if (empty) {
        empty.hidden = false;
        text(empty, "Select a valid global level.");
      }
      return;
    }
    fetchJson(
      "/api/collective_board?level=" +
        encodeURIComponent(level) +
        "&location_id=" +
        encodeURIComponent(lid) +
        "&state=" +
        encodeURIComponent(activeGlobalBoardState)
    )
      .then(function (x) {
        if (!x.ok) throw new Error((x.body && x.body.error) || "feed failed");
        var posts = x.body.posts || [];
        ul.innerHTML = "";
        if (!posts.length) {
          if (empty) empty.hidden = false;
          return;
        }
        if (empty) empty.hidden = true;
        posts.forEach(function (p) {
          ul.appendChild(renderPost(p, activeGlobalBoardState));
        });
      })
      .catch(function () {
        ul.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          text(empty, "Could not load Collective Board posts for this level.");
        }
      });
  }

  function loadGlobalPanel() {
    var tab = document.querySelector(".qb-js-global-tab.is-active");
    if (!tab) return;
    var scope = tab.getAttribute("data-global-scope") || "earth";
    var gid = tab.getAttribute("data-global-id") || "";
    if (scope === "earth") gid = gid || "0";
    activeGlobalScope = scope;
    activeGlobalGeoId = gid;
    var globalStatsBtn = document.getElementById("qb-global-location-stats-link");
    if (globalStatsBtn) {
      var showGlobalStats =
        dashCfg.showGlobalLocationStatistics &&
        ((scope === "earth" && dashCfg.showGlobalEarthStatistics) ||
          (scope === "continent" &&
            dashCfg.showGlobalContinentStatistics &&
            gid) ||
          (scope === "country" && dashCfg.showGlobalCountryStatistics && gid) ||
          (scope === "zone" && dashCfg.showGlobalZoneStatistics && gid));
      globalStatsBtn.hidden = !showGlobalStats;
      if (showGlobalStats) {
        globalStatsBtn.href = buildLocationStatsUrl(scope, gid);
      }
    }
    loadLeadershipCouncil("global", scope, scope === "earth" ? "0" : gid);
    var boardTitle = document.getElementById("qb-global-board-title");
    var boardSub = document.getElementById("qb-global-board-subtitle");
    if (boardTitle) {
      text(boardTitle, boardNames[scope] || uiTr("collective_earth_board"));
    }
    if (boardSub) {
      text(boardSub, uiTr("board_subtitle_live"));
    }
    loadGlobalCollectiveBoard();
  }

  document.querySelectorAll(".qb-js-global-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      if (tab.hidden) return;
      document.querySelectorAll(".qb-js-global-tab").forEach(function (t) {
        var on = t === tab;
        t.classList.toggle("is-active", on);
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      loadGlobalPanel();
      if (window.qbPlanetary && window.qbPlanetary.onLocationTabChange) {
        var scope = tab.getAttribute("data-global-scope") || "";
        var gid = tab.getAttribute("data-global-id") || "";
        if (scope === "earth" && !gid) gid = "0";
        window.qbPlanetary.onLocationTabChange(gid, scope, "global");
      }
    });
  });

  document.querySelectorAll(".qb-js-global-board-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      activeGlobalBoardState = tab.getAttribute("data-board-state") || "live";
      document.querySelectorAll(".qb-js-global-board-tab").forEach(function (t) {
        var on = t === tab;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      loadGlobalCollectiveBoard();
    });
  });

  var selectedGlobalLabels = [];

  function clearGlobalSelection() {
    selectedGlobalLabels.forEach(function (el) {
      el.classList.remove("is-selected");
    });
    selectedGlobalLabels = [];
  }

  function appendGlobalNode(container, label, id, rowKind) {
    var wrap = document.createElement("div");
    wrap.className = "qb-tree-node";
    var row = document.createElement("div");
    row.className = "qb-tree-row";
    var chev = document.createElement("button");
    chev.type = "button";
    chev.className = "qb-tree-chev";
    chev.textContent = "▸";
    var lab = document.createElement("button");
    lab.type = "button";
    lab.className = "qb-tree-label";
    lab.textContent = label;
    lab.setAttribute("data-geo-id", id);
    var kids = document.createElement("div");
    kids.className = "qb-tree-children";
    kids.hidden = true;
    row.appendChild(chev);
    row.appendChild(lab);
    wrap.appendChild(row);
    wrap.appendChild(kids);
    container.appendChild(wrap);

    chev.addEventListener("click", function (e) {
      e.stopPropagation();
      if (kids.getAttribute("data-loaded") === "1") {
        kids.hidden = !kids.hidden;
        chev.textContent = kids.hidden ? "▸" : "▾";
        return;
      }
      if (rowKind === "zone") return;
      var parentKey = rowKind === "root" ? "EARTH" : id;
      fetchGlobalChildren(parentKey).then(function (rows) {
        kids.innerHTML = "";
        var nextKind =
          rowKind === "root" ? "continent" : rowKind === "continent" ? "country" : "zone";
        rows.forEach(function (r) {
          appendGlobalNode(kids, r.name, r.id, nextKind);
        });
        kids.setAttribute("data-loaded", "1");
        kids.hidden = false;
        chev.textContent = "▾";
      });
    });

    lab.addEventListener("click", function (e) {
      e.preventDefault();
      clearGlobalSelection();
      lab.classList.add("is-selected");
      selectedGlobalLabels.push(lab);
      if (rowKind === "root") {
        globalSel.continent = null;
        globalSel.country = null;
        globalSel.zone = null;
        updateGlobalTabsFromSelection();
        var earthTab = document.querySelector('.qb-js-global-tab[data-global-scope="earth"]');
        if (earthTab) {
          document.querySelectorAll(".qb-js-global-tab").forEach(function (t) {
            var on = t === earthTab;
            t.classList.toggle("is-active", on);
            t.setAttribute("aria-selected", on ? "true" : "false");
          });
          loadGlobalPanel();
        }
        return;
      }
      if (rowKind === "continent") {
        globalSel.continent = { id: id, name: label };
        globalSel.country = null;
        globalSel.zone = null;
        updateGlobalTabsFromSelection();
        document.querySelectorAll(".qb-js-global-tab")[1].click();
      } else if (rowKind === "country") {
        globalSel.country = { id: id, name: label };
        globalSel.zone = null;
        updateGlobalTabsFromSelection();
        document.querySelectorAll(".qb-js-global-tab")[2].click();
      } else if (rowKind === "zone") {
        globalSel.zone = { id: id, name: label };
        updateGlobalTabsFromSelection();
        var zt = document.getElementById("qb-global-tab-zone");
        if (zt && !zt.hidden) zt.click();
      }
    });
  }

  function initGlobalTreeOnce() {
    if (globalTreeInited) return;
    var gro = document.getElementById("qb-tree-global-root");
    if (!gro) return;
    gro.innerHTML = "";
    appendGlobalNode(gro, "Earth", "EARTH", "root");
    globalTreeInited = true;
  }

  /* --- Messaging --- */
  var msgFlash = document.getElementById("qb-msg-flash");
  var currentViewMsg = null;

  function msgSetFlash(t) {
    text(msgFlash, t || "");
  }

  function refreshPrivateMsgBadge() {
    fetch("/api/messages/unread_count", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        var badge = document.getElementById("qb-private-msg-badge");
        if (!badge) return;
        var n = x.ok && x.b ? parseInt(x.b.unread_count, 10) || 0 : 0;
        badge.textContent = String(n);
        badge.hidden = n <= 0;
      })
      .catch(function () {});
  }

  function loadMessagesFolder(folder) {
    var listId =
      folder === "sent"
        ? "qb-msg-sent-list"
        : folder === "drafts"
          ? "qb-msg-drafts-list"
          : "qb-msg-inbox-list";
    var ul = document.getElementById(listId);
    if (!ul) return;
    fetch("/api/messages?folder=" + encodeURIComponent(folder), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Could not load messages");
        ul.innerHTML = "";
        (x.b.messages || []).forEach(function (m) {
          var li = document.createElement("li");
          li.className = "qb-msg-li mb-2 pb-2 border-bottom border-secondary";
          var unread =
            folder === "inbox" && !m.read_at && String(m.status || "") !== "read";
          var peer = folder === "sent" ? m.recipient_id : m.sender_id;
          var peerLabel = folder === "sent" ? "To" : "From";
          li.innerHTML =
            '<div class="text-muted small">' +
            esc(m.created_at || "") +
            (unread ? ' · <span class="text-info">unread</span>' : "") +
            "</div>" +
            "<div><strong>" +
            peerLabel +
            ":</strong> <span class='font-monospace'>" +
            esc(peer) +
            "</span></div>" +
            "<div><strong>Subject:</strong> " +
            esc(m.subject || "(no subject)") +
            "</div>" +
            '<div class="mt-1"><button type="button" class="qb-btn qb-btn-outline btn-sm qb-msg-open-folder" data-mid="' +
            esc(m.message_id) +
            '" data-box="' +
            esc(folder) +
            '">Read</button></div>';
          ul.appendChild(li);
        });
        ul.querySelectorAll(".qb-msg-open-folder").forEach(function (btn) {
          btn.addEventListener("click", function () {
            openMessage(btn.getAttribute("data-mid"), btn.getAttribute("data-box") || folder);
          });
        });
      })
      .catch(function () {
        msgSetFlash("Could not load " + folder + ".");
      });
  }

  function showMsgPanel(name) {
    ["inbox", "sent", "drafts", "compose", "view"].forEach(function (p) {
      var el = document.getElementById("qb-msg-panel-" + p);
      if (el) el.hidden = p !== name;
    });
    document.querySelectorAll(".qb-msg-tab").forEach(function (b) {
      var t = b.getAttribute("data-msg-tab");
      if (name === "view") {
        b.classList.remove("is-active");
      } else {
        b.classList.toggle("is-active", t === name);
      }
    });
  }

  document.querySelectorAll(".qb-msg-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var t = btn.getAttribute("data-msg-tab");
      if (!t || t === "view") return;
      showMsgPanel(t);
      if (t === "inbox") loadInbox();
      if (t === "sent") loadSent();
      if (t === "drafts") loadDrafts();
    });
  });

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function loadInbox() {
    loadMessagesFolder("inbox");
    return;
    fetch("/api/messages/inbox", { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var ul = document.getElementById("qb-msg-inbox-list");
        if (!ul) return;
        ul.innerHTML = "";
        (data.messages || []).forEach(function (m) {
          var li = document.createElement("li");
          li.className = "qb-msg-li mb-2 pb-2 border-bottom border-secondary";
          li.innerHTML =
            '<div class="text-muted small">' +
            esc(m.created_at || "") +
            "</div>" +
            "<div><strong>From:</strong> <span class='font-monospace'>" +
            esc(m.sender_id) +
            "</span></div>" +
            "<div><strong>Subject:</strong> " +
            esc(m.subject || "(no subject)") +
            "</div>" +
            '<div class="mt-1"><button type="button" class="qb-btn qb-btn-outline btn-sm qb-msg-read" data-mid="' +
            esc(m.message_id) +
            '">Read</button></div>';
          ul.appendChild(li);
        });
        ul.querySelectorAll(".qb-msg-read").forEach(function (btn) {
          btn.addEventListener("click", function () {
            openMessage(btn.getAttribute("data-mid"), "inbox");
          });
        });
      })
      .catch(function () {
        msgSetFlash("Could not load inbox.");
      });
  }

  function loadSent() {
    loadMessagesFolder("sent");
    return;
    fetch("/api/messages/sent", { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var ul = document.getElementById("qb-msg-sent-list");
        if (!ul) return;
        ul.innerHTML = "";
        (data.messages || []).forEach(function (m) {
          var li = document.createElement("li");
          li.className = "qb-msg-li mb-2 pb-2 border-bottom border-secondary";
          li.innerHTML =
            '<div class="text-muted small">' +
            esc(m.created_at || "") +
            "</div>" +
            "<div><strong>To:</strong> <span class='font-monospace'>" +
            esc(m.recipient_id) +
            "</span></div>" +
            "<div><strong>Subject:</strong> " +
            esc(m.subject || "(no subject)") +
            "</div>" +
            '<div class="mt-1"><button type="button" class="qb-btn qb-btn-outline btn-sm qb-msg-open" data-mid="' +
            esc(m.message_id) +
            '">Open</button></div>';
          ul.appendChild(li);
        });
        ul.querySelectorAll(".qb-msg-open").forEach(function (btn) {
          btn.addEventListener("click", function () {
            openMessage(btn.getAttribute("data-mid"), "sent");
          });
        });
      });
  }

  function loadDrafts() {
    loadMessagesFolder("drafts");
    return;
    fetch("/api/messages/drafts", { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var ul = document.getElementById("qb-msg-drafts-list");
        if (!ul) return;
        ul.innerHTML = "";
        (data.messages || []).forEach(function (m) {
          var li = document.createElement("li");
          li.className = "qb-msg-li mb-2 pb-2 border-bottom border-secondary";
          li.innerHTML =
            '<div class="text-muted small">' +
            esc(m.created_at || "") +
            "</div>" +
            "<div><strong>To:</strong> <span class='font-monospace'>" +
            esc(m.recipient_id) +
            "</span></div>" +
            "<div><strong>Subject:</strong> " +
            esc(m.subject || "(no subject)") +
            "</div>" +
            '<div class="mt-1"><button type="button" class="qb-btn qb-btn-outline btn-sm qb-msg-open" data-mid="' +
            esc(m.message_id) +
            '">Open</button></div>';
          ul.appendChild(li);
        });
        ul.querySelectorAll(".qb-msg-open").forEach(function (btn) {
          btn.addEventListener("click", function () {
            openMessage(btn.getAttribute("data-mid"), "drafts");
          });
        });
      });
  }

  function fetchMessageById(mid, box) {
    return fetch(
      "/api/messages?folder=" + encodeURIComponent(box || "inbox"),
      { credentials: "same-origin" }
    ).then(function (r) {
      return r.json();
    }).then(function (data) {
      var list = data.messages || [];
      return list.find(function (x) {
        return x.message_id === mid;
      });
    });
  }

  function openMessage(mid, box) {
    fetchMessageById(mid, box).then(function (m) {
      if (!m) {
        msgSetFlash("Message not found.");
        return;
      }
      currentViewMsg = { msg: m, box: box };
      showMsgPanel("view");
      text(document.getElementById("qb-msg-view-meta"), "");
      var meta =
        "From: " +
        m.sender_id +
        " · To: " +
        m.recipient_id +
        " · " +
        (m.created_at || "");
      text(document.getElementById("qb-msg-view-meta"), meta);
      text(document.getElementById("qb-msg-view-subject"), m.subject || "(no subject)");
      text(document.getElementById("qb-msg-view-body"), m.body || "");
      if (box === "inbox") {
        fetch("/api/messages/read/" + encodeURIComponent(mid), {
          method: "POST",
          credentials: "same-origin",
        })
          .then(function () {
            refreshPrivateMsgBadge();
            fetchNotifications();
          })
          .catch(function () {});
      }
    });
  }

  var backBtn = document.getElementById("qb-msg-back-list");
  if (backBtn) {
    backBtn.addEventListener("click", function () {
      var b = (currentViewMsg && currentViewMsg.box) || "inbox";
      if (b === "sent") {
        showMsgPanel("sent");
        loadSent();
      } else if (b === "drafts") {
        showMsgPanel("drafts");
        loadDrafts();
      } else {
        showMsgPanel("inbox");
        loadInbox();
      }
    });
  }

  var replyBtn = document.getElementById("qb-msg-reply-btn");
  if (replyBtn) {
    replyBtn.addEventListener("click", function () {
      if (!currentViewMsg || !currentViewMsg.msg) return;
      var m = currentViewMsg.msg;
      var replyTo =
        currentViewMsg.box === "inbox" ? m.sender_id : m.recipient_id;
      showMsgPanel("compose");
      var to = document.getElementById("qb-msg-to");
      var sub = document.getElementById("qb-msg-subject");
      var body = document.getElementById("qb-msg-body");
      if (to) to.value = replyTo;
      if (sub) sub.value = m.subject ? "Re: " + m.subject : "";
      if (body) body.value = "";
    });
  }

  var delBtn = document.getElementById("qb-msg-delete-btn");
  if (delBtn) {
    delBtn.addEventListener("click", function () {
      if (!currentViewMsg || !currentViewMsg.msg) return;
      var mid = currentViewMsg.msg.message_id;
      fetch("/api/messages/delete/" + encodeURIComponent(mid), {
        method: "POST",
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error(x.b.error || "delete failed");
          msgSetFlash("Message deleted.");
          showMsgPanel("inbox");
          loadInbox();
        })
        .catch(function (e) {
          msgSetFlash(e.message || "Delete failed");
        });
    });
  }

  var composeForm = document.getElementById("qb-msg-compose-form");
  if (composeForm) {
    composeForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var to = (document.getElementById("qb-msg-to") || {}).value || "";
      var subject = (document.getElementById("qb-msg-subject") || {}).value || "";
      var body = (document.getElementById("qb-msg-body") || {}).value || "";
      fetch("/api/messages/send", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          recipient_id: to.trim(),
          subject: subject,
          body: body,
          is_draft: false,
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error(x.b.error || "Send failed");
          msgSetFlash("Message sent.");
          composeForm.reset();
          showMsgPanel("sent");
          loadSent();
          refreshPrivateMsgBadge();
          fetchNotifications();
        })
        .catch(function (e) {
          msgSetFlash(e.message || "Send failed");
        });
    });
  }

  var draftBtn = document.getElementById("qb-msg-save-draft");
  if (draftBtn) {
    draftBtn.addEventListener("click", function () {
      var to = (document.getElementById("qb-msg-to") || {}).value || "";
      var subject = (document.getElementById("qb-msg-subject") || {}).value || "";
      var body = (document.getElementById("qb-msg-body") || {}).value || "";
      if (!body.trim()) {
        msgSetFlash("Draft needs a message body.");
        return;
      }
      fetch("/api/messages/send", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          recipient_id: to.trim(),
          subject: subject,
          body: body,
          is_draft: true,
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error(x.b.error || "Save failed");
          msgSetFlash("Draft saved.");
          showMsgPanel("drafts");
          loadDrafts();
        })
        .catch(function (e) {
          msgSetFlash(e.message || "Save failed");
        });
    });
  }

  var privateMsgBtn = document.getElementById("qb-private-msg-btn");
  var privateMsgMenu = document.getElementById("qb-private-msg-menu");
  if (privateMsgBtn && privateMsgMenu) {
    privateMsgBtn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var open = privateMsgMenu.hidden;
      privateMsgMenu.hidden = !open;
      privateMsgBtn.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) refreshPrivateMsgBadge();
    });
    document.querySelectorAll(".qb-private-msg-menu-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var action = btn.getAttribute("data-msg-menu");
        privateMsgMenu.hidden = true;
        privateMsgBtn.setAttribute("aria-expanded", "false");
        openModal("qb-messages-modal");
        showMsgPanel(action || "inbox");
        if (action === "inbox") loadInbox();
        if (action === "sent") loadSent();
        if (action === "drafts") loadDrafts();
      });
    });
    document.addEventListener("click", function (ev) {
      if (!ev.target.closest("#qb-private-msg-wrap")) {
        privateMsgMenu.hidden = true;
        privateMsgBtn.setAttribute("aria-expanded", "false");
      }
    });
    refreshPrivateMsgBadge();
  }

  var adminRejectTargetId = null;
  var adminEditManifestTargetId = null;
  function adminNomFlash(msg) {
    text(document.getElementById("qb-admin-nominations-flash"), msg || "");
  }
  function nominationStatusBadge(status) {
    var s = String(status || "pending").toLowerCase();
    var cls = "qb-nom-status--pending";
    if (s === "approved") cls = "qb-nom-status--approved";
    else if (s === "rejected") cls = "qb-nom-status--rejected";
    return (
      "<span class='qb-nom-status-badge " +
      cls +
      "'>" +
      escHtml(s) +
      "</span>"
    );
  }
  function renderAdminPrivateDetails(d) {
    var body = document.getElementById("qb-admin-private-details-body");
    if (!body || !d) return;
    function hierarchyText(hier) {
      if (!hier) return "—";
      return ["state", "district", "tehsil", "village"]
        .map(function (scope) {
          var x = hier[scope];
          if (!x || !x.name) return "";
          return scope.charAt(0).toUpperCase() + scope.slice(1) + ": " + x.name;
        })
        .filter(Boolean)
        .join(" · ") || "—";
    }
    var txHtml = "";
    if (d.recent_transactions && d.recent_transactions.length) {
      txHtml =
        "<ul class='list-unstyled mb-0'>" +
        d.recent_transactions
          .map(function (t) {
            return (
              "<li class='font-monospace'>" +
              escHtml(String(t.amount)) +
              " · " +
              escHtml(t.reason || "") +
              " · " +
              escHtml(t.created_at || "") +
              "</li>"
            );
          })
          .join("") +
        "</ul>";
    } else {
      txHtml = "<p class='text-muted mb-0'>No recent transactions.</p>";
    }
    body.innerHTML =
      "<p class='mb-1'><strong>Name:</strong> " +
      escHtml(d.full_name || "") +
      "</p>" +
      "<p class='mb-1'><strong>Private ID:</strong> <span class='font-monospace'>" +
      escHtml(d.private_id || "") +
      "</span></p>" +
      "<p class='mb-1'><strong>Public ID:</strong> <span class='font-monospace'>" +
      escHtml(d.public_id || "") +
      "</span></p>" +
      "<p class='mb-1'><strong>Gender:</strong> " +
      escHtml(d.gender || "") +
      "</p>" +
      "<p class='mb-1'><strong>Age:</strong> " +
      escHtml(d.age == null ? "—" : String(d.age)) +
      " · <strong>Age group:</strong> " +
      escHtml(d.age_group || d.life_stage || "") +
      "</p>" +
      "<p class='mb-1'><strong>Birth location:</strong> " +
      escHtml(d.birth_location_label || hierarchyText(d.birth_location_hierarchy)) +
      "</p>" +
      "<p class='mb-1'><strong>Current location:</strong> " +
      escHtml(d.current_location_label || hierarchyText(d.current_location_hierarchy)) +
      "</p>" +
      "<p class='mb-1'><strong>Sun sign:</strong> " +
      escHtml(d.sun_sign || "") +
      " · <strong>Element:</strong> " +
      escHtml(d.element || "") +
      "</p>" +
      "<p class='mb-1'><strong>Karma index:</strong> " +
      escHtml(d.karma_index == null ? "0" : String(d.karma_index)) +
      "</p>" +
      "<p class='mb-1'><strong>Account type:</strong> " +
      escHtml(d.account_type || "") +
      "</p>" +
      "<p class='mb-1'><strong>Wallet balance:</strong> " +
      escHtml(d.wallet_balance == null ? "0" : String(d.wallet_balance)) +
      " Karma Points</p>" +
      "<h3 class='h6 mt-3 mb-2 text-secondary text-uppercase small'>Recent transactions</h3>" +
      txHtml;
  }
  function openAdminPrivateDetails(privateId) {
    var flash = document.getElementById("qb-admin-private-details-flash");
    if (flash) text(flash, "Loading…");
    openModal("qb-admin-private-details-modal");
    fetch(
      "/api/user/private_details?private_id=" + encodeURIComponent(privateId),
      { credentials: "same-origin", headers: { Accept: "application/json" } }
    )
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
        if (flash) text(flash, "");
        renderAdminPrivateDetails(x.b);
      })
      .catch(function (err) {
        if (flash) text(flash, err.message || "Could not load details");
      });
  }
  function bindAdminNominationActions(ul) {
    if (!ul) return;
    ul.querySelectorAll(".qb-js-nom-approve").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-id");
        fetch("/api/admin/nomination/approve/" + encodeURIComponent(id), {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
          .then(function (x) {
            if (!x.ok) throw new Error((x.b && x.b.error) || "Approve failed");
            adminNomFlash("Nomination approved.");
            loadAdminNominations();
            loadQuantumElectionUi(qpVillageId, "village");
          })
          .catch(function (err) {
            adminNomFlash(err.message || "Approve failed");
          });
      });
    });
    ul.querySelectorAll(".qb-js-nom-reject").forEach(function (btn) {
      btn.addEventListener("click", function () {
        adminRejectTargetId = btn.getAttribute("data-id");
        text(
          document.getElementById("qb-admin-reject-candidate-line"),
          "Candidate: " + (btn.getAttribute("data-name") || "")
        );
        var ta = document.getElementById("qb-admin-reject-reason");
        if (ta) ta.value = "";
        openModal("qb-admin-reject-modal");
      });
    });
    ul.querySelectorAll(".qb-js-nom-edit-manifest").forEach(function (btn) {
      btn.addEventListener("click", function () {
        adminEditManifestTargetId = btn.getAttribute("data-id");
        text(
          document.getElementById("qb-admin-edit-manifest-candidate-line"),
          "Candidate: " + (btn.getAttribute("data-name") || "")
        );
        var whyEl = document.getElementById("qb-admin-edit-why");
        var chEl = document.getElementById("qb-admin-edit-changes");
        if (whyEl) whyEl.value = btn.getAttribute("data-why") || "";
        if (chEl) chEl.value = btn.getAttribute("data-changes") || "";
        openModal("qb-admin-edit-manifest-modal");
      });
    });
    ul.querySelectorAll(".qb-js-nom-private-details").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var pid = btn.getAttribute("data-private-id");
        if (pid) openAdminPrivateDetails(pid);
      });
    });
  }
  function renderAdminNominationItem(n) {
      var li = document.createElement("li");
      li.className = "qb-admin-nom-item mb-3 pb-3 border-bottom border-secondary";
      var rawName = ((n.first_name || "") + " " + (n.last_name || "")).trim();
      var name = escHtml(rawName);
      var rejectBlock =
        n.status === "rejected" && n.rejection_reason
          ? "<div class='small text-warning mt-1'><strong>Rejection reason:</strong> " +
            escHtml(n.rejection_reason) +
            "</div>"
          : "";
      li.innerHTML =
        "<div class='d-flex flex-wrap justify-content-between align-items-start gap-2'>" +
        "<div><strong>" +
        name +
        "</strong> <span class='font-monospace'>" +
        escHtml(n.public_id || "") +
        "</span> " +
        nominationStatusBadge(n.status) +
        "</div>" +
        "<button type='button' class='qb-btn qb-btn-outline btn-sm qb-js-nom-private-details' data-private-id='" +
        escAttr(n.candidate_private_id || "") +
        "'>View Private Details</button>" +
        "</div>" +
        "<div class='small text-muted'>Gender: " +
        escHtml(n.gender || "") +
        " · Age: " +
        escHtml(n.age == null ? "—" : String(n.age)) +
        " · " +
        escHtml(n.age_group || "") +
        " · Zodiac: " +
        escHtml(n.sun_sign || n.zodiac_sign || "") +
        "</div>" +
        "<div class='small mt-1'><strong>Manifest</strong><br/>" +
        escHtml(n.manifest_text || "").replace(/\n/g, "<br/>") +
        "</div>" +
        rejectBlock +
        "<div class='d-flex flex-wrap gap-2 mt-2'>" +
        (n.status !== "approved"
          ? "<button type='button' class='qb-btn qb-btn-primary btn-sm qb-js-nom-approve' data-id='" +
            escAttr(String(n.id)) +
            "'>Approve</button>"
          : "") +
        (n.status === "pending" || n.status === "approved"
          ? "<button type='button' class='qb-btn qb-btn-outline btn-sm qb-js-nom-reject' data-id='" +
            escAttr(String(n.id)) +
            "' data-name='" +
            escAttr(rawName) +
            "'>Reject</button>"
          : "") +
        "<button type='button' class='qb-btn qb-btn-outline btn-sm qb-js-nom-edit-manifest' data-id='" +
        escAttr(String(n.id)) +
        "' data-name='" +
        escAttr(rawName) +
        "' data-why='" +
        escAttr(n.why_stand || "") +
        "' data-changes='" +
        escAttr(n.changes || "") +
        "'>Edit Manifest</button>" +
        "</div>";
    return li;
  }

  function renderAdminNominationsList(pending, approved) {
    var ulPending = document.getElementById("qb-admin-nominations-pending");
    var ulApproved = document.getElementById("qb-admin-nominations-approved");
    var emptyP = document.getElementById("qb-admin-nominations-pending-empty");
    var emptyA = document.getElementById("qb-admin-nominations-approved-empty");
    if (ulPending) ulPending.innerHTML = "";
    if (ulApproved) ulApproved.innerHTML = "";
    pending = pending || [];
    approved = approved || [];
    if (emptyP) emptyP.hidden = pending.length > 0;
    if (emptyA) emptyA.hidden = approved.length > 0;
    pending.forEach(function (n) {
      if (ulPending) ulPending.appendChild(renderAdminNominationItem(n));
    });
    approved.forEach(function (n) {
      if (ulApproved) ulApproved.appendChild(renderAdminNominationItem(n));
    });
    bindAdminNominationActions(ulPending);
    bindAdminNominationActions(ulApproved);
  }

  function loadAdminNominations() {
    fetch("/api/admin/nominations?status=all", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
        var line = document.getElementById("qb-admin-nominations-cycle-line");
        if (line && x.b.cycle) {
          text(
            line,
            "Cycle: " +
              (x.b.cycle.zodiac_sign || "") +
              " · phase " +
              (x.b.cycle.status || "")
          );
        }
        renderAdminNominationsList(x.b.pending || [], x.b.approved || []);
      })
      .catch(function (err) {
        adminNomFlash(err.message || "Could not load nominations");
      });
  }
  var adminNomBtn = document.getElementById("qb-admin-manage-nominations-btn");
  if (adminNomBtn) {
    adminNomBtn.addEventListener("click", function () {
      adminNomFlash("");
      openModal("qb-admin-nominations-modal");
      loadAdminNominations();
    });
  }
  var electionHistoryBtn = document.getElementById("qb-election-history-btn");
  if (electionHistoryBtn) {
    electionHistoryBtn.addEventListener("click", openElectionHistoryModal);
  }
  var adminElectionHistoryBtn = document.getElementById("qb-admin-election-history-btn");
  if (adminElectionHistoryBtn) {
    adminElectionHistoryBtn.addEventListener("click", openElectionHistoryModal);
  }
  var adminRejectConfirm = document.getElementById("qb-admin-reject-confirm");
  if (adminRejectConfirm) {
    adminRejectConfirm.addEventListener("click", function () {
      if (!adminRejectTargetId) return;
      var reason = ((document.getElementById("qb-admin-reject-reason") || {}).value || "").trim();
      if (!reason) {
        alert("Rejection reason is required.");
        return;
      }
      fetch("/api/admin/nomination/reject/" + encodeURIComponent(adminRejectTargetId), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ reason: reason }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Reject failed");
          closeModal("qb-admin-reject-modal");
          adminNomFlash("Nomination rejected; candidate notified.");
          loadAdminNominations();
          loadQuantumElectionUi(qpVillageId, "village");
        })
        .catch(function (err) {
          alert(err.message || "Reject failed");
        });
    });
  }
  var adminEditManifestSave = document.getElementById("qb-admin-edit-manifest-save");
  if (adminEditManifestSave) {
    adminEditManifestSave.addEventListener("click", function () {
      if (!adminEditManifestTargetId) return;
      var why = ((document.getElementById("qb-admin-edit-why") || {}).value || "").trim();
      var changes = ((document.getElementById("qb-admin-edit-changes") || {}).value || "").trim();
      if (!why) {
        alert("Reason to fight is required.");
        return;
      }
      fetch(
        "/api/admin/nomination/edit_manifest/" + encodeURIComponent(adminEditManifestTargetId),
        {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ why_stand: why, changes: changes }),
        }
      )
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          closeModal("qb-admin-edit-manifest-modal");
          adminNomFlash("Manifest updated.");
          loadAdminNominations();
        })
        .catch(function (err) {
          alert(err.message || "Save failed");
        });
    });
  }
  function loadAdminVillageMembers() {
    var flash = document.getElementById("qb-admin-village-members-flash");
    var tbody = document.getElementById("qb-admin-village-members-tbody");
    var empty = document.getElementById("qb-admin-village-members-empty");
    var subtitle = document.getElementById("qb-admin-village-members-subtitle");
    if (flash) text(flash, "Loading…");
    if (tbody) tbody.innerHTML = "";
    var vid = dashCfg.defaultVillageId || "";
    var url =
      "/api/admin/location_members?location_type=village&location_id=" +
      encodeURIComponent(vid);
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
        if (flash) text(flash, "");
        if (subtitle) {
          text(
            subtitle,
            (x.b.location_title || "Village") +
              " · " +
              (x.b.location_id || vid)
          );
        }
        var members = x.b.members || [];
        if (!members.length) {
          if (empty) empty.hidden = false;
          return;
        }
        if (empty) empty.hidden = true;
        if (!tbody) return;
        members.forEach(function (m) {
          var tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" +
            escHtml(m.full_name || "") +
            "</td>" +
            "<td>" +
            escHtml(m.gender || "") +
            "</td>" +
            "<td class='font-monospace'>" +
            escHtml(m.age == null ? "—" : String(m.age)) +
            "</td>" +
            "<td>" +
            escHtml(m.life_stage || "") +
            "</td>" +
            "<td>" +
            escHtml(m.sun_sign || "") +
            "</td>" +
            "<td class='font-monospace small'>" +
            escHtml(m.private_id || "") +
            "</td>" +
            "<td class='font-monospace small'>" +
            escHtml(m.public_id || "") +
            "</td>" +
            "<td class='font-monospace small'>" +
            escHtml(m.birth_location_id || "") +
            "</td>" +
            "<td class='font-monospace small'>" +
            escHtml(m.current_location_id || "") +
            "</td>";
          tbody.appendChild(tr);
        });
      })
      .catch(function (err) {
        if (flash) text(flash, err.message || "Could not load members");
      });
  }
  var adminVillageMembersBtn = document.getElementById("qb-admin-village-members-btn");
  if (adminVillageMembersBtn && dashCfg.isAdmin) {
    adminVillageMembersBtn.addEventListener("click", function () {
      openModal("qb-admin-village-members-modal");
      loadAdminVillageMembers();
    });
  }

  if (document.querySelector(".qb-js-global-tab")) {
    updateGlobalTabsFromSelection();
    loadGlobalPanel();
  }

  function parseJsonResponse(r) {
    var ct = (r.headers.get("Content-Type") || "").toLowerCase();
    return r.text().then(function (text) {
      if (!text || !text.trim()) {
        return { ok: r.ok, b: { error: "Empty response from server" } };
      }
      if (ct.indexOf("application/json") === -1 && text.trim().charAt(0) === "<") {
        return {
          ok: false,
          b: {
            error:
              "Server returned HTML instead of JSON. You may need to log in again, or the birth chart route failed on the server.",
          },
        };
      }
      try {
        return { ok: r.ok, b: JSON.parse(text) };
      } catch (parseErr) {
        return {
          ok: false,
          b: { error: "Invalid JSON from server: " + (parseErr.message || "parse error") },
        };
      }
    });
  }

  function renderVedicGrid(el, gridCells) {
    if (!el || !gridCells || !gridCells.length) return;
    el.innerHTML = "";
    gridCells.forEach(function (cell) {
      var box = document.createElement("div");
      box.className = "qb-vedic-cell";
      var houseNum = cell.house != null ? String(cell.house) : "";
      var planets = (cell.planets || []).join(" ");
      box.innerHTML =
        "<span class='qb-vedic-cell-house'>" +
        escHtml(houseNum) +
        "</span>" +
        "<span class='qb-vedic-cell-sign'>" +
        escHtml(cell.sign || "") +
        "</span>" +
        "<span class='qb-vedic-cell-planets'>" +
        escHtml(planets) +
        "</span>";
      el.appendChild(box);
    });
  }

  function renderBirthChartTable(rows) {
    var tbody = document.getElementById("qb-birth-chart-planets-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    (rows || []).forEach(function (p) {
      var tr = document.createElement("tr");
      var pada = p.pada != null && p.pada !== "" ? String(p.pada) : "—";
      tr.innerHTML =
        "<td>" +
        escHtml(p.name || "") +
        "</td><td>" +
        escHtml(p.sign || "") +
        "</td><td class='font-monospace small'>" +
        escHtml(p.degree || "—") +
        "</td><td>" +
        escHtml(p.nakshatra || "—") +
        "</td><td class='text-center'>" +
        escHtml(pada) +
        "</td><td class='text-center'>" +
        (p.retrograde ? "<span class='text-warning'>R</span>" : "—") +
        "</td>";
      tbody.appendChild(tr);
    });
  }

  /* legacy removed */
  function _renderChartGridLegacy_UNUSED(el, chart) {
    if (!el || !chart) return;
    var cells = chart.houses;
    if (!cells && chart.houses && typeof chart.houses === "object" && !Array.isArray(chart.houses)) {
      cells = Object.keys(chart.houses)
        .sort(function (a, b) {
          return parseInt(a, 10) - parseInt(b, 10);
        })
        .map(function (k) {
          return { house: parseInt(k, 10), sign: chart.houses[k], planets: [] };
        });
    }
    if (!cells || !cells.length) return;
    el.innerHTML = "";
    cells.forEach(function (cell) {
      var box = document.createElement("div");
      box.className = "qb-chart-cell";
      var planets = (cell.planets || []).join(" ");
      box.innerHTML =
        "<div class='qb-chart-cell-sign'>" +
        escHtml(cell.sign || "") +
        "</div>" +
        "<div class='qb-chart-cell-planets small'>" +
        escHtml(planets) +
        "</div>";
      el.appendChild(box);
    });
  }

  function renderBirthChartPayload(data) {
    var flash = document.getElementById("qb-birth-chart-flash");
    var unavail = document.getElementById("qb-birth-chart-unavailable");
    var body = document.getElementById("qb-birth-chart-body");
    if (flash) text(flash, "");
    if (unavail) {
      if (data.library_missing || data.mock) {
        unavail.hidden = false;
        text(
          unavail,
          data.message ||
            "Showing simplified chart. Install jyotishyam for full Vedic calculations."
        );
      } else if (data.error) {
        unavail.hidden = false;
        text(unavail, data.error + (data.details ? " — " + data.details : ""));
      } else {
        unavail.hidden = true;
        text(unavail, "");
      }
    }
    if (body) body.hidden = false;
    var meta = document.getElementById("qb-birth-chart-meta");
    if (meta) {
      var asc = data.ascendant || {};
      text(
        meta,
        "Lagna: " +
          (asc.sign || "—") +
          " " +
          (asc.degree || "") +
          " · " +
          (asc.nakshatra || "") +
          (asc.pada ? " Pada " + asc.pada : "")
      );
    }
    renderVedicGrid(document.getElementById("qb-birth-chart-rasi-grid"), data.rasi_grid);
    renderVedicGrid(document.getElementById("qb-birth-chart-chandra-grid"), data.chandra_grid);
    renderBirthChartTable(data.table_rows || []);
  }

  function loadBirthChartModal() {
    var flash = document.getElementById("qb-birth-chart-flash");
    var unavail = document.getElementById("qb-birth-chart-unavailable");
    var body = document.getElementById("qb-birth-chart-body");
    if (flash) text(flash, "Loading chart…");
    if (unavail) {
      unavail.hidden = true;
      text(unavail, "");
    }
    if (body) body.hidden = true;
    return fetch("/api/user/birth_chart", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(parseJsonResponse)
      .then(function (x) {
        var data = x.b || {};
        if (!x.ok && data.error) {
          throw new Error(data.error);
        }
        if (data.error && !data.available && !data.mock) {
          throw new Error(data.error);
        }
        if (data.available === false && !data.mock) {
          if (unavail) {
            unavail.hidden = false;
            text(unavail, data.message || data.error || "Chart unavailable.");
          }
          return;
        }
        renderBirthChartPayload(data);
      })
      .catch(function (err) {
        if (flash) text(flash, "");
        if (body) body.hidden = true;
        if (unavail) {
          unavail.hidden = false;
          text(unavail, err.message || "Could not load chart.");
        }
      });
  }

  var birthChartBtn = document.getElementById("qb-birth-chart-btn");
  if (birthChartBtn) {
    birthChartBtn.addEventListener("click", function () {
      openModal("qb-birth-chart-modal");
      loadBirthChartModal();
    });
  }

  var adminUpgradeSelected = null;
  var adminUpgradeSearchTimer = null;
  var adminUpgradeSearch = document.getElementById("qb-admin-upgrade-search");
  var adminUpgradeSuggest = document.getElementById("qb-admin-upgrade-suggest");
  var adminUpgradeSelectedEl = document.getElementById("qb-admin-upgrade-selected");
  var adminUpgradeSubmit = document.getElementById("qb-admin-upgrade-submit");

  function syncAdminUpgradeSubmit() {
    if (adminUpgradeSubmit) {
      adminUpgradeSubmit.disabled = !(
        adminUpgradeSelected &&
        (document.getElementById("qb-admin-upgrade-type") || {}).value
      );
    }
  }

  if (adminUpgradeSearch) {
    adminUpgradeSearch.addEventListener("input", function () {
      adminUpgradeSelected = null;
      syncAdminUpgradeSubmit();
      if (adminUpgradeSelectedEl) adminUpgradeSelectedEl.hidden = true;
      var q = (adminUpgradeSearch.value || "").trim();
      clearTimeout(adminUpgradeSearchTimer);
      if (!q || q.length < 2) {
        if (adminUpgradeSuggest) {
          adminUpgradeSuggest.hidden = true;
          adminUpgradeSuggest.innerHTML = "";
        }
        return;
      }
      adminUpgradeSearchTimer = setTimeout(function () {
        fetch("/api/admin/users/search?q=" + encodeURIComponent(q), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
          .then(function (x) {
            if (!adminUpgradeSuggest) return;
            adminUpgradeSuggest.innerHTML = "";
            (x.b.users || []).forEach(function (u) {
              var li = document.createElement("li");
              var btn = document.createElement("button");
              btn.type = "button";
              btn.className = "qb-btn qb-btn-outline btn-sm w-100 text-start mb-1";
              btn.textContent =
                (u.full_name || "") + " · " + (u.public_id || "") + " (" + (u.account_type || "") + ")";
              btn.addEventListener("click", function () {
                adminUpgradeSelected = u;
                adminUpgradeSearch.value = u.public_id || "";
                adminUpgradeSuggest.hidden = true;
                if (adminUpgradeSelectedEl) {
                  adminUpgradeSelectedEl.hidden = false;
                  text(
                    adminUpgradeSelectedEl,
                    "Selected: " + (u.full_name || "") + " · " + (u.public_id || "")
                  );
                }
                syncAdminUpgradeSubmit();
              });
              li.appendChild(btn);
              adminUpgradeSuggest.appendChild(li);
            });
            adminUpgradeSuggest.hidden = !(x.b.users && x.b.users.length);
          });
      }, 250);
    });
  }

  var adminUpgradeType = document.getElementById("qb-admin-upgrade-type");
  if (adminUpgradeType) {
    adminUpgradeType.addEventListener("change", syncAdminUpgradeSubmit);
  }

  if (adminUpgradeSubmit) {
    adminUpgradeSubmit.addEventListener("click", function () {
      if (!adminUpgradeSelected) return;
      var newType = ((document.getElementById("qb-admin-upgrade-type") || {}).value || "").trim();
      if (!newType) return;
      var flash = document.getElementById("qb-admin-upgrade-flash");
      if (flash) text(flash, "Upgrading…");
      fetch("/api/upgrade/user", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          public_id: adminUpgradeSelected.public_id,
          new_account_type: newType,
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Upgrade failed");
          if (flash) {
            text(
              flash,
              "Upgraded " + (x.b.full_name || adminUpgradeSelected.public_id) + " to " + newType + "."
            );
          }
          adminUpgradeSelected = null;
          syncAdminUpgradeSubmit();
        })
        .catch(function (err) {
          if (flash) text(flash, err.message || "Upgrade failed");
        });
    });
  }

  function initVillageCommerce() {
    /* Marketplace moved to /marketplace — village hub handles karma & business registration. */
  }

  function loadKarmaTypes() {
    return fetch("/api/karma/karma/types", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var sel = document.getElementById("qb-karma-action-select");
        if (!sel) return;
        sel.innerHTML = "";
        (x.b.actions || []).forEach(function (a) {
          var opt = document.createElement("option");
          opt.value = a.action_code;
          opt.textContent = a.label + " (₹" + a.rupee_value + ")";
          sel.appendChild(opt);
        });
      });
  }

  function loadKarmaPending() {
    return fetch("/api/karma/claims", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var ul = document.getElementById("qb-karma-pending-list");
        var empty = document.getElementById("qb-karma-pending-empty");
        if (!ul) return;
        ul.innerHTML = "";
        var rows = (x.b.claims || []).filter(function (c) {
          return c.status === "pending" || c.status === "partially_approved";
        });
        if (!rows.length) {
          if (empty) empty.hidden = false;
          return;
        }
        if (empty) empty.hidden = true;
        rows.forEach(function (c) {
          var li = document.createElement("li");
          li.className = "mb-2";
          li.textContent =
            (c.action_label || c.action_code) +
            " · " +
            (c.status || "") +
            " · ₹" +
            (c.amount_rupees || 0);
          ul.appendChild(li);
        });
      });
  }

  var karmaClaimForm = document.getElementById("qb-village-karma-claim-form");
  if (karmaClaimForm) {
    karmaClaimForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var flash = document.getElementById("qb-karma-flash");
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          function (pos) {
            var lat = document.getElementById("qb-karma-gps-lat");
            var lng = document.getElementById("qb-karma-gps-lng");
            if (lat) lat.value = String(pos.coords.latitude);
            if (lng) lng.value = String(pos.coords.longitude);
            submitKarmaClaimForm(flash);
          },
          function () {
            submitKarmaClaimForm(flash);
          }
        );
      } else {
        submitKarmaClaimForm(flash);
      }
    });
  }

  function submitKarmaClaimForm(flash) {
    var form = document.getElementById("qb-village-karma-claim-form");
    if (!form) return;
    if (flash) text(flash, "Submitting…");
    fetch("/api/karma/claims", {
      method: "POST",
      credentials: "same-origin",
      body: new FormData(form),
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Failed");
        if (flash) {
          text(
            flash,
            x.b && x.b.karma_recorded
              ? "Karma recorded! You can share your good deed."
              : "Karma claim submitted for Council review."
          );
        }
        form.reset();
        loadKarmaPending();
        if (x.b && x.b.karma_recorded) {
          qbShowShareKarma({
            action_code: x.b.action_code,
            amount_rupees: x.b.amount_rupees,
            action_label: x.b.action_label,
          });
        }
      })
      .catch(function (err) {
        if (flash) text(flash, err.message || "Error");
      });
  }

  var villageBusinessBtn = document.getElementById("qb-village-business-btn");
  if (villageBusinessBtn) {
    villageBusinessBtn.addEventListener("click", function () {
      openModal("qb-business-register-modal");
    });
  }

  var businessRegisterForm = document.getElementById("qb-business-register-form");
  if (businessRegisterForm) {
    businessRegisterForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var flash = document.getElementById("qb-business-register-flash");
      fetch("/api/businesses/register", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          business_name: (document.getElementById("qb-biz-name") || {}).value || "",
          business_type: (document.getElementById("qb-biz-type") || {}).value || "",
          address: (document.getElementById("qb-biz-address") || {}).value || "",
          gst_number: (document.getElementById("qb-biz-gst") || {}).value || "",
          pan_number: (document.getElementById("qb-biz-pan") || {}).value || "",
          terms_accepted: !!(document.getElementById("qb-biz-terms") || {}).checked,
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Registration failed");
          if (flash) text(flash, "Business registration submitted for Council approval.");
          closeModal("qb-business-register-modal");
        })
        .catch(function (err) {
          if (flash) text(flash, err.message || "Error");
        });
    });
  }

  function loadAdminKarmaPanel() {
    if (!dashCfg.isAdmin) return;
    fetch("/api/karma/pending", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var el = document.getElementById("qb-admin-pending-summary");
        if (el) {
          el.textContent =
            "Pending: " +
            (x.b.pending_count || 0) +
            " txn · ₹" +
            (x.b.pending_rupees || 0) +
            " · " +
            (x.b.unsettled_karma || 0) +
            " karma";
        }
      });
    fetch("/api/admin/karma/nested-wallets", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var circ = document.getElementById("qb-admin-circulation-summary");
        if (circ && x.b.circulation) {
          circ.textContent =
            "Circulation: " +
            x.b.circulation.total_qoins +
            " Karma Points (₹" +
            x.b.circulation.total_rupees +
            ")";
        }
        var nw = document.getElementById("qb-admin-nested-wallets");
        if (!nw) return;
        nw.innerHTML = "";
        (x.b.wallets || []).slice(0, 12).forEach(function (w) {
          var li = document.createElement("li");
          li.textContent =
            w.owner_type +
            " / " +
            w.owner_id +
            " — " +
            w.balance_qoins +
            " Karma Points (₹" +
            w.total_rupees +
            ")";
          nw.appendChild(li);
        });
      });
    fetch("/api/admin/karma/karma-types", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var ul = document.getElementById("qb-admin-karma-types-list");
        if (!ul) return;
        ul.innerHTML = "";
        (x.b.actions || []).forEach(function (a) {
          var li = document.createElement("li");
          li.textContent = a.action_code + " — " + a.label + " (₹" + a.rupee_value + ")";
          ul.appendChild(li);
        });
      });
  }

  var adminSettlementBtn = document.getElementById("qb-admin-settlement-btn");
  if (adminSettlementBtn) {
    adminSettlementBtn.addEventListener("click", function () {
      var flash = document.getElementById("qb-admin-settlement-flash");
      if (flash) text(flash, "Running settlement…");
      fetch("/api/admin/karma/settlement", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ force: true }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Settlement failed");
          var res = (x.b && x.b.result) || {};
          if (flash) {
            text(
              flash,
              "Done — " +
                (res.users_settled || 0) +
                " statement(s). Insufficient: " +
                ((res.insufficient_users || []).length || 0)
            );
          }
          loadAdminKarmaPanel();
        })
        .catch(function (err) {
          if (flash) text(flash, err.message || "Error");
        });
    });
  }

  var adminKarmaSave = document.getElementById("qb-admin-karma-save");
  if (adminKarmaSave) {
    adminKarmaSave.addEventListener("click", function () {
      var code = (document.getElementById("qb-admin-karma-code") || {}).value || "";
      var label = (document.getElementById("qb-admin-karma-label") || {}).value || "";
      var val = parseInt(String((document.getElementById("qb-admin-karma-value") || {}).value || ""), 10);
      fetch("/api/admin/karma/karma-types", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          action_code: code.trim(),
          label: label.trim(),
          rupee_value: val,
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          loadAdminKarmaPanel();
          loadKarmaTypes();
        })
        .catch(function (err) {
          alert(err.message || "Could not save karma type");
        });
    });
  }

  loadKarmaTypes();
  loadAdminKarmaPanel();

  function refreshLocationMode(nextMode) {
    return fetch("/api/user/location-mode", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ mode: nextMode }),
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Could not switch location");
        window.location.reload();
      });
  }

  function bindLocationToggle(btnId) {
    var btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener("click", function () {
      var cur = btn.getAttribute("data-mode") || "present";
      var next = cur === "birth" ? "present" : "birth";
      refreshLocationMode(next).catch(function (err) {
        alert(err.message || "Location switch failed");
      });
    });
  }
  bindLocationToggle("qb-location-toggle-public");

  var saveMotherTongueBtn = document.getElementById("save-mother-tongue");
  if (saveMotherTongueBtn) {
    saveMotherTongueBtn.addEventListener("click", function () {
      var sel = document.getElementById("mother-tongue");
      var flash = document.getElementById("qb-mother-tongue-flash");
      if (!sel) return;
      var code = (sel.value || "").trim();
      var opt = sel.options[sel.selectedIndex];
      var name = opt ? opt.getAttribute("data-name") || opt.textContent || "" : "";
      text(flash, "Saving…");
      fetch("/api/user/mother-tongue", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          mother_tongue_code: code || null,
          mother_tongue_name: name || null,
        }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
          text(flash, "Saved.");
          window.setTimeout(function () {
            window.location.reload();
          }, 400);
        })
        .catch(function (err) {
          text(flash, err.message || "Error");
        });
    });
  }

  var villageServicesBtn = document.getElementById("qb-village-services-btn");
  if (villageServicesBtn) {
    villageServicesBtn.addEventListener("click", openVillageServicesModal);
  }
  var electionsBtn = document.getElementById("qb-elections-btn");
  if (electionsBtn) {
    electionsBtn.addEventListener("click", openElectionsModal);
  }
  if (!electionsEnabled && electionPausedBanner) {
    electionPausedBanner.hidden = false;
  }

  var accountIdsBtn = document.getElementById("qb-my-account-ids-btn");
  if (accountIdsBtn) {
    accountIdsBtn.addEventListener("click", function () {
      fetch("/api/user/account-ids", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Load failed");
          var list = document.getElementById("qb-account-ids-list");
          var empty = document.getElementById("qb-account-ids-empty");
          if (!list) return;
          list.innerHTML = "";
          var rows = x.b.accounts || [];
          if (!rows.length) {
            if (empty) empty.hidden = false;
          } else {
            if (empty) empty.hidden = true;
            rows.forEach(function (row) {
              var li = document.createElement("li");
              li.className = "mb-2 p-2 border rounded";
              var primary = parseInt(row.is_primary, 10) === 1;
              li.innerHTML =
                "<strong class=\"font-monospace\">" +
                (row.account_id || "") +
                "</strong>" +
                (primary ? ' <span class="badge bg-primary">Primary</span>' : "") +
                "<br><span class=\"text-muted\">" +
                (row.location_type || "") +
                " · " +
                (row.location_path || "") +
                "</span>" +
                (row.last_used_at
                  ? '<br><span class="text-muted">Last used: ' + row.last_used_at + "</span>"
                  : "");
              list.appendChild(li);
            });
          }
          openModal("qb-account-ids-modal");
        })
        .catch(function (err) {
          alert(err.message || "Could not load account IDs");
        });
    });
  }

  window.qbOpenModal = openModal;
  window.qbCloseModal = closeModal;

  /* --- Referral panel & Share Karma --- */
  var lastShareKarmaPayload = null;

  function qbReferralConfig() {
    return (dashCfg && {
      code: dashCfg.referralCode,
      count: dashCfg.referralCount,
      earnings: dashCfg.referralEarnings,
      regUrl: dashCfg.referralRegistrationUrl,
      qr: dashCfg.referralQrBase64,
    }) || {};
  }

  function qbLogShare(shareType) {
    fetch("/api/referral/share", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ share_type: shareType }),
    }).catch(function () {});
  }

  function qbCopyText(value, toastMsg) {
    if (!value) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(function () {
        if (window.qbToast) window.qbToast(toastMsg || uiTr("copied"), "success");
      });
    } else {
      var ta = document.createElement("textarea");
      ta.value = value;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        if (window.qbToast) window.qbToast(toastMsg || uiTr("copied"), "success");
      } catch (_e) {}
      document.body.removeChild(ta);
    }
  }

  function qbShareWhatsApp(text) {
    if (!text) return;
    qbLogShare("whatsapp");
    window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank");
  }

  function qbReferralInviteText() {
    var cfg = qbReferralConfig();
    return (
      "Join Qumanity — India's quantum governance platform. " +
      "Sign up with my referral code " +
      (cfg.code || "") +
      ": " +
      (cfg.regUrl || "")
    );
  }

  function qbShowShareKarma(payload) {
    lastShareKarmaPayload = payload || null;
    var btn = document.getElementById("qb-share-karma-btn");
    if (btn) btn.hidden = false;
    fetch("/api/referral/karma-share-text", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        action_code: (payload && payload.action_code) || "",
        amount_rupees: (payload && payload.amount_rupees) || 0,
      }),
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) return;
        var el = document.getElementById("qb-share-karma-text");
        if (el) el.textContent = x.b.text || "";
        openModal("qb-share-karma-modal");
      })
      .catch(function () {});
  }

  window.qbShowShareKarma = qbShowShareKarma;

  (function initReferralPanel() {
    var cfg = qbReferralConfig();
    var copyCode = document.getElementById("qb-referral-copy-code");
    if (copyCode) {
      copyCode.addEventListener("click", function () {
        qbCopyText(cfg.code, uiTr("copied"));
        qbLogShare("copy_code");
      });
    }
    var copyLink = document.getElementById("qb-referral-copy-link");
    if (copyLink) {
      copyLink.addEventListener("click", function () {
        qbCopyText(cfg.regUrl, uiTr("copied"));
        qbLogShare("copy_link");
      });
    }
    var wa = document.getElementById("qb-referral-whatsapp");
    if (wa) {
      wa.addEventListener("click", function () {
        qbShareWhatsApp(qbReferralInviteText());
      });
    }
    var showQr = document.getElementById("qb-referral-show-qr");
    var qrWrap = document.getElementById("qb-referral-qr-wrap");
    if (showQr && qrWrap) {
      showQr.addEventListener("click", function () {
        qrWrap.hidden = !qrWrap.hidden;
        if (!qrWrap.hidden) qbLogShare("qr_code");
        if (!cfg.qr && !qrWrap.hidden) {
          fetch("/api/referral/generate-qr", {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
          })
            .then(function (r) {
              return r.json();
            })
            .then(function (b) {
              var img = document.getElementById("qb-referral-qr-img");
              if (img && b.qr_code_base64) {
                img.src = "data:image/png;base64," + b.qr_code_base64;
              }
              var linkEl = document.getElementById("qb-referral-link-text");
              if (linkEl && b.registration_url) linkEl.textContent = b.registration_url;
            })
            .catch(function () {});
        }
      });
    }
  })();

  (function initShareKarmaModal() {
    var shareBtn = document.getElementById("qb-share-karma-btn");
    if (shareBtn) {
      shareBtn.addEventListener("click", function () {
        qbShowShareKarma(lastShareKarmaPayload || {});
      });
    }
    var wa = document.getElementById("qb-share-karma-whatsapp");
    if (wa) {
      wa.addEventListener("click", function () {
        var t = document.getElementById("qb-share-karma-text");
        qbShareWhatsApp(t ? t.textContent : "");
      });
    }
    var copy = document.getElementById("qb-share-karma-copy");
    if (copy) {
      copy.addEventListener("click", function () {
        var t = document.getElementById("qb-share-karma-text");
        qbCopyText(t ? t.textContent : "", uiTr("copied"));
        qbLogShare("copy_text");
      });
    }
    var qrBtn = document.getElementById("qb-share-karma-qr");
    var qrWrap = document.getElementById("qb-share-karma-qr-wrap");
    if (qrBtn && qrWrap) {
      qrBtn.addEventListener("click", function () {
        qrWrap.hidden = !qrWrap.hidden;
        if (!qrWrap.hidden) {
          qbLogShare("share_qr");
          fetch("/api/referral/generate-qr", {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
          })
            .then(function (r) {
              return r.json();
            })
            .then(function (b) {
              var img = document.getElementById("qb-share-karma-qr-img");
              if (img && b.qr_code_base64) {
                img.src = "data:image/png;base64," + b.qr_code_base64;
              }
            })
            .catch(function () {});
        }
      });
    }
  })();

  (function initVolunteerFeatures() {
    var applyOpen = document.getElementById("applyVolunteerBtn");
    if (applyOpen) {
      applyOpen.addEventListener("click", function () {
        openModal("qb-volunteer-apply-modal");
      });
    }
    var applyForm = document.getElementById("qb-volunteer-apply-form");
    if (applyForm) {
      applyForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var status = document.getElementById("qb-volunteer-apply-status");
        fetch("/api/volunteer/apply", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            bank_name: (document.getElementById("qb-volunteer-bank-name") || {}).value || "",
            account_number: (document.getElementById("qb-volunteer-account-number") || {}).value || "",
            branch: (document.getElementById("qb-volunteer-branch") || {}).value || "",
            ifsc_code: (document.getElementById("qb-volunteer-ifsc") || {}).value || "",
            reason: (document.getElementById("qb-volunteer-reason") || {}).value || "",
          }),
        })
          .then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
          .then(function (x) {
            if (!x.ok) throw new Error((x.b && x.b.error) || "Failed");
            closeModal("qb-volunteer-apply-modal");
            if (status) status.textContent = "Application submitted. Admin will review your request.";
            if (window.qbToast) window.qbToast("Volunteer application submitted", "success");
          })
          .catch(function (err) {
            if (window.qbToast) window.qbToast(err.message || "Error", "error");
          });
      });
    }

    var dashOpen = document.getElementById("qb-volunteer-dashboard-open");
    if (dashOpen) {
      dashOpen.addEventListener("click", function () {
        openModal("qb-volunteer-dashboard-modal");
        loadVolunteerDashboard();
      });
    }

    function loadVolunteerDashboard() {
      var codeEl = document.getElementById("qb-volunteer-dash-code");
      var perfBody = document.getElementById("qb-volunteer-perf-body");
      var signupsBody = document.getElementById("qb-volunteer-signups-body");
      fetch("/api/volunteer/dashboard", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Failed");
          if (codeEl) codeEl.textContent = x.b.volunteer_code || "—";
          var perf = x.b.performance || {};
          if (perfBody) {
            perfBody.innerHTML =
              "<tr><td>Signups</td><td>" +
              ((perf.week && perf.week.signups) || 0) +
              "</td><td>" +
              ((perf.month && perf.month.signups) || 0) +
              "</td><td>" +
              ((perf.year && perf.year.signups) || 0) +
              "</td><td>" +
              ((perf.total && perf.total.signups) || 0) +
              "</td></tr>" +
              "<tr><td>Karma Points</td><td>" +
              ((perf.week && perf.week.qoins) || 0) +
              "</td><td>" +
              ((perf.month && perf.month.qoins) || 0) +
              "</td><td>" +
              ((perf.year && perf.year.qoins) || 0) +
              "</td><td>" +
              ((perf.total && perf.total.qoins) || 0) +
              "</td></tr>";
          }
        })
        .catch(function () {
          if (perfBody) perfBody.innerHTML = "<tr><td colspan='5' class='text-danger'>Could not load dashboard</td></tr>";
        });
      fetch("/api/volunteer/signups", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (b) {
          if (!signupsBody) return;
          signupsBody.innerHTML = "";
          (b.signups || []).forEach(function (row) {
            var tr = document.createElement("tr");
            tr.innerHTML =
              "<td>" +
              (row.user_name || "") +
              "</td><td>" +
              (row.signup_date || "") +
              "</td><td>" +
              (row.status || "") +
              "</td><td>" +
              (row.qoins_earned || 0) +
              " Karma Points</td>";
            signupsBody.appendChild(tr);
          });
          if (!signupsBody.children.length) {
            signupsBody.innerHTML = "<tr><td colspan='4' class='text-muted'>No signups yet.</td></tr>";
          }
        })
        .catch(function () {
          if (signupsBody) signupsBody.innerHTML = "<tr><td colspan='4' class='text-danger'>Could not load signups</td></tr>";
        });
    }

    var copyBtn = document.getElementById("qb-volunteer-dash-copy");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var code = (document.getElementById("qb-volunteer-dash-code") || {}).textContent || "";
        if (code && navigator.clipboard) {
          navigator.clipboard.writeText(code.trim());
          if (window.qbToast) window.qbToast("Volunteer code copied", "success");
        }
      });
    }

    var exportBtn = document.getElementById("qb-volunteer-export");
    if (exportBtn) {
      exportBtn.addEventListener("click", function () {
        fetch("/api/volunteer/signups", {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (b) {
            var lines = ["User Name,Signup Date,Status,Karma Points Earned"];
            (b.signups || []).forEach(function (row) {
              lines.push(
                [
                  row.user_name || "",
                  row.signup_date || "",
                  row.status || "",
                  row.qoins_earned || 0,
                ].join(",")
              );
            });
            var blob = new Blob([lines.join("\n")], { type: "text/csv" });
            var a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "volunteer-signups.csv";
            a.click();
          });
      });
    }

    function loadEmploymentRequests() {
      var list = document.getElementById("qb-admin-employment-list");
      if (!list) return;
      fetch("/api/admin/employment/requests", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (b) {
          list.innerHTML = "";
          (b.requests || []).forEach(function (req) {
            var li = document.createElement("li");
            li.className = "mb-3 p-2 border border-secondary rounded";
            li.innerHTML =
              "<strong>" +
              (req.applicant_name || "") +
              "</strong><br>" +
              (req.applicant_state || "") +
              " · " +
              (req.applicant_village_id || "") +
              "<br><span class='text-muted'>" +
              (req.reason || "") +
              "</span><br><span class='text-muted small'>" +
              (req.bank_name || req.bank_account_details || "") +
              (req.ifsc_code ? " · IFSC: " + req.ifsc_code : "") +
              "</span>";
            var actions = document.createElement("div");
            actions.className = "d-flex gap-2 mt-2";
            var approve = document.createElement("button");
            approve.type = "button";
            approve.className = "qb-btn qb-btn-primary btn-sm";
            approve.textContent = "Approve";
            approve.addEventListener("click", function () {
              fetch("/api/admin/employment/approve", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ request_id: req.id }),
              })
                .then(function (r) {
                  return r.json().then(function (body) {
                    return { ok: r.ok, body: body };
                  });
                })
                .then(function (x) {
                  if (!x.ok) throw new Error((x.body && x.body.error) || "Failed");
                  loadEmploymentRequests();
                  if (window.qbToast) window.qbToast("Approved — code " + (x.body.volunteer_code || x.body.agent_code || ""), "success");
                })
                .catch(function (err) {
                  if (window.qbToast) window.qbToast(err.message || "Error", "error");
                });
            });
            var reject = document.createElement("button");
            reject.type = "button";
            reject.className = "qb-btn qb-btn-outline btn-sm";
            reject.textContent = "Reject";
            reject.addEventListener("click", function () {
              var note = window.prompt("Rejection reason (optional):") || "";
              fetch("/api/admin/employment/reject", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ request_id: req.id, review_note: note }),
              })
                .then(function (r) {
                  return r.json().then(function (body) {
                    return { ok: r.ok, body: body };
                  });
                })
                .then(function (x) {
                  if (!x.ok) throw new Error((x.body && x.body.error) || "Failed");
                  loadEmploymentRequests();
                })
                .catch(function (err) {
                  if (window.qbToast) window.qbToast(err.message || "Error", "error");
                });
            });
            actions.appendChild(approve);
            actions.appendChild(reject);
            li.appendChild(actions);
            list.appendChild(li);
          });
          if (!list.children.length) {
            list.innerHTML = "<li class='text-muted'>No pending requests.</li>";
          }
        })
        .catch(function () {});
    }
    var refreshBtn = document.getElementById("qb-admin-employment-refresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", loadEmploymentRequests);
      loadEmploymentRequests();
    }
  })();

  qbInitCopyButtons(document);
  window.qbFamilyFlash = familyFlash;
  window.qbOpenMarkDeceasedModal = openMarkDeceasedModal;
  window.qbOpenFamilyTreeAddModal = openFamilyTreeAddModal;
  window.qbOpenFamilyMemberEditModal = function (graphMemberId) {
    var id = parseInt(String(graphMemberId), 10);
    if (!id) return;
    fetch("/api/family/all_members", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (b) {
          return { ok: r.ok, b: b };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "load failed");
        var rows = x.b.members || [];
        var m = rows.find(function (row) {
          return parseInt(String(row.id), 10) === id;
        });
        if (!m) throw new Error("Member not found");
        openFamilyMemberEditModal(m);
      })
      .catch(function (err) {
        familyFlash(err.message || "Could not open editor", "error");
      });
  };

  /* ── Varna / Dharma Profile ── */
  function qbVarnaFetch(path, opts) {
    return fetch("/api/varna" + path, Object.assign({ credentials: "same-origin", headers: { Accept: "application/json" } }, opts || {}))
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); });
  }

  var varnaAppealBtn = document.getElementById("qb-varna-appeal-btn");
  var varnaAppealModal = document.getElementById("qb-varna-appeal-modal");
  if (varnaAppealBtn && varnaAppealModal && window.bootstrap) {
    var appealModal = new bootstrap.Modal(varnaAppealModal);
    varnaAppealBtn.addEventListener("click", function () { appealModal.show(); });
    var appealSubmit = document.getElementById("qb-varna-appeal-submit");
    if (appealSubmit) {
      appealSubmit.addEventListener("click", function () {
        var reason = (document.getElementById("qb-varna-appeal-reason") || {}).value || "";
        var evidence = (document.getElementById("qb-varna-appeal-evidence") || {}).value || "";
        qbVarnaFetch("/appeal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: reason, evidence: evidence }),
        }).then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Appeal failed");
          if (window.qbToast) window.qbToast(x.b.message || "Appeal submitted", "success");
          appealModal.hide();
        }).catch(function (err) {
          if (window.qbToast) window.qbToast(err.message || "Appeal failed", "error");
        });
      });
    }
  }

  var varnaHistoryBtn = document.getElementById("qb-varna-history-btn");
  if (varnaHistoryBtn && window.bootstrap) {
    var historyModalEl = document.getElementById("qb-varna-history-modal");
    var historyModal = historyModalEl ? new bootstrap.Modal(historyModalEl) : null;
    varnaHistoryBtn.addEventListener("click", function () {
      qbVarnaFetch("/profile").then(function (x) {
        if (!x.ok) return;
        var list = document.getElementById("qb-varna-history-list");
        if (!list) return;
        list.innerHTML = "";
        (x.b.history || []).forEach(function (h) {
          var li = document.createElement("li");
          li.className = "mb-2 pb-2 border-bottom border-secondary";
          li.textContent = (h.calculation_date || "") + " — " + (h.primary_category || "?") + " (" + (h.category_type || "") + ")";
          list.appendChild(li);
        });
        if (historyModal) historyModal.show();
      });
    });
  }

  var varnaRolesBtn = document.getElementById("qb-varna-roles-btn");
  if (varnaRolesBtn && window.bootstrap) {
    var rolesModalEl = document.getElementById("qb-varna-roles-modal");
    var rolesModal = rolesModalEl ? new bootstrap.Modal(rolesModalEl) : null;
    varnaRolesBtn.addEventListener("click", function () {
      qbVarnaFetch("/eligible-roles").then(function (x) {
        if (!x.ok) return;
        var list = document.getElementById("qb-varna-roles-list");
        if (!list) return;
        list.innerHTML = "";
        (x.b.eligible_roles || []).forEach(function (role) {
          var li = document.createElement("li");
          li.textContent = role;
          list.appendChild(li);
        });
        if (rolesModal) rolesModal.show();
      });
    });
  }

  var adminVarnaRecalc = document.getElementById("qb-admin-varna-recalc-btn");
  if (adminVarnaRecalc) {
    adminVarnaRecalc.addEventListener("click", function () {
      var flash = document.getElementById("qb-admin-varna-flash");
      fetch("/api/admin/recalculate-categories", { method: "POST", credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (b) {
          if (flash) flash.textContent = b.success ? "Recalculation complete." : (b.error || "Failed");
          if (window.qbToast && b.success) window.qbToast("Categories recalculated", "success");
        })
        .catch(function () { if (flash) flash.textContent = "Recalculation failed"; });
    });
  }

  function loadAdminVarnaStats() {
    if (!document.getElementById("qb-admin-varna-section")) return;
    qbVarnaFetch("/admin/stats").then(function (x) {
      if (!x.ok || !x.b) return;
      var dist = x.b.distribution || {};
      document.querySelectorAll("#qb-admin-varna-distribution [data-cat]").forEach(function (el) {
        var k = el.getAttribute("data-cat");
        el.textContent = dist[k] != null ? dist[k] : "0";
      });
      var pc = document.getElementById("qb-admin-varna-pending-count");
      if (pc) pc.textContent = String(x.b.pending_appeals || 0);
    });
  }
  loadAdminVarnaStats();

  var adminAppealsBtn = document.getElementById("qb-admin-varna-appeals-btn");
  if (adminAppealsBtn) {
    adminAppealsBtn.addEventListener("click", function () {
      var panel = document.getElementById("qb-admin-varna-appeals-panel");
      var list = document.getElementById("qb-admin-varna-appeals-list");
      qbVarnaFetch("/admin/appeals").then(function (x) {
        if (!x.ok || !list) return;
        list.innerHTML = "";
        (x.b || []).forEach(function (a) {
          var li = document.createElement("li");
          li.className = "mb-2 p-2 border border-secondary rounded";
          li.innerHTML = "<strong>" + (a.first_name || "") + " " + (a.last_name || "") + "</strong><br>" +
            (a.reason || "") +
            "<br><button type='button' class='qb-btn qb-btn-primary btn-sm mt-1 me-1' data-approve='" + a.id + "'>Approve</button>" +
            "<button type='button' class='qb-btn qb-btn-danger btn-sm mt-1' data-reject='" + a.id + "'>Reject</button>";
          list.appendChild(li);
        });
        list.querySelectorAll("[data-approve]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            fetch("/api/varna/admin/appeal/" + btn.getAttribute("data-approve"), {
              method: "POST", credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({ action: "approve" }),
            }).then(function () { loadAdminVarnaStats(); adminAppealsBtn.click(); });
          });
        });
        list.querySelectorAll("[data-reject]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            fetch("/api/varna/admin/appeal/" + btn.getAttribute("data-reject"), {
              method: "POST", credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({ action: "reject" }),
            }).then(function () { loadAdminVarnaStats(); adminAppealsBtn.click(); });
          });
        });
        if (panel) panel.hidden = false;
      });
    });
  }

  function loadUserDonationHistory() {
    var totalEl = document.getElementById("qb-user-donation-total");
    var listEl = document.getElementById("qb-user-donation-list");
    var emptyEl = document.getElementById("qb-user-donation-empty");
    if (!listEl) return;
    fetch("/api/donation/history", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        if (totalEl) totalEl.textContent = String(b.total_confirmed || 0);
        listEl.innerHTML = "";
        var rows = b.donations || [];
        if (!rows.length) {
          if (emptyEl) emptyEl.hidden = false;
          return;
        }
        if (emptyEl) emptyEl.hidden = true;
        rows.forEach(function (d) {
          var li = document.createElement("li");
          li.className = "mb-1";
          var rupees = d.amount_rupees != null ? d.amount_rupees : d.amount;
          li.textContent =
            "₹" + rupees + " — " + (d.status || "") + " — " + (d.created_at || "");
          listEl.appendChild(li);
        });
      })
      .catch(function () {});
  }
  loadUserDonationHistory();

  var editModal = document.getElementById("qb-edit-request-modal");
  var editOpen = document.getElementById("qb-edit-request-open");
  var editCancel = document.getElementById("qb-edit-request-cancel");
  var editSubmit = document.getElementById("qb-edit-request-submit");
  var editErr = document.getElementById("qb-edit-request-error");
  if (editOpen && editModal) {
    editOpen.addEventListener("click", function () {
      editModal.hidden = false;
      if (editErr) editErr.hidden = true;
    });
  }
  if (editCancel && editModal) {
    editCancel.addEventListener("click", function () {
      editModal.hidden = true;
    });
  }
  if (editSubmit) {
    editSubmit.addEventListener("click", function () {
      var field = document.getElementById("qb-edit-field");
      var val = document.getElementById("qb-edit-new-value");
      var reason = document.getElementById("qb-edit-reason");
      fetch("/api/edit/request", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          field_name: field ? field.value : "",
          new_value: val ? val.value : "",
          reason: reason ? reason.value : "",
        }),
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Request failed");
          if (editModal) editModal.hidden = true;
          if (window.qbToast) window.qbToast("Edit request submitted.", "success");
        })
        .catch(function (err) {
          if (editErr) {
            editErr.textContent = err.message || "Could not submit request";
            editErr.hidden = false;
          }
        });
    });
  }

  function loadAdminDonations() {
    var tbody = document.getElementById("qb-admin-donations-tbody");
    var totalEl = document.getElementById("qb-admin-donation-total");
    var countEl = document.getElementById("qb-admin-donation-count");
    var pendingEl = document.getElementById("qb-admin-donation-pending");
    var confirmedEl = document.getElementById("qb-admin-donation-confirmed");
    var emptyEl = document.getElementById("qb-admin-donations-empty");
    if (!tbody) return;
    fetch("/api/donation/admin/list", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        if (totalEl) totalEl.textContent = String(b.total_amount || b.total_confirmed || 0);
        if (countEl) countEl.textContent = String(b.total_donations || 0);
        if (pendingEl) pendingEl.textContent = String(b.pending_count || 0);
        if (confirmedEl) confirmedEl.textContent = String(b.confirmed_count || 0);
        tbody.innerHTML = "";
        var rows = b.donations || [];
        if (!rows.length) {
          if (emptyEl) emptyEl.hidden = false;
          return;
        }
        if (emptyEl) emptyEl.hidden = true;
        rows.forEach(function (d) {
          var tr = document.createElement("tr");
          var name = d.user_name || ((d.first_name || "") + " " + (d.last_name || "")).trim();
          var contact = "";
          if (d.email) contact += escHtml(d.email);
          if (d.phone) {
            contact += (contact ? "<br>" : "") + escHtml(d.phone);
          }
          var rupees = d.amount_rupees != null ? d.amount_rupees : d.amount;
          var payStatus = String(d.payment_status || "").toLowerCase();
          var statusBadge = String(d.status || "");
          if (payStatus === "pending_verification") {
            statusBadge = "pending verification";
          }
          var actions = "";
          var needsAction =
            d.status === "pending" || payStatus === "pending_verification";
          if (needsAction) {
            actions =
              "<button type='button' class='qb-btn qb-btn-primary btn-sm me-1' data-don-confirm='" +
              d.id + "'>Verify</button>" +
              "<button type='button' class='qb-btn qb-btn-danger btn-sm' data-don-reject='" +
              d.id + "'>Reject</button>";
          } else {
            actions = "<span class='text-muted'>—</span>";
          }
          if (d.webhook_verified) {
            statusBadge += " (webhook)";
          }
          var txnRef = d.upi_txn_reference || d.txn_reference || "—";
          tr.innerHTML =
            "<td>" + escHtml(name) + (contact ? "<br><span class='text-muted'>" + contact + "</span>" : "") + "</td>" +
            "<td class='font-monospace'>" + escHtml(txnRef) + "</td>" +
            "<td>₹" + rupees + "</td>" +
            "<td>" + escHtml(d.payment_method || "") + "</td>" +
            "<td>" + escHtml(statusBadge) + "</td>" +
            "<td>" + escHtml(d.created_at || "") + "</td>" +
            "<td>" + actions + "</td>";
          tbody.appendChild(tr);
        });
        tbody.querySelectorAll("[data-don-confirm]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            fetch("/api/admin/donation/verify/" + btn.getAttribute("data-don-confirm"), {
              method: "POST",
              credentials: "same-origin",
              headers: { Accept: "application/json" },
            }).then(function (r) {
              return r.json().then(function (b) {
                if (window.qbToast) {
                  window.qbToast(b.message || "Donation verified", "success");
                }
                loadAdminDonations();
              });
            });
          });
        });
        tbody.querySelectorAll("[data-don-reject]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var reason = prompt("Rejection reason (optional):") || "";
            fetch("/api/admin/donation/reject/" + btn.getAttribute("data-don-reject"), {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({ reason: reason }),
            }).then(function (r) {
              return r.json().then(function (b) {
                if (window.qbToast) {
                  window.qbToast(b.message || "Donation rejected", "warning");
                }
                loadAdminDonations();
              });
            });
          });
        });
      })
      .catch(function () {});
  }
  var adminDonRefresh = document.getElementById("qb-admin-donations-refresh");
  if (adminDonRefresh) adminDonRefresh.addEventListener("click", loadAdminDonations);
  if (document.getElementById("qb-admin-donations-tbody")) loadAdminDonations();

  function loadAdminEditRequests() {
    var listEl = document.getElementById("qb-admin-edit-list");
    var emptyEl = document.getElementById("qb-admin-edit-empty");
    if (!listEl) return;
    fetch("/api/edit/admin/list", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        listEl.innerHTML = "";
        var rows = b.requests || [];
        if (!rows.length) {
          if (emptyEl) emptyEl.hidden = false;
          return;
        }
        if (emptyEl) emptyEl.hidden = true;
        rows.forEach(function (req) {
          var li = document.createElement("li");
          li.className = "mb-2 p-2 border border-secondary rounded";
          var name = ((req.first_name || "") + " " + (req.last_name || "")).trim();
          li.innerHTML =
            "<strong>" + name + "</strong><br>" +
            "Field: " + (req.field_name || "") + "<br>" +
            "New: " + (req.new_value || "") + "<br>" +
            "Reason: " + (req.reason || "") +
            "<br><button type='button' class='qb-btn qb-btn-primary btn-sm mt-1 me-1' data-edit-approve='" +
            req.id + "'>Approve</button>" +
            "<button type='button' class='qb-btn qb-btn-danger btn-sm mt-1' data-edit-reject='" +
            req.id + "'>Reject</button>";
          listEl.appendChild(li);
        });
        listEl.querySelectorAll("[data-edit-approve]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            fetch("/api/edit/admin/approve", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({ request_id: btn.getAttribute("data-edit-approve") }),
            }).then(function () { loadAdminEditRequests(); });
          });
        });
        listEl.querySelectorAll("[data-edit-reject]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var reason = prompt("Rejection reason (optional):") || "";
            fetch("/api/edit/admin/reject", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({
                request_id: btn.getAttribute("data-edit-reject"),
                reason: reason,
              }),
            }).then(function () { loadAdminEditRequests(); });
          });
        });
      })
      .catch(function () {});
  }
  var adminEditRefresh = document.getElementById("qb-admin-edit-refresh");
  if (adminEditRefresh) adminEditRefresh.addEventListener("click", loadAdminEditRequests);
  if (document.getElementById("qb-admin-edit-list")) loadAdminEditRequests();

  document.dispatchEvent(new CustomEvent("qb-dash-ready"));
})();
