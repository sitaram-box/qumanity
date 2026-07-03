(function () {
  "use strict";
  var STEPS = [
    { title: "Welcome to Qumanity", body: "A decentralized governance platform for Indian villages." },
    { title: "Find Your Village", body: "620,000+ villages connected. Search and explore statistics." },
    { title: "Meet Your Village Council", body: "Councils rotate monthly based on zodiac cycles." },
    { title: "Earn Karma Points", body: "Karma = verifiable record of civic contribution." },
    { title: "Cast Your First Vote", body: "Your vote is recorded on the Karma Ledger." },
  ];
  var idx = 0;

  function showStep() {
    var s = STEPS[idx];
    if (window.qbToast) window.qbToast("Tour " + (idx + 1) + "/5: " + s.title + " — " + s.body, "info");
    idx += 1;
    if (idx >= STEPS.length) {
      if (window.qbToast) window.qbToast("Register to participate in real governance", "success");
      return;
    }
    setTimeout(showStep, 3500);
  }

  window.qbStartProductTour = function () {
    idx = 0;
    showStep();
  };
})();
