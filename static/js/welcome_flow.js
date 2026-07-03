(function () {
  "use strict";

  var STORAGE_KEY = "qb_welcome_path";

  function createModal() {
    if (document.getElementById("qb-welcome-flow")) return;
    var el = document.createElement("div");
    el.id = "qb-welcome-flow";
    el.className = "qb-modal-backdrop";
    el.innerHTML =
      '<div class="qb-modal-dialog" role="dialog" aria-modal="true">' +
      '<div class="qb-modal-head"><h2 class="h5 mb-0">Who are you?</h2>' +
      '<button type="button" class="qb-modal-close" id="qb-welcome-close">×</button></div>' +
      '<p class="small text-muted">Choose your path to get started.</p>' +
      '<div class="d-flex flex-column gap-2">' +
      '<button type="button" class="qb-btn qb-btn-primary btn-sm" data-path="citizen">🏘️ Citizen</button>' +
      '<button type="button" class="qb-btn qb-btn-secondary btn-sm" data-path="developer">💻 Developer</button>' +
      '<button type="button" class="qb-btn qb-btn-outline btn-sm" data-path="researcher">📚 Researcher</button>' +
      "</div></div>";
    document.body.appendChild(el);
    el.querySelector("#qb-welcome-close").addEventListener("click", function () {
      el.hidden = true;
      localStorage.setItem(STORAGE_KEY, "dismissed");
    });
    el.querySelectorAll("[data-path]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var path = btn.getAttribute("data-path");
        localStorage.setItem(STORAGE_KEY, path);
        el.hidden = true;
        if (path === "citizen") window.location.href = "/demo";
        else if (path === "developer")
          window.location.href = "https://github.com/sitaram-box/qumanity";
        else window.open("/white-paper", "_blank");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (localStorage.getItem(STORAGE_KEY)) return;
    if (!document.body.classList.contains("qb-page-home")) return;
    createModal();
    var modal = document.getElementById("qb-welcome-flow");
    if (modal) modal.hidden = false;
  });
})();
