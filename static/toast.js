/**
 * Qumanity — lightweight toast notifications + form UX helpers.
 *
 * Public API:
 *   window.qbToast(message, type = "info", timeoutMs = 4000)
 *     type: "info" | "success" | "error" | "warning"
 *
 * Also auto-wires:
 *   - Server flash messages (.qb-alert) are mirrored into toasts.
 *   - Forms with [data-qb-submitting] disable their submit button + show a
 *     spinner on submit to prevent double submission.
 */
(function () {
  "use strict";

  function ensureContainer() {
    var el = document.getElementById("qb-toast-container");
    if (!el) {
      el = document.createElement("div");
      el.id = "qb-toast-container";
      el.className = "qb-toast-container";
      el.setAttribute("aria-live", "polite");
      el.setAttribute("aria-atomic", "true");
      document.body.appendChild(el);
    }
    return el;
  }

  function showToast(message, type, timeoutMs) {
    if (!message) return;
    var container = ensureContainer();
    var toast = document.createElement("div");
    toast.className = "qb-toast qb-toast--" + (type || "info");
    toast.setAttribute("role", type === "error" ? "alert" : "status");

    var text = document.createElement("div");
    text.className = "qb-toast__body";
    text.textContent = message;
    toast.appendChild(text);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "qb-toast__close";
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = "&times;";
    toast.appendChild(close);

    container.appendChild(toast);
    requestAnimationFrame(function () {
      toast.classList.add("is-visible");
    });

    var timer = null;
    function dismiss() {
      if (timer) window.clearTimeout(timer);
      toast.classList.remove("is-visible");
      window.setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 220);
    }
    close.addEventListener("click", dismiss);

    var ms = typeof timeoutMs === "number" ? timeoutMs : 4000;
    if (ms > 0) {
      timer = window.setTimeout(dismiss, ms);
    }
    return dismiss;
  }

  window.qbToast = showToast;

  function mirrorFlashMessages() {
    var alerts = document.querySelectorAll(".qb-alert[data-qb-toast]");
    alerts.forEach(function (node) {
      var type = node.classList.contains("qb-alert-error") ? "error" : "success";
      showToast((node.textContent || "").trim(), type, 5000);
      node.setAttribute("hidden", "hidden");
    });
  }

  function wireFormSubmitGuards() {
    var forms = document.querySelectorAll("form[data-qb-submitting]");
    forms.forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector('button[type="submit"], [data-qb-submit]');
        if (!btn || btn.dataset.qbBusy === "1") return;
        btn.dataset.qbBusy = "1";
        btn.setAttribute("aria-busy", "true");
        btn.disabled = true;
        var label = btn.dataset.qbBusyLabel;
        if (label) {
          btn.dataset.qbOriginalLabel = btn.innerHTML;
          btn.innerHTML =
            '<span class="qb-spinner" aria-hidden="true"></span> ' + label;
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    ensureContainer();
    mirrorFlashMessages();
    wireFormSubmitGuards();
  });
})();
