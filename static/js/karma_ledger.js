(function () {
  "use strict";
  var SAMPLE = [
    { id: "#42", action: "Voted on Road Repair", karma: 10, element: "Earth", date: "Jul 28", verified: "Blockchain" },
    { id: "#18", action: "Reported Water Issue", karma: 25, element: "Water", date: "Jul 27", verified: "Moderator" },
    { id: "#7", action: "Volunteer Cleanup", karma: 50, element: "Fire", date: "Jul 25", verified: "Photo Proof" },
  ];
  var root = document.getElementById("qb-karma-ledger-root");
  if (!root) return;
  var html =
    '<div class="table-responsive"><table class="table table-sm table-dark mb-0"><thead><tr>' +
    "<th>Citizen ID</th><th>Action</th><th>Karma</th><th>Element</th><th>Date</th><th>Verification</th>" +
    "</tr></thead><tbody>";
  SAMPLE.forEach(function (r) {
    html +=
      "<tr><td>" +
      r.id +
      "</td><td>" +
      r.action +
      "</td><td>+" +
      r.karma +
      "</td><td>" +
      r.element +
      "</td><td>" +
      r.date +
      "</td><td>" +
      r.verified +
      " ✅</td></tr>";
  });
  html += "</tbody></table></div>";
  root.innerHTML = html;
})();
