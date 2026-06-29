(function () {
  "use strict";

  var root = document.getElementById("qb-voting-machine");
  if (!root) return;

  var toggle = document.getElementById("qb-voting-machine-toggle");
  var panel = document.getElementById("qb-voting-machine-panel");
  var closeBtn = document.getElementById("qb-voting-machine-close");
  var levelType = root.getAttribute("data-level-type") || "earth";
  var locationId = root.getAttribute("data-location-id") || "";

  var signEl = document.getElementById("qb-vm-sign");
  var phaseEl = document.getElementById("qb-vm-phase");
  var inactiveEl = document.getElementById("qb-vm-inactive");
  var activeBody = document.getElementById("qb-vm-active-body");
  var countdownEl = document.getElementById("qb-vm-countdown");
  var candidatesEl = document.getElementById("qb-vm-candidates");
  var turnoutEl = document.getElementById("qb-vm-turnout");
  var pastList = document.getElementById("qb-vm-past-list");
  var voteLink = document.getElementById("qb-vm-vote-link");

  var pollTimer = null;
  var countdownTimer = null;

  var INACTIVE_MSG =
    "Elections are only active at Village level. Higher level elections coming soon.";

  function showRoot() {
    root.hidden = false;
  }

  function openPanel() {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
  }

  function closePanel() {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }

  toggle.addEventListener("click", function () {
    if (panel.hidden) openPanel();
    else closePanel();
  });
  closeBtn.addEventListener("click", closePanel);

  function formatPhase(phase) {
    if (!phase) return "—";
    if (phase === "inactive") return "Coming soon";
    return phase.charAt(0).toUpperCase() + phase.slice(1);
  }

  function setInactive(message) {
    if (inactiveEl) {
      inactiveEl.textContent = message || INACTIVE_MSG;
      inactiveEl.hidden = false;
    }
    if (activeBody) activeBody.hidden = true;
    if (phaseEl) {
      phaseEl.textContent = "Coming soon";
      phaseEl.setAttribute("data-phase", "inactive");
    }
    if (countdownEl) countdownEl.hidden = true;
  }

  function setActive() {
    if (inactiveEl) inactiveEl.hidden = true;
    if (activeBody) activeBody.hidden = false;
  }

  function renderCountdown(endIso) {
    if (!endIso || !countdownEl) return;
    countdownEl.hidden = false;
    function tick() {
      var end = new Date(endIso + "T23:59:59");
      var now = new Date();
      var diff = end - now;
      if (diff <= 0) {
        countdownEl.textContent = "Voting closed";
        return;
      }
      var days = Math.floor(diff / 86400000);
      var hrs = Math.floor((diff % 86400000) / 3600000);
      var mins = Math.floor((diff % 3600000) / 60000);
      countdownEl.textContent =
        "Closes in " + days + "d " + hrs + "h " + mins + "m";
    }
    tick();
    if (countdownTimer) clearInterval(countdownTimer);
    countdownTimer = setInterval(tick, 60000);
  }

  function renderCandidates(candidates) {
    if (!candidatesEl) return;
    if (!candidates || !candidates.length) {
      candidatesEl.innerHTML =
        "<p class=\"small text-muted mb-0\">No candidates yet.</p>";
      return;
    }
    candidatesEl.innerHTML = candidates
      .map(function (c) {
        var cls = "qb-vm-candidate" + (c.is_winner ? " is-winner" : "");
        var pos = c.position || c.gender || "";
        return (
          "<div class=\"" +
          cls +
          "\"><span>" +
          (c.name || "Candidate") +
          " <span class=\"text-muted\">(" +
          pos +
          ")</span></span><span>" +
          (c.vote_count || 0) +
          " votes</span></div>"
        );
      })
      .join("");
  }

  function renderPast(past) {
    if (!pastList) return;
    if (!past || !past.length) {
      pastList.innerHTML = "<li class=\"text-muted\">No past results.</li>";
      return;
    }
    pastList.innerHTML = past
      .map(function (p) {
        return (
          "<li>" +
          p.zodiac_sign +
          " " +
          p.year +
          "-" +
          String(p.month).padStart(2, "0") +
          ": Nayak " +
          (p.male_winner || "—") +
          ", Nayika " +
          (p.female_winner || "—") +
          "</li>"
        );
      })
      .join("");
  }

  function applyPayload(data) {
    if (!data) return;
    var sign = data.active_zodiac_sign;
    signEl.textContent = sign ? sign + " Zodiac" : "Zodiac Elections";

    if (!data.voting_active) {
      setInactive(data.inactive_message || INACTIVE_MSG);
      showRoot();
      return;
    }

    setActive();
    var cycleSign = (data.cycle && data.cycle.zodiac_sign) || sign;
    if (cycleSign) {
      signEl.textContent = cycleSign + " Election";
    }
    var phase = data.phase || (data.cycle && data.cycle.status) || "upcoming";
    phaseEl.textContent = formatPhase(phase);
    phaseEl.setAttribute("data-phase", phase);

    if (phase === "voting" && data.countdown_end) {
      renderCountdown(data.countdown_end);
    } else if (countdownEl) {
      countdownEl.hidden = true;
    }

    if (data.cycle) {
      renderCandidates(data.cycle.candidates);
      turnoutEl.textContent =
        "Turnout: " +
        (data.cycle.voter_turnout || 0) +
        " / " +
        (data.cycle.total_voters || 0) +
        " voters";
    } else {
      renderCandidates([]);
      turnoutEl.textContent = "";
    }
    renderPast(data.past_results);
    showRoot();
  }

  function fetchStatus() {
    if (!locationId) return;
    var url =
      "/api/election/widget?level_type=" +
      encodeURIComponent(levelType) +
      "&location_id=" +
      encodeURIComponent(locationId);
    fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data && data.elections_enabled) applyPayload(data);
      })
      .catch(function () {
        /* silent */
      });
  }

  fetchStatus();
  pollTimer = setInterval(fetchStatus, 30000);

  if (voteLink && locationId && levelType === "village") {
    voteLink.href =
      "/dashboard?election_level=" +
      encodeURIComponent(levelType) +
      "&election_location=" +
      encodeURIComponent(locationId);
    voteLink.classList.remove("qb-btn-neutral");
    voteLink.classList.add("qb-btn-secondary");
  } else if (voteLink) {
    voteLink.textContent = "Village elections only";
    voteLink.classList.add("qb-btn-neutral");
    voteLink.removeAttribute("href");
    voteLink.style.pointerEvents = "none";
  }
})();
