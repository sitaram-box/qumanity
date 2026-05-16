/**
 * D3-based family graph — Personal Account → Family tab.
 * GET /api/family/tree → { members, relationships, viewer, sentences, … }
 */
(function () {
  var VIEWER_ID = -1;
  var W = 960;
  var H = 560;
  var state = {
    members: [],
    relationships: [],
    sentences: {},
    byId: {},
    viewer: null,
  };

  function el(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function genderIcon(g) {
    var x = (g || "").toLowerCase();
    if (x === "male") return "♂";
    if (x === "female") return "♀";
    return "";
  }

  function memberById(id) {
    return state.byId[id] || null;
  }

  function buildIndex() {
    state.byId = {};
    (state.members || []).forEach(function (m) {
      state.byId[m.id] = m;
    });
    if (state.viewer && state.viewer.id != null) {
      VIEWER_ID = parseInt(String(state.viewer.id), 10);
    }
  }

  function layersFromGraph() {
    var vid = VIEWER_ID;
    var rels = state.relationships || [];
    var parents = [];
    var children = [];
    var spouses = [];
    var siblings = [];
    var gp = [];
    rels.forEach(function (r) {
      var s = r.source;
      var t = r.target;
      var typ = (r.type || r.relation_type || "").toLowerCase();
      if (typ === "parent" && s === vid && t !== vid) {
        parents.push(t);
      } else if (typ === "child" && s === vid && t !== vid) {
        children.push(t);
      } else if (typ === "spouse" && (s === vid || t === vid)) {
        spouses.push(s === vid ? t : s);
      } else if (typ === "sibling" && (s === vid || t === vid)) {
        siblings.push(s === vid ? t : s);
      }
    });
    parents = parents.filter(function (x, i, a) {
      return a.indexOf(x) === i;
    });
    children = children.filter(function (x, i, a) {
      return a.indexOf(x) === i;
    });
    spouses = spouses.filter(function (x, i, a) {
      return a.indexOf(x) === i;
    });
    siblings = siblings.filter(function (x, i, a) {
      return a.indexOf(x) === i;
    });
    parents.forEach(function (pid) {
      rels.forEach(function (r) {
        var typ = (r.type || r.relation_type || "").toLowerCase();
        if (
          typ === "parent" &&
          r.source === pid &&
          r.target !== vid &&
          parents.indexOf(r.target) < 0 &&
          gp.indexOf(r.target) < 0
        ) {
          gp.push(r.target);
        }
      });
    });
    return {
      gp: gp,
      parents: parents,
      center: [vid].concat(spouses),
      siblings: siblings,
      children: children,
    };
  }

  function layoutPositions() {
    var L = layersFromGraph();
    var pos = {};
    var wrap = el("family-tree-container") || el("qb-family-graph");
    var cw = wrap && wrap.clientWidth ? Math.max(320, wrap.clientWidth) : W;
    var cx = cw / 2;
    var y0 = 56;
    var y1 = 200;
    var y2 = 340;
    var y3 = 480;
    function spreadRow(ids, y) {
      var list = ids.slice();
      var n = Math.max(list.length, 1);
      var step = Math.min(168, (cw - 48) / n);
      var start = cx - ((n - 1) * step) / 2;
      list.forEach(function (id, i) {
        pos[id] = { x: start + i * step, y: y };
      });
    }
    spreadRow(L.gp, y0);
    spreadRow(L.parents, y0 + 52);
    spreadRow(L.center, y1);
    if (L.siblings.length) {
      spreadRow(L.siblings, y1 + 58);
    }
    spreadRow(L.children, y2);
    (state.members || []).forEach(function (m) {
      if (pos[m.id] == null) {
        pos[m.id] = { x: cx, y: y3 };
      }
    });
    return { pos: pos, width: cw };
  }

  function hidePopover() {
    var p = el("qb-family-tree-popover");
    if (p) p.remove();
  }

  function showPopover(svg, screenX, screenY, html) {
    hidePopover();
    var host = el("family-tree-container") || document.body;
    var d = document.createElement("div");
    d.id = "qb-family-tree-popover";
    d.className = "qb-family-tree-popover";
    d.innerHTML = html;
    host.appendChild(d);
    var rect = host.getBoundingClientRect();
    d.style.left = Math.max(8, screenX - rect.left + host.scrollLeft) + "px";
    d.style.top = Math.max(8, screenY - rect.top + host.scrollTop) + "px";
    setTimeout(function () {
      document.addEventListener(
        "click",
        function one(ev) {
          if (!ev.target.closest("#qb-family-tree-popover")) hidePopover();
          document.removeEventListener("click", one);
        },
        { capture: true }
      );
    }, 0);
  }

  function draw() {
    var host = el("qb-family-graph");
    if (!host || typeof d3 === "undefined") return;
    host.innerHTML = "";
    hidePopover();
    var layout = layoutPositions();
    var pos = layout.pos;
    var cw = layout.width;
    var ch = H;
    var svg = d3
      .select(host)
      .append("svg")
      .attr("viewBox", "0 0 " + cw + " " + ch)
      .attr("preserveAspectRatio", "xMidYMin meet")
      .attr("class", "qb-family-graph-svg");

    var rels = state.relationships || [];

    var linkG = svg.append("g").attr("class", "qb-family-graph-links");
    rels.forEach(function (r) {
      var a = pos[r.source];
      var b = pos[r.target];
      if (!a || !b) return;
      linkG
        .append("line")
        .attr("x1", a.x)
        .attr("y1", a.y)
        .attr("x2", b.x)
        .attr("y2", b.y)
        .attr("class", "qb-family-graph-link qb-family-graph-link--" + esc(r.type || r.relation_type));
    });

    var nodeG = svg.append("g").attr("class", "qb-family-graph-nodes");
    (state.members || []).forEach(function (m) {
      var p = pos[m.id];
      if (!p) return;
      var g = nodeG.append("g").attr("transform", "translate(" + p.x + "," + p.y + ")");
      var dead = !!m.is_dead;
      var ph = !!m.is_placeholder;
      var boxClass =
        "qb-family-graph-node-box" +
        (dead ? " is-dead" : "") +
        (m.is_self ? " is-self" : "") +
        (ph ? " is-placeholder" : "");
      g.append("rect")
        .attr("x", -78)
        .attr("y", -40)
        .attr("width", 156)
        .attr("height", 80)
        .attr("rx", 10)
        .attr("class", boxClass)
        .attr("data-mid", m.id)
        .style("cursor", ph || !m.is_self ? "pointer" : "default");

      var displayName = ph ? "Add" : m.member_name || "—";
      g.append("text")
        .attr("text-anchor", "middle")
        .attr("y", -14)
        .attr("class", "qb-family-graph-node-name")
        .text(displayName + (ph ? " +" : ""));

      var gicon = genderIcon(m.gender);
      var ageStr = m.age != null && m.age !== "" ? " · " + m.age : "";
      g.append("text")
        .attr("text-anchor", "middle")
        .attr("y", 4)
        .attr("class", "qb-family-graph-node-sub")
        .text((gicon ? gicon + " " : "") + (m.relationship_to_user || m.relationship || "") + ageStr);

      if (dead) {
        g.append("text")
          .attr("text-anchor", "middle")
          .attr("y", 22)
          .attr("class", "qb-family-graph-dead-icon")
          .text("†");
      }

      if (!m.is_self && !ph) {
        var actions = g.append("g").attr("transform", "translate(0, 34)");
        actions
          .append("text")
          .attr("text-anchor", "middle")
          .attr("class", "qb-family-graph-action qb-family-graph-edit")
          .attr("data-id", m.id)
          .style("cursor", "pointer")
          .text("✎ Edit");
        actions
          .append("text")
          .attr("text-anchor", "middle")
          .attr("x", 52)
          .attr("class", "qb-family-graph-action qb-family-graph-delete")
          .attr("data-id", m.id)
          .attr("data-source", m.source || "manual")
          .style("cursor", "pointer")
          .text("⌫");
      }
    });
  }

  function fillMemberSelects(sel, excludeId) {
    if (!sel) return;
    var cur = sel.value;
    sel.innerHTML = '<option value="">— None —</option>';
    var vid = VIEWER_ID;
    var oYou = document.createElement("option");
    oYou.value = String(vid);
    oYou.textContent = "You (account)";
    sel.appendChild(oYou);
    (state.members || []).forEach(function (m) {
      if (m.is_self) return;
      if (excludeId != null && String(m.id) === String(excludeId)) return;
      var o = document.createElement("option");
      o.value = String(m.id);
      o.textContent = m.member_name || "Member " + m.id;
      sel.appendChild(o);
    });
    if (cur && [].some.call(sel.options, function (opt) { return opt.value === cur; })) {
      sel.value = cur;
    }
  }

  function findParentOfTarget(mid) {
    var o = null;
    (state.relationships || []).forEach(function (r) {
      var typ = (r.type || r.relation_type || "").toLowerCase();
      if (typ === "parent" && r.source === mid) o = r.target;
    });
    return o;
  }

  function findChildOfTarget(mid) {
    var o = null;
    (state.relationships || []).forEach(function (r) {
      var typ = (r.type || r.relation_type || "").toLowerCase();
      if (typ === "child" && r.source === mid) o = r.target;
    });
    return o;
  }

  function findSpouse(mid) {
    var o = null;
    (state.relationships || []).forEach(function (r) {
      var typ = (r.type || r.relation_type || "").toLowerCase();
      if (typ !== "spouse") return;
      if (r.source === mid) o = r.target;
      else if (r.target === mid) o = r.source;
    });
    return o;
  }

  function findSibling(mid) {
    var o = null;
    (state.relationships || []).forEach(function (r) {
      var typ = (r.type || r.relation_type || "").toLowerCase();
      if (typ !== "sibling") return;
      if (r.source === mid) o = r.target;
      else if (r.target === mid) o = r.source;
    });
    return o;
  }

  function openEditModal(mid) {
    if (window.qbOpenFamilyMemberEditModal) {
      window.qbOpenFamilyMemberEditModal(mid);
      return;
    }
    var m = memberById(mid);
    if (!m || m.is_self) return;
    el("qb-ft-edit-id").value = String(mid);
    el("qb-ft-edit-name").value = m.member_name || "";
    el("qb-ft-edit-gender").value = m.gender || "";
    el("qb-ft-edit-age").value = m.age != null ? String(m.age) : "";
    el("qb-ft-edit-dead").checked = !!m.is_dead;
    fillMemberSelects(el("qb-ft-edit-parent-of"), mid);
    fillMemberSelects(el("qb-ft-edit-child-of"), mid);
    fillMemberSelects(el("qb-ft-edit-spouse-of"), mid);
    fillMemberSelects(el("qb-ft-edit-sibling-of"), mid);
    var po = findParentOfTarget(mid);
    var co = findChildOfTarget(mid);
    var so = findSpouse(mid);
    var sib = findSibling(mid);
    if (el("qb-ft-edit-parent-of")) el("qb-ft-edit-parent-of").value = po != null ? String(po) : "";
    if (el("qb-ft-edit-child-of")) el("qb-ft-edit-child-of").value = co != null ? String(co) : "";
    if (el("qb-ft-edit-spouse-of")) el("qb-ft-edit-spouse-of").value = so != null ? String(so) : "";
    if (el("qb-ft-edit-sibling-of")) el("qb-ft-edit-sibling-of").value = sib != null ? String(sib) : "";
    text(el("qb-ft-edit-status"), "");
    if (window.qbOpenModal) window.qbOpenModal("qb-ft-graph-edit-modal");
    else if (window.openModal) window.openModal("qb-ft-graph-edit-modal");
  }

  function openAddModal() {
    var f = el("qb-ft-graph-add-form");
    if (f) f.reset();
    fillMemberSelects(el("qb-ft-add-parent-of"), null);
    fillMemberSelects(el("qb-ft-add-child-of"), null);
    fillMemberSelects(el("qb-ft-add-spouse-of"), null);
    fillMemberSelects(el("qb-ft-add-sibling-of"), null);
    text(el("qb-ft-add-status"), "");
    if (window.qbOpenModal) window.qbOpenModal("qb-ft-graph-add-modal");
    else if (window.openModal) window.openModal("qb-ft-graph-add-modal");
  }

  function text(node, v) {
    if (node) node.textContent = v || "";
  }

  function applyTreeData(data) {
    state.members = data.members || [];
    state.relationships = data.relationships || [];
    state.sentences = data.sentences || {};
    state.viewer = data.viewer || null;
    buildIndex();
    draw();
  }

  function reload() {
    var host = el("qb-family-graph");
    return fetch("/api/family/tree", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.text().then(function (text) {
          var ct = (r.headers.get("content-type") || "").toLowerCase();
          var data = null;
          if (ct.indexOf("application/json") !== -1 && text) {
            try {
              data = JSON.parse(text);
            } catch (parseErr) {
              console.error("Family tree: invalid JSON", parseErr);
              throw new Error("Server returned invalid JSON");
            }
          } else if (text && text.trim().indexOf("<") === 0) {
            throw new Error("Server returned HTML instead of JSON (HTTP " + r.status + ")");
          }
          if (!r.ok) {
            var msg =
              (data && (data.error || data.message)) ||
              "HTTP " + r.status;
            throw new Error(msg);
          }
          if (data == null) {
            throw new Error("Expected JSON from /api/family/tree");
          }
          return data;
        });
      })
      .then(function (data) {
        applyTreeData(data);
      })
      .catch(function (err) {
        console.error("Failed to load family tree:", err);
        if (host) {
          host.innerHTML =
            '<p class="small text-danger mb-0 qb-family-graph-error" role="alert">Unable to load family tree. ' +
            esc(err.message || "Please try again later.") +
            "</p>";
        }
      });
  }

  function parseOptInt(v) {
    if (v == null || v === "") return null;
    var n = parseInt(String(v), 10);
    return isNaN(n) ? null : n;
  }

  function wire() {
    var host = el("qb-family-graph");
    if (!host) return;

    host.addEventListener("click", function (ev) {
      var rectHit = ev.target.closest(".qb-family-graph-node-box");
      if (rectHit && rectHit.getAttribute("data-mid")) {
        var mid = parseInt(rectHit.getAttribute("data-mid") || "0", 10);
        var m = memberById(mid);
        if (!m) return;
        if (m.is_placeholder) {
          var rel = m.relationship_to_user || m.relationship || "";
          if (window.qbOpenFamilyTreeAddModal) {
            window.qbOpenFamilyTreeAddModal(rel, rel, mid);
          }
          return;
        }
        if (m.is_self) return;
        var html =
          "<div class='qb-family-tree-popover-inner'><strong>" +
          esc(m.member_name) +
          "</strong><div class='small text-muted'>" +
          esc(m.relationship_to_user || m.relationship || "") +
          "</div>" +
          "<div class='qb-family-tree-popover-actions mt-2'>" +
          "<button type='button' class='qb-btn qb-btn-outline btn-sm' data-pop='edit' data-id='" +
          mid +
          "'>Edit</button> " +
          "<button type='button' class='qb-btn btn-outline-danger btn-sm' data-pop='del' data-id='" +
          mid +
          "' data-src='" +
          String(m.source || "manual").replace(/"/g, "") +
          "'>Remove</button> " +
          (!m.is_dead
            ? "<button type='button' class='qb-btn qb-btn-outline btn-sm' data-pop='dead' data-id='" +
              mid +
              "' data-src='" +
              String(m.source || "manual").replace(/"/g, "") +
              "'>Mark deceased</button>"
            : "") +
          "</div></div>";
        showPopover(null, ev.clientX, ev.clientY, html);
        return;
      }

      var popBtn = ev.target.closest("[data-pop]");
      if (popBtn) {
        var action = popBtn.getAttribute("data-pop") || "";
        var id = parseInt(popBtn.getAttribute("data-id") || "0", 10);
        if (action === "edit") {
          hidePopover();
          openEditModal(id);
        } else if (action === "del") {
          hidePopover();
          var src = popBtn.getAttribute("data-src") || "manual";
          if (!window.confirm("Remove this family member from your tree?")) return;
          fetch("/api/family/remove_member", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ id: id, source: src }),
          })
            .then(function (r) {
              return r.json().then(function (b) {
                return { ok: r.ok, b: b };
              });
            })
            .then(function (x) {
              if (!x.ok) throw new Error((x.b && x.b.error) || "Remove failed");
              if (window.qbFamilyFlash) window.qbFamilyFlash("Member removed.", "ok");
              reload();
            })
            .catch(function (err) {
              if (window.qbFamilyFlash) window.qbFamilyFlash(err.message || "Remove failed", "error");
            });
        } else if (action === "dead") {
          hidePopover();
          var srcDead = popBtn.getAttribute("data-src") || "manual";
          fetch("/api/family/mark_deceased", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ members: [{ id: id, source: srcDead }] }),
          })
            .then(function (r) {
              return r.json().then(function (b) {
                return { ok: r.ok, b: b };
              });
            })
            .then(function (x) {
              if (!x.ok) throw new Error((x.b && x.b.error) || "Update failed");
              if (window.qbFamilyFlash) window.qbFamilyFlash("Marked as deceased.", "ok");
              if (x.b.members) applyTreeData(x.b);
              else reload();
            })
            .catch(function (err) {
              if (window.qbFamilyFlash) window.qbFamilyFlash(err.message || "Update failed", "error");
            });
        }
        return;
      }

      var ed = ev.target.closest(".qb-family-graph-edit");
      if (ed) {
        ev.preventDefault();
        openEditModal(parseInt(ed.getAttribute("data-id") || "0", 10));
        return;
      }
      var del = ev.target.closest(".qb-family-graph-delete");
      if (del) {
        ev.preventDefault();
        var id2 = parseInt(del.getAttribute("data-id") || "0", 10);
        var src2 = del.getAttribute("data-source") || "manual";
        if (!window.confirm("Remove this family member from your tree?")) return;
        fetch("/api/family/remove_member", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ id: id2, source: src2 }),
        })
          .then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
          .then(function (x) {
            if (!x.ok) throw new Error((x.b && x.b.error) || "Remove failed");
            if (window.qbFamilyFlash) window.qbFamilyFlash("Member removed.", "ok");
            reload();
          })
          .catch(function (err) {
            if (window.qbFamilyFlash) window.qbFamilyFlash(err.message || "Remove failed", "error");
          });
      }
    });

    var addBtn = el("qb-family-graph-add");
    if (addBtn)
      addBtn.addEventListener("click", function () {
        if (window.qbOpenFamilyTreeAddModal) {
          window.qbOpenFamilyTreeAddModal("", "", "");
        } else {
          openAddModal();
        }
      });

    var deadBtn = el("qb-family-graph-mark-dead");
    if (deadBtn) {
      deadBtn.addEventListener("click", function () {
        if (window.qbOpenMarkDeceasedModal) window.qbOpenMarkDeceasedModal();
      });
    }

    var addForm = el("qb-ft-graph-add-form");
    if (addForm) {
      addForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var st = el("qb-ft-add-status");
        text(st, "Saving…");
        var body = {
          member_name: (el("qb-ft-add-name").value || "").trim(),
          gender: (el("qb-ft-add-gender").value || "").trim(),
          age: parseOptInt(el("qb-ft-add-age").value),
          is_dead: el("qb-ft-add-dead").checked,
          parent_of: parseOptInt(el("qb-ft-add-parent-of").value),
          child_of: parseOptInt(el("qb-ft-add-child-of").value),
          spouse_of: parseOptInt(el("qb-ft-add-spouse-of").value),
          sibling_of: parseOptInt(el("qb-ft-add-sibling-of").value),
        };
        if (!body.member_name) {
          text(st, "Name is required.");
          return;
        }
        fetch("/api/family/add_member", {
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
            if (window.qbCloseModal) window.qbCloseModal("qb-ft-graph-add-modal");
            else if (window.closeModal) window.closeModal("qb-ft-graph-add-modal");
            if (window.qbFamilyFlash) window.qbFamilyFlash("Member added.", "ok");
            applyTreeData(x.b);
          })
          .catch(function (err) {
            text(st, err.message || "Save failed");
          });
      });
    }

    var editForm = el("qb-ft-graph-edit-form");
    if (editForm) {
      editForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var st = el("qb-ft-edit-status");
        text(st, "Saving…");
        var mid = parseInt(el("qb-ft-edit-id").value || "0", 10);
        var body = {
          member_id: mid,
          member_name: (el("qb-ft-edit-name").value || "").trim(),
          gender: (el("qb-ft-edit-gender").value || "").trim(),
          age: parseOptInt(el("qb-ft-edit-age").value),
          is_dead: el("qb-ft-edit-dead").checked,
          parent_of: parseOptInt(el("qb-ft-edit-parent-of").value),
          child_of: parseOptInt(el("qb-ft-edit-child-of").value),
          spouse_of: parseOptInt(el("qb-ft-edit-spouse-of").value),
          sibling_of: parseOptInt(el("qb-ft-edit-sibling-of").value),
        };
        if (!body.member_name) {
          text(st, "Name is required.");
          return;
        }
        fetch("/api/family/update_relationships", {
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
            if (window.qbCloseModal) window.qbCloseModal("qb-ft-graph-edit-modal");
            else if (window.closeModal) window.closeModal("qb-ft-graph-edit-modal");
            if (window.qbFamilyFlash) window.qbFamilyFlash("Profile updated.", "ok");
            applyTreeData(x.b);
          })
          .catch(function (err) {
            text(st, err.message || "Save failed");
          });
      });
    }
  }

  window.qbReloadFamilyGraph = reload;

  document.addEventListener("DOMContentLoaded", function () {
    wire();
  });
})();
