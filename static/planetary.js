/**
 * Dynamic planetary symbols in element boxes — tab-aware on dashboard.
 */
(function () {
  "use strict";

  var state = {
    mainTab: "private",
    locationId: null,
    locationType: null,
  };

  function renderPlanetSymbols(container, planets) {
    if (!container) return;
    container.innerHTML = "";
    if (!planets || !planets.length) {
      container.innerHTML = '<span class="qb-no-planets">—</span>';
      return;
    }
    var lang = (document.documentElement.lang || "en").toLowerCase();
    planets.forEach(function (p) {
      var span = document.createElement("span");
      span.className = "qb-planet-name planet-name" + (p.retrograde ? " is-retrograde" : "");
      var label =
        lang === "hi"
          ? p.sanskrit || p.display || p.name || "?"
          : p.name || p.display || p.sanskrit || "?";
      span.title = label + (p.retrograde ? " (R)" : "");
      span.setAttribute("aria-label", span.title);
      span.textContent = label;
      container.appendChild(span);
    });
  }

  function fillElementRow(row, grouped) {
    if (!row || !grouped) return;
    row.querySelectorAll(".qb-planet-symbols").forEach(function (el) {
      var elKey = el.getAttribute("data-element");
      renderPlanetSymbols(el, grouped[elKey] || []);
    });
  }

  function updatePlanetaryPositions() {
    var dashRow = document.getElementById("qb-element-row");
    if (!dashRow) return;

    var payload = { tab: state.mainTab };

    if (state.mainTab === "public" || state.mainTab === "global") {
      payload.location_id = state.locationId;
      payload.location_type = state.locationType;
    }

    fetch("/api/planetary/current", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok) return;
        fillElementRow(dashRow, res.data);
      })
      .catch(function () {});
  }

  function loadLocationPagePlanets(row) {
    var cfg = window.QBLocationDonate || {};
    var q =
      "?location_id=" +
      encodeURIComponent(cfg.locationId || "") +
      "&location_type=" +
      encodeURIComponent(cfg.scope || "");
    fetch("/api/planetary/current" + q, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        fillElementRow(row, data);
      })
      .catch(function () {});
  }

  function activeLocationTab(selector) {
    return (
      document.querySelector(selector + ".is-active") ||
      document.querySelector(selector + ".active")
    );
  }

  function onMainTabChange(tab) {
    state.mainTab = tab || "private";

    if (tab === "public") {
      var pub = activeLocationTab(".qb-js-public-tab");
      if (pub) {
        state.locationId = pub.getAttribute("data-location-id");
        state.locationType = pub.getAttribute("data-scope") || pub.getAttribute("data-level");
      }
    } else if (tab === "global") {
      var glob = activeLocationTab(".qb-js-global-tab");
      if (glob) {
        state.locationId = glob.getAttribute("data-global-id") || glob.getAttribute("data-location-id");
        state.locationType = glob.getAttribute("data-global-scope") || glob.getAttribute("data-level");
        if (state.locationType === "earth" && !state.locationId) {
          state.locationId = "0";
        }
      }
    } else {
      state.locationId = null;
      state.locationType = null;
    }

    elementStatsCache = {};
    updatePlanetaryPositions();
  }

  function onLocationTabChange(locationId, locationType, mainTab) {
    if (mainTab) state.mainTab = mainTab;
    state.locationId = locationId || null;
    state.locationType = locationType || null;
    elementStatsCache = {};
    updatePlanetaryPositions();
  }

  function initFromDom() {
    var activeNav = document.querySelector(".qb-dash-nav-btn.is-active");
    var tab = activeNav ? activeNav.getAttribute("data-dash-tab") : "private";
    onMainTabChange(tab);
  }

  var initDone = false;
  var elementStatsCache = {};
  var elementEmoji = { Fire: "🔥", Earth: "🌍", Air: "💨", Water: "💧" };

  function elementContextPayload() {
    return {
      tab: state.mainTab,
      location_id: state.locationId,
      location_type: state.locationType,
    };
  }

  function renderElementPopup(popup, element, data) {
    if (!popup) return;
    var emoji = elementEmoji[element] || "";
    var lang = (document.documentElement.lang || "en").toLowerCase();
    var signsHtml = "";
    var rawSigns = (data && data.signs) || [];
    var signs = [];
    if (Array.isArray(rawSigns)) {
      signs = rawSigns;
    } else if (rawSigns && typeof rawSigns === "object") {
      Object.keys(rawSigns).forEach(function (sign) {
        signs.push({
          name_en: sign,
          name_sa: sign,
          count: rawSigns[sign],
          planets: [],
        });
      });
    }
    signs.forEach(function (sign) {
      var signName = lang === "hi" ? sign.name_sa || sign.name_en : sign.name_en || sign.name_sa;
      var planetsHtml = "";
      (sign.planets || []).forEach(function (planet) {
        // Sanskrit names (Surya, Mangala, …) everywhere; English name as fallback.
        var planetName = planet.sanskrit || planet.name || "";
        planetsHtml +=
          '<span class="popup-planet qb-popup-planet" title="' +
          (planet.name || planetName) +
          '">' +
          planetName +
          "</span>";
      });
      signsHtml +=
        '<div class="popup-sign qb-element-popup-sign">' +
        '<div class="popup-sign-header qb-element-popup-sign-row">' +
        '<span class="popup-sign-name qb-element-popup-sign-name">' +
        signName +
        "</span>" +
        '<span class="popup-sign-count qb-element-popup-sign-count">' +
        Number(sign.count || 0).toLocaleString() +
        " members</span>" +
        "</div>" +
        '<div class="popup-planets qb-element-popup-planets">' +
        (planetsHtml || "—") +
        "</div>" +
        "</div>";
    });
    popup.innerHTML =
      '<button type="button" class="popup-close-btn" aria-label="Close">&times;</button>' +
      '<div class="popup-header qb-element-popup-header">' +
      '<span class="popup-element-icon">' +
      emoji +
      "</span>" +
      '<span class="popup-element-name">' +
      element.toUpperCase() +
      " ELEMENT</span>" +
      "</div>" +
      '<div class="popup-total qb-element-popup-total">Total ' +
      element +
      " Members: " +
      Number((data && data.total) || 0).toLocaleString() +
      "</div>" +
      '<div class="popup-signs-list qb-element-popup-signs">' +
      signsHtml +
      "</div>";
    // Don't re-show if the user closed the popup while data was loading.
    if (currentOpenPopup === popup) {
      popup.classList.add("show");
      popup.removeAttribute("hidden");
      popup.style.display = "block";
      popup.setAttribute("aria-hidden", "false");
    }
  }

  function loadElementStats(element, popup) {
    if (!popup) return;
    var ctx = elementContextPayload();
    var cacheKey = element + "|" + ctx.tab + "|" + (ctx.location_id || "") + "|" + (ctx.location_type || "");
    if (elementStatsCache[cacheKey]) {
      renderElementPopup(popup, element, elementStatsCache[cacheKey]);
      return;
    }
    popup.innerHTML =
      '<button type="button" class="popup-close-btn" aria-label="Close">&times;</button>' +
      '<div class="popup-loading qb-element-popup-total">Loading…</div>';
    popup.classList.add("show");
    popup.removeAttribute("hidden");
    popup.style.display = "block";

    var params = new URLSearchParams();
    params.set("active_tab", ctx.tab || "private");
    if (ctx.location_id) params.set("location_id", ctx.location_id);
    if (ctx.location_type) params.set("location_type", ctx.location_type);

    fetch("/api/element/popup/" + encodeURIComponent(element) + "?" + params.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok) throw new Error((res.data && res.data.error) || "Failed");
        elementStatsCache[cacheKey] = res.data;
        renderElementPopup(popup, element, res.data);
      })
      .catch(function () {
        popup.innerHTML =
          '<button type="button" class="popup-close-btn" aria-label="Close">&times;</button>' +
          '<div class="popup-error qb-element-popup-total">Failed to load data</div>';
      });
  }

  var currentOpenPopup = null;

  function hideElementPopup(btn, popup) {
    if (btn) btn.classList.remove("is-popup-open");
    popup.classList.remove("show");
    popup.style.display = "none";
    popup.setAttribute("hidden", "");
    popup.setAttribute("aria-hidden", "true");
    if (currentOpenPopup === popup) currentOpenPopup = null;
  }

  function closeAllElementPopups() {
    document.querySelectorAll(".qb-element-popup").forEach(function (popup) {
      var btn = popup.closest(".qb-element-btn");
      hideElementPopup(btn, popup);
    });
    currentOpenPopup = null;
  }

  function openElementPopup(btn, element, popup) {
    closeAllElementPopups();
    btn.classList.add("is-popup-open");
    popup.classList.add("show");
    popup.removeAttribute("hidden");
    popup.style.display = "block";
    popup.setAttribute("aria-hidden", "false");
    currentOpenPopup = popup;
    loadElementStats(element, popup);
  }

  function wireElementPopups() {
    var row = document.getElementById("qb-element-row");
    if (!row) return;
    row.querySelectorAll(".qb-element-btn").forEach(function (btn) {
      var element = btn.getAttribute("data-element");
      var popup = btn.querySelector(".qb-element-popup");
      if (!element || !popup) return;

      btn.addEventListener("click", function (event) {
        // Clicks inside the popup (popup is nested in the button) are not toggles.
        if (event.target.closest(".qb-element-popup")) {
          if (event.target.closest(".popup-close-btn")) {
            event.stopPropagation();
            hideElementPopup(btn, popup);
          }
          return;
        }
        event.stopPropagation();
        if (currentOpenPopup === popup) {
          hideElementPopup(btn, popup);
        } else {
          openElementPopup(btn, element, popup);
        }
      });
    });

    document.addEventListener("click", function (event) {
      if (!currentOpenPopup) return;
      if (event.target.closest(".qb-element-btn") || event.target.closest(".qb-element-popup")) {
        return;
      }
      closeAllElementPopups();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && currentOpenPopup) closeAllElementPopups();
    });
  }

  function initPlanetaryOnce() {
    if (initDone) return;
    if (!document.getElementById("qb-element-row")) return;
    initDone = true;
    initFromDom();
    wireElementPopups();
  }

  document.addEventListener("DOMContentLoaded", function () {
    initPlanetaryOnce();

    var locRow = document.getElementById("qb-location-element-row");
    if (locRow) {
      loadLocationPagePlanets(locRow);
    }

    var deceasedBtn = document.getElementById("qb-deceased-submit");
    if (deceasedBtn) {
      deceasedBtn.addEventListener("click", function () {
        var statusEl = document.getElementById("qb-deceased-status");
        var pid = (document.getElementById("qb-deceased-private-id") || {}).value || "";
        var dod = (document.getElementById("qb-deceased-date") || {}).value || "";
        var heir = (document.getElementById("qb-deceased-heir") || {}).value || "";
        var obit = (document.getElementById("qb-deceased-obituary") || {}).value || "";
        if (!pid.trim() || !dod) {
          if (statusEl) statusEl.textContent = "Private ID and date of death are required.";
          return;
        }
        deceasedBtn.disabled = true;
        if (statusEl) statusEl.textContent = "Processing…";
        fetch("/api/mentor/mark-deceased", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_private_id: pid.trim(),
            date_of_death: dod,
            heir_private_id: heir.trim() || null,
            obituary: obit.trim() || null,
          }),
        })
          .then(function (r) {
            return r.json().then(function (j) {
              return { ok: r.ok, body: j };
            });
          })
          .then(function (res) {
            if (statusEl) {
              if (res.ok && res.body.success) {
                statusEl.textContent =
                  "Marked deceased. Archived " + (res.body.archived_posts || 0) + " posts.";
                if (window.qbToast) window.qbToast(statusEl.textContent, "success");
              } else {
                statusEl.textContent = res.body.error || "Failed.";
                if (window.qbToast) window.qbToast(statusEl.textContent, "error");
              }
            }
          })
          .catch(function () {
            if (statusEl) statusEl.textContent = "Request failed.";
          })
          .finally(function () {
            deceasedBtn.disabled = false;
          });
      });
    }
  });

  document.addEventListener("qb-dash-ready", initPlanetaryOnce);

  window.qbPlanetary = {
    fillElementRow: fillElementRow,
    updatePlanetaryPositions: updatePlanetaryPositions,
    onMainTabChange: onMainTabChange,
    onLocationTabChange: onLocationTabChange,
  };
})();
