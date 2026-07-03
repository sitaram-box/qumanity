(function () {
  "use strict";
  var form = document.getElementById("qb-panchayat-form");
  if (!form) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var fd = new FormData(form);
    fetch("/api/pilot/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        village_id: "pilot-eoi-" + String(fd.get("village_name") || "unknown").slice(0, 40),
        category: "panchayat_onboarding",
        rating: 5,
        comment: JSON.stringify({
          village: fd.get("village_name"),
          district: fd.get("district"),
          state: fd.get("state"),
          population: fd.get("population"),
          coordinator: fd.get("coordinator"),
        }),
      }),
    })
      .then(function () {
        if (window.qbToast) window.qbToast("Thank you! We will contact you soon.", "success");
        form.reset();
      })
      .catch(function () {
        if (window.qbToast) window.qbToast("Could not submit. Try again later.", "error");
      });
  });
})();
