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

  // --- Embedded concierge modal ---------------------------------------------
  function deriveConciergeOrigin() {
    var configuredOrigin =
      typeof window.__CONCIERGE_ORIGIN__ === "string"
        ? window.__CONCIERGE_ORIGIN__.trim()
        : "";
    if (configuredOrigin) {
      return configuredOrigin.replace(/\/+$/, "");
    }

    var script =
      document.currentScript ||
      document.querySelector('script[src*="/embed/concierge-bridge.js"]');
    if (script && script.src) {
      try {
        return new URL(script.src, window.location.href).origin;
      } catch (e) {
        /* ignore parse errors */
      }
    }
    return "";
  }

  function ensureModalStyles() {
    if (document.getElementById("concierge-modal-styles")) return;
    var style = document.createElement("style");
    style.id = "concierge-modal-styles";
    style.textContent = [
      "#concierge-nav-link{display:inline-flex;align-items:center;justify-content:center;margin-left:40px;",
      "font-size:17px;font-weight:700;line-height:1;text-decoration:none;border:0;cursor:pointer;padding:0;white-space:nowrap;",
      "background:linear-gradient(to right,#FF6B6B,#FFA726);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;transition:filter .15s ease;}",
      "#concierge-nav-link:hover,#concierge-nav-link:focus-visible{filter:brightness(1.12) saturate(1.1);outline:none;}",
      "#concierge-modal-overlay{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;",
      "background:rgba(17,17,23,.5);z-index:2147483646;padding:20px;opacity:0;pointer-events:none;transition:opacity .2s ease;}",
      "#concierge-modal-overlay.concierge-open{opacity:1;pointer-events:auto;}",
      "#concierge-modal-panel{position:relative;background:#ffffff;border-radius:12px;width:min(960px,90vw);height:min(800px,85vh);",
      "box-shadow:0 20px 60px rgba(0,0,0,.35);overflow:hidden;transform:translateY(12px) scale(.98);transition:transform .2s ease;}",
      "#concierge-modal-overlay.concierge-open #concierge-modal-panel{transform:translateY(0) scale(1);}",
      "#concierge-modal-close{position:absolute;top:10px;right:10px;z-index:2;border:0;border-radius:999px;width:32px;height:32px;",
      "cursor:pointer;background:rgba(255,255,255,.95);color:#28272b;font-size:22px;line-height:1;display:flex;align-items:center;justify-content:center;}",
      "#concierge-modal-close:hover{background:#f4f4f7;}",
      "#concierge-widget-frame{width:100%;height:100%;border:0;background:#fff;display:block;}"
    ].join("");
    document.head.appendChild(style);
  }

  function requestStorefrontCartRefresh() {
    // The storefront cart badge is sourced from react-query cache; a synthetic
    // focus/visibility tick prompts stale cart queries to refetch immediately.
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(
      new CustomEvent("astronomy_concierge:cart_mutated", {
        detail: { source: "astronomy-concierge" },
      })
    );
  }

  function ensureNavLink(onOpen) {
    var currencySelect = document.querySelector(
      'select[data-cy="currency-switcher"]'
    );
    if (!currencySelect) return;

    var currencyContainer = currencySelect.closest("div");
    if (!currencyContainer || !currencyContainer.parentNode) return;

    var existingLink = document.getElementById("concierge-nav-link");
    if (existingLink && existingLink.parentNode === currencyContainer.parentNode) {
      if (existingLink.nextSibling !== currencyContainer) {
        currencyContainer.parentNode.insertBefore(existingLink, currencyContainer);
      }
      return;
    }

    if (existingLink && existingLink.parentNode) {
      existingLink.parentNode.removeChild(existingLink);
    }

    var link = document.createElement("button");
    link.id = "concierge-nav-link";
    link.type = "button";
    link.textContent = "AI Astronomy Concierge";
    link.setAttribute("aria-haspopup", "dialog");
    link.setAttribute("aria-controls", "concierge-modal-overlay");
    link.addEventListener("click", onOpen);
    currencyContainer.parentNode.insertBefore(link, currencyContainer);
  }

  function mountConciergeWidget(origin) {
    if (!origin) return;
    ensureModalStyles();

    var overlay = document.getElementById("concierge-modal-overlay");
    var panel;
    var frame;
    var closeButton;
    var keyHandlerAttached = false;
    var messageHandlerAttached = false;

    function onMessage(event) {
      if (!origin || event.origin !== origin) return;
      if (!frame || event.source !== frame.contentWindow) return;
      var data = event.data;
      if (
        !data ||
        typeof data !== "object" ||
        data.type !== "astronomy_concierge.cart_mutated"
      ) {
        return;
      }
      requestStorefrontCartRefresh();
    }

    function closeModal() {
      if (!overlay) return;
      overlay.classList.remove("concierge-open");
      document.body.style.overflow = "";
      var navLink = document.getElementById("concierge-nav-link");
      if (navLink) navLink.focus();
    }

    function onKeyDown(event) {
      if (event.key === "Escape") {
        closeModal();
      }
    }

    function openModal() {
      if (!overlay) return;
      if (!frame.src) {
        try {
          var frameUrl = new URL("/", origin);
          frameUrl.searchParams.set("parent_origin", window.location.origin);
          frame.src = frameUrl.toString();
        } catch (e) {
          frame.src = origin + "/";
        }
      }
      overlay.classList.add("concierge-open");
      document.body.style.overflow = "hidden";
      if (!messageHandlerAttached) {
        window.addEventListener("message", onMessage);
        messageHandlerAttached = true;
      }
      if (!keyHandlerAttached) {
        document.addEventListener("keydown", onKeyDown);
        keyHandlerAttached = true;
      }
      window.setTimeout(function () {
        if (closeButton) closeButton.focus();
      }, 0);
    }

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "concierge-modal-overlay";
      overlay.setAttribute("role", "dialog");
      overlay.setAttribute("aria-modal", "true");
      overlay.setAttribute("aria-label", "AI Astronomy Concierge");

      panel = document.createElement("div");
      panel.id = "concierge-modal-panel";

      closeButton = document.createElement("button");
      closeButton.id = "concierge-modal-close";
      closeButton.type = "button";
      closeButton.setAttribute("aria-label", "Close AI Astronomy Concierge");
      closeButton.textContent = "×";
      closeButton.addEventListener("click", closeModal);

      frame = document.createElement("iframe");
      frame.id = "concierge-widget-frame";
      frame.title = "AI Astronomy Concierge";
      frame.loading = "eager";

      panel.appendChild(closeButton);
      panel.appendChild(frame);
      overlay.appendChild(panel);
      document.body.appendChild(overlay);

      overlay.addEventListener("click", function (event) {
        if (event.target === overlay) {
          closeModal();
        }
      });

      panel.addEventListener("click", function (event) {
        event.stopPropagation();
      });
    } else {
      panel = document.getElementById("concierge-modal-panel");
      frame = document.getElementById("concierge-widget-frame");
      closeButton = document.getElementById("concierge-modal-close");
    }

    ensureNavLink(openModal);

    var observer = new MutationObserver(function () {
      ensureNavLink(openModal);
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  mountConciergeWidget(deriveConciergeOrigin());
})();
