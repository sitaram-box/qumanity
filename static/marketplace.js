(function () {
  "use strict";

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function jsonFetch(url, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    opts.headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    return fetch(url, opts).then(function (r) {
      return r.json().then(function (b) {
        return { ok: r.ok, b: b };
      });
    });
  }

  function loadListings() {
    var q = new URLSearchParams();
    var kw = document.getElementById("mp-search").value.trim();
    var cat = document.getElementById("mp-category").value;
    var minP = document.getElementById("mp-min-price").value;
    var maxP = document.getElementById("mp-max-price").value;
    var minR = document.getElementById("mp-min-rating").value;
    if (kw) q.set("q", kw);
    if (cat) q.set("category", cat);
    if (minP) q.set("min_price", minP);
    if (maxP) q.set("max_price", maxP);
    if (minR) q.set("min_rating", minR);
    if (document.getElementById("mp-delivery-only").checked) q.set("delivery", "1");
    jsonFetch("/api/marketplace/listings?" + q.toString()).then(function (x) {
      var ul = document.getElementById("mp-listings");
      var empty = document.getElementById("mp-listings-empty");
      ul.innerHTML = "";
      var rows = (x.b && x.b.listings) || [];
      if (!rows.length) {
        empty.hidden = false;
        return;
      }
      empty.hidden = true;
      rows.forEach(function (L) {
        var li = document.createElement("li");
        li.className = "mb-3 pb-3 border-bottom border-secondary";
        li.innerHTML =
          "<strong>" +
          esc(L.title) +
          "</strong>" +
          (L.verified_seller ? " <span class='badge bg-success'>Verified</span>" : "") +
          "<br/><span class='text-muted'>" +
          esc(L.category) +
          (L.subcategory ? " · " + esc(L.subcategory) : "") +
          "</span><br/>₹" +
          esc(L.price_rupees) +
          " · ★ " +
          esc(L.avg_rating || 0) +
          " (" +
          esc(L.rating_count || 0) +
          ") · " +
          esc(L.seller_name) +
          "<br/>" +
          (L.delivery_available ? "Delivery · " : "") +
          (L.pickup_available ? "Pickup" : "") +
          "<br/><button type='button' class='qb-btn qb-btn-outline btn-sm mt-1' data-add='" +
          L.id +
          "'>Add to cart</button>";
        ul.appendChild(li);
      });
      ul.querySelectorAll("[data-add]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          jsonFetch("/api/marketplace/cart", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ listing_id: parseInt(btn.getAttribute("data-add"), 10), quantity: 1 }),
          }).then(function () {
            loadCart();
          });
        });
      });
    });
  }

  function loadCart() {
    jsonFetch("/api/marketplace/cart").then(function (x) {
      var ul = document.getElementById("mp-cart");
      ul.innerHTML = "";
      (x.b.items || []).forEach(function (it) {
        var li = document.createElement("li");
        li.className = "mb-1";
        li.textContent = it.title + " × " + it.quantity + " · ₹" + it.line_total;
        ul.appendChild(li);
      });
      document.getElementById("mp-cart-total").textContent = String(x.b.total_rupees || 0);
    });
  }

  function loadOrders() {
    jsonFetch("/api/marketplace/orders?role=buyer").then(function (x) {
      var ul = document.getElementById("mp-orders");
      ul.innerHTML = "";
      (x.b.orders || []).forEach(function (o) {
        var li = document.createElement("li");
        li.className = "mb-2";
        li.textContent = o.order_ref + " · ₹" + o.total_rupees + " · " + o.status;
        ul.appendChild(li);
      });
    });
  }

  function checkSellerPanel() {
    jsonFetch("/api/businesses/mine").then(function (x) {
      var panel = document.getElementById("mp-seller-panel");
      if (panel && x.b.approved) panel.hidden = false;
    });
  }

  document.getElementById("mp-search-btn").addEventListener("click", loadListings);
  document.getElementById("mp-checkout-btn").addEventListener("click", function () {
    var flash = document.getElementById("mp-cart-flash");
    flash.textContent = "Checking out…";
    jsonFetch("/api/marketplace/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        delivery_mode: document.getElementById("mp-delivery-mode").value,
      }),
    })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Checkout failed");
        flash.textContent = "Order " + x.b.order_ref + " placed (Qoins pending settlement).";
        loadCart();
        loadOrders();
      })
      .catch(function (err) {
        flash.textContent = err.message;
      });
  });

  var listingForm = document.getElementById("mp-listing-form");
  if (listingForm) {
    listingForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var flash = document.getElementById("mp-listing-flash");
      flash.textContent = "Publishing…";
      fetch("/api/marketplace/listings", {
        method: "POST",
        credentials: "same-origin",
        body: new FormData(listingForm),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            return { ok: r.ok, b: b };
          });
        })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Failed");
          flash.textContent = "Listing published.";
          listingForm.reset();
          loadListings();
        })
        .catch(function (err) {
          flash.textContent = err.message;
        });
    });
  }

  loadListings();
  loadCart();
  loadOrders();
  checkSellerPanel();
})();
