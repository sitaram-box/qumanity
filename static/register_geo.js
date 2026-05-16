(function () {
  "use strict";

  async function fetchJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error("request failed");
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
  }

  function setIndiaSection(prefix, show) {
    const wrap = document.getElementById(prefix + "_india_geo");
    if (!wrap) return;
    wrap.hidden = !show;
    ["state", "district", "tehsil", "village"].forEach(function (lvl) {
      const sel = document.getElementById(prefix + "_" + lvl);
      if (!sel) return;
      sel.disabled = !show;
      if (!show) {
        sel.innerHTML = "";
        const o = document.createElement("option");
        o.value = "";
        o.textContent = "—";
        sel.appendChild(o);
      }
    });
    const hid = document.getElementById(prefix + "_location_id");
    const disp = document.getElementById(prefix + "_location_id_display");
    if (!show) {
      if (hid) hid.value = "";
      if (disp) disp.value = "";
    }
  }

  async function loadCountries(continentId, countrySelect) {
    if (!continentId) {
      populateSelect(countrySelect, "— Select continent first —", []);
      return;
    }
    try {
      const rows = await fetchJson(
        "/api/countries?continent_id=" + encodeURIComponent(continentId),
      );
      populateSelect(countrySelect, "— Select country —", rows);
    } catch (e) {
      populateSelect(countrySelect, "— Error loading countries —", []);
    }
  }

  const indianReady = { birth: false, current: false };

  async function ensureIndianFor(prefix) {
    if (indianReady[prefix]) return;
    if (window.QBInitIndianChain) {
      await window.QBInitIndianChain(prefix);
      indianReady[prefix] = true;
    }
  }

  function wirePrefix(prefix) {
    const cSel = document.getElementById(prefix + "_continent_id");
    const coSel = document.getElementById(prefix + "_country_id");
    if (!cSel || !coSel) return;

    cSel.addEventListener("change", async function () {
      await loadCountries(cSel.value, coSel);
      setIndiaSection(prefix, false);
    });

    coSel.addEventListener("change", async function () {
      const isIndia = coSel.value === "IND";
      setIndiaSection(prefix, isIndia);
      if (isIndia) {
        await ensureIndianFor(prefix);
      }
    });

    if (cSel.value) {
      loadCountries(cSel.value, coSel).then(function () {
        var initC = coSel.getAttribute("data-initial-country") || "";
        if (initC) {
          coSel.value = initC;
        }
        if (coSel.value === "IND") {
          setIndiaSection(prefix, true);
          ensureIndianFor(prefix);
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("register-form")) return;
    wirePrefix("birth");
    wirePrefix("current");
  });
})();
