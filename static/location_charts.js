/**
 * Location geography page — Chart.js pie and bar charts for member breakdowns.
 */
(function () {
  "use strict";

  var GENDER_COLORS = {
    Male: "#4ECDC4",
    Female: "#FF6B6B",
    Other: "#FFE66D",
  };

  var ELEMENT_COLORS = {
    Fire: "#FF6B35",
    Earth: "#4CAF50",
    Water: "#2196F3",
    Air: "#9C27B0",
  };

  var LIFE_STAGE_COLORS = {
    Balak: "#FF6B6B",
    Yuvak: "#4ECDC4",
    Vridh: "#FFD93D",
    Sanyas: "#845EC2",
  };

  var LIFE_STAGE_LABELS = {
    Balak: "Balak (0-24)",
    Yuvak: "Yuvak (25-49)",
    Vridh: "Vridh (50-75)",
    Sanyas: "Sanyas (75+)",
  };

  var ZODIAC_SUN_COLORS = [
    "#FF6B6B",
    "#FFB74D",
    "#FFD93D",
    "#6BCB77",
    "#4D96FF",
    "#9B59B6",
    "#1ABC9C",
    "#E74C3C",
    "#F39C12",
    "#2ECC71",
    "#3498DB",
    "#8E44AD",
  ];

  var ZODIAC_ORDER = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
  ];

  function rowsToMap(rows) {
    var map = {};
    (rows || []).forEach(function (r) {
      map[String(r.label)] = Number(r.count) || 0;
    });
    return map;
  }

  function colorFor(label, colorMap, fallbackIndex) {
    if (colorMap[label]) return colorMap[label];
    return ZODIAC_SUN_COLORS[fallbackIndex % ZODIAC_SUN_COLORS.length];
  }

  function pieChart(canvasId, labels, values, colors, title) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || typeof Chart === "undefined") return;
    new Chart(ctx, {
      type: "pie",
      data: {
        labels: labels,
        datasets: [
          {
            label: title,
            data: values,
            backgroundColor: colors,
            borderWidth: 2,
            borderColor: "#ffffff",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: "#F1F5F9",
              font: { size: 13, family: "Inter, system-ui, sans-serif" },
              padding: 14,
              usePointStyle: true,
            },
          },
          tooltip: {
            backgroundColor: "rgba(15, 23, 42, 0.92)",
            titleColor: "#F8FAFC",
            bodyColor: "#CBD5E1",
            borderColor: "#475569",
            borderWidth: 1,
            callbacks: {
              label: function (context) {
                var value = context.parsed || 0;
                var total = (context.dataset.data || []).reduce(function (a, b) {
                  return a + b;
                }, 0);
                var pct = total ? ((value / total) * 100).toFixed(1) : "0.0";
                return context.label + ": " + value + " (" + pct + "%)";
              },
            },
          },
        },
      },
    });
  }

  function barChart(canvasId, labels, values, colors, title) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || typeof Chart === "undefined") return;
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: title,
            data: values,
            backgroundColor: colors,
            borderRadius: 8,
            borderSkipped: false,
            maxBarThickness: 48,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(15, 23, 42, 0.92)",
            titleColor: "#F8FAFC",
            bodyColor: "#CBD5E1",
            borderColor: "#475569",
            borderWidth: 1,
            callbacks: {
              label: function (context) {
                return context.parsed.y + " users";
              },
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { color: "#94A3B8", precision: 0 },
            grid: { color: "#334155" },
          },
          x: {
            ticks: {
              color: "#94A3B8",
              font: { size: 11 },
              maxRotation: 45,
              minRotation: 0,
            },
            grid: { display: false },
          },
        },
      },
    });
  }

  function buildGenderSeries(stats) {
    var map = rowsToMap(stats.gender);
    var male = map.Male || 0;
    var female = map.Female || 0;
    var total = Number(stats.total_users) || 0;
    var other = Math.max(0, total - male - female);
    var labels = ["Male", "Female"];
    var values = [male, female];
    var colors = [GENDER_COLORS.Male, GENDER_COLORS.Female];
    if (other > 0) {
      labels.push("Other");
      values.push(other);
      colors.push(GENDER_COLORS.Other);
    }
    return { labels: labels, values: values, colors: colors };
  }

  function buildElementSeries(rows) {
    var map = rowsToMap(rows);
    var order = ["Fire", "Earth", "Water", "Air"];
    var labels = [];
    var values = [];
    var colors = [];
    order.forEach(function (key) {
      if (map[key] > 0 || labels.length < 4) {
        labels.push(key);
        values.push(map[key] || 0);
        colors.push(ELEMENT_COLORS[key]);
      }
    });
    return { labels: labels, values: values, colors: colors };
  }

  function buildLifeStageSeries(rows) {
    var map = rowsToMap(rows);
    var order = ["Balak", "Yuvak", "Vridh", "Sanyas"];
    var labels = [];
    var values = [];
    var colors = [];
    order.forEach(function (key, i) {
      labels.push(LIFE_STAGE_LABELS[key] || key);
      values.push(map[key] || 0);
      colors.push(LIFE_STAGE_COLORS[key] || colorFor(key, LIFE_STAGE_COLORS, i));
    });
    return { labels: labels, values: values, colors: colors };
  }

  function buildZodiacSunSeries(rows) {
    var map = rowsToMap(rows);
    var labels = [];
    var values = [];
    var colors = [];
    ZODIAC_ORDER.forEach(function (sign, i) {
      labels.push(sign);
      values.push(map[sign] || 0);
      colors.push(ZODIAC_SUN_COLORS[i]);
    });
    return { labels: labels, values: values, colors: colors };
  }

  window.qbInitLocationCharts = function (prefix) {
    var el = document.getElementById("stats-json-" + prefix);
    if (!el) return;
    var stats = JSON.parse(el.textContent);

    var gender = buildGenderSeries(stats);
    pieChart(
      prefix + "-gender",
      gender.labels,
      gender.values,
      gender.colors,
      "Gender"
    );

    var element = buildElementSeries(stats.sun_element);
    pieChart(
      prefix + "-element",
      element.labels,
      element.values,
      element.colors,
      "Zodiac Element"
    );

    var signs = buildZodiacSunSeries(stats.sun_sign);
    barChart(
      prefix + "-sign",
      signs.labels,
      signs.values,
      signs.colors,
      "Zodiac Sun"
    );

    var life = buildLifeStageSeries(stats.age_group);
    barChart(
      prefix + "-age",
      life.labels,
      life.values,
      life.colors,
      "Life stage"
    );
  };
})();
