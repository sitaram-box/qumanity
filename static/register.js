(function () {
  "use strict";

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function ageGroupFromAge(age) {
    if (!Number.isFinite(age) || age < 1) return "1-9";
    if (age >= 90) return "90-100+";
    var lower = Math.floor(age / 10) * 10;
    var upper = lower + 9;
    if (lower < 1) return "1-9";
    return String(lower) + "-" + String(upper);
  }

  function sunSignFromDate(month, day) {
    if ((month === 3 && day >= 21) || (month === 4 && day <= 19)) return "Aries";
    if ((month === 4 && day >= 20) || (month === 5 && day <= 20)) return "Taurus";
    if ((month === 5 && day >= 21) || (month === 6 && day <= 20)) return "Gemini";
    if ((month === 6 && day >= 21) || (month === 7 && day <= 22)) return "Cancer";
    if ((month === 7 && day >= 23) || (month === 8 && day <= 22)) return "Leo";
    if ((month === 8 && day >= 23) || (month === 9 && day <= 22)) return "Virgo";
    if ((month === 9 && day >= 23) || (month === 10 && day <= 22)) return "Libra";
    if ((month === 10 && day >= 23) || (month === 11 && day <= 21)) return "Scorpio";
    if ((month === 11 && day >= 22) || (month === 12 && day <= 21))
      return "Sagittarius";
    if ((month === 12 && day >= 22) || (month === 1 && day <= 19))
      return "Capricorn";
    if ((month === 1 && day >= 20) || (month === 2 && day <= 18)) return "Aquarius";
    return "Pisces";
  }

  function elementFromSunSign(sign) {
    if (sign === "Aries" || sign === "Leo" || sign === "Sagittarius") return "Fire";
    if (sign === "Taurus" || sign === "Virgo" || sign === "Capricorn") return "Earth";
    if (sign === "Gemini" || sign === "Libra" || sign === "Aquarius") return "Air";
    return "Water";
  }

  function computeAge(dob) {
    var now = new Date();
    var years = now.getFullYear() - dob.getFullYear();
    var beforeBirthday =
      now.getMonth() < dob.getMonth() ||
      (now.getMonth() === dob.getMonth() && now.getDate() < dob.getDate());
    if (beforeBirthday) years -= 1;
    return Math.max(0, years);
  }

  function parseDobInput(dobStr) {
    if (!dobStr || !/^\d{4}-\d{2}-\d{2}$/.test(dobStr)) return null;
    var parts = dobStr.split("-");
    var y = Number(parts[0]);
    var m = Number(parts[1]);
    var d = Number(parts[2]);
    if (!Number.isInteger(y) || !Number.isInteger(m) || !Number.isInteger(d)) return null;
    var dt = new Date(y, m - 1, d);
    if (
      dt.getFullYear() !== y ||
      dt.getMonth() !== m - 1 ||
      dt.getDate() !== d
    ) {
      return null;
    }
    return dt;
  }

  function updateLiveSummary() {
    var dobInput = document.getElementById("date_of_birth");
    var timeInput = document.getElementById("birth_time");
    var out = document.getElementById("live_profile_summary");
    if (!dobInput || !timeInput || !out) return;

    var dob = parseDobInput(dobInput.value);
    if (!dob) {
      out.value = "Age: — | Element: — | Sun Sign: —";
      return;
    }

    var age = computeAge(dob);
    var ageGroup = ageGroupFromAge(age);
    var sunSign = sunSignFromDate(dob.getMonth() + 1, dob.getDate());
    var element = elementFromSunSign(sunSign);

    // Birth time change should also trigger refresh per requirement.
    var _timeValue = timeInput.value || "";
    out.value = "Age: " + ageGroup + " | Element: " + element + " | Sun Sign: " + sunSign;
  }

  function syncLocationIdDisplay(prefix) {
    var hidden = document.getElementById(prefix + "_location_id");
    var target = document.getElementById(prefix + "_location_id_display");
    if (!hidden || !target) return;
    target.value = hidden.value || "";
  }

  function clearLocationIdDisplay(prefix) {
    var hidden = document.getElementById(prefix + "_location_id");
    var target = document.getElementById(prefix + "_location_id_display");
    if (hidden) hidden.value = "";
    if (target) target.value = "";
  }

  function wireLocationIdDisplay(prefix) {
    var stateSel = document.getElementById(prefix + "_state");
    var districtSel = document.getElementById(prefix + "_district");
    var tehsilSel = document.getElementById(prefix + "_tehsil");
    var villageSel = document.getElementById(prefix + "_village");

    if (stateSel) stateSel.addEventListener("change", function () { clearLocationIdDisplay(prefix); });
    if (districtSel) districtSel.addEventListener("change", function () { clearLocationIdDisplay(prefix); });
    if (tehsilSel) tehsilSel.addEventListener("change", function () { clearLocationIdDisplay(prefix); });
    if (villageSel) villageSel.addEventListener("change", function () { syncLocationIdDisplay(prefix); });

    // locations.js writes hidden id on village selection; defer one tick to mirror value.
    if (villageSel) {
      villageSel.addEventListener("change", function () {
        setTimeout(function () {
          syncLocationIdDisplay(prefix);
        }, 0);
      });
    }

    syncLocationIdDisplay(prefix);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var dobInput = document.getElementById("date_of_birth");
    var timeInput = document.getElementById("birth_time");
    if (dobInput) dobInput.addEventListener("change", updateLiveSummary);
    if (dobInput) dobInput.addEventListener("input", updateLiveSummary);
    if (timeInput) timeInput.addEventListener("change", updateLiveSummary);
    if (timeInput) timeInput.addEventListener("input", updateLiveSummary);

    wireLocationIdDisplay("birth");
    wireLocationIdDisplay("current");
    updateLiveSummary();
  });
})();
