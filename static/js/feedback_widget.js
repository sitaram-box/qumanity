(function () {
  "use strict";
  var btn = document.createElement("button");
  btn.type = "button";
  btn.id = "qb-feedback-widget";
  btn.className = "qb-feedback-widget-btn";
  btn.setAttribute("aria-label", "Rate this page");
  btn.title = "Ratings";
  btn.innerHTML =
    '<svg class="qb-feedback-star-icon" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
    '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" fill="currentColor" stroke="none"/>' +
    "</svg>";
  document.body.appendChild(btn);

  btn.addEventListener("click", function () {
    var rating = window.prompt("Rate this page (1 = poor, 5 = great):", "5");
    var message = window.prompt("Optional feedback (max 500 chars):", "") || "";
    fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_path: window.location.pathname,
        rating: parseInt(rating, 10) || null,
        message: message.slice(0, 500),
        category: document.body.className || "general",
      }),
    })
      .then(function () {
        if (window.qbToast) window.qbToast("Thank you for your feedback!", "success");
      })
      .catch(function () {
        if (window.qbToast) window.qbToast("Could not send feedback", "error");
      });
  });
})();
