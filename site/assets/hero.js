/* The blast-radius demo.
 *
 * The estate below is the real fixture from tests/fixtures/estate/, and the
 * connections are the ones `estate scan` actually resolves from it - same
 * resolution methods, same confidence scores. The point of the demo is that
 * the shape of the advice changes with the shape of the estate: pick an
 * endpoint only services use and the landing order is two steps; pick one the
 * TV app calls and it becomes an expand-and-contract that takes months.
 *
 * No dependencies, no build step. */

(function () {
  "use strict";

  var ESTATE = {
    "payments-api": { stack: "java", kind: "backend" },
    "ledger-rust": { stack: "rust", kind: "backend" },
    "checkout-node": { stack: "node", kind: "backend" },
    "notifications-dotnet": { stack: "dotnet", kind: "backend" },
    "ios-app": { stack: "ios-swift", kind: "client" },
    "roku-app": { stack: "roku-brightscript", kind: "client" },
    "web-react": { stack: "react-web", kind: "client" }
  };

  var EDGES = [
    { from: "notifications-dotnet", to: "payments-api", by: "declared", c: 0.95,
      ev: "Startup.cs:3", paths: ["/v2/charge", "/v2/refund"] },
    { from: "checkout-node", to: "payments-api", by: "env", c: 0.75,
      ev: "src/pay.ts:4", paths: ["/v2/charge"] },
    { from: "web-react", to: "payments-api", by: "env", c: 0.75,
      ev: "src/api.tsx:2", paths: ["/v2/charge"] },
    { from: "roku-app", to: "payments-api", by: "host", c: 0.70,
      ev: "source/Api.brs:3", paths: ["/v2/charge"] },
    { from: "ios-app", to: "payments-api", by: "path", c: 0.60,
      ev: "Sources/Endpoints.swift:2", paths: ["/v2/charge", "/v2/refund"] },
    { from: "payments-api", to: "ledger-rust", by: "declared", c: 0.95,
      ev: "LedgerClient.java:5", paths: ["/ledger/entry"] }
  ];

  var ENDPOINTS = [
    { label: "POST /v2/charge", repo: "payments-api", path: "/v2/charge" },
    { label: "GET /v2/refund/{id}", repo: "payments-api", path: "/v2/refund" },
    { label: "GET /internal/metrics", repo: "payments-api", path: "/internal/metrics" },
    { label: "POST /ledger/entry", repo: "ledger-rust", path: "/ledger/entry" }
  ];

  var root = document.getElementById("demo");
  if (!root) return;

  var state = { endpoint: ENDPOINTS[0] };

  function affected(target, path) {
    // Breadth-first over callers, exactly as `estate impact` does.
    var levels = [];
    var seen = {};
    seen[target] = true;
    var frontier = [target];
    var depth = 0;

    while (frontier.length && depth < 6) {
      var level = [];
      frontier.forEach(function (name) {
        EDGES.forEach(function (edge) {
          if (edge.to !== name || seen[edge.from]) return;
          // Only count a direct caller if it uses this endpoint.
          if (depth === 0 && path && edge.paths.indexOf(path) === -1) return;
          seen[edge.from] = true;
          level.push({
            repo: edge.from, by: edge.by, c: edge.c, ev: edge.ev,
            through: name, kind: ESTATE[edge.from].kind
          });
        });
      });
      if (!level.length) break;
      level.sort(function (a, b) {
        if (a.kind === b.kind) return a.repo < b.repo ? -1 : 1;
        return a.kind === "client" ? -1 : 1;
      });
      levels.push(level);
      frontier = level.map(function (item) { return item.repo; });
      depth += 1;
    }
    return levels;
  }

  function landingOrder(target, levels) {
    var flat = [].concat.apply([], levels);
    var clients = flat.filter(function (i) { return i.kind === "client"; });
    var services = flat.filter(function (i) { return i.kind === "backend"; });
    var steps = [];

    if (clients.length) {
      steps.push("Add the new shape to <code>" + target +
                 "</code> alongside the old one. Do not remove anything yet.");
    } else {
      steps.push("Change <code>" + target + "</code>.");
    }
    if (services.length) {
      var names = services.map(function (i) {
        return "<code>" + i.repo + "</code>";
      }).join(", ");
      steps.push("Update and deploy the services that call it: " + names + ".");
    }
    if (clients.length) {
      var apps = clients.map(function (i) {
        return "<code>" + i.repo + "</code>";
      }).join(", ");
      steps.push("Ship the client apps: " + apps +
                 ". Each needs its own release, and users on older versions " +
                 "keep calling the old shape.");
      steps.push("Only once client adoption is high enough, remove the old " +
                 "shape. <span class=\"muted\">Usually months, not days.</span>");
    }
    if (!flat.length) {
      steps.push("Nothing else in the estate depends on this endpoint. " +
                 "<span class=\"muted\">Change it freely.</span>");
    }
    return steps;
  }

  function columns(target, levels) {
    var hit = {};
    [].concat.apply([], levels).forEach(function (item) { hit[item.repo] = item; });

    var services = [], clients = [];
    Object.keys(ESTATE).forEach(function (name) {
      if (name === target) return;
      (ESTATE[name].kind === "client" ? clients : services).push(name);
    });

    function node(name) {
      var info = ESTATE[name];
      var mark = hit[name];
      var classes = ["node"];
      if (name === target) classes.push("source");
      if (mark) classes.push("hit");
      if (info.kind === "client") classes.push("client");
      var meta = mark
        ? "affected · " + mark.by + " " + mark.c.toFixed(2) + " · " + mark.ev
        : (info.kind === "client" ? "client app" : info.stack);
      return '<div class="' + classes.join(" ") + '">' +
             '<span class="name">' + name + "</span>" +
             '<span class="meta">' + meta + "</span></div>";
    }

    return '<div class="column"><h4>Changing</h4>' + node(target) + "</div>" +
           '<div class="column"><h4>Services</h4>' +
           services.map(node).join("") + "</div>" +
           '<div class="column"><h4>Client apps</h4>' +
           clients.map(node).join("") + "</div>";
  }

  function render() {
    var endpoint = state.endpoint;
    var levels = affected(endpoint.repo, endpoint.path);
    var flat = [].concat.apply([], levels);
    var clients = flat.filter(function (i) { return i.kind === "client"; });

    var chips = ENDPOINTS.map(function (item, index) {
      var on = item === endpoint;
      return '<button class="chip" role="button" aria-pressed="' + on +
             '" data-index="' + index + '">' + item.label + "</button>";
    }).join("");

    var summary = flat.length
      ? flat.length + " repos affected" +
        (clients.length ? ", " + clients.length + " of them client apps" : "")
      : "nothing else depends on this";

    root.innerHTML =
      '<div class="demo-head">' +
        "<strong>estate impact " + endpoint.repo + " " + endpoint.path +
        "</strong><span>" + summary + "</span></div>" +
      '<div class="demo-body">' +
        '<div class="chips" role="group" aria-label="Choose an endpoint">' +
          chips + "</div>" +
        '<div class="estate">' + columns(endpoint.repo, levels) + "</div>" +
        '<div class="order"><h4>Ship in this order</h4><ol>' +
          landingOrder(endpoint.repo, levels).map(function (step) {
            return "<li>" + step + "</li>";
          }).join("") +
        "</ol></div>" +
        '<p class="demo-note">Every connection above cites the file and line ' +
        "that proves it. This is the real fixture estate from the test suite " +
        "— try the metrics endpoint to see what nothing-depends-on-it looks " +
        "like.</p>" +
      "</div>";

    // Reveal the steps in sequence, so the ordering reads as a consequence
    // rather than a list.
    var items = root.querySelectorAll(".order li");
    var reduce = window.matchMedia &&
                 window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    Array.prototype.forEach.call(items, function (item, index) {
      if (reduce) { item.classList.add("show"); return; }
      setTimeout(function () { item.classList.add("show"); }, 120 + index * 130);
    });
  }

  root.addEventListener("click", function (event) {
    var chip = event.target.closest && event.target.closest(".chip");
    if (!chip) return;
    state.endpoint = ENDPOINTS[parseInt(chip.getAttribute("data-index"), 10)];
    render();
  });

  render();
})();
