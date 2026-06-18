/**
 * Registration geography — single combined input + <datalist> per level.
 *
 * Each level (state → district → tehsil → village) is a text input wired to a
 * <datalist>: the user can click to see the full list OR type to filter it.
 * The visible inputs hold the localized NAME; the matching location ID is
 * resolved from the name and written to the hidden id fields that are actually
 * submitted with the form.
 */
(function () {
  "use strict";

  var LEVELS = ["state", "district", "tehsil", "village"];

  // hidden id field per level (village uses *_location_id)
  function hiddenIdFor(prefix, level) {
    if (level === "village") return prefix + "_location_id";
    return prefix + "_" + level + "_id";
  }

  // name(lowercased) -> id  and  id -> name, kept per prefix+level
  var geoMaps = {
    birth: { state: {}, district: {}, tehsil: {}, village: {} },
    current: { state: {}, district: {}, tehsil: {}, village: {} },
  };
  var revMaps = {
    birth: { state: {}, district: {}, tehsil: {}, village: {} },
    current: { state: {}, district: {}, tehsil: {}, village: {} },
  };
  // last resolved id per level so cascades don't re-fire needlessly
  var lastIds = {
    birth: { state: "", district: "", tehsil: "", village: "" },
    current: { state: "", district: "", tehsil: "", village: "" },
  };

  function notifyLocationComplete(prefix) {
    if (window.QBLocationSelectionComplete) {
      window.QBLocationSelectionComplete(prefix);
    }
  }

  async function fetchJson(url) {
    var lang = window.QBGeoLang || "";
    var sep = url.indexOf("?") >= 0 ? "&" : "?";
    var fullUrl = lang ? url + sep + "lang=" + encodeURIComponent(lang) : url;
    var res = await fetch(fullUrl, { credentials: "same-origin" });
    if (!res.ok) throw new Error("request failed");
    return res.json();
  }

  function populateDatalist(prefix, level, rows) {
    var listEl = document.getElementById(prefix + "_" + level + "_list");
    var input = document.getElementById(prefix + "_" + level);
    geoMaps[prefix][level] = {};
    revMaps[prefix][level] = {};
    if (listEl) listEl.innerHTML = "";
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var name = String(r.name == null ? "" : r.name);
      var id = String(r.id == null ? "" : r.id);
      if (!name || !id) continue;
      geoMaps[prefix][level][name.trim().toLowerCase()] = id;
      revMaps[prefix][level][id] = name;
      if (listEl) {
        var opt = document.createElement("option");
        opt.value = name;
        listEl.appendChild(opt);
      }
    }
    if (input) input.disabled = rows.length === 0;
  }

  function resolveId(prefix, level, value) {
    var key = String(value || "").trim().toLowerCase();
    if (!key) return "";
    return geoMaps[prefix][level][key] || "";
  }

  function setHidden(prefix, level, id) {
    var hid = document.getElementById(hiddenIdFor(prefix, level));
    if (hid) hid.value = id || "";
  }

  function clearLevel(prefix, level) {
    var input = document.getElementById(prefix + "_" + level);
    var listEl = document.getElementById(prefix + "_" + level + "_list");
    if (input) {
      input.value = "";
      input.disabled = true;
    }
    if (listEl) listEl.innerHTML = "";
    geoMaps[prefix][level] = {};
    revMaps[prefix][level] = {};
    lastIds[prefix][level] = "";
    setHidden(prefix, level, "");
  }

  function clearFrom(prefix, level) {
    var start = LEVELS.indexOf(level);
    if (start < 0) start = 0;
    for (var i = start; i < LEVELS.length; i++) {
      clearLevel(prefix, LEVELS[i]);
    }
    syncVillageDisplay(prefix);
  }

  function syncVillageDisplay(prefix) {
    var disp = document.getElementById(prefix + "_location_id_display");
    var hid = document.getElementById(prefix + "_location_id");
    if (disp) disp.value = (hid && hid.value) || "";
  }

  async function loadLevel(prefix, level, parentId) {
    var endpoints = {
      state: "/api/states",
      district: "/api/districts?state_id=" + encodeURIComponent(parentId || ""),
      tehsil: "/api/tehsils?district_id=" + encodeURIComponent(parentId || ""),
      village: "/api/villages?tehsil_id=" + encodeURIComponent(parentId || ""),
    };
    var rows;
    try {
      rows = await fetchJson(endpoints[level]);
    } catch (e) {
      rows = [];
    }
    populateDatalist(prefix, level, rows);
    return rows;
  }

  async function onLevelInput(prefix, level) {
    var input = document.getElementById(prefix + "_" + level);
    if (!input) return;
    var id = resolveId(prefix, level, input.value);

    if (level === "village") {
      setHidden(prefix, "village", id);
      lastIds[prefix].village = id;
      syncVillageDisplay(prefix);
      if (id) notifyLocationComplete(prefix);
      return;
    }

    // not a complete match yet → clear this id and everything below
    if (!id) {
      setHidden(prefix, level, "");
      lastIds[prefix][level] = "";
      clearFrom(prefix, LEVELS[LEVELS.indexOf(level) + 1]);
      return;
    }

    if (id === lastIds[prefix][level]) return; // already loaded children
    lastIds[prefix][level] = id;
    setHidden(prefix, level, id);
    clearFrom(prefix, LEVELS[LEVELS.indexOf(level) + 1]);
    await loadLevel(prefix, LEVELS[LEVELS.indexOf(level) + 1], id);
  }

  function wireLevelInputs(prefix) {
    LEVELS.forEach(function (level) {
      var input = document.getElementById(prefix + "_" + level);
      if (!input || input.getAttribute("data-qb-geo-bound") === "1") return;
      input.setAttribute("data-qb-geo-bound", "1");
      input.addEventListener("input", function () {
        onLevelInput(prefix, level);
      });
      input.addEventListener("change", function () {
        onLevelInput(prefix, level);
      });
    });
  }

  function populateSelect(selectEl, placeholder, rows) {
    selectEl.innerHTML = "";
    var opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = placeholder;
    selectEl.appendChild(opt0);
    for (var i = 0; i < rows.length; i++) {
      var o = document.createElement("option");
      o.value = rows[i].id;
      o.textContent = rows[i].name;
      selectEl.appendChild(o);
    }
    selectEl.disabled = rows.length === 0;
  }

  function setIndiaSection(prefix, show) {
    var wrap = document.getElementById(prefix + "_india_geo");
    if (wrap) wrap.hidden = !show;
    var globalWrap = document.getElementById(prefix + "_global_state_group");
    if (globalWrap) globalWrap.hidden = show;
    if (show) {
      // Leaving global-state mode — drop any non-India province list.
      clearGlobalState(prefix, "— Select country first —");
    } else {
      indianReady[prefix] = false;
      clearFrom(prefix, "state");
    }
  }

  // Searchable global state (input + datalist + hidden id field) per prefix.
  var globalStateMaps = { birth: {}, current: {} }; // name(lower) -> id
  var globalStateRev = { birth: {}, current: {} }; // id -> name

  function globalStateEls(prefix) {
    return {
      search: document.getElementById(prefix + "_global_state_search"),
      list: document.getElementById(prefix + "_global_state_list"),
      hidden: document.getElementById(prefix + "_global_state_id"),
      group: document.getElementById(prefix + "_global_state_group"),
    };
  }

  function clearGlobalState(prefix, placeholder) {
    var els = globalStateEls(prefix);
    globalStateMaps[prefix] = {};
    globalStateRev[prefix] = {};
    if (els.list) els.list.innerHTML = "";
    if (els.search) {
      els.search.value = "";
      els.search.placeholder = placeholder || "Type or select state…";
      els.search.disabled = true;
      els.search.removeAttribute("required");
    }
    if (els.hidden) els.hidden.value = "";
    if (els.group) els.group.hidden = true;
  }

  function resolveGlobalState(prefix) {
    var els = globalStateEls(prefix);
    if (!els.search || !els.hidden) return;
    var key = String(els.search.value || "").trim().toLowerCase();
    els.hidden.value = (key && globalStateMaps[prefix][key]) || "";
  }

  function elsHasGlobalState(prefix) {
    var els = globalStateEls(prefix);
    return Boolean(els.hidden && String(els.hidden.value || "").trim());
  }

  function maybeCompleteAfterGlobalState(prefix) {
    if (elsHasGlobalState(prefix)) notifyLocationComplete(prefix);
  }

  function wireGlobalStateInput(prefix) {
    var els = globalStateEls(prefix);
    if (!els.search || els.search.getAttribute("data-qb-geo-bound") === "1") return;
    els.search.setAttribute("data-qb-geo-bound", "1");
    els.search.addEventListener("input", function () {
      resolveGlobalState(prefix);
    });
    els.search.addEventListener("change", function () {
      resolveGlobalState(prefix);
      maybeCompleteAfterGlobalState(prefix);
    });
  }

  async function loadGlobalStates(prefix, countryIso) {
    var els = globalStateEls(prefix);
    if (!els.search || !els.hidden) return { has_states: false };
    wireGlobalStateInput(prefix);

    // Preserve a server-restored id (form error re-render) before clearing.
    var savedId =
      String(els.hidden.value || "").trim() ||
      String(
        ((window.QBRegisterGeoRestore || {})[prefix] || {}).global_state_id || ""
      ).trim();

    if (!countryIso || countryIso === "IND") {
      clearGlobalState(prefix, "— Select country first —");
      return { has_states: false };
    }
    try {
      var res = await fetchJson("/api/country/" + encodeURIComponent(countryIso) + "/states");
      if (res.has_states) {
        var rows = res.states || [];
        globalStateMaps[prefix] = {};
        globalStateRev[prefix] = {};
        if (els.list) els.list.innerHTML = "";
        for (var i = 0; i < rows.length; i++) {
          var name = String(rows[i].name == null ? "" : rows[i].name);
          var id = String(rows[i].id == null ? "" : rows[i].id);
          if (!name || !id) continue;
          globalStateMaps[prefix][name.trim().toLowerCase()] = id;
          globalStateRev[prefix][id] = name;
          if (els.list) {
            var opt = document.createElement("option");
            opt.value = name;
            els.list.appendChild(opt);
          }
        }
        if (els.group) els.group.hidden = false;
        els.search.disabled = false;
        els.search.placeholder = "Type to search state / province…";
        els.search.setAttribute("required", "required");
        // Restore previously selected state (e.g. after a form error).
        if (savedId && globalStateRev[prefix][savedId]) {
          els.search.value = globalStateRev[prefix][savedId];
          els.hidden.value = savedId;
          notifyLocationComplete(prefix);
        }
      } else {
        clearGlobalState(prefix, "— Not required for this country —");
      }
      return res;
    } catch (e) {
      clearGlobalState(prefix, "— Error loading states —");
      return { has_states: false };
    }
  }

  async function loadCountries(continentId, countrySelect) {
    if (!continentId) {
      populateSelect(countrySelect, "— Select continent first —", []);
      return;
    }
    try {
      var rows = await fetchJson(
        "/api/countries?continent_id=" + encodeURIComponent(continentId)
      );
      rows.sort(function (a, b) {
        if (a.id === "IND") return -1;
        if (b.id === "IND") return 1;
        return String(a.name).localeCompare(String(b.name));
      });
      populateSelect(countrySelect, "— Select country —", rows);
    } catch (e) {
      populateSelect(countrySelect, "— Error loading countries —", []);
    }
  }

  var indianReady = { birth: false, current: false };

  window.QBResetIndianChain = function (prefix) {
    indianReady[prefix] = false;
    clearFrom(prefix, "state");
  };

  async function restoreChain(prefix, chain) {
    if (!chain || !chain.state_id) return;

    await loadLevel(prefix, "state", "");
    var stateName = revMaps[prefix].state[chain.state_id];
    if (!stateName) return;
    var stateInput = document.getElementById(prefix + "_state");
    if (stateInput) stateInput.value = stateName;
    setHidden(prefix, "state", chain.state_id);
    lastIds[prefix].state = chain.state_id;

    if (!chain.district_id) return;
    await loadLevel(prefix, "district", chain.state_id);
    var distName = revMaps[prefix].district[chain.district_id];
    if (!distName) return;
    var distInput = document.getElementById(prefix + "_district");
    if (distInput) distInput.value = distName;
    setHidden(prefix, "district", chain.district_id);
    lastIds[prefix].district = chain.district_id;

    if (!chain.tehsil_id) return;
    await loadLevel(prefix, "tehsil", chain.district_id);
    var tehName = revMaps[prefix].tehsil[chain.tehsil_id];
    if (!tehName) return;
    var tehInput = document.getElementById(prefix + "_tehsil");
    if (tehInput) tehInput.value = tehName;
    setHidden(prefix, "tehsil", chain.tehsil_id);
    lastIds[prefix].tehsil = chain.tehsil_id;

    if (!chain.village_id) return;
    await loadLevel(prefix, "village", chain.tehsil_id);
    var vilName = revMaps[prefix].village[chain.village_id];
    var vilInput = document.getElementById(prefix + "_village");
    if (vilInput) vilInput.value = vilName || "";
    setHidden(prefix, "village", chain.village_id);
    lastIds[prefix].village = chain.village_id;
    syncVillageDisplay(prefix);
    notifyLocationComplete(prefix);
  }

  async function ensureIndianFor(prefix) {
    wireLevelInputs(prefix);
    // Always reload the full Indian state list from /api/states so birth and
    // current each get the correct 37 states — never reuse a stale/partial list
    // (e.g. after switching continent/country or after the other prefix loaded).
    await loadLevel(prefix, "state", "");
    indianReady[prefix] = true;
    var restore = window.QBRegisterGeoRestore || {};
    var chain = restore[prefix];
    if (chain && chain.state_id && !lastIds[prefix].state) {
      await restoreChain(prefix, chain);
    }
  }

  window.QBEnsureIndianFor = ensureIndianFor;

  /** Refresh geo dropdowns when a wizard step becomes visible. */
  window.QBRefreshRegisterGeoForStep = async function (stepNum) {
    var map = { 2: "birth", 3: "current" };
    var prefix = map[stepNum];
    if (!prefix) return;
    var coSel = document.getElementById(prefix + "_country_id");
    if (!coSel || coSel.value !== "IND") return;
    setIndiaSection(prefix, true);
    await ensureIndianFor(prefix);
  };

  function wirePrefix(prefix) {
    var cSel = document.getElementById(prefix + "_continent_id");
    var coSel = document.getElementById(prefix + "_country_id");
    if (!cSel || !coSel) return;

    cSel.addEventListener("change", async function () {
      indianReady[prefix] = false;
      await loadCountries(cSel.value, coSel);
      setIndiaSection(prefix, false);
      await loadGlobalStates(prefix, "");
    });

    coSel.addEventListener("change", async function () {
      var isIndia = coSel.value === "IND";
      setIndiaSection(prefix, isIndia);
      if (isIndia) {
        await ensureIndianFor(prefix);
      } else {
        var res = await loadGlobalStates(prefix, coSel.value);
        if (coSel.value && res && !res.has_states) {
          notifyLocationComplete(prefix);
        }
      }
      if (prefix === "birth" && window.QBLoadMotherTongueForCountry) {
        window.QBLoadMotherTongueForCountry(coSel.value);
      }
    });

    if (cSel.value) {
      loadCountries(cSel.value, coSel).then(function () {
        var initC = coSel.getAttribute("data-initial-country") || "IND";
        if (initC) coSel.value = initC;
        if (coSel.value === "IND") {
          setIndiaSection(prefix, true);
          ensureIndianFor(prefix);
        } else if (coSel.value) {
          setIndiaSection(prefix, false);
          loadGlobalStates(prefix, coSel.value).then(function (res) {
            if (res && (elsHasGlobalState(prefix) || !res.has_states)) {
              notifyLocationComplete(prefix);
            }
            if (prefix === "birth" && window.QBLoadMotherTongueForCountry) {
              window.QBLoadMotherTongueForCountry(coSel.value);
            }
          });
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("register-form")) return;
    window.QBGeoLang = "en";
    ["birth", "current"].forEach(function (prefix) {
      var cSel = document.getElementById(prefix + "_continent_id");
      if (cSel && !cSel.value) cSel.value = "AS";
    });
    wirePrefix("birth");
    wirePrefix("current");
  });
})();
