/**
 * Homepage enhanced geography search — Ctrl+K, pills, popular/recent.
 */
(function () {
  "use strict";

  var LS_RECENT = "qb_geo_recent";
  var POPULAR = ["Delhi", "Mumbai", "Bengaluru", "Odisha", "Rohini", "Kerala"];
  var currentFilter = "all";

  function qs(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
  }

  function loadRecent() {
    try {
      return JSON.parse(localStorage.getItem(LS_RECENT) || "[]");
    } catch (e) {
      return [];
    }
  }

  function saveRecent(row) {
    var list = loadRecent().filter(function (r) { return r.url !== row.url; });
    list.unshift(row);
    localStorage.setItem(LS_RECENT, JSON.stringify(list.slice(0, 5)));
  }

  function renderPopular() {
    var ul = qs("geo-popular");
    if (!ul) return;
    ul.innerHTML = POPULAR.map(function (name) {
      return '<li><button type="button" class="qb-search-pill" data-popular="' + escapeHtml(name) + '">' + escapeHtml(name) + "</button></li>";
    }).join("");
    ul.querySelectorAll("[data-popular]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var inp = qs("geo-q");
        if (inp) { inp.value = btn.getAttribute("data-popular"); inp.dispatchEvent(new Event("input")); }
      });
    });
  }

  function renderRecent() {
    var ul = qs("geo-recent");
    if (!ul) return;
    var items = loadRecent();
    if (!items.length) {
      ul.innerHTML = '<li class="small text-muted px-2">No recent places yet.</li>';
      return;
    }
    ul.innerHTML = items.map(function (r) {
      return '<li><a href="' + escapeHtml(r.url) + '" class="d-block px-2 py-1">' + escapeHtml(r.name) + "</a></li>";
    }).join("");
  }

  function showPreview(row) {
    var preview = qs("geo-preview");
    var nameEl = qs("geo-preview-name");
    var kindEl = qs("geo-preview-kind");
    var cta = qs("geo-preview-cta");
    if (!preview || !row) return;
    if (nameEl) nameEl.textContent = row.name;
    if (kindEl) kindEl.textContent = row.kind;
    if (cta) cta.href = row.url;
    preview.hidden = false;
    saveRecent(row);
    renderRecent();
  }

  function doSearch(q) {
    var ul = qs("geo-results");
    var dropdown = qs("geo-dropdown");
    var preview = qs("geo-preview");
    if (!ul) return;
    ul.innerHTML = "";
    if (preview) preview.hidden = true;
    if (q.length < 2) {
      if (dropdown) dropdown.hidden = false;
      return;
    }
    if (dropdown) dropdown.hidden = true;
    var url = "/api/geo-search?q=" + encodeURIComponent(q);
    if (currentFilter !== "all") url += "&kind=" + encodeURIComponent(currentFilter);
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (rows) {
        ul.innerHTML = "";
        if (!rows.length) {
          ul.innerHTML = '<li class="qb-story-search__empty">No matches — try another spelling.</li>';
          return;
        }
        rows.forEach(function (row) {
          var li = document.createElement("li");
          li.className = "qb-story-search__hit";
          li.innerHTML =
            '<a href="' + escapeHtml(row.url) + '" data-preview="1">' +
            escapeHtml(row.name) + ' <span class="qb-story-search__kind">(' + escapeHtml(row.kind) + ")</span></a>";
          li.querySelector("a").addEventListener("click", function (e) {
            e.preventDefault();
            showPreview(row);
          });
          ul.appendChild(li);
        });
        if (rows[0]) showPreview(rows[0]);
      })
      .catch(function () {
        ul.innerHTML = '<li class="qb-story-search__empty qb-story-search__empty--error">Search failed — try again.</li>';
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var inp = qs("geo-q");
    var clearBtn = qs("geo-q-clear");
    var dropdown = qs("geo-dropdown");
    if (!inp) return;

    renderPopular();
    renderRecent();

    var t = null;
    inp.addEventListener("input", function () {
      if (clearBtn) clearBtn.classList.toggle("is-visible", inp.value.length > 0);
      clearTimeout(t);
      var q = inp.value.trim();
      t = setTimeout(function () { doSearch(q); }, 220);
    });

    inp.addEventListener("focus", function () {
      if (inp.value.trim().length < 2 && dropdown) dropdown.hidden = false;
    });

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        inp.value = "";
        clearBtn.classList.remove("is-visible");
        doSearch("");
        inp.focus();
      });
    }

    document.querySelectorAll(".qb-search-pill[data-filter]").forEach(function (pill) {
      pill.addEventListener("click", function () {
        document.querySelectorAll(".qb-search-pill[data-filter]").forEach(function (p) {
          p.classList.remove("is-active");
        });
        pill.classList.add("is-active");
        currentFilter = pill.getAttribute("data-filter") || "all";
        doSearch(inp.value.trim());
      });
    });

    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inp.focus();
      }
    });
  });
})();
