/**
 * App module — SPA router and initialization.
 * Uses hash-based routing (#/dashboard, #/watches/new, etc.).
 */
var App = (function () {
  'use strict';

  var _routes = [
    { pattern: /^\/dashboard$/, view: 'dashboard', handler: showDashboard },
    { pattern: /^\/watches\/new$/, view: 'watches-new', handler: showWatchFormNew },
    { pattern: /^\/watches\/([^/]+)\/edit$/, view: 'watches-edit', handler: showWatchFormEdit },
    { pattern: /^\/portfolio$/, view: 'portfolio', handler: showPortfolio }
  ];

  function init() {
    Auth.init();

    // Logout button
    var logoutBtn = document.getElementById('btn-logout');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', function () {
        Auth.logout();
      });
    }

    // Listen for hash changes
    window.addEventListener('hashchange', onRouteChange);

    // Initial route
    onRouteChange();
  }

  function onRouteChange() {
    var hash = window.location.hash || '';
    var path = hash.replace(/^#/, '') || '/dashboard';

    // If not authenticated, show login
    if (!Api.isAuthenticated()) {
      if (path !== '/login') {
        // Preserve intended destination (optional)
      }
      showLogin();
      return;
    }

    // If authenticated but on login page, redirect to dashboard
    if (path === '/login') {
      navigateTo('/dashboard');
      return;
    }

    // Match route
    var matched = false;
    for (var i = 0; i < _routes.length; i++) {
      var route = _routes[i];
      var match = path.match(route.pattern);
      if (match) {
        hideAllViews();
        showAppShell();
        updateActiveNav(route.view);
        route.handler(match);
        matched = true;
        break;
      }
    }

    if (!matched) {
      // Default to dashboard
      navigateTo('/dashboard');
    }
  }

  function navigateTo(path) {
    var nextHash = '#' + path;
    if (window.location.hash === nextHash) {
      onRouteChange();
      return;
    }
    window.location.hash = nextHash;
  }

  function showLogin() {
    hideAppShell();
    hideAllViews();
    var loginPage = document.getElementById('page-login');
    if (loginPage) loginPage.hidden = false;
    Auth.show();
  }

  function showAppShell() {
    var loginPage = document.getElementById('page-login');
    var appShell = document.getElementById('app-shell');
    if (loginPage) loginPage.hidden = true;
    if (appShell) appShell.hidden = false;
  }

  function hideAppShell() {
    var appShell = document.getElementById('app-shell');
    if (appShell) appShell.hidden = true;
  }

  function hideAllViews() {
    var views = document.querySelectorAll('.view');
    for (var i = 0; i < views.length; i++) {
      views[i].hidden = true;
    }
  }

  function updateActiveNav(routeKey) {
    var links = document.querySelectorAll('.nav-link');
    for (var i = 0; i < links.length; i++) {
      var link = links[i];
      if (link.getAttribute('data-route') === routeKey) {
        link.classList.add('active');
      } else {
        link.classList.remove('active');
      }
    }
  }

  function showDashboard() {
    var view = document.getElementById('view-dashboard');
    if (view) view.hidden = false;
    Dashboard.load();
  }

  function showWatchFormNew() {
    var view = document.getElementById('view-watch-form');
    var title = document.getElementById('watch-form-title');
    if (view) view.hidden = false;
    if (title) title.textContent = 'Add Watch';
    WatchForm.load(null);
  }

  function showWatchFormEdit(match) {
    var watchId = match[1];
    var view = document.getElementById('view-watch-form');
    var title = document.getElementById('watch-form-title');
    if (view) view.hidden = false;
    if (title) title.textContent = 'Edit Watch';
    WatchForm.load(watchId);
  }

  function showPortfolio() {
    var view = document.getElementById('view-portfolio');
    if (view) view.hidden = false;
    Portfolio.load();
  }

  function showLoading() {
    var el = document.getElementById('loading-overlay');
    if (el) {
      el.hidden = false;
      el.setAttribute('aria-hidden', 'false');
    }
  }

  function hideLoading() {
    var el = document.getElementById('loading-overlay');
    if (el) {
      el.hidden = true;
      el.setAttribute('aria-hidden', 'true');
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    navigateTo: navigateTo,
    showLoading: showLoading,
    hideLoading: hideLoading
  };
})();
