// Astronomy Concierge — storefront bridge script.
//
// This file is served by the concierge web app (http://localhost:8090) and is
// loaded INTO the Astronomy Shop storefront page (http://localhost:8080) via
// the frontend-proxy Envoy override (see
// stage/splunk-otel/frontend-proxy/envoy.tmpl.yaml). Because it runs on the
// storefront's OWN origin, it can read the real shopper session that the
// storefront keeps in localStorage (key "session", value {userId,currencyCode})
// — something a script on :8090 cannot do, since localStorage is per-origin.
//
// What it does:
//   1. Reconciles the storefront's localStorage shopper id with a shared,
//      port-agnostic `concierge_session` cookie on host `localhost`. Cookies on
//      `localhost` are sent to every port, so the concierge UI on :8090 can read
//      the same id and scope its cart calls to the same shopper. That makes the
//      cart shared across the storefront tab and the concierge tab.
//   2. Keeps polling briefly, because the storefront creates its localStorage
//      session lazily (after its bundles hydrate) — later than the tiny inline
//      bootstrap that the proxy also injects.
//
// Future: this is the natural place to mount the concierge as an embedded
// widget (e.g. an iframe pointing at this origin). A disabled stub is included
// below to show the intended extension point.
//
// No secrets are read or transmitted; the shopper id is a non-sensitive demo
// identifier (a UUID), the same value the storefront already exposes client-side.

(function () {
  "use strict";

  var COOKIE_NAME = "concierge_session";
  var STORE_KEY = "session";

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function setCookie(name, value) {
    // Host-only cookie on `localhost` (no Domain attribute) so it is shared
    // across ports (:8080 <-> :8090). SameSite=Lax is fine for top-level
    // navigation between the two tabs.
    document.cookie =
      name + "=" + encodeURIComponent(value) + "; path=/; SameSite=Lax";
  }

  function readLocalSession() {
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function writeLocalSession(session) {
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify(session));
    } catch (e) {
      /* ignore quota / disabled storage */
    }
  }

  // Reconcile the localStorage shopper id and the shared cookie. Returns the
  // resolved shopper id (or "").
  function reconcile() {
    var cookieId = getCookie(COOKIE_NAME);
    var session = readLocalSession();
    var localId = session && session.userId ? session.userId : "";

    if (localId && !cookieId) {
      // Storefront already has a shopper; publish it for the concierge.
      setCookie(COOKIE_NAME, localId);
      return localId;
    }
    if (cookieId && !localId) {
      // Concierge (or a prior storefront tab) established a shopper first; adopt
      // it so this storefront tab uses the same cart.
      writeLocalSession({
        userId: cookieId,
        currencyCode: (session && session.currencyCode) || "USD",
      });
      return cookieId;
    }
    if (cookieId && localId && cookieId !== localId) {
      // Both exist and differ: the visible storefront cart wins; re-point the
      // shared cookie so the concierge aligns to this shopper.
      setCookie(COOKIE_NAME, localId);
      return localId;
    }
    return cookieId || localId || "";
  }

  // The storefront writes its localStorage session lazily during hydration, so
  // reconcile a few times to catch a freshly-created id, then stop.
  var attempts = 0;
  var MAX_ATTEMPTS = 40; // ~20s at 500ms
  reconcile();
  var timer = window.setInterval(function () {
    attempts += 1;
    var resolved = reconcile();
    if (resolved || attempts >= MAX_ATTEMPTS) {
      window.clearInterval(timer);
    }
  }, 500);

  // --- Future widget mount (disabled) --------------------------------------
  // The same injection seam can embed the concierge directly into the shop UI.
  // Left disabled so this release only bridges the session. To enable, flip the
  // guard and adjust styling/origin as needed.
  //
  // function mountConciergeWidget(origin) {
  //   if (document.getElementById("concierge-widget-frame")) return;
  //   var frame = document.createElement("iframe");
  //   frame.id = "concierge-widget-frame";
  //   frame.src = origin + "/";
  //   frame.title = "Astronomy Concierge";
  //   frame.style.cssText =
  //     "position:fixed;bottom:16px;right:16px;width:380px;height:560px;" +
  //     "border:0;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.25);z-index:2147483647;";
  //   document.body.appendChild(frame);
  // }
  // mountConciergeWidget(window.__CONCIERGE_ORIGIN__ || "");
})();
