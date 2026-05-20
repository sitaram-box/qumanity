(function () {
  "use strict";

  const gridEl = document.getElementById("qb-cal-grid");
  const loadingEl = document.getElementById("qb-cal-loading");
  const errorEl = document.getElementById("qb-cal-error");
  const detailEl = document.getElementById("qb-cal-detail");
  const detailTitleEl = document.getElementById("qb-cal-detail-title");
  const dayGridEl = document.getElementById("qb-cal-day-grid");
  const detailBackBtn = document.getElementById("qb-cal-detail-back");

  let solarMonths = [];
  let userBirthday = null;
  let eventsByMonth = {};

  function showError(msg) {
    loadingEl.hidden = true;
    gridEl.hidden = true;
    errorEl.hidden = false;
    errorEl.textContent = msg;
  }

  function fmtShort(iso) {
    const d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function fmtDayNum(iso) {
    return iso.slice(8, 10).replace(/^0/, "");
  }

  function birthdayInRange(dob, start, end) {
    if (!dob) return false;
    const b = new Date(dob + "T12:00:00");
    const s = new Date(start + "T12:00:00");
    const e = new Date(end + "T12:00:00");
    for (let y = s.getFullYear(); y <= e.getFullYear(); y += 1) {
      const candidate = new Date(y, b.getMonth(), b.getDate());
      if (candidate >= s && candidate <= e) return true;
    }
    return false;
  }

  function birthdayOnDate(dob, iso) {
    if (!dob) return false;
    return dob.slice(5) === iso.slice(5);
  }

  async function fetchJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Request failed (${res.status})`);
    }
    return res.json();
  }

  function buildEventList(festivals, lunar, maxItems) {
    const combined = [];
    (festivals || []).forEach((f) => {
      combined.push({ date: f.date, label: f.name, kind: "festival" });
    });
    (lunar || []).forEach((l) => {
      combined.push({
        date: l.date,
        label: l.event_name,
        kind: "lunar",
      });
    });
    combined.sort((a, b) => a.date.localeCompare(b.date));
    const shown = combined.slice(0, maxItems);
    return { shown, total: combined.length };
  }

  function renderMonthCard(month, events) {
    const card = document.createElement("article");
    card.className = "qb-cal-month-card";
    card.tabIndex = 0;
    card.style.setProperty("--qb-cal-accent", month.colour_code);
    card.dataset.month = month.name;

    const hasBirthday = birthdayInRange(
      userBirthday && userBirthday.date,
      month.start_date,
      month.end_date
    );

    const { shown, total } = buildEventList(
      events.festivals,
      events.lunar_events,
      5
    );

    const eventsHtml = shown
      .map(
        (ev) =>
          `<li><span class="qb-cal-ev-date">${fmtShort(ev.date)}</span>${escapeHtml(ev.label)}</li>`
      )
      .join("");

    const more =
      total > shown.length
        ? `<p class="qb-cal-events-more">+${total - shown.length} more events</p>`
        : "";

    card.innerHTML = `
      ${hasBirthday ? '<span class="qb-cal-birthday-badge" title="Your birthday">🎂</span>' : ""}
      <div class="qb-cal-month-head">
        <div>
          <div class="qb-cal-month-name">${escapeHtml(month.name)}</div>
          <div class="qb-cal-month-sanskrit">${escapeHtml(month.sanskrit)}</div>
        </div>
        <span class="qb-cal-element-badge" title="${escapeHtml(month.element)}">${month.element_symbol}</span>
      </div>
      <div class="qb-cal-date-range">${fmtShort(month.start_date)} – ${fmtShort(month.end_date)}</div>
      <div class="qb-cal-events">
        <div class="qb-cal-events-title">Key events</div>
        <ul>${eventsHtml || "<li class=\"text-muted\">No major events listed</li>"}</ul>
        ${more}
      </div>
    `;

    card.addEventListener("click", () => openMonthDetail(month, events));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openMonthDetail(month, events);
      }
    });

    return card;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function openMonthDetail(month, events) {
    gridEl.hidden = true;
    detailEl.hidden = false;
    detailTitleEl.textContent = `${month.name} (${month.sanskrit}) · ${fmtShort(month.start_date)} – ${fmtShort(month.end_date)}`;

    const combined = [];
    (events.festivals || []).forEach((f) => {
      combined.push({ date: f.date, label: f.name, kind: "festival" });
    });
    (events.lunar_events || []).forEach((l) => {
      combined.push({ date: l.date, label: l.event_name, kind: "lunar" });
    });
    const byDate = {};
    combined.forEach((ev) => {
      if (!byDate[ev.date]) byDate[ev.date] = [];
      byDate[ev.date].push(ev);
    });

    dayGridEl.innerHTML = "";
    dayGridEl.style.setProperty("--qb-cal-accent", month.colour_code);

    const dows = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    dows.forEach((d) => {
      const el = document.createElement("div");
      el.className = "qb-cal-dow";
      el.textContent = d;
      dayGridEl.appendChild(el);
    });

    const start = new Date(month.start_date + "T12:00:00");
    const end = new Date(month.end_date + "T12:00:00");
    const padStart = start.getDay();
    const cursor = new Date(start);
    cursor.setDate(cursor.getDate() - padStart);

    const todayIso = new Date().toISOString().slice(0, 10);
    const totalCells = Math.ceil((padStart + (end - start) / 86400000 + 1 + (6 - end.getDay())) / 7) * 7;

    for (let i = 0; i < totalCells; i += 1) {
      const iso =
        cursor.getFullYear() +
        "-" +
        String(cursor.getMonth() + 1).padStart(2, "0") +
        "-" +
        String(cursor.getDate()).padStart(2, "0");
      const inRange = cursor >= start && cursor <= end;
      const cell = document.createElement("div");
      cell.className = "qb-cal-day" + (inRange ? "" : " is-outside");
      if (iso === todayIso && inRange) cell.classList.add("is-today");

      const markers = (byDate[iso] || [])
        .map(
          (m) =>
            `<span class="qb-cal-day-marker is-${m.kind}">${escapeHtml(m.label)}</span>`
        )
        .join("");

      const cake =
        birthdayOnDate(userBirthday && userBirthday.date, iso)
          ? '<span class="qb-cal-day-cake" title="Your birthday">🎂</span>'
          : "";

      cell.innerHTML = `
        ${cake}
        <div class="qb-cal-day-num">${cursor.getDate()}</div>
        <div class="qb-cal-day-markers">${markers}</div>
      `;
      dayGridEl.appendChild(cell);
      cursor.setDate(cursor.getDate() + 1);
    }
  }

  if (detailBackBtn) {
    detailBackBtn.addEventListener("click", () => {
      detailEl.hidden = true;
      gridEl.hidden = false;
    });
  }

  async function loadEventsForSolarMonth(month) {
    const key = month.name;
    if (eventsByMonth[key]) return eventsByMonth[key];

    const params = new URLSearchParams({
      year: "2026",
      solar: month.name,
    });
    const data = await fetchJson("/api/calendar/events?" + params.toString());
    eventsByMonth[key] = data;
    return data;
  }

  async function init() {
    try {
      const [monthsPayload, birthdayPayload] = await Promise.all([
        fetchJson("/api/calendar/solar-months"),
        fetchJson("/api/calendar/user-birthdays"),
      ]);

      solarMonths = monthsPayload.months || [];
      userBirthday = birthdayPayload.birthday || null;

      gridEl.innerHTML = "";
      for (const month of solarMonths) {
        const events = await loadEventsForSolarMonth(month);
        gridEl.appendChild(renderMonthCard(month, events));
      }

      loadingEl.hidden = true;
      gridEl.hidden = false;
    } catch (err) {
      showError(err.message || "Failed to load calendar.");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
