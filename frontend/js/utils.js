/**
 * Utils module — formatting helpers for currency, dates, and P&L display.
 */
var Utils = (function () {
  'use strict';

  /**
   * Format integer cents as a dollar string, e.g. 15099 → "$150.99"
   */
  function formatCurrency(cents) {
    if (cents == null) return '$0.00';
    var dollars = (cents / 100).toFixed(2);
    // Add thousands separator
    var parts = dollars.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return '$' + parts.join('.');
  }

  /**
   * Format P&L value in cents with sign, e.g. 5000 → "+$50.00", -3000 → "-$30.00"
   */
  function formatPnl(cents) {
    if (cents == null || cents === 0) return '$0.00';
    var abs = Math.abs(cents);
    var formatted = formatCurrency(abs);
    if (cents > 0) return '+' + formatted;
    return '-' + formatted;
  }

  /**
   * Return CSS class for P&L coloring.
   */
  function pnlClass(cents) {
    if (cents == null || cents === 0) return 'pnl-breakeven';
    return cents > 0 ? 'pnl-profit' : 'pnl-loss';
  }

  /**
   * Format an ISO date string to a readable format, e.g. "2024-03-15" → "Mar 15, 2024"
   */
  function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      var d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) {
      return dateStr;
    }
  }

  /**
   * Escape HTML special characters to prevent XSS.
   */
  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Build a query string from an object of params.
   * Skips null/undefined/empty values.
   */
  function buildQueryString(params) {
    var parts = [];
    Object.keys(params).forEach(function (key) {
      var val = params[key];
      if (val == null || val === '') return;
      if (Array.isArray(val)) {
        val.forEach(function (v) {
          parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(v));
        });
      } else {
        parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(val));
      }
    });
    return parts.length > 0 ? '?' + parts.join('&') : '';
  }

  /**
   * Capitalize first letter of a string.
   */
  function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  /**
   * Format a status value for display, e.g. "in_collection" → "In Collection"
   */
  function formatStatus(status) {
    if (!status) return '';
    return status.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  return {
    formatCurrency: formatCurrency,
    formatPnl: formatPnl,
    pnlClass: pnlClass,
    formatDate: formatDate,
    escapeHtml: escapeHtml,
    buildQueryString: buildQueryString,
    capitalize: capitalize,
    formatStatus: formatStatus
  };
})();
