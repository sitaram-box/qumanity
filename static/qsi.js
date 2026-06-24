/**
 * Quantum Spiritual Interface (QSI) — Sacred Spin wheel
 */
(function () {
  "use strict";

  var services = [];
  var currentSpin = null;
  var chosenName = "";
  var isLoggedIn = false;

  function toast(msg, type) {
    if (window.qbToast) {
      window.qbToast(msg, type || "info");
    }
  }

  function api(path, opts) {
    opts = opts || {};
    return fetch(path, {
      method: opts.method || "GET",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw new Error(d.error || "Request failed");
        return d;
      });
    });
  }

  function el(id) {
    return document.getElementById(id);
  }

  function loadServices() {
    return api("/api/qsi/services").then(function (d) {
      services = d.services || [];
    });
  }

  function loadUserName() {
    if (!isLoggedIn) return Promise.resolve();
    return api("/api/qsi/user-name").then(function (d) {
      if (d.preference && d.preference.chosen_name) {
        chosenName = d.preference.chosen_name;
        var inp = el("qsi-chosen-name");
        if (inp) inp.value = chosenName;
      }
    });
  }

  function showModal() {
    var backdrop = el("qb-qsi-modal");
    if (!backdrop) return;
    backdrop.hidden = false;
    backdrop.setAttribute("aria-hidden", "false");
  }

  function hideModal() {
    var backdrop = el("qb-qsi-modal");
    if (!backdrop) return;
    backdrop.hidden = true;
    backdrop.setAttribute("aria-hidden", "true");
  }

  function renderServiceCard(spin) {
    var card = el("qsi-service-card");
    if (!card) return;
    var svc = spin.service || {};
    card.hidden = false;
    el("qsi-svc-icon").textContent = svc.icon || "🕉️";
    el("qsi-svc-en").textContent = svc.service_name_en || "";
    el("qsi-svc-hi").textContent = svc.service_name_hi || "";
    el("qsi-svc-trans").textContent = svc.translation || "";
    el("qsi-svc-desc").textContent = svc.description || "";
    el("qsi-svc-name").textContent = spin.chosen_name || chosenName;

    var durationWrap = el("qsi-duration-wrap");
    var detailsForm = el("qsi-details-form");
    var cat = svc.category || "";
    if (durationWrap) durationWrap.hidden = cat !== "B";
    if (detailsForm) {
      detailsForm.hidden = false;
      buildDetailsFields(svc.service_id, cat);
    }

    var completeBtn = el("qsi-complete-btn");
    if (completeBtn) {
      completeBtn.hidden = cat === "A" || spin.status === "completed";
    }
  }

  function buildDetailsFields(serviceId, category) {
    var form = el("qsi-details-form");
    if (!form) return;
    form.innerHTML = "";
    var fields = [];

    if (category === "A") {
      if (serviceId === 1) {
        fields = [
          { key: "repetition_count", label: "Repetitions", type: "number", value: 108 },
          { key: "mala_count", label: "Mala count", type: "number", value: 1 },
          { key: "duration_minutes", label: "Duration (minutes)", type: "number", value: 30 },
          { key: "book_writing", label: "Handwritten naam patrika?", type: "checkbox" },
        ];
      } else if (serviceId === 2) {
        fields = [
          { key: "event_name", label: "Event name", type: "text" },
          { key: "location", label: "Location", type: "text" },
          { key: "date", label: "Date", type: "date" },
          { key: "participants", label: "Participants", type: "number" },
        ];
      } else {
        fields = [
          { key: "event_name", label: "Event name", type: "text" },
          { key: "location", label: "Location", type: "text" },
          { key: "date", label: "Date", type: "date" },
          { key: "participants", label: "Participants", type: "number" },
        ];
      }
    } else if (category === "B") {
      fields = [
        { key: "event_name", label: "Event / gathering name", type: "text" },
        { key: "location", label: "Location", type: "text" },
        { key: "start_date", label: "Start date", type: "date" },
        { key: "participants", label: "Participants (expected)", type: "number" },
      ];
    } else if (category === "C") {
      fields = [
        { key: "provider_name", label: "Teacher / expert name", type: "text" },
        { key: "location", label: "Location", type: "text" },
        { key: "fees", label: "Fees (₹, optional)", type: "number" },
      ];
    }

    fields.forEach(function (f) {
      var grp = document.createElement("div");
      grp.className = "form-group";
      if (f.type === "checkbox") {
        grp.innerHTML =
          "<label><input type=\"checkbox\" data-qsi-field=\"" +
          f.key +
          "\" /> " +
          f.label +
          "</label>";
      } else {
        grp.innerHTML =
          "<label class=\"form-label\">" +
          f.label +
          "</label><input class=\"form-control form-control-sm\" type=\"" +
          f.type +
          "\" data-qsi-field=\"" +
          f.key +
          "\" value=\"" +
          (f.value || "") +
          "\" />";
      }
      form.appendChild(grp);
    });
  }

  function collectDetails() {
    var form = el("qsi-details-form");
    if (!form) return {};
    var details = {};
    form.querySelectorAll("[data-qsi-field]").forEach(function (inp) {
      var key = inp.getAttribute("data-qsi-field");
      if (inp.type === "checkbox") {
        details[key] = inp.checked;
      } else if (inp.type === "number") {
        details[key] = parseInt(inp.value, 10) || 0;
      } else {
        details[key] = inp.value;
      }
    });
    return details;
  }

  function spinWheel() {
    if (!isLoggedIn) {
      toast("Please log in to spin the Sacred Wheel", "warning");
      window.location.href = "/login";
      return;
    }
    var nameInp = el("qsi-chosen-name");
    chosenName = (nameInp && nameInp.value.trim()) || chosenName;
    if (!chosenName) {
      toast("Enter your chosen Name of God first", "warning");
      return;
    }

    var wrap = el("qsi-wheel-wrap");
    var wheel = el("qsi-wheel");
    if (!wheel || !wrap) return;

    wrap.classList.add("qb-qsi-spinning");
    var extra = 360 * 5 + Math.floor(Math.random() * 360);
    wheel.style.transform = "rotate(" + extra + "deg)";

    api("/api/qsi/user-name", {
      method: "POST",
      body: { chosen_name: chosenName },
    })
      .then(function () {
        return api("/api/qsi/spin", {
          method: "POST",
          body: { chosen_name: chosenName },
        });
      })
      .then(function (d) {
        setTimeout(function () {
          wrap.classList.remove("qb-qsi-spinning");
          currentSpin = d.spin;
          renderServiceCard(currentSpin);
          toast("The wheel reveals: " + (d.spin.service && d.spin.service.service_name_en), "success");
        }, 4200);
      })
      .catch(function (err) {
        wrap.classList.remove("qb-qsi-spinning");
        toast(err.message, "error");
      });
  }

  function startService(mode) {
    if (!currentSpin) return;
    var duration = 0;
    var durInp = el("qsi-duration-days");
    if (durInp && !durInp.parentElement.hidden) {
      duration = parseInt(durInp.value, 10) || 0;
    }
    api("/api/qsi/service/start", {
      method: "POST",
      body: {
        spin_id: currentSpin.id,
        mode: mode,
        duration_days: duration,
        details: collectDetails(),
      },
    })
      .then(function (d) {
        currentSpin = d.spin;
        toast("Service started — " + mode, "success");
        if (currentSpin.status === "completed") {
          toast("Instant practice recorded (invisible karma accumulates)", "info");
        }
      })
      .catch(function (err) {
        toast(err.message, "error");
      });
  }

  function completeService() {
    if (!currentSpin) return;
    api("/api/qsi/service/complete", {
      method: "POST",
      body: { spin_id: currentSpin.id },
    })
      .then(function (d) {
        currentSpin = d.spin;
        toast("Marked complete — awaiting verification", "success");
        var completeBtn = el("qsi-complete-btn");
        if (completeBtn) completeBtn.hidden = true;
      })
      .catch(function (err) {
        toast(err.message, "error");
      });
  }

  function bindEvents() {
    var trigger = el("qb-qsi-trigger");
    if (trigger) {
      trigger.addEventListener("click", function () {
        if (!isLoggedIn) {
          toast("Log in to access QSI", "warning");
          window.location.href = "/login";
          return;
        }
        showModal();
        loadUserName();
      });
    }

    var closeBtn = document.querySelector("[data-qb-close-modal=\"qb-qsi-modal\"]");
    if (closeBtn) closeBtn.addEventListener("click", hideModal);

    var spinBtn = el("qsi-spin-btn");
    if (spinBtn) spinBtn.addEventListener("click", spinWheel);

    var getBtn = el("qsi-get-btn");
    var provideBtn = el("qsi-provide-btn");
    if (getBtn) getBtn.addEventListener("click", function () { startService("get"); });
    if (provideBtn) provideBtn.addEventListener("click", function () { startService("provide"); });

    var completeBtn = el("qsi-complete-btn");
    if (completeBtn) completeBtn.addEventListener("click", completeService);

    var historyLink = el("qsi-history-link");
    if (historyLink) {
      historyLink.addEventListener("click", function (e) {
        e.preventDefault();
        window.location.href = "/qsi/history";
      });
    }
  }

  function init() {
    var cfg = document.getElementById("qb-dash-config-json");
    if (cfg) {
      try {
        var c = JSON.parse(cfg.textContent);
        isLoggedIn = !!c.userPrivateId;
      } catch (e) { /* ignore */ }
    } else if (document.body.classList.contains("qb-page-dashboard")) {
      isLoggedIn = true;
    }

    loadServices().then(bindEvents);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
