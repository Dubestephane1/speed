/* Site Speed — audit form logic.
   Tries the live /audit-api backend (Cloudflare Pages Function).
   If the API is not deployed yet, shows a clearly-labeled demo result
   so the page can be viewed before the backend exists. */

(function () {
  "use strict";

  var form = document.getElementById("audit-form");
  var result = document.getElementById("result");
  var heading = document.getElementById("result-heading");
  var body = document.getElementById("result-body");

  var VALID_ORIGINS = ["speed.stephanedube.dev", "localhost", "127.0.0.1"];

  function normalizeUrl(raw) {
    var url = raw.trim();
    if (!/^https?:\/\//i.test(url)) {
      url = "https://" + url;
    }
    try {
      var parsed = new URL(url);
      if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
        throw new Error("unsupported protocol");
      }
      return parsed.toString();
    } catch (e) {
      return null;
    }
  }

  function scoreClass(score) {
    if (score < 50) return "bad";
    if (score < 90) return "meh";
    return "";
  }

  function showError(msg) {
    heading.textContent = msg;
    body.innerHTML = "";
    result.className = "result-box visible";
  }

  function render(data) {
    var cls = scoreClass(data.score);
    var issues = (data.issues || []).map(function (i) {
      return "<li>" + i.title + "</li>";
    }).join("");
    body.innerHTML =
      '<div class="result-score ' + cls + '">' + data.score + '<span class="card-unit">/100</span></div>' +
      '<p class="result-meta">Main content on a phone loads in about <strong>' +
      data.lcp_sec + ' seconds</strong></p>' +
      (issues ? '<strong>Top problems found:</strong><ul>' + issues + "</ul>" : "") +
      '<p class="form-note" style="margin-top:14px;">Want the exact fix list with the load time to expect after each fix? Reply to the report email — it\'s free.</p>';
    result.className = "result-box visible";
  }

  function renderDemo() {
    heading.textContent = "";
    body.innerHTML =
      '<span class="demo-tag">Demo preview — connect the audit API for live numbers</span>' +
      '<div class="result-score bad">14<span class="card-unit">/100</span></div>' +
      '<p class="result-meta">Main content on a phone loads in about <strong>9.3 seconds</strong></p>' +
      '<strong>Top problems found:</strong><ul>' +
      "<li>Largest contentful paint — slow server response</li>" +
      "<li>Unoptimized images — too heavy for mobile</li>" +
      "<li>Render-blocking scripts delaying the page</li></ul>";
    result.className = "result-box visible";
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var url = normalizeUrl(document.getElementById("url").value);
    if (!url) {
      showError("Please enter a valid URL (e.g. https://yourbusiness.com).");
      return;
    }
    var email = document.getElementById("email").value.trim();

    fetch("/audit-api", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url, email: email })
    })
      .then(function (res) {
        if (!res.ok) throw new Error("api status " + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || typeof data.score !== "number") throw new Error("bad payload");
        render(data);
      })
      .catch(function (err) {
        console.warn("Audit API unavailable (" + err.message + "); showing demo result.");
        renderDemo();
      });
  });
})();