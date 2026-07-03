/**
 * Quadratic Voting (QV) frontend module.
 */
const QV = {
  refreshTimer: null,

  init() {
    this.bindEvents();
    const list = document.getElementById("qv-referendum-list");
    if (list) {
      this.loadReferendums();
      this.startAutoRefresh();
    }
    const voteSlider = document.getElementById("qv-vote-slider");
    if (voteSlider) {
      voteSlider.addEventListener("input", () => this.updateCostDisplay(voteSlider.value));
      this.updateCostDisplay(voteSlider.value);
    }
    const proposeForm = document.getElementById("qv-propose-form");
    if (proposeForm) {
      proposeForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.submitProposal(new FormData(proposeForm));
      });
    }
    const castBtn = document.getElementById("qv-cast-vote-btn");
    if (castBtn) {
      castBtn.addEventListener("click", () => {
        const refId = castBtn.dataset.referendumId;
        const votes = parseInt(document.getElementById("qv-vote-slider")?.value || "1", 10);
        const balance = parseInt(castBtn.dataset.credits || "0", 10);
        const cost = this.calculateCost(votes);
        const msg =
          `This will cost ${cost} credits. You have ${balance} credits remaining. Proceed?`;
        if (window.confirm(msg)) {
          this.castVote(refId, votes);
        }
      });
    }
    document.querySelectorAll("[data-qv-approve]").forEach((btn) => {
      btn.addEventListener("click", () =>
        this.reviewReferendum(btn.dataset.qvApprove, "approve")
      );
    });
    document.querySelectorAll("[data-qv-reject]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const reason = window.prompt("Rejection reason (optional):") || "";
        this.reviewReferendum(btn.dataset.qvReject, "reject", reason);
      });
    });
    const convertBtn = document.getElementById("qv-convert-karma-btn");
    if (convertBtn) {
      convertBtn.addEventListener("click", () => this.convertKarma());
    }
  },

  bindEvents() {
    const levelFilter = document.getElementById("qv-filter-level");
    const statusFilter = document.getElementById("qv-filter-status");
    const applyFilters = () => {
      const filters = {};
      if (levelFilter?.value) filters.level = levelFilter.value;
      if (statusFilter?.value) filters.status = statusFilter.value;
      this.loadReferendums(filters);
    };
    levelFilter?.addEventListener("change", applyFilters);
    statusFilter?.addEventListener("change", applyFilters);
  },

  calculateCost(votes) {
    const v = parseInt(votes, 10) || 0;
    return v * v;
  },

  updateCostDisplay(votes) {
    const el = document.getElementById("qv-cost-display");
    if (el) {
      el.textContent = `${this.calculateCost(votes)} credits`;
    }
  },

  async loadReferendums(filters = {}) {
    const list = document.getElementById("qv-referendum-list");
    if (!list) return;
    const params = new URLSearchParams(filters);
    try {
      const res = await fetch(`/api/qv/referendums?${params.toString()}`);
      const data = await res.json();
      const items = data.referendums || [];
      if (!items.length) {
        list.innerHTML =
          '<p class="text-muted small mb-0">No referendums match your filters.</p>';
        return;
      }
      list.innerHTML = items
        .map((r) => {
          const status = (r.status || "draft").toLowerCase();
          const support = r.total_weighted_support || 0;
          const end = r.voting_end ? new Date(r.voting_end) : null;
          const countdown =
            status === "active" && end
              ? `<span class="qv-countdown" data-end="${r.voting_end}">—</span>`
              : "";
          return `
            <div class="col-12 col-md-6 col-lg-4">
              <article class="qv-card">
                <span class="qv-badge qv-badge--${status}">${status}</span>
                <h3 class="qv-card-title">${this.escapeHtml(r.title)}</h3>
                <p class="small text-muted flex-grow-1">${this.escapeHtml(
                  (r.description || "").slice(0, 120)
                )}${(r.description || "").length > 120 ? "…" : ""}</p>
                <p class="small mb-0">Level: <strong>${r.level}</strong></p>
                <p class="qv-support mb-0">Support: ${support}</p>
                ${countdown}
                <a href="/qv/referendum/${r.id}" class="qb-btn qb-btn-primary btn-sm mt-2 align-self-start">View</a>
              </article>
            </div>`;
        })
        .join("");
      this.tickCountdowns();
    } catch (_err) {
      window.qbToast?.("Could not load referendums", "error");
    }
  },

  tickCountdowns() {
    document.querySelectorAll(".qv-countdown[data-end]").forEach((el) => {
      const end = new Date(el.dataset.end);
      const diff = end - Date.now();
      if (diff <= 0) {
        el.textContent = "Ended";
        return;
      }
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      el.textContent = `${d}d ${h}h ${m}m left`;
    });
  },

  async castVote(referendumId, votes) {
    try {
      const res = await fetch(`/api/qv/referendums/${referendumId}/vote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ votes }),
      });
      const data = await res.json();
      if (!res.ok) {
        window.qbToast?.(data.error || "Vote failed", "error");
        return;
      }
      window.qbToast?.(data.message || "Vote recorded", "success");
      setTimeout(() => window.location.reload(), 800);
    } catch (_err) {
      window.qbToast?.("Vote request failed", "error");
    }
  },

  async submitProposal(formData) {
    const title = (formData.get("title") || "").trim();
    const description = (formData.get("description") || "").trim();
    const level = formData.get("level") || "village";
    if (!title || title.length > 255) {
      window.qbToast?.("Title is required (max 255 characters)", "warning");
      return;
    }
    if (!description) {
      window.qbToast?.("Description is required", "warning");
      return;
    }
    try {
      const res = await fetch("/api/qv/referendums", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, description, level }),
      });
      const data = await res.json();
      if (!res.ok) {
        window.qbToast?.(data.error || "Could not submit proposal", "error");
        return;
      }
      window.qbToast?.("Referendum submitted for council review", "success");
      window.location.href = `/qv/referendum/${data.referendum_id}`;
    } catch (_err) {
      window.qbToast?.("Proposal request failed", "error");
    }
  },

  async reviewReferendum(referendumId, action, reason = "") {
    const url =
      action === "approve"
        ? `/api/qv/referendums/${referendumId}/approve`
        : `/api/qv/referendums/${referendumId}/reject`;
    const opts = { method: "PUT", headers: { "Content-Type": "application/json" } };
    if (action === "reject") {
      opts.body = JSON.stringify({ reason });
    }
    try {
      const res = await fetch(url, opts);
      const data = await res.json();
      if (!res.ok) {
        window.qbToast?.(data.error || "Action failed", "error");
        return;
      }
      window.qbToast?.(
        action === "approve" ? "Referendum approved" : "Referendum rejected",
        "success"
      );
      setTimeout(() => window.location.reload(), 800);
    } catch (_err) {
      window.qbToast?.("Request failed", "error");
    }
  },

  async convertKarma() {
    try {
      const res = await fetch("/api/qv/credits/convert", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        window.qbToast?.(data.error || "Conversion failed", "error");
        return;
      }
      const total = data.summary?.total || 0;
      window.qbToast?.(`Converted ${total} credits for this month`, "success");
      setTimeout(() => window.location.reload(), 800);
    } catch (_err) {
      window.qbToast?.("Conversion request failed", "error");
    }
  },

  startAutoRefresh() {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    this.refreshTimer = setInterval(() => {
      const level = document.getElementById("qv-filter-level")?.value;
      const status = document.getElementById("qv-filter-status")?.value;
      const filters = {};
      if (level) filters.level = level;
      if (status) filters.status = status;
      this.loadReferendums(filters);
      this.tickCountdowns();
    }, 30000);
  },

  escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = text || "";
    return d.innerHTML;
  },
};

document.addEventListener("DOMContentLoaded", () => QV.init());
