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

  function parseJsonField(raw, fallback) {
    try {
      return JSON.parse(raw || "[]");
    } catch (e) {
      return fallback;
    }
  }

  var selectedJobId = null;

  function loadJobs() {
    var q = new URLSearchParams();
    var cat = document.getElementById("jp-filter-category").value;
    var typ = document.getElementById("jp-filter-type").value;
    if (cat) q.set("category", cat);
    if (typ) q.set("job_type", typ);
    jsonFetch("/api/jobs?" + q.toString()).then(function (x) {
      var ul = document.getElementById("jp-jobs-list");
      var empty = document.getElementById("jp-jobs-empty");
      ul.innerHTML = "";
      var rows = (x.b && x.b.jobs) || [];
      if (!rows.length) {
        empty.hidden = false;
        return;
      }
      empty.hidden = true;
      rows.forEach(function (j) {
        var li = document.createElement("li");
        li.className = "mb-3 pb-3 border-bottom border-secondary";
        li.innerHTML =
          "<strong>" +
          esc(j.title) +
          "</strong> · " +
          esc(j.job_type) +
          " · " +
          esc(j.category) +
          "<br/>₹" +
          esc(j.salary_qoins) +
          " / " +
          esc(j.salary_period) +
          "<br/><span class='text-muted'>" +
          esc(j.description || "").slice(0, 160) +
          "</span><br/>" +
          "<button type='button' class='qb-btn qb-btn-primary btn-sm mt-1 me-1' data-apply='" +
          j.id +
          "'>Apply</button>" +
          "<button type='button' class='qb-btn qb-btn-outline btn-sm mt-1' data-view-apps='" +
          j.id +
          "'>Applicants</button>";
        ul.appendChild(li);
      });
      ul.querySelectorAll("[data-apply]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          jsonFetch("/api/jobs/" + btn.getAttribute("data-apply") + "/apply", { method: "POST" })
            .then(function (x) {
              if (!x.ok) throw new Error((x.b && x.b.error) || "Apply failed");
              alert("Application submitted.");
            })
            .catch(function (err) {
              alert(err.message);
            });
        });
      });
      ul.querySelectorAll("[data-view-apps]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          selectedJobId = btn.getAttribute("data-view-apps");
          loadApplicants(selectedJobId);
        });
      });
    });
  }

  function loadApplicants(jobId) {
    jsonFetch("/api/jobs/" + jobId + "/applications").then(function (x) {
      var panel = document.getElementById("jp-applicants-panel");
      var ul = document.getElementById("jp-applicants-list");
      panel.hidden = false;
      ul.innerHTML = "";
      (x.b.applications || []).forEach(function (a) {
        var li = document.createElement("li");
        li.className = "mb-2 pb-2 border-bottom border-secondary";
        li.innerHTML =
          esc(a.first_name + " " + a.last_name) +
          " · " +
          esc(a.status) +
          " <button type='button' class='qb-btn qb-btn-outline btn-sm ms-1' data-hire='" +
          a.id +
          "'>Hire</button>";
        ul.appendChild(li);
      });
      ul.querySelectorAll("[data-hire]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          jsonFetch("/api/jobs/applications/" + btn.getAttribute("data-hire") + "/status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: "hired" }),
          }).then(function () {
            loadApplicants(jobId);
            loadJobs();
          });
        });
      });
    });
  }

  function loadProfile() {
    jsonFetch("/api/jobs/seeker-profile").then(function (x) {
      if (!x.b.profile) return;
      var p = x.b.profile;
      document.getElementById("jp-skills").value = (p.skills || []).join(", ");
      document.getElementById("jp-availability").value = p.availability || "Full-time";
      document.getElementById("jp-experience").value = JSON.stringify(p.experience || [], null, 0);
      document.getElementById("jp-education").value = JSON.stringify(p.education || [], null, 0);
    });
  }

  document.getElementById("jp-refresh-btn").addEventListener("click", loadJobs);

  var postForm = document.getElementById("jp-post-form");
  if (postForm) {
    postForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var flash = document.getElementById("jp-post-flash");
      jsonFetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: document.getElementById("jp-title").value,
          job_type: document.getElementById("jp-job-type").value,
          category: document.getElementById("jp-category").value,
          description: document.getElementById("jp-description").value,
          requirements: document.getElementById("jp-requirements").value,
          salary_qoins: parseInt(document.getElementById("jp-salary").value, 10),
          salary_period: document.getElementById("jp-salary-period").value,
          openings: parseInt(document.getElementById("jp-openings").value, 10),
          deadline: document.getElementById("jp-deadline").value || null,
        }),
      })
        .then(function (x) {
          if (!x.ok) throw new Error((x.b && x.b.error) || "Post failed");
          flash.textContent = "Job posted.";
          postForm.reset();
          loadJobs();
        })
        .catch(function (err) {
          flash.textContent = err.message;
        });
    });
  }

  document.getElementById("jp-profile-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var flash = document.getElementById("jp-profile-flash");
    var skills = document
      .getElementById("jp-skills")
      .value.split(",")
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
    jsonFetch("/api/jobs/seeker-profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skills: skills,
        availability: document.getElementById("jp-availability").value,
        experience: parseJsonField(document.getElementById("jp-experience").value, []),
        education: parseJsonField(document.getElementById("jp-education").value, []),
      }),
    })
      .then(function (x) {
        if (!x.ok) throw new Error((x.b && x.b.error) || "Save failed");
        flash.textContent = "Profile saved.";
      })
      .catch(function (err) {
        flash.textContent = err.message;
      });
  });

  loadJobs();
  loadProfile();
})();
