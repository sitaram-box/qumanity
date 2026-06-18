(function () {
  "use strict";

  var modal = document.getElementById("qb-admin-panel-modal");
  var openBtn = document.getElementById("qb-admin-panel-open");
  var closeBtn = document.getElementById("qb-admin-panel-close");

  if (!modal) return;

  function openAdminPanel() {
    modal.hidden = false;
    document.body.classList.add("qb-admin-panel-open");
    if (openBtn) openBtn.setAttribute("aria-expanded", "true");
    var first = modal.querySelector(".qb-admin-tool-btn");
    if (first) first.focus();
  }

  function closeAdminPanel() {
    modal.hidden = true;
    document.body.classList.remove("qb-admin-panel-open");
    if (openBtn) {
      openBtn.setAttribute("aria-expanded", "false");
      openBtn.focus();
    }
  }

  window.openAdminPanel = openAdminPanel;
  window.closeAdminPanel = closeAdminPanel;

  if (openBtn) {
    openBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      openAdminPanel();
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      closeAdminPanel();
    });
  }

  modal.addEventListener("click", function (ev) {
    if (ev.target === modal) {
      closeAdminPanel();
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && !modal.hidden) {
      closeAdminPanel();
    }
  });
})();
