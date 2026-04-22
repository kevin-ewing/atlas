/**
 * Auth module — login page logic, lockout display.
 */
var Auth = (function () {
  'use strict';

  var _lockoutTimer = null;

  function init() {
    var form = document.getElementById('login-form');
    if (form) {
      form.addEventListener('submit', handleLogin);
    }
  }

  function show() {
    clearLockoutTimer();
    resetForm();
  }

  function resetForm() {
    var form = document.getElementById('login-form');
    if (form) form.reset();
    clearFieldErrors();
    setFormError('');
    hideLockout();
  }

  function clearFieldErrors() {
    var usernameInput = document.getElementById('login-username');
    var passwordInput = document.getElementById('login-password');
    var usernameError = document.getElementById('login-username-error');
    var passwordError = document.getElementById('login-password-error');

    if (usernameInput) usernameInput.classList.remove('invalid');
    if (passwordInput) passwordInput.classList.remove('invalid');
    if (usernameError) usernameError.textContent = '';
    if (passwordError) passwordError.textContent = '';
  }

  function setFormError(msg) {
    var el = document.getElementById('login-error');
    if (el) el.textContent = msg || '';
  }

  function handleLogin(e) {
    e.preventDefault();
    clearFieldErrors();
    setFormError('');
    hideLockout();

    var username = document.getElementById('login-username').value.trim();
    var password = document.getElementById('login-password').value;

    // Inline validation
    var valid = true;
    if (!username) {
      showFieldError('login-username', 'Username is required');
      valid = false;
    }
    if (!password) {
      showFieldError('login-password', 'Password is required');
      valid = false;
    }
    if (!valid) return;

    var submitBtn = document.querySelector('#login-form button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    Api.post('/auth/login', { username: username, password: password })
      .then(function (data) {
        Api.setToken(data.token);
        App.navigateTo('/dashboard');
      })
      .catch(function (err) {
        if (submitBtn) submitBtn.disabled = false;

        if (err.data && err.data.error) {
          var error = err.data.error;

          if (error.code === 'ACCOUNT_LOCKED') {
            showLockout(error.details && error.details.remainingSeconds);
            return;
          }

          setFormError(error.message || 'Login failed');
          return;
        }

        setFormError('Unable to connect. Please try again.');
      });
  }

  function showFieldError(inputId, message) {
    var input = document.getElementById(inputId);
    var errorEl = document.getElementById(inputId + '-error');
    if (input) input.classList.add('invalid');
    if (errorEl) errorEl.textContent = message;
  }

  function showLockout(remainingSeconds) {
    var el = document.getElementById('login-lockout');
    var spanEl = document.getElementById('lockout-remaining');
    if (!el || !spanEl) return;

    el.hidden = false;
    updateLockoutDisplay(spanEl, remainingSeconds || 0);

    clearLockoutTimer();
    if (remainingSeconds > 0) {
      var remaining = remainingSeconds;
      _lockoutTimer = setInterval(function () {
        remaining--;
        if (remaining <= 0) {
          clearLockoutTimer();
          hideLockout();
          return;
        }
        updateLockoutDisplay(spanEl, remaining);
      }, 1000);
    }
  }

  function updateLockoutDisplay(el, seconds) {
    if (seconds <= 0) {
      el.textContent = 'a moment';
      return;
    }
    var mins = Math.floor(seconds / 60);
    var secs = seconds % 60;
    if (mins > 0) {
      el.textContent = mins + 'm ' + secs + 's';
    } else {
      el.textContent = secs + 's';
    }
  }

  function hideLockout() {
    var el = document.getElementById('login-lockout');
    if (el) el.hidden = true;
  }

  function clearLockoutTimer() {
    if (_lockoutTimer) {
      clearInterval(_lockoutTimer);
      _lockoutTimer = null;
    }
  }

  function logout() {
    Api.clearToken();
    App.navigateTo('/login');
  }

  return {
    init: init,
    show: show,
    logout: logout
  };
})();
