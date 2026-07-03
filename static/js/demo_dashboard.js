(function () {
  "use strict";
  document.querySelectorAll(".qb-demo-action").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (window.qbToast) {
        window.qbToast("Demo Mode — Register to save your vote", "info");
      }
    });
  });
})();
