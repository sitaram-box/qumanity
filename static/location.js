(function () {
  "use strict";

  function openModal(id) {
    var el = document.getElementById(id);
    if (el) el.hidden = false;
  }

  function closeModal(id) {
    var el = document.getElementById(id);
    if (el) el.hidden = true;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var backLink = document.getElementById("qb-location-back-link");
    if (backLink) {
      backLink.addEventListener("click", function (e) {
        if (window.history.length > 1) {
          e.preventDefault();
          window.history.back();
        }
      });
    }

    var cfg = window.QBLocationDonate || {};
    var openBtn = document.getElementById("qb-location-donate-open");
    var closeBtn = document.getElementById("qb-location-donate-close");
    var amountEl = document.getElementById("qb-location-donate-amount");
    var preview = document.getElementById("qb-location-donate-preview");
    var previewList = document.getElementById("qb-location-donate-preview-list");
    var submitBtn = document.getElementById("qb-location-donate-submit");
    var errEl = document.getElementById("qb-location-donate-error");

    if (openBtn) {
      openBtn.addEventListener("click", function () {
        openModal("qb-location-donate-modal");
        renderPreview();
      });
    }
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        closeModal("qb-location-donate-modal");
      });
    }

    function renderPreview() {
      var amount = parseInt((amountEl && amountEl.value) || "0", 10);
      if (!amount || amount < 1 || amount > 200) return;
      fetch("/api/donation/preview", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          amount: amount,
          donation_amount: amount,
          village_id: cfg.scope === "village" ? cfg.locationId : "",
          country_id: cfg.scope === "country" ? cfg.locationId : "IND",
        }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (b) {
          if (!previewList) return;
          previewList.innerHTML = "";
          (b.distribution || []).forEach(function (row) {
            if (!row.rupee_amount) return;
            var li = document.createElement("li");
            li.textContent = (row.tier || row.wallet_type) + ": ₹" + row.rupee_amount;
            previewList.appendChild(li);
          });
          if (preview) preview.hidden = false;
        })
        .catch(function () {});
    }

    if (amountEl) {
      amountEl.addEventListener("input", renderPreview);
    }

    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        var amount = parseInt((amountEl && amountEl.value) || "0", 10);
        if (!amount || amount < 1 || amount > 200) {
          if (errEl) {
            errEl.textContent = "Enter an amount between ₹1 and ₹200.";
            errEl.hidden = false;
          }
          return;
        }
        var methodRadio = document.querySelector('input[name="loc-donate-method"]:checked');
        var method = methodRadio ? methodRadio.value : "card";
        submitBtn.disabled = true;
        if (errEl) errEl.hidden = true;

        fetch("/api/donation/create-order", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ amount: amount }),
        })
          .then(function (r) {
            return r.json().then(function (b) {
              return { ok: r.ok, b: b };
            });
          })
          .then(function (x) {
            if (!x.ok) throw new Error((x.b && x.b.error) || "Could not create order");
            if (!window.Razorpay || !x.b.key_id) {
              throw new Error("Payment gateway unavailable");
            }
            return new Promise(function (resolve, reject) {
              var rzp = new Razorpay({
                key: x.b.key_id,
                amount: amount * 100,
                currency: "INR",
                order_id: x.b.order_id,
                name: "Qumanity",
                description: "Donation to " + (cfg.locationName || "location"),
                handler: function (response) {
                  resolve(response);
                },
                modal: {
                  ondismiss: function () {
                    reject(new Error("Payment cancelled"));
                  },
                },
              });
              rzp.open();
            });
          })
          .then(function (payment) {
            return fetch("/api/location/donate", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({
                amount: amount,
                location_scope: cfg.scope,
                location_id: cfg.locationId,
                payment_method: method,
                razorpay_payment_id: payment.razorpay_payment_id,
                razorpay_order_id: payment.razorpay_order_id,
                razorpay_signature: payment.razorpay_signature,
              }),
            }).then(function (r) {
              return r.json().then(function (b) {
                return { ok: r.ok, b: b };
              });
            });
          })
          .then(function (x) {
            if (!x.ok) throw new Error((x.b && x.b.error) || "Donation failed");
            closeModal("qb-location-donate-modal");
            if (window.qbToast) window.qbToast("Thank you for your donation!", "success");
          })
          .catch(function (err) {
            if (errEl) {
              errEl.textContent = err.message || "Donation failed";
              errEl.hidden = false;
            }
          })
          .finally(function () {
            submitBtn.disabled = false;
          });
      });
    }
  });
})();
