/**
 * Qumanity global UI helpers:
 *  - Language dropdown (persists choice via /api/set-language, then reloads).
 *  - Translation loading overlay (showTranslationLoader / hideTranslationLoader).
 *  - Top-right hamburger menu (open/close, outside-click + ESC to close).
 *
 * English is the default language for everyone. We never prompt the user to
 * pick a language on first visit — the dropdown in the hamburger menu is the
 * only way to switch, and it only lists the user's relevant languages
 * (state default, mother tongue, English) as rendered server-side.
 */
(function () {
  function showTranslationLoader() {
    var el = document.getElementById("qb-translation-loader");
    if (el) el.hidden = false;
  }

  function hideTranslationLoader() {
    var el = document.getElementById("qb-translation-loader");
    if (el) el.hidden = true;
  }

  // Expose globally so other scripts (e.g. dashboard.js) can reuse them.
  window.showTranslationLoader = showTranslationLoader;
  window.hideTranslationLoader = hideTranslationLoader;

  function notify(message, type) {
    if (typeof window.qbToast === "function") {
      window.qbToast(message, type || "error");
    } else {
      alert(message);
    }
  }

  function reloadForLanguage(lang) {
    // The server reads the new language from the session (set by
    // /api/set-language); we just need a fresh, uncached full-page load. Clear
    // any prior cache-busters so the URL never accumulates params, then bust
    // the cache once. `replace` keeps the back button clean.
    var u = new URL(window.location.href);
    u.searchParams.delete("_lang");
    u.searchParams.delete("_");
    u.searchParams.set("_", String(Date.now()));
    window.location.replace(u.toString());
  }

  function initLanguageDropdown() {
    var sel = document.getElementById("language-dropdown");
    if (!sel || sel.getAttribute("data-qb-lang-bound") === "1") return;
    sel.setAttribute("data-qb-lang-bound", "1");
    sel.addEventListener("change", function () {
      var lang = sel.value || "en";
      showTranslationLoader();
      fetch("/api/set-language", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ language: lang }),
      })
        .then(function () {
          reloadForLanguage(lang);
        })
        .catch(function () {
          hideTranslationLoader();
          reloadForLanguage(lang);
        });
    });
  }

  // Safety net: always clear the translation overlay once a page is shown
  // (covers normal loads and back/forward cache restores) so it can never get
  // stuck if a navigation is interrupted.
  window.addEventListener("pageshow", hideTranslationLoader);

  function initHamburgerMenu() {
    var btn = document.getElementById("qb-hamburger-btn");
    var menu = document.getElementById("qb-hamburger-menu");
    if (!btn || !menu || btn.getAttribute("data-qb-menu-bound") === "1") return;
    btn.setAttribute("data-qb-menu-bound", "1");

    function closeMenu() {
      menu.classList.remove("show");
      btn.setAttribute("aria-expanded", "false");
    }

    function openMenu() {
      menu.classList.add("show");
      btn.setAttribute("aria-expanded", "true");
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (menu.classList.contains("show")) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    // Close when clicking outside the menu.
    document.addEventListener("click", function (e) {
      if (!menu.classList.contains("show")) return;
      if (menu.contains(e.target) || btn.contains(e.target)) return;
      closeMenu();
    });

    // Close on Escape.
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.classList.contains("show")) {
        closeMenu();
        btn.focus();
      }
    });

    menu.addEventListener("click", function (e) {
      var item = e.target.closest("a[role='menuitem'], button[role='menuitem']");
      if (!item) return;
      if (item.id === "qb-admin-panel-open") {
        closeMenu();
        return;
      }
      closeMenu();
    });
  }

  function init() {
    initLanguageDropdown();
    initHamburgerMenu();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
