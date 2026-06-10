(function () {
  "use strict";

  var state = {
    purpose: null,
    firstName: "",
    lastName: "",
    dateOfBirth: "",
    candidates: [],
    selectedUserId: null,
    resetToken: null,
    userPrivateId: null,
  };

  var steps = [
    "recovery-step-purpose",
    "recovery-step-identity",
    "recovery-step-select-user",
    "recovery-step-location",
    "recovery-step-id-result",
    "recovery-step-password",
    "recovery-step-password-done",
  ];

  function $(id) {
    return document.getElementById(id);
  }

  function showStep(stepId) {
    steps.forEach(function (id) {
      var el = $(id);
      if (el) el.hidden = id !== stepId;
    });
    clearErr();
  }

  function showErr(msg) {
    var el = $("recovery-error");
    if (!el) return;
    el.textContent = msg || "Something went wrong.";
    el.hidden = !msg;
  }

  function clearErr() {
    showErr("");
  }

  function purposeLabel(purpose) {
    return purpose === "reset_password"
      ? "Resetting your password"
      : "Recovering your Private ID";
  }

  function jsonFetch(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().then(function (data) {
        return { ok: r.ok, status: r.status, data: data };
      });
    });
  }

  function identityPayload(extra) {
    var payload = {
      purpose: state.purpose,
      first_name: state.firstName,
      last_name: state.lastName,
      date_of_birth: state.dateOfBirth,
    };
    if (state.selectedUserId != null) {
      payload.user_id = state.selectedUserId;
    }
    if (extra) {
      Object.keys(extra).forEach(function (k) {
        payload[k] = extra[k];
      });
    }
    return payload;
  }

  function renderCandidates() {
    var list = $("recovery-candidate-list");
    var continueBtn = $("recovery-select-user-continue");
    if (!list) return;
    list.innerHTML = "";
    state.selectedUserId = null;
    if (continueBtn) continueBtn.disabled = true;

    state.candidates.forEach(function (c) {
      var label = document.createElement("label");
      label.className = "d-block mb-2 p-2 border rounded";
      var input = document.createElement("input");
      input.type = "radio";
      input.name = "recovery_candidate";
      input.value = String(c.user_id);
      input.className = "me-2";
      input.addEventListener("change", function () {
        state.selectedUserId = Number(c.user_id);
        if (continueBtn) continueBtn.disabled = false;
      });
      label.appendChild(input);
      label.appendChild(
        document.createTextNode(
          c.first_name + " " + c.last_name + (c.gender ? " (" + c.gender + ")" : "")
        )
      );
      list.appendChild(label);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("recovery-app")) return;

    document.querySelectorAll("[data-purpose]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.purpose = btn.getAttribute("data-purpose");
        var label = $("recovery-purpose-label");
        if (label) label.textContent = purposeLabel(state.purpose);
        showStep("recovery-step-identity");
      });
    });

    $("recovery-back-purpose").addEventListener("click", function () {
      showStep("recovery-step-purpose");
    });

    $("recovery-identity-form").addEventListener("submit", function (ev) {
      ev.preventDefault();
      clearErr();
      state.firstName = ($("recovery-first-name").value || "").trim();
      state.lastName = ($("recovery-last-name").value || "").trim();
      state.dateOfBirth = ($("recovery-dob").value || "").trim();
      if (!state.firstName || !state.lastName || !state.dateOfBirth) {
        showErr("Enter your full name and date of birth.");
        return;
      }

      jsonFetch("/api/recovery/search", {
        first_name: state.firstName,
        last_name: state.lastName,
        date_of_birth: state.dateOfBirth,
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error((res.data && res.data.error) || "Search failed.");
          }
          state.candidates = res.data.candidates || [];
          if (res.data.multiple) {
            renderCandidates();
            showStep("recovery-step-select-user");
          } else {
            state.selectedUserId =
              state.candidates.length === 1 ? state.candidates[0].user_id : null;
            showStep("recovery-step-location");
          }
        })
        .catch(function (e) {
          showErr(e.message);
        });
    });

    $("recovery-back-identity").addEventListener("click", function () {
      showStep("recovery-step-identity");
    });

    $("recovery-select-user-continue").addEventListener("click", function () {
      if (state.selectedUserId == null) {
        showErr("Select your account to continue.");
        return;
      }
      showStep("recovery-step-location");
    });

    $("recovery-back-location").addEventListener("click", function () {
      if (state.candidates.length > 1) {
        showStep("recovery-step-select-user");
      } else {
        showStep("recovery-step-identity");
      }
    });

    $("recovery-verify-location").addEventListener("click", function () {
      clearErr();
      var birthLocationId = ($("recovery_location_id").value || "").trim();
      if (!birthLocationId) {
        showErr("Select your birth village.");
        return;
      }

      jsonFetch(
        "/api/recovery/verify",
        identityPayload({ birth_location_id: birthLocationId })
      )
        .then(function (res) {
          if (!res.ok) {
            throw new Error((res.data && res.data.error) || "Verification failed.");
          }
          if (state.purpose === "recovery_id") {
            $("recovery-id-message").textContent =
              res.data.message || "Your Private ID is shown below.";
            $("recovery-result-private-id").textContent = res.data.private_id || "";
            $("recovery-result-public-id").textContent = res.data.public_id || "";
            showStep("recovery-step-id-result");
            return;
          }
          state.resetToken = res.data.reset_token || null;
          state.userPrivateId = res.data.user_private_id || null;
          showStep("recovery-step-password");
        })
        .catch(function (e) {
          showErr(e.message);
        });
    });

    $("recovery-reset-submit").addEventListener("click", function () {
      clearErr();
      var pw = $("recovery-new-password").value;
      var cf = $("recovery-confirm-password").value;
      if (!pw || pw.length < 9) {
        showErr("Password must be at least 9 characters with upper, lower, number, and special character.");
        return;
      }
      if (pw !== cf) {
        showErr("Passwords do not match.");
        return;
      }

      jsonFetch("/api/recovery/reset-password", {
        user_private_id: state.userPrivateId,
        new_password: pw,
        confirm_password: cf,
        reset_token: state.resetToken,
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error((res.data && res.data.error) || "Password reset failed.");
          }
          $("recovery-password-done-message").textContent =
            res.data.message || "Please save these IDs in a safe place.";
          $("recovery-done-private-id").textContent = res.data.private_id || "";
          $("recovery-done-public-id").textContent = res.data.public_id || "";
          showStep("recovery-step-password-done");
        })
        .catch(function (e) {
          showErr(e.message);
        });
    });
  });
})();
