(function () {
  "use strict";

  var form = document.getElementById("login-form");
  var hidden = document.getElementById("private_id");
  var digits = document.querySelectorAll(".qb-private-id-digit");
  if (!form || !hidden || !digits.length) return;

  function digitsValue() {
    return Array.prototype.map.call(digits, function (el) {
      return (el.value || "").replace(/\D/g, "");
    }).join("");
  }

  function syncHidden() {
    hidden.value = digitsValue();
  }

  function focusDigit(index) {
    if (index >= 0 && index < digits.length) {
      digits[index].focus();
      digits[index].select();
    }
  }

  digits.forEach(function (input, index) {
    input.addEventListener("input", function () {
      var val = (input.value || "").replace(/\D/g, "");
      if (val.length > 1) {
        val = val.charAt(0);
      }
      input.value = val;
      syncHidden();
      if (val && index < digits.length - 1) {
        focusDigit(index + 1);
      }
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Backspace" && !input.value && index > 0) {
        focusDigit(index - 1);
      }
      if (e.key === "ArrowLeft" && index > 0) {
        e.preventDefault();
        focusDigit(index - 1);
      }
      if (e.key === "ArrowRight" && index < digits.length - 1) {
        e.preventDefault();
        focusDigit(index + 1);
      }
    });

    input.addEventListener("paste", function (e) {
      e.preventDefault();
      var text = (e.clipboardData || window.clipboardData).getData("text") || "";
      var nums = text.replace(/\D/g, "").slice(0, 9);
      for (var i = 0; i < digits.length; i++) {
        digits[i].value = nums.charAt(i) || "";
      }
      syncHidden();
      focusDigit(Math.min(nums.length, digits.length - 1));
    });
  });

  form.addEventListener("submit", function (e) {
    syncHidden();
    var value = hidden.value;
    if (!/^\d{9}$/.test(value)) {
      e.preventDefault();
      if (window.qbToast) {
        window.qbToast("Enter all 9 digits of your Private ID.", "error");
      }
      focusDigit(0);
    }
  });

  focusDigit(0);
})();
