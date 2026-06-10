/**
 * Chained geography dropdowns — shows names; keeps deepest village ID in hidden input.
 */

(function () {
  "use strict";

  async function fetchJson(url) {
    const lang = window.QBGeoLang || "";
    const sep = url.indexOf("?") >= 0 ? "&" : "?";
    const fullUrl = lang ? url + sep + "lang=" + encodeURIComponent(lang) : url;
    const res = await fetch(fullUrl, { credentials: "same-origin" });
    if (!res.ok) {
      throw new Error("Request failed");
    }
    return res.json();
  }

  function populateSelect(selectEl, placeholder, rows) {
    selectEl.innerHTML = "";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = placeholder;
    selectEl.appendChild(opt0);
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      const o = document.createElement("option");
      o.value = r.id;
      o.textContent = r.name;
      selectEl.appendChild(o);
    }
    selectEl.disabled = rows.length === 0;
    selectEl.dispatchEvent(new CustomEvent("qb-options-updated"));
  }

  function clearChain(prefix, fromLevel) {
    const levels = ["district", "tehsil", "village"];
    const start = fromLevel === "state" ? 0 : levels.indexOf(fromLevel) + 1;
    for (let i = start; i < levels.length; i++) {
      const sel = document.getElementById(prefix + "_" + levels[i]);
      if (sel) populateSelect(sel, "— Select " + levels[i] + " —", []);
    }
    const hidden = document.getElementById(prefix + "_location_id");
    if (hidden) hidden.value = "";
  }

  async function syncHidden(prefix) {
    const vSel = document.getElementById(prefix + "_village");
    const hidden = document.getElementById(prefix + "_location_id");
    if (!vSel || !hidden) return;
    hidden.value = vSel.value || "";
  }

  function setup(prefix) {
    const stateSel = document.getElementById(prefix + "_state");
    const distSel = document.getElementById(prefix + "_district");
    const tehSel = document.getElementById(prefix + "_tehsil");
    const vilSel = document.getElementById(prefix + "_village");
    if (!stateSel || !distSel || !tehSel || !vilSel) return;

    stateSel.addEventListener("change", async function () {
      clearChain(prefix, "state");
      const sid = stateSel.value;
      if (!sid) return;
      try {
        const rows = await fetchJson(
          "/api/districts?state_id=" + encodeURIComponent(sid),
        );
        populateSelect(distSel, "— Select district —", rows);
      } catch (e) {
        populateSelect(distSel, "— Error loading —", []);
      }
    });

    distSel.addEventListener("change", async function () {
      clearChain(prefix, "district");
      const did = distSel.value;
      if (!did) return;
      try {
        const rows = await fetchJson(
          "/api/tehsils?district_id=" + encodeURIComponent(did),
        );
        populateSelect(tehSel, "— Select tehsil —", rows);
      } catch (e) {
        populateSelect(tehSel, "— Error loading —", []);
      }
    });

    tehSel.addEventListener("change", async function () {
      clearChain(prefix, "tehsil");
      const tid = tehSel.value;
      if (!tid) return;
      try {
        const rows = await fetchJson(
          "/api/villages?tehsil_id=" + encodeURIComponent(tid),
        );
        populateSelect(vilSel, "— Select village —", rows);
      } catch (e) {
        populateSelect(vilSel, "— Error loading —", []);
      }
    });

    vilSel.addEventListener("change", function () {
      syncHidden(prefix);
    });

    populateSelect(distSel, "— Select district —", []);
    populateSelect(tehSel, "— Select tehsil —", []);
    populateSelect(vilSel, "— Select village —", []);
  }

  async function loadStatesFor(prefix) {
    const stateSel = document.getElementById(prefix + "_state");
    if (!stateSel) return;
    try {
      const rows = await fetchJson("/api/states");
      populateSelect(stateSel, "— Select state —", rows);
    } catch (e) {
      populateSelect(stateSel, "— Error loading states —", []);
    }
  }

  async function initIndianChain(prefix) {
    await loadStatesFor(prefix);
    setup(prefix);
  }

  async function initIndianChains() {
    await initIndianChain("birth");
    await initIndianChain("current");
  }

  window.QBInitIndianChain = initIndianChain;
  window.QBInitIndianRegisterChains = initIndianChains;

  document.addEventListener("DOMContentLoaded", async function () {
    if (document.getElementById("recovery-app")) {
      await initIndianChain("recovery");
      return;
    }
    const form = document.getElementById("register-form");
    if (!form) return;
    if (form.classList.contains("qb-register-defer-india")) return;
    await initIndianChains();
  });
})();
