(function () {
  "use strict";

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function ageGroupFromAge(age) {
    if (!Number.isFinite(age) || age < 1) return "1-9";
    if (age >= 90) return "90-100+";
    var lower = Math.floor(age / 10) * 10;
    var upper = lower + 9;
    if (lower < 1) return "1-9";
    return String(lower) + "-" + String(upper);
  }

  function sunSignFromDate(month, day) {
    if ((month === 3 && day >= 21) || (month === 4 && day <= 19)) return "Aries";
    if ((month === 4 && day >= 20) || (month === 5 && day <= 20)) return "Taurus";
    if ((month === 5 && day >= 21) || (month === 6 && day <= 20)) return "Gemini";
    if ((month === 6 && day >= 21) || (month === 7 && day <= 22)) return "Cancer";
    if ((month === 7 && day >= 23) || (month === 8 && day <= 22)) return "Leo";
    if ((month === 8 && day >= 23) || (month === 9 && day <= 22)) return "Virgo";
    if ((month === 9 && day >= 23) || (month === 10 && day <= 22)) return "Libra";
    if ((month === 10 && day >= 23) || (month === 11 && day <= 21)) return "Scorpio";
    if ((month === 11 && day >= 22) || (month === 12 && day <= 21))
      return "Sagittarius";
    if ((month === 12 && day >= 22) || (month === 1 && day <= 19))
      return "Capricorn";
    if ((month === 1 && day >= 20) || (month === 2 && day <= 18)) return "Aquarius";
    return "Pisces";
  }

  function elementFromSunSign(sign) {
    if (sign === "Aries" || sign === "Leo" || sign === "Sagittarius") return "Fire";
    if (sign === "Taurus" || sign === "Virgo" || sign === "Capricorn") return "Earth";
    if (sign === "Gemini" || sign === "Libra" || sign === "Aquarius") return "Air";
    return "Water";
  }

  function computeAge(dob) {
    var now = new Date();
    var years = now.getFullYear() - dob.getFullYear();
    var beforeBirthday =
      now.getMonth() < dob.getMonth() ||
      (now.getMonth() === dob.getMonth() && now.getDate() < dob.getDate());
    if (beforeBirthday) years -= 1;
    return Math.max(0, years);
  }

  function parseDobInput(dobStr) {
    if (!dobStr || !/^\d{4}-\d{2}-\d{2}$/.test(dobStr)) return null;
    var parts = dobStr.split("-");
    var y = Number(parts[0]);
    var m = Number(parts[1]);
    var d = Number(parts[2]);
    if (!Number.isInteger(y) || !Number.isInteger(m) || !Number.isInteger(d)) return null;
    var dt = new Date(y, m - 1, d);
    if (
      dt.getFullYear() !== y ||
      dt.getMonth() !== m - 1 ||
      dt.getDate() !== d
    ) {
      return null;
    }
    return dt;
  }

  function updateLiveSummary() {
    var dobInput = document.getElementById("date_of_birth");
    var timeInput = document.getElementById("birth_time");
    var out = document.getElementById("live_profile_summary");
    if (!dobInput || !timeInput || !out) return;

    var dob = parseDobInput(dobInput.value);
    if (!dob) {
      out.value = "Age: — | Element: — | Sun Sign: —";
      return;
    }

    var age = computeAge(dob);
    var ageGroup = ageGroupFromAge(age);
    var sunSign = sunSignFromDate(dob.getMonth() + 1, dob.getDate());
    var element = elementFromSunSign(sunSign);
    var _timeValue = timeInput.value || "";
    out.value = "Age: " + ageGroup + " | Element: " + element + " | Sun Sign: " + sunSign;
  }

  function syncGeoLanguage() {
    // Registration page is English-only — geo labels always load in English.
    window.QBGeoLang = "en";
  }

  /* --- Location selection display (editable until registration submits) --- */
  function locationSelectorId(prefix) {
    return prefix + "-location-selector";
  }

  function locationDisplayId(prefix) {
    return prefix === "birth" ? "birth-location-display" : "current-location-display";
  }

  function locationNameId(prefix) {
    return prefix === "birth" ? "birth-location-name" : "current-location-name";
  }

  function locationSelectedFlag(prefix) {
    var el = document.getElementById(prefix + "_location_selected");
    return el && el.value === "1";
  }

  function setLocationSelectedFlag(prefix, on) {
    var el = document.getElementById(prefix + "_location_selected");
    if (el) el.value = on ? "1" : "0";
  }

  function resolveLocationSummaryId(prefix) {
    var country = document.getElementById(prefix + "_country_id");
    if (!country || !country.value) return "";
    if (country.value === "IND") {
      var vil = document.getElementById(prefix + "_location_id");
      return vil ? String(vil.value || "").trim() : "";
    }
    var globalGroup = document.getElementById(prefix + "_global_state_group");
    var globalState = document.getElementById(prefix + "_global_state_id");
    if (globalGroup && !globalGroup.hidden && globalState && globalState.value) {
      return String(globalState.value).trim();
    }
    return String(country.value).trim();
  }

  function isLocationSelectionComplete(prefix) {
    var country = document.getElementById(prefix + "_country_id");
    if (!country || !country.value) return false;
    if (country.value === "IND") {
      var vil = document.getElementById(prefix + "_location_id");
      return Boolean(vil && String(vil.value || "").trim());
    }
    var globalGroup = document.getElementById(prefix + "_global_state_group");
    if (globalGroup && !globalGroup.hidden) {
      var gs = document.getElementById(prefix + "_global_state_id");
      return Boolean(gs && String(gs.value || "").trim());
    }
    return true;
  }

  function escapeHtmlLite(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function showLocationSelector(prefix) {
    setLocationSelectedFlag(prefix, false);
    var selector = document.getElementById(locationSelectorId(prefix));
    var display = document.getElementById(locationDisplayId(prefix));
    if (selector) selector.hidden = false;
    if (display) display.hidden = true;
  }

  function showLocationDisplay(prefix) {
    if (!isLocationSelectionComplete(prefix)) return;

    var summaryId = resolveLocationSummaryId(prefix);
    var selector = document.getElementById(locationSelectorId(prefix));
    var display = document.getElementById(locationDisplayId(prefix));
    var nameEl = document.getElementById(locationNameId(prefix));

    setLocationSelectedFlag(prefix, true);
    if (selector) selector.hidden = true;
    if (display) display.hidden = false;

    if (!summaryId) return;

    fetch("/api/location/" + encodeURIComponent(summaryId) + "/details", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.data || !res.data.full_path) return;
        if (nameEl) nameEl.textContent = res.data.full_path;
      })
      .catch(function () {});
  }

  /** Never locked during registration — only the dashboard locks locations. */
  window.QBIsLocationLocked = function (_prefix) {
    return false;
  };

  window.QBLocationSelectionComplete = function (prefix) {
    showLocationDisplay(prefix);
  };

  window.QBRestoreLocationDisplay = function (prefix) {
    if (locationSelectedFlag(prefix) || isLocationSelectionComplete(prefix)) {
      showLocationDisplay(prefix);
    } else {
      showLocationSelector(prefix);
    }
  };

  function wireLocationEditButtons() {
    var editBirth = document.getElementById("edit-birth-location");
    var editCurrent = document.getElementById("edit-current-location");
    if (editBirth) {
      editBirth.addEventListener("click", function () {
        showLocationSelector("birth");
      });
    }
    if (editCurrent) {
      editCurrent.addEventListener("click", function () {
        showLocationSelector("current");
      });
    }
  }

  function loadMotherTongueOptions(countryId, selectedCode) {
    var sel = document.getElementById("mother_tongue_code");
    var section = document.getElementById("mother-tongue-section");
    if (!sel) return;

    var keep = selectedCode || sel.value || window.QBRegisterMotherTongueInitial || "";

    if (!countryId) {
      if (section) section.hidden = true;
      sel.innerHTML = "";
      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "— Select language —";
      sel.appendChild(opt0);
      syncGeoLanguage();
      return;
    }

    if (section) section.hidden = false;
    sel.innerHTML = "";
    var loading = document.createElement("option");
    loading.value = "";
    loading.textContent = "Loading languages…";
    sel.appendChild(loading);
    sel.disabled = true;

    fetch("/api/country/" + encodeURIComponent(countryId) + "/languages", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        sel.disabled = false;
        sel.innerHTML = "";
        var blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "— Select language —";
        sel.appendChild(blank);

        var languages = (res.data && res.data.languages) || [];
        if (!languages.length) {
          languages = [{ code: "en", name: "English", name_local: "English", is_primary: 1 }];
        }

        languages.forEach(function (langRow) {
          var o = document.createElement("option");
          o.value = langRow.code;
          o.textContent = langRow.name || langRow.name_local || langRow.code;
          if (keep && keep === langRow.code) {
            o.selected = true;
          } else if (!keep && langRow.is_primary) {
            o.selected = true;
          }
          sel.appendChild(o);
        });
        syncGeoLanguage();
      })
      .catch(function () {
        sel.disabled = false;
        sel.innerHTML = "";
        var errBlank = document.createElement("option");
        errBlank.value = "";
        errBlank.textContent = "— Select language —";
        sel.appendChild(errBlank);
        var fallback = document.createElement("option");
        fallback.value = "en";
        fallback.textContent = "English";
        if (keep === "en") fallback.selected = true;
        sel.appendChild(fallback);
        syncGeoLanguage();
      });
  }

  window.QBLoadMotherTongueForCountry = loadMotherTongueOptions;

  function updatePasswordRequirements() {
    var pw = document.getElementById("password");
    if (!pw) return;
    var val = pw.value || "";
    function setReq(id, ok) {
      var el = document.getElementById(id);
      if (!el) return;
      var label = el.getAttribute("data-label") || el.textContent.replace(/^[✓○]\s*/, "");
      el.setAttribute("data-label", label);
      el.textContent = (ok ? "✓ " : "○ ") + label;
      el.classList.toggle("is-met", ok);
      el.classList.toggle("is-unmet", !ok);
    }
    setReq("req-length", val.length >= 9);
    setReq("req-upper", /[A-Z]/.test(val));
    setReq("req-lower", /[a-z]/.test(val));
    setReq("req-number", /[0-9]/.test(val));
    setReq("req-special", /[!@#$%^&*]/.test(val));
  }

  function updatePasswordMatch() {
    var pw = document.getElementById("password");
    var cpw = document.getElementById("confirm_password");
    var msg = document.getElementById("password-match-message");
    if (!pw || !cpw || !msg) return;
    if (!cpw.value) {
      msg.hidden = true;
      msg.textContent = "";
      return;
    }
    if (pw.value !== cpw.value) {
      msg.hidden = false;
      msg.textContent = "Passwords do not match.";
    } else {
      msg.hidden = true;
      msg.textContent = "";
    }
  }

  function applyFieldErrors() {
    var data = window.QBRegisterFieldErrors;
    if (!data || typeof data !== "object") return;

    var firstEl = null;
    Object.keys(data).forEach(function (field) {
      var el = document.getElementById(field);
      if (!el) return;
      el.classList.add("qb-field-error");
      var group = el.closest(".qb-form-group") || el.closest(".col-md-6");
      if (group) group.classList.add("has-error");
      if (!firstEl) firstEl = el;
    });

    // Jump the wizard to the earliest step containing an errored field.
    if (firstEl && typeof window.QBRegisterWizardGoTo === "function") {
      var stepEl = firstEl.closest(".form-step");
      if (stepEl) {
        window.QBRegisterWizardGoTo(parseInt(stepEl.getAttribute("data-step"), 10) || 1);
      }
    }

    var alert = document.getElementById("register-error-alert");
    if (alert) {
      alert.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (firstEl) {
      setTimeout(function () {
        firstEl.focus({ preventScroll: true });
        firstEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 120);
    }
  }

  function prepareFormSubmission() {
    var birthComplete =
      locationSelectedFlag("birth") || isLocationSelectionComplete("birth");
    var currentComplete =
      locationSelectedFlag("current") || isLocationSelectionComplete("current");

    if (!birthComplete) {
      if (window.qbToast) {
        window.qbToast("Please select your birth location first.", "warning");
      }
      if (typeof window.QBRegisterWizardGoTo === "function") {
        window.QBRegisterWizardGoTo(2);
      }
      return false;
    }
    if (!currentComplete) {
      if (window.qbToast) {
        window.qbToast("Please select your current location first.", "warning");
      }
      if (typeof window.QBRegisterWizardGoTo === "function") {
        window.QBRegisterWizardGoTo(3);
      }
      return false;
    }

    if (!locationSelectedFlag("birth") && birthComplete) {
      setLocationSelectedFlag("birth", true);
    }
    if (!locationSelectedFlag("current") && currentComplete) {
      setLocationSelectedFlag("current", true);
    }
    return true;
  }

  /* --- Multi-step wizard ---------------------------------------------------
     Shows one .form-step at a time; the underlying single <form> POST and all
     field names/IDs stay unchanged so server validation keeps working. */
  function initRegisterWizard(form) {
    var steps = Array.prototype.slice.call(form.querySelectorAll(".form-step"));
    if (!steps.length) return;
    var indicators = document.querySelectorAll("#register-steps [data-step-indicator]");
    var current = 1;
    var maxStep = steps.length;

    function goToStep(n, opts) {
      if (n < 1) n = 1;
      if (n > maxStep) n = maxStep;
      current = n;
      steps.forEach(function (step) {
        var sn = parseInt(step.getAttribute("data-step"), 10) || 0;
        step.hidden = sn !== current;
      });
      indicators.forEach(function (ind) {
        var sn = parseInt(ind.getAttribute("data-step-indicator"), 10) || 0;
        ind.classList.toggle("active", sn === current);
        ind.classList.toggle("completed", sn < current);
      });
      if (!opts || !opts.noScroll) {
        var container = document.querySelector(".register-container") || form;
        container.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      // Reload location dropdowns when entering birth (2) or current (3) step.
      if (typeof window.QBRefreshRegisterGeoForStep === "function") {
        window.QBRefreshRegisterGeoForStep(current);
      }
    }

    function stepIsValid(stepEl) {
      var fields = stepEl.querySelectorAll("input, select, textarea");
      for (var i = 0; i < fields.length; i++) {
        var f = fields[i];
        if (f.disabled || f.type === "hidden" || f.offsetParent === null) continue;
        if (!f.checkValidity()) {
          f.reportValidity();
          f.focus();
          return false;
        }
      }
      return true;
    }

    form.querySelectorAll(".btn-next").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var stepEl = btn.closest(".form-step");
        if (stepEl && !stepIsValid(stepEl)) return;
        goToStep(parseInt(btn.getAttribute("data-next-step"), 10) || current + 1);
      });
    });

    form.querySelectorAll(".btn-prev").forEach(function (btn) {
      btn.addEventListener("click", function () {
        goToStep(parseInt(btn.getAttribute("data-prev-step"), 10) || current - 1);
      });
    });

    window.QBRegisterWizardGoTo = goToStep;
    // Donation step (Indian flow) renders inside step 4 after a valid submit.
    if (window.QBRegisterShowDonation) {
      goToStep(maxStep, { noScroll: true });
    } else {
      goToStep(1, { noScroll: true });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("register-form");
    if (!form) return;

    syncGeoLanguage();
    try {
      ["birth", "current"].forEach(function (prefix) {
        sessionStorage.removeItem(prefix + "_location_locked");
        sessionStorage.removeItem(prefix + "_location_summary_id");
      });
    } catch (_e) {}
    wireLocationEditButtons();
    ["birth", "current"].forEach(function (prefix) {
      window.QBRestoreLocationDisplay(prefix);
    });

    initRegisterWizard(form);

    form.addEventListener("submit", function (e) {
      if (!prepareFormSubmission()) {
        e.preventDefault();
      }
    });

    var dobInput = document.getElementById("date_of_birth");
    var timeInput = document.getElementById("birth_time");
    if (dobInput) dobInput.addEventListener("change", updateLiveSummary);
    if (dobInput) dobInput.addEventListener("input", updateLiveSummary);
    if (timeInput) timeInput.addEventListener("change", updateLiveSummary);
    if (timeInput) timeInput.addEventListener("input", updateLiveSummary);

    updateLiveSummary();

    var mt = document.getElementById("mother_tongue_code");
    var birthCountry = document.getElementById("birth_country_id");
    loadMotherTongueOptions(
      birthCountry ? birthCountry.value : "IND",
      window.QBRegisterMotherTongueInitial || ""
    );
    syncGeoLanguage();
    if (mt) {
      mt.addEventListener("change", function () {
        syncGeoLanguage();
      });
    }

    var pwInput = document.getElementById("password");
    var cpwInput = document.getElementById("confirm_password");
    if (pwInput) {
      pwInput.addEventListener("input", function () {
        updatePasswordRequirements();
        updatePasswordMatch();
      });
      updatePasswordRequirements();
    }
    if (cpwInput) {
      cpwInput.addEventListener("input", updatePasswordMatch);
    }

    applyFieldErrors();

    var refInput = document.getElementById("referral_code");
    if (refInput) {
      try {
        var params = new URLSearchParams(window.location.search);
        var ref = params.get("ref");
        if (ref && !refInput.value) {
          refInput.value = ref.trim().toUpperCase();
        }
        if (window.QBRegisterRefLocked || params.get("ref")) {
          refInput.readOnly = true;
          refInput.setAttribute("aria-readonly", "true");
        }
      } catch (_e) {}
      refInput.addEventListener("input", function () {
        refInput.value = refInput.value.toUpperCase();
      });
    }

    /* --- Donation step (Indian registration) --- */
    var selectedAmount = null;
    var donationSelect = document.getElementById("donation-select");
    var paymentMethodsDiv = document.getElementById("reg-payment-methods");
    var qrPlaceholder = document.getElementById("reg-qr-placeholder");
    var cashFields = document.getElementById("reg-donate-cash-fields");
    var cashReferralInput = document.getElementById("reg-donate-referral-id");
    var cashReferralError = document.getElementById("reg-cash-referral-error");
    var qrConfirmBtn = null;
    var txnRefInput = document.getElementById("reg-txn-reference");
    var txnSubmitBtn = document.getElementById("reg-txn-submit-btn");
    var txnRefError = document.getElementById("reg-txn-ref-error");
    var previewBox = document.getElementById("reg-distribution-preview");
    var previewList = document.getElementById("reg-distribution-list");
    var previewTotal = document.getElementById("reg-distribution-total");
    var previewLoading = document.getElementById("reg-distribution-loading");
    var previewError = document.getElementById("reg-distribution-error");
    var previewContent = document.getElementById("reg-distribution-content");
    var donateSubmit = document.getElementById("reg-donation-submit");
    var donateErr = document.getElementById("reg-donation-error");
    var previewRequestId = 0;
    var qrPaymentConfirmed = false;
    var txnReferenceSubmitted = false;
    var cashReferralValid = false;
    var cashReferralTimer = null;
    var pendingDonationId = null;
    var paymentWaitingEl = document.getElementById("reg-payment-waiting");
    var webhookStatusEl = document.getElementById("reg-qr-webhook-status");
    var qrImageEl = document.getElementById("reg-qr-image");
    var qrAmountEl = document.getElementById("reg-qr-amount");
    var qrUpiEl = document.getElementById("reg-qr-upi-id");
    var PAYMENT_SUCCESS_MSG =
      "Transaction reference accepted! You can now submit your registration.";

    function isValidTxnReference(ref) {
      if (!ref) return false;
      if (ref.length < 10 || ref.length > 30) return false;
      return /^[A-Za-z0-9]+$/.test(ref);
    }

    function updateTxnSubmitState() {
      if (!txnSubmitBtn) return;
      var ref = txnRefInput ? txnRefInput.value.trim() : "";
      txnSubmitBtn.disabled = !isValidTxnReference(ref) || txnReferenceSubmitted;
    }

    function setDonationSubmitEnabled(enabled) {
      if (!donateSubmit) return;
      donateSubmit.disabled = !enabled;
      if (enabled) {
        donateSubmit.classList.remove("qb-btn-neutral");
        donateSubmit.classList.add("qb-btn-primary", "active");
      } else {
        donateSubmit.classList.remove("qb-btn-primary", "active");
        donateSubmit.classList.add("qb-btn-neutral");
      }
    }

    function resetPaymentState() {
      qrPaymentConfirmed = false;
      txnReferenceSubmitted = false;
      cashReferralValid = false;
      pendingDonationId = null;
      if (cashReferralTimer) {
        clearTimeout(cashReferralTimer);
        cashReferralTimer = null;
      }
      if (qrAmountEl) qrAmountEl.textContent = "—";
      if (txnRefInput) txnRefInput.value = "";
      if (txnRefError) txnRefError.hidden = true;
      if (paymentWaitingEl) {
        paymentWaitingEl.hidden = false;
        paymentWaitingEl.textContent =
          "Scan the QR and pay. Then enter your UPI transaction reference.";
      }
      if (txnSubmitBtn) {
        txnSubmitBtn.hidden = false;
        txnSubmitBtn.disabled = true;
      }
      if (webhookStatusEl) {
        webhookStatusEl.hidden = true;
        webhookStatusEl.textContent = "";
        webhookStatusEl.classList.remove("text-danger");
        webhookStatusEl.classList.add("text-success");
      }
      if (cashReferralError) cashReferralError.hidden = true;
      setDonationSubmitEnabled(false);
    }

    function resetQrPaymentState() {
      resetPaymentState();
    }

    function showStaticBankQr(amount) {
      qrPaymentConfirmed = false;
      pendingDonationId = null;
      if (donateErr) donateErr.hidden = true;
      if (qrAmountEl) qrAmountEl.textContent = formatRupee(amount);
      if (paymentWaitingEl) {
        paymentWaitingEl.textContent = "Preparing payment…";
        paymentWaitingEl.hidden = false;
      }
      if (txnSubmitBtn) txnSubmitBtn.disabled = true;
      if (webhookStatusEl) webhookStatusEl.hidden = true;
      setDonationSubmitEnabled(false);
      fetch("/api/donation/init-bank-qr", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ amount: amount }),
      })
        .then(function (r) {
          return parseJsonResponse(r).then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) {
            throw new Error((x.b && x.b.error) || "Could not start QR payment");
          }
          pendingDonationId = x.b.donation_id;
          if (paymentWaitingEl) {
            paymentWaitingEl.textContent =
              "Scan the QR and pay. Then enter your UPI transaction reference below.";
            paymentWaitingEl.hidden = false;
          }
          if (txnSubmitBtn) txnSubmitBtn.disabled = true;
          updateTxnSubmitState();
        })
        .catch(function (err) {
          if (donateErr) {
            donateErr.textContent = err.message || "Could not initialize payment";
            donateErr.hidden = false;
          }
          if (paymentWaitingEl) paymentWaitingEl.hidden = true;
        });
    }

    function submitTxnReference() {
      var amount = getSelectedAmount();
      var ref = txnRefInput ? txnRefInput.value.trim() : "";
      if (!pendingDonationId || !amount || amount <= 0) return;
      if (!isValidTxnReference(ref)) {
        if (txnRefError) {
          txnRefError.textContent =
            "Please enter a valid transaction reference number";
          txnRefError.hidden = false;
        }
        return;
      }
      if (txnRefError) txnRefError.hidden = true;
      if (txnSubmitBtn) txnSubmitBtn.disabled = true;
      fetch("/api/donation/submit-txn-reference", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          donation_id: pendingDonationId,
          txn_reference: ref,
        }),
      })
        .then(function (r) {
          return parseJsonResponse(r).then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok || !x.b || !x.b.success) {
            throw new Error(
              (x.b && x.b.error) ||
                "Please enter a valid transaction reference number"
            );
          }
          txnReferenceSubmitted = true;
          qrPaymentConfirmed = true;
          if (txnRefInput) txnRefInput.readOnly = true;
          if (paymentWaitingEl) paymentWaitingEl.hidden = true;
          if (webhookStatusEl) {
            webhookStatusEl.textContent = PAYMENT_SUCCESS_MSG;
            webhookStatusEl.hidden = false;
          }
          setDonationSubmitEnabled(true);
          if (window.qbToast) {
            window.qbToast("Transaction reference submitted.", "success");
          }
        })
        .catch(function (err) {
          txnReferenceSubmitted = false;
          updateTxnSubmitState();
          if (txnRefError) {
            txnRefError.textContent =
              err.message || "Please enter a valid transaction reference number";
            txnRefError.hidden = false;
          }
        });
    }

    if (txnRefInput) {
      txnRefInput.addEventListener("input", function () {
        txnRefInput.value = txnRefInput.value.replace(/[^A-Za-z0-9]/g, "");
        if (txnRefError) txnRefError.hidden = true;
        updateTxnSubmitState();
      });
    }
    if (txnSubmitBtn) {
      txnSubmitBtn.addEventListener("click", submitTxnReference);
    }

    function validateCashReferral() {
      var methodRadio = document.querySelector('input[name="reg-donate-method"]:checked');
      if (!methodRadio || methodRadio.value !== "cash") return;
      var refId = cashReferralInput ? cashReferralInput.value.trim().toUpperCase() : "";
      if (!refId) {
        cashReferralValid = false;
        if (cashReferralError) {
          cashReferralError.textContent = "Referral ID is required for cash payments.";
          cashReferralError.hidden = false;
        }
        setDonationSubmitEnabled(false);
        return;
      }
      if (cashReferralTimer) clearTimeout(cashReferralTimer);
      cashReferralTimer = setTimeout(function () {
        fetch("/api/referral/validate", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ referral_code: refId }),
        })
          .then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
          .then(function (x) {
            cashReferralValid = x.ok && x.b && x.b.valid;
            if (cashReferralError) {
              if (cashReferralValid) {
                cashReferralError.hidden = true;
              } else {
                cashReferralError.textContent =
                  (x.b && x.b.error) || "Invalid Referral ID.";
                cashReferralError.hidden = false;
              }
            }
            setDonationSubmitEnabled(cashReferralValid);
          })
          .catch(function () {
            cashReferralValid = false;
            setDonationSubmitEnabled(false);
          });
      }, 400);
    }

    if (cashReferralInput) {
      cashReferralInput.addEventListener("input", function () {
        cashReferralInput.value = cashReferralInput.value.toUpperCase();
        validateCashReferral();
      });
    }

    function currentCountryId() {
      var co = document.getElementById("current_country_id");
      return co ? String(co.value || "").trim().toUpperCase() : "";
    }

    function villageIdForPreview() {
      var v = document.getElementById("current_location_id");
      return v ? String(v.value || "").trim() : "";
    }

    function continentIdForPreview() {
      var c = document.getElementById("current_continent_id");
      return c ? String(c.value || "").trim().toUpperCase() : "";
    }

    function getSelectedAmount() {
      if (donationSelect && donationSelect.value !== "") {
        var sel = parseInt(donationSelect.value, 10);
        return isNaN(sel) ? null : sel;
      }
      return selectedAmount;
    }

    function updatePaymentMethodsVisibility(amount) {
      var show = amount !== null && !isNaN(amount) && amount > 0;
      if (paymentMethodsDiv) paymentMethodsDiv.hidden = !show;
      if (amount === 0) {
        document
          .querySelectorAll('input[name="reg-donate-method"]')
          .forEach(function (r) {
            r.checked = false;
          });
        if (qrPlaceholder) qrPlaceholder.hidden = true;
        if (cashFields) cashFields.hidden = true;
        resetQrPaymentState();
        setDonationSubmitEnabled(true);
        return;
      }
      if (!show) {
        document
          .querySelectorAll('input[name="reg-donate-method"]')
          .forEach(function (r) {
            r.checked = false;
          });
        if (qrPlaceholder) qrPlaceholder.hidden = true;
        if (cashFields) cashFields.hidden = true;
        resetQrPaymentState();
        setDonationSubmitEnabled(false);
        return;
      }
      setDonationSubmitEnabled(false);
    }

    function hasReferralCode() {
      if (!refInput) return false;
      return Boolean(refInput.value.trim());
    }

    function formatRupee(amount) {
      var n = Number(amount);
      if (isNaN(n)) return "₹0";
      if (Math.abs(n - Math.round(n)) < 0.001) return "₹" + Math.round(n);
      return "₹" + n.toFixed(2);
    }

    function parseJsonResponse(response) {
      var ct = (response.headers.get("content-type") || "").toLowerCase();
      if (ct.indexOf("application/json") === -1) {
        return response.text().then(function (text) {
          var snippet = (text || "").trim().slice(0, 120);
          throw new Error(
            "Server returned non-JSON response" +
              (response.status ? " (HTTP " + response.status + ")" : "") +
              (snippet ? ": " + snippet : "")
          );
        });
      }
      return response.json();
    }

    function showPreviewState(state) {
      if (previewBox) previewBox.hidden = false;
      if (previewLoading) previewLoading.hidden = state !== "loading";
      if (previewError) previewError.hidden = state !== "error";
      if (previewContent) previewContent.hidden = state !== "ready";
    }

    function fetchDonationPreview(amount) {
      if (amount === null || isNaN(amount) || amount < 0 || amount > 200) return;

      var noReferral = !hasReferralCode();
      var noRefNotice = document.getElementById("reg-no-referral-notice");
      if (noRefNotice) noRefNotice.hidden = !noReferral;

      var previewUrl = noReferral
        ? "/api/donation/preview/no-referral"
        : "/api/donation/preview";

      var previewTitle = document.getElementById("reg-distribution-preview-title");
      var previewNote = document.getElementById("reg-distribution-preview-note");
      var locHeading = document.getElementById("reg-distribution-locations-heading");
      var userShareEl = document.getElementById("reg-distribution-user-share");

      if (previewTitle) {
        previewTitle.textContent = noReferral
          ? "📊 Distribution Preview (No Referral)"
          : "Donation Distribution Preview";
      }

      var reqId = ++previewRequestId;
      showPreviewState("loading");
      if (previewError) previewError.textContent = "";

      fetch(previewUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          donation_amount: amount,
          amount: amount,
          village_id: villageIdForPreview(),
          country_id: currentCountryId() || "IND",
          continent_id: continentIdForPreview(),
          referral_code: refInput ? refInput.value.trim() : "",
        }),
      })
        .then(function (r) {
          return parseJsonResponse(r).then(function (b) {
            return { ok: r.ok, status: r.status, b: b };
          });
        })
        .then(function (x) {
          if (reqId !== previewRequestId) return;
          if (!x.ok || x.b.success === false) {
            throw new Error((x.b && x.b.error) || "HTTP " + (x.status || "error"));
          }
          if (!previewList) return;

          previewList.innerHTML = "";
          (x.b.distribution || []).forEach(function (row) {
            var tier = row.tier || row.wallet_type || "";
            if (tier === "new_user" || tier === "referrer") return;
            var amt = row.amount_rupees != null ? row.amount_rupees : row.rupee_amount;
            if (!amt && !row.amount_paise) return;
            var li = document.createElement("li");
            var label = row.name || (tier.charAt(0).toUpperCase() + tier.slice(1));
            li.innerHTML = "<strong>" + label + ":</strong> " + formatRupee(amt);
            previewList.appendChild(li);
          });

          if (noReferral && previewNote) {
            if (x.b.system_generated || amount === 0) {
              previewNote.textContent =
                "✨ ₹0 selected — system generates 1 Karma Point (₹1) for distribution.";
              previewNote.hidden = false;
            } else {
              previewNote.hidden = true;
            }
          }

          if (locHeading) locHeading.hidden = !noReferral;

          if (userShareEl) {
            var userAmt =
              x.b.user_share_rupees != null
                ? x.b.user_share_rupees
                : x.b.user_pending_rupees;
            if (noReferral && userAmt != null) {
              userShareEl.hidden = false;
              userShareEl.textContent =
                "20% to Your Wallet (after first vote): " + formatRupee(userAmt);
            } else {
              var userRow = (x.b.distribution || []).find(function (r) {
                return r.tier === "new_user";
              });
              if (userRow && !noReferral) {
                userShareEl.hidden = false;
                userShareEl.textContent =
                  "Your share (after first vote): " +
                  formatRupee(userRow.rupee_amount || 0);
              } else {
                userShareEl.hidden = true;
              }
            }
          }

          if (previewTotal) {
            previewTotal.textContent = formatRupee(
              x.b.effective_rupees != null
                ? x.b.effective_rupees
                : x.b.total_rupees != null
                  ? x.b.total_rupees
                  : amount
            );
          }

          showPreviewState("ready");
        })
        .catch(function (err) {
          if (reqId !== previewRequestId) return;
          showPreviewState("error");
          if (previewError) {
            previewError.textContent =
              "Unable to load preview. " + (err.message || "Please try again.");
          }
        });
    }

    function renderPreview() {
      fetchDonationPreview(getSelectedAmount());
    }

    if (refInput) {
      refInput.addEventListener("input", function () {
        var amt = getSelectedAmount();
        if (amt !== null && !isNaN(amt)) renderPreview();
      });
    }

    if (donationSelect) {
      donationSelect.addEventListener("change", function () {
        var val = donationSelect.value;
        if (val === "") return;
        var amount = parseInt(val, 10);
        if (isNaN(amount)) return;
        selectedAmount = amount;
        updatePaymentMethodsVisibility(amount);
        fetchDonationPreview(amount);
        var qrRadio = document.querySelector(
          'input[name="reg-donate-method"][value="qr"]'
        );
        if (qrRadio && qrRadio.checked && amount > 0) {
          resetQrPaymentState();
          showStaticBankQr(amount);
        }
      });
    }

    document.querySelectorAll(".reg-donate-method-radio").forEach(function (radio) {
      radio.addEventListener("change", function () {
        var isCash = radio.value === "cash" && radio.checked;
        var isQr = radio.value === "qr" && radio.checked;
        if (cashFields) cashFields.hidden = !isCash;
        if (qrPlaceholder) qrPlaceholder.hidden = !isQr;
        if (isCash) {
          resetQrPaymentState();
          cashReferralValid = false;
          setDonationSubmitEnabled(false);
          validateCashReferral();
        } else if (isQr) {
          var amt = getSelectedAmount();
          if (amt > 0) showStaticBankQr(amt);
        } else {
          resetQrPaymentState();
        }
      });
    });

    function finalizeRegistrationDonation(payload) {
      return fetch("/api/register/donate", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      }).then(function (r) {
        return parseJsonResponse(r).then(function (b) {
          return { ok: r.ok, b: b };
        });
      });
    }

    if (window.QBRegisterShowDonation) {
      var section = document.getElementById("reg-donation-section");
      if (section) section.classList.remove("d-none");
      var noRefNotice = document.getElementById("reg-no-referral-notice");
      if (noRefNotice && !hasReferralCode()) noRefNotice.hidden = false;
    }

    function escapeHtml(s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
        return {
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }[c];
      });
    }

    /* Post-registration modal: user must confirm IDs are saved before login. */
    function showIdSaveModal(ids) {
      var rows = [
        { label: "Private ID (9-digit)", value: ids.private_id, key: "private" },
        { label: "Public ID (Account ID)", value: ids.public_id, key: "public" },
      ]
        .filter(function (r) {
          return r.value;
        })
        .map(function (r) {
          return (
            '<div class="qb-id-copy-row mb-3">' +
            '<div class="flex-grow-1">' +
            '<span class="small text-muted d-block">' + escapeHtml(r.label) + "</span>" +
            '<span class="font-monospace" id="reg-modal-id-' + r.key + '">' +
            escapeHtml(r.value) +
            "</span></div>" +
            '<button type="button" class="qb-btn qb-btn-outline btn-sm reg-modal-copy-btn" data-copy="' +
            escapeHtml(r.value) +
            '">📋 Copy</button>' +
            "</div>"
          );
        })
        .join("");

      var backdrop = document.createElement("div");
      backdrop.className = "qb-id-modal-backdrop";
      backdrop.id = "id-save-modal";
      backdrop.setAttribute("role", "dialog");
      backdrop.setAttribute("aria-modal", "true");
      backdrop.innerHTML =
        '<div class="qb-id-modal">' +
        '<h2 class="h5 mb-2">🎉 Account Created Successfully!</h2>' +
        (ids.account_status === "pending_verification"
          ? '<p class="small text-warning mb-2">Your donation is pending admin verification. You can log in with limited access until verified.</p>'
          : "") +
        '<p class="qb-id-modal-warning small mb-3">⚠️ Please save these IDs. You will need them to log in. You cannot recover your account without them.</p>' +
        rows +
        '<button type="button" class="qb-btn qb-btn-primary" id="reg-modal-close-btn">✅ I have saved my IDs</button>' +
        "</div>";
      document.body.appendChild(backdrop);

      backdrop.querySelectorAll(".reg-modal-copy-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var text = btn.getAttribute("data-copy") || "";
          if (!text || !navigator.clipboard) return;
          navigator.clipboard.writeText(text).then(function () {
            btn.textContent = "✓ Copied!";
            window.setTimeout(function () {
              btn.textContent = "📋 Copy";
            }, 2000);
          });
        });
      });

      document
        .getElementById("reg-modal-close-btn")
        .addEventListener("click", function () {
          backdrop.remove();
          window.location.href = "/login";
        });
    }

    if (donateSubmit) {
      donateSubmit.addEventListener("click", function () {
        var amount = getSelectedAmount();
        if (amount === null || isNaN(amount) || amount < 0 || amount > 200) {
          if (donateErr) {
            donateErr.textContent =
              "Select a donation amount from the dropdown (₹0–₹200).";
            donateErr.hidden = false;
          }
          return;
        }
        var methodRadio = document.querySelector('input[name="reg-donate-method"]:checked');
        var method = methodRadio ? methodRadio.value : "";
        if (amount > 0 && !method) {
          if (donateErr) {
            donateErr.textContent = "Select a payment method (Cash or QR Code).";
            donateErr.hidden = false;
          }
          return;
        }
        if (
          amount > 0 &&
          method === "qr" &&
          !qrPaymentConfirmed &&
          !txnReferenceSubmitted
        ) {
          if (donateErr) {
            donateErr.textContent =
              "Pay via QR, then enter and submit your UPI transaction reference.";
            donateErr.hidden = false;
          }
          return;
        }
        if (amount > 0 && method === "cash" && !cashReferralValid) {
          if (donateErr) {
            donateErr.textContent = "Enter a valid Referral ID for cash payment.";
            donateErr.hidden = false;
          }
          return;
        }
        if (amount === 0) method = "qr";
        var referralId = "";
        if (method === "cash") {
          var refEl = document.getElementById("reg-donate-referral-id");
          referralId = refEl ? refEl.value.trim().toUpperCase() : "";
          if (!referralId) {
            if (donateErr) {
              donateErr.textContent = "Enter the volunteer's Referral ID for cash payment.";
              donateErr.hidden = false;
            }
            return;
          }
        }
        donateSubmit.disabled = true;
        if (donateErr) donateErr.hidden = true;

        finalizeRegistrationDonation({
          amount: amount,
          method: method,
          payment_method: method,
          referral_code: referralId,
        })
          .then(function (x) {
            if (!x.ok) throw new Error((x.b && x.b.error) || "Registration failed");
            if (x.b.message && window.qbToast) window.qbToast(x.b.message, "success");
            showIdSaveModal({
              private_id: x.b.private_id,
              public_id: x.b.public_id,
              account_status: x.b.account_status,
            });
          })
          .catch(function (err) {
            var amount = getSelectedAmount();
            var methodRadio = document.querySelector('input[name="reg-donate-method"]:checked');
            var method = methodRadio ? methodRadio.value : "";
            if (
              amount === 0 ||
              method === "cash" ||
              (method === "qr" && qrPaymentConfirmed)
            ) {
              setDonationSubmitEnabled(true);
            }
            if (donateErr) {
              donateErr.textContent = err.message || "Could not complete registration";
              donateErr.hidden = false;
            }
          });
      });
    }
  });
})();
