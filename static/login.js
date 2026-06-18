document.addEventListener("DOMContentLoaded", function () {
  "use strict";

  var form = document.getElementById("login-form");
  var hidden = document.getElementById("private_id");
  var boxes = document.querySelectorAll(".otp-box");
  if (!form || !boxes.length) return;

  function digitsValue() {
    return Array.prototype.map.call(boxes, function (el) {
      return (el.value || "").replace(/\D/g, "");
    }).join("");
  }

  function syncHidden() {
    if (hidden) {
      hidden.value = digitsValue();
    }
  }

  function focusBox(index) {
    if (index >= 0 && index < boxes.length) {
      boxes[index].focus();
      boxes[index].select();
    }
  }

  boxes.forEach(function (box) {
    box.value = "";
  });
  syncHidden();

  boxes.forEach(function (box, index) {
    box.addEventListener("keydown", function (e) {
      if (e.key.length === 1 && !/\d/.test(e.key)) {
        e.preventDefault();
        return;
      }
      if (e.key === "Backspace" && !box.value && index > 0) {
        focusBox(index - 1);
      }
      if (e.key === "ArrowLeft" && index > 0) {
        e.preventDefault();
        focusBox(index - 1);
      }
      if (e.key === "ArrowRight" && index < boxes.length - 1) {
        e.preventDefault();
        focusBox(index + 1);
      }
    });

    box.addEventListener("input", function () {
      var val = (box.value || "").replace(/\D/g, "");
      box.value = val.length > 1 ? val.charAt(0) : val;
      syncHidden();
      if (box.value && index < boxes.length - 1) {
        focusBox(index + 1);
      }
    });

    box.addEventListener("paste", function (e) {
      e.preventDefault();
      var text = (e.clipboardData || window.clipboardData).getData("text") || "";
      var digits = text.replace(/\D/g, "").slice(0, 9);
      for (var i = 0; i < boxes.length; i++) {
        boxes[i].value = digits.charAt(i) || "";
      }
      syncHidden();
      var focusAt = Math.min(digits.length, boxes.length - 1);
      for (var j = 0; j < boxes.length; j++) {
        if (!boxes[j].value) {
          focusAt = j;
          break;
        }
      }
      focusBox(focusAt);
    });
  });

  form.addEventListener("submit", function (e) {
    syncHidden();
    var value = digitsValue();
    if (!/^\d{9}$/.test(value)) {
      e.preventDefault();
      if (window.qbToast) {
        window.qbToast("Please enter exactly 9 digits for your Private ID.", "error");
      }
      focusBox(0);
    }
  });

  focusBox(0);
});
