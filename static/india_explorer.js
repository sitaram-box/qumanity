/**
 * India Explorer — council-only geography browser.
 *
 * Reuses the existing dashboard geography API:
 *   - GET /api/locations/children?parent_id=<id>   -> [{ id, name }, ...]
 *
 * Tree levels: India (root) -> State -> District -> Tehsil -> Village.
 * Click a location name to open its geography overview page. Expand/collapse with the
 * chevron. The breadcrumb reflects the deepest branch you expand or select.
 */
(function () {
  "use strict";

  var ROOT_ID = "IND";
  var els = {};

  function qs(id) {
    return document.getElementById(id);
  }

  function nextKind(kind) {
    return kind === "root"
      ? "state"
      : kind === "state"
        ? "district"
        : kind === "district"
          ? "tehsil"
          : "village";
  }

  function isExpandable(kind) {
    return kind !== "village";
  }

  function fetchChildren(parentId) {
    return fetch(
      "/api/locations/children?parent_id=" + encodeURIComponent(parentId),
      { credentials: "same-origin", headers: { Accept: "application/json" } }
    ).then(function (r) {
      if (!r.ok) throw new Error("children");
      return r.json();
    });
  }

  function locationPageUrl(kind, geoId) {
    if (kind === "root" || geoId === ROOT_ID) {
      return "/location/country/IND";
    }
    return "/location/" + kind + "/" + encodeURIComponent(geoId);
  }

  /* --- Breadcrumb --- */
  function renderBreadcrumb(path) {
    if (!els.breadcrumb) return;
    els.breadcrumb.innerHTML = "";
    var full = [{ id: ROOT_ID, name: "India", kind: "root" }].concat(path || []);
    full.forEach(function (node, i) {
      if (i > 0) {
        var sep = document.createElement("span");
        sep.className = "qb-ie-crumb-sep";
        sep.textContent = "›";
        els.breadcrumb.appendChild(sep);
      }
      var crumb = document.createElement("button");
      crumb.type = "button";
      crumb.className = "qb-ie-crumb";
      if (i === 0) crumb.classList.add("is-root");
      crumb.textContent = node.name;
      crumb.setAttribute("data-geo-id", node.id);
      crumb.addEventListener("click", function () {
        window.location.href = locationPageUrl(node.kind || "root", node.id);
      });
      els.breadcrumb.appendChild(crumb);
    });
  }

  /* --- Tree nodes --- */
  function buildNode(item, kind, parentPath) {
    var path = parentPath.concat([{ id: item.id, name: item.name, kind: kind }]);

    var node = document.createElement("div");
    node.className = "qb-ie-node";
    node.setAttribute("data-name", String(item.name || "").toLowerCase());

    var row = document.createElement("div");
    row.className = "qb-ie-row";

    var chev = document.createElement("button");
    chev.type = "button";
    chev.className = "qb-ie-chev";
    if (!isExpandable(kind)) chev.classList.add("is-leaf");
    chev.setAttribute("aria-label", "Expand");
    chev.textContent = isExpandable(kind) ? "▸" : "•";

    var label = document.createElement("button");
    label.type = "button";
    label.className = "qb-ie-label qb-ie-kind-" + kind;
    label.textContent = item.name;
    label.setAttribute("data-geo-id", item.id);

    var kids = document.createElement("div");
    kids.className = "qb-ie-children";
    kids.hidden = true;

    row.appendChild(chev);
    row.appendChild(label);
    node.appendChild(row);
    node.appendChild(kids);

    function toggle() {
      if (!isExpandable(kind)) return;
      if (kids.getAttribute("data-loaded") === "1") {
        kids.hidden = !kids.hidden;
        chev.textContent = kids.hidden ? "▸" : "▾";
        return;
      }
      chev.textContent = "…";
      fetchChildren(item.id)
        .then(function (rows) {
          kids.innerHTML = "";
          var nk = nextKind(kind);
          (rows || []).forEach(function (r) {
            kids.appendChild(buildNode(r, nk, path));
          });
          kids.setAttribute("data-loaded", "1");
          kids.hidden = false;
          chev.textContent = "▾";
        })
        .catch(function () {
          chev.textContent = "▸";
        });
    }

    chev.addEventListener("click", function (e) {
      e.stopPropagation();
      renderBreadcrumb(path);
      toggle();
    });

    label.addEventListener("click", function (e) {
      e.preventDefault();
      clearSelection();
      label.classList.add("is-selected");
      renderBreadcrumb(path);
      window.location.href = locationPageUrl(kind, item.id);
    });

    return node;
  }

  var selectedLabel = null;
  function clearSelection() {
    if (selectedLabel) selectedLabel.classList.remove("is-selected");
    selectedLabel = null;
  }

  /* --- Search (filters already-loaded nodes) --- */
  function applySearch(query) {
    var q = String(query || "").trim().toLowerCase();
    var nodes = els.tree.querySelectorAll(".qb-ie-node");
    if (!q) {
      nodes.forEach(function (n) {
        n.hidden = false;
      });
      if (els.empty) els.empty.hidden = true;
      return;
    }
    nodes.forEach(function (n) {
      n.hidden = true;
    });
    var anyMatch = false;
    nodes.forEach(function (n) {
      var name = n.getAttribute("data-name") || "";
      if (name.indexOf(q) === -1) return;
      anyMatch = true;
      var cur = n;
      while (cur && cur.classList && cur.classList.contains("qb-ie-node")) {
        cur.hidden = false;
        var kids = cur.querySelector(":scope > .qb-ie-children");
        if (kids && kids !== n && kids.contains(n)) kids.hidden = false;
        var parentKids = cur.parentElement;
        if (parentKids && parentKids.classList.contains("qb-ie-children")) {
          parentKids.hidden = false;
        }
        cur =
          parentKids &&
          parentKids.closest &&
          parentKids.closest(".qb-ie-node");
      }
    });
    if (els.empty) els.empty.hidden = anyMatch;
  }

  /* --- Init --- */
  function init() {
    els.tree = qs("qb-ie-tree");
    els.breadcrumb = qs("qb-ie-breadcrumb");
    els.search = qs("qb-ie-search");
    els.empty = qs("qb-ie-empty");
    if (!els.tree) return;

    renderBreadcrumb([]);

    fetchChildren(ROOT_ID)
      .then(function (rows) {
        els.tree.innerHTML = "";
        (rows || []).forEach(function (r) {
          els.tree.appendChild(buildNode(r, "state", []));
        });
      })
      .catch(function () {
        els.tree.innerHTML =
          '<p class="qb-ie-error small">Could not load locations.</p>';
      });

    if (els.search) {
      var t = null;
      els.search.addEventListener("input", function () {
        if (t) clearTimeout(t);
        t = setTimeout(function () {
          applySearch(els.search.value);
        }, 150);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
