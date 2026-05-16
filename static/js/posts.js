/**
 * Post voting: .js-qb-vote buttons with data-post-id and data-vote (-1,0,1).
 */
(function () {
  "use strict";

  function setScore(postId, score) {
    var el = document.querySelector(".js-qb-post-score[data-post-id='" + postId + "']");
    if (el) el.textContent = String(score);
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".js-qb-vote");
    if (!btn) return;
    var postId = btn.getAttribute("data-post-id");
    var vote = parseInt(btn.getAttribute("data-vote"), 10);
    if (!postId || isNaN(vote)) return;
    fetch("/api/post/vote", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ post_id: parseInt(postId, 10), vote_value: vote }),
    })
      .then(function (r) {
        return r.json().then(function (body) {
          return { ok: r.ok, body: body };
        });
      })
      .then(function (x) {
        if (!x.ok) throw new Error(x.body.error || "Vote failed");
        if (x.body.total_score !== undefined && x.body.total_score !== null) {
          setScore(postId, x.body.total_score);
        }
      })
      .catch(function (err) {
        alert(err.message || "Vote failed");
      });
  });
})();
