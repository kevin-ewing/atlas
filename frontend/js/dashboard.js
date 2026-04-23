/**
 * Dashboard module — watch list with accordion cards.
 * Shows summary cards with maker, model, thumbnail, and net P&L.
 * Expands on click to show full details.
 */
var Dashboard = (function () {
  'use strict';

  var _watches = [];
  var _detailCache = {}; // Cache for lazy-loaded watch details keyed by watchId
  var _masonryFrame = null;
  var _resizeBound = false;

  function load() {
    var listEl = document.getElementById('watch-list');
    var emptyEl = document.getElementById('watch-list-empty');
    if (!listEl) return;

    ensureMasonryResizeHandler();
    listEl.innerHTML = '';
    _detailCache = {};
    if (emptyEl) emptyEl.hidden = true;
    App.showLoading();

    Api.get('/watches')
      .then(function (data) {
        _watches = data.watches || data || [];
        render();
        // Lazy-load detail data for all watches in the background
        prefetchDetails();
      })
      .catch(function () {
        listEl.innerHTML = '<p class="empty-state">Failed to load watches.</p>';
      })
      .finally(function () {
        App.hideLoading();
      });
  }

  /** Prefetch detail data for every watch so expanding is instant. */
  function prefetchDetails() {
    _watches.forEach(function (watch) {
      if (_detailCache[watch.watchId]) return;
      Promise.all([
        Api.get('/watches/' + watch.watchId),
        Api.get('/watches/' + watch.watchId + '/expenses').catch(function () { return { expenses: [] }; }),
        Api.get('/watches/' + watch.watchId + '/sale').catch(function () { return null; }),
        Api.get('/watches/' + watch.watchId + '/images').catch(function () { return { images: [] }; })
      ]).then(function (results) {
        _detailCache[watch.watchId] = {
          fullWatch: results[0],
          expenses: results[1].expenses || results[1] || [],
          sale: (results[2] && !results[2].error) ? results[2] : null,
          images: results[3].images || results[3] || []
        };
      }).catch(function () {
        // Silently ignore — will fetch on demand when expanded
      });
    });
  }

  function render() {
    var listEl = document.getElementById('watch-list');
    var emptyEl = document.getElementById('watch-list-empty');
    if (!listEl) return;

    if (_watches.length === 0) {
      listEl.innerHTML = '';
      if (emptyEl) emptyEl.hidden = false;
      return;
    }

    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = '';

    _watches.forEach(function (watch) {
      var card = createCard(watch);
      listEl.appendChild(card);
    });

    scheduleMasonryLayout();
  }

  // Palette colors for placeholder icon backgrounds
  var _placeholderColors = [
    'rgba(120, 179, 214, 0.22)',  // sky
    'rgba(252, 203, 203, 0.35)',  // blush
    'rgba(79, 121, 105, 0.18)',   // forest
    'rgba(216, 105, 105, 0.18)',  // clay
    'rgba(222, 227, 226, 0.5)',   // paper
  ];

  function createCard(watch) {
    var card = document.createElement('div');
    card.className = 'watch-card';
    card.setAttribute('role', 'listitem');
    card.dataset.watchId = watch.watchId;

    // Summary row
    var summary = document.createElement('div');
    summary.className = 'watch-card-summary';
    summary.setAttribute('tabindex', '0');
    summary.setAttribute('role', 'button');
    summary.setAttribute('aria-expanded', 'false');

    // Thumbnail
    var thumbHtml = '';
    if (watch.thumbnailUrl) {
      thumbHtml = '<img class="watch-thumb" src="' + Utils.escapeHtml(watch.thumbnailUrl) + '" alt="' + Utils.escapeHtml(watch.maker + ' ' + watch.model) + '">';
    } else {
      // Pick a color from the palette based on the watch index
      var colorIndex = _watches.indexOf(watch) % _placeholderColors.length;
      var bgColor = _placeholderColors[colorIndex];
      thumbHtml = '<div class="watch-thumb-placeholder" aria-hidden="true" style="background:' + bgColor + '"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><polyline points="12 9 12 12 14 13"/><path d="M9 2h6"/><path d="M9 22h6"/><path d="M16.5 3.5l1 1"/><path d="M7.5 3.5l-1 1"/></svg></div>';
    }

    // P&L — only show dollar amount for sold watches; show status label otherwise
    var pnlHtml = '';
    var status = watch.status || 'in_collection';
    if (status === 'sold') {
      var pnlCents = watch.pnlCents || 0;
      var pnlClass = Utils.pnlClass(pnlCents);
      var pnlText = Utils.formatPnl(pnlCents);
      pnlHtml = '<span class="watch-card-pnl ' + pnlClass + '">' + pnlText + '</span>';
    } else {
      pnlHtml = '<span class="watch-card-pnl" style="color:var(--color-text-muted);font-size:0.8125rem">' + Utils.formatStatus(status) + '</span>';
    }

    summary.setAttribute('aria-label', watch.maker + ' ' + watch.model);

    summary.innerHTML =
      thumbHtml +
      '<div class="watch-card-info">' +
        '<div class="watch-card-maker">' + Utils.escapeHtml(watch.maker) + '</div>' +
        '<div class="watch-card-model">' + Utils.escapeHtml(watch.model) + '</div>' +
      '</div>' +
      pnlHtml +
      '<span class="watch-card-expand-icon" aria-hidden="true">▼</span>';

    summary.addEventListener('click', function () {
      toggleCard(card, watch);
    });
    summary.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleCard(card, watch);
      }
    });

    card.appendChild(summary);

    // Detail section (hidden by default)
    var detail = document.createElement('div');
    detail.className = 'watch-card-detail';
    card.appendChild(detail);

    return card;
  }

  function toggleCard(card, watch) {
    var isExpanded = card.classList.contains('expanded');
    var summaryEl = card.querySelector('.watch-card-summary');

    if (isExpanded) {
      card.classList.remove('expanded');
      if (summaryEl) summaryEl.setAttribute('aria-expanded', 'false');
      scheduleMasonryLayout();
    } else {
      collapseOtherCards(card);
      card.classList.add('expanded');
      if (summaryEl) summaryEl.setAttribute('aria-expanded', 'true');
      scheduleMasonryLayout();
      loadCardDetail(card, watch);
    }
  }

  function collapseOtherCards(activeCard) {
    var cards = document.querySelectorAll('#watch-list .watch-card.expanded');
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      if (card === activeCard) continue;

      card.classList.remove('expanded');
      var summaryEl = card.querySelector('.watch-card-summary');
      if (summaryEl) summaryEl.setAttribute('aria-expanded', 'false');
    }
  }

  function loadCardDetail(card, watch) {
    var detail = card.querySelector('.watch-card-detail');
    if (!detail) return;

    // Use cached data if available (from background prefetch)
    var cached = _detailCache[watch.watchId];
    if (cached) {
      renderDetail(detail, cached.fullWatch, cached.expenses, cached.sale, cached.images, watch.watchId);
      return;
    }

    detail.innerHTML = '<p class="empty-state">Loading…</p>';
    scheduleMasonryLayout();

    // Fetch full watch data, expenses, sale, and images in parallel
    Promise.all([
      Api.get('/watches/' + watch.watchId),
      Api.get('/watches/' + watch.watchId + '/expenses').catch(function () { return { expenses: [] }; }),
      Api.get('/watches/' + watch.watchId + '/sale').catch(function () { return null; }),
      Api.get('/watches/' + watch.watchId + '/images').catch(function () { return { images: [] }; })
    ]).then(function (results) {
      var fullWatch = results[0];
      var expensesData = results[1];
      var saleData = results[2];
      var imagesData = results[3];

      var expenses = expensesData.expenses || expensesData || [];
      var sale = saleData && saleData.error ? null : saleData;
      var images = imagesData.images || imagesData || [];

      // Cache for future use
      _detailCache[watch.watchId] = {
        fullWatch: fullWatch,
        expenses: expenses,
        sale: sale,
        images: images
      };

      renderDetail(detail, fullWatch, expenses, sale, images, watch.watchId);
    }).catch(function () {
      detail.innerHTML = '<p class="empty-state">Failed to load details.</p>';
      scheduleMasonryLayout();
    });
  }

  function renderDetail(container, watch, expenses, sale, images, watchId) {
    var html = '';

    // Single unified grid for all label/value pairs
    html += '<div class="detail-grid">';

    // Attributes section title
    html += '<div class="detail-section-title" style="grid-column:1/-1">Attributes</div>';
    html += detailRow('Reference', watch.referenceNumber);
    html += detailRow('Year', watch.yearOfProduction);
    html += detailRow('Case Material', watch.caseMaterial);
    html += detailRow('Case Diameter', watch.caseDiameterMm ? watch.caseDiameterMm + ' mm' : null);
    html += detailRow('Movement', Utils.capitalize(watch.movementType));
    html += detailRow('Dial Color', watch.dialColor);
    html += detailRow('Band Material', watch.bandMaterial);
    html += detailRow('Band Color', watch.bandColor);
    html += detailRow('Condition', Utils.capitalize(watch.condition));
    html += detailRow('Box Included', watch.boxIncluded != null ? (watch.boxIncluded ? 'Yes' : 'No') : null);
    html += detailRow('Papers Included', watch.papersIncluded != null ? (watch.papersIncluded ? 'Yes' : 'No') : null);
    html += detailRow('Serial Number', watch.serialNumber);
    html += detailRow('Acquisition Date', Utils.formatDate(watch.acquisitionDate));
    html += detailRow('Source', watch.acquisitionSource);
    html += detailRow('Purchase Price', watch.purchasePriceCents != null ? Utils.formatCurrency(watch.purchasePriceCents) : null);
    html += detailRow('Status', Utils.formatStatus(watch.status));
    if (watch.features && watch.features.length > 0) {
      html += detailRow('Features', watch.features.map(function (f) { return Utils.capitalize(f); }).join(', '));
    }
    if (watch.notes) {
      html += '<div class="detail-label" style="grid-column:1/-1;margin-top:0.5rem">Notes</div>';
      html += '<div class="detail-value" style="grid-column:1/-1">' + Utils.escapeHtml(watch.notes) + '</div>';
    }

    // Sale section — inline in the same grid
    if (sale && sale.salePriceCents != null) {
      html += '<div class="detail-section-title" style="grid-column:1/-1;margin-top:1rem">Sale</div>';
      html += detailRow('Sale Price', Utils.formatCurrency(sale.salePriceCents));
      html += detailRow('Sale Date', Utils.formatDate(sale.saleDate));
      html += detailRow('Buyer / Platform', sale.buyerOrPlatform);
      if (sale.notes) {
        html += detailRow('Notes', sale.notes);
      }
    }

    html += '</div>'; // close detail-grid

    // Expenses section — uses its own table layout
    if (expenses.length > 0) {
      html += '<div class="detail-section" style="margin-top:1.25rem">';
      html += '<div class="detail-section-title">Expenses</div>';
      html += '<table class="expense-table"><thead><tr>';
      html += '<th>Category</th><th>Description</th><th>Date</th><th>Amount</th>';
      html += '</tr></thead><tbody>';
      var totalExpenseCents = 0;
      expenses.forEach(function (exp) {
        totalExpenseCents += exp.amountCents || 0;
        html += '<tr>';
        html += '<td>' + Utils.escapeHtml(exp.category || '') + '</td>';
        html += '<td>' + Utils.escapeHtml(exp.description || '') + '</td>';
        html += '<td>' + Utils.formatDate(exp.expenseDate) + '</td>';
        html += '<td>' + Utils.formatCurrency(exp.amountCents) + '</td>';
        html += '</tr>';
      });
      html += '</tbody><tfoot><tr>';
      html += '<td colspan="3"><strong>Total</strong></td>';
      html += '<td><strong>' + Utils.formatCurrency(totalExpenseCents) + '</strong></td>';
      html += '</tr></tfoot></table>';
      html += '</div>';
    }

    // Images section — only if there are images
    if (images.length > 0) {
      html += '<div class="detail-section" style="margin-top:1.25rem">';
      html += '<div class="detail-section-title">Images</div>';
      html += '<div class="image-gallery">';
      images.forEach(function (img) {
        var url = img.url || img.s3Url || '';
        html += '<img src="' + Utils.escapeHtml(url) + '" alt="Watch image" loading="lazy">';
      });
      html += '</div>';
      html += '</div>';
    }

    // Actions
    html += '<div class="watch-card-actions">';
    html += '<a href="#/watches/' + watchId + '/edit" class="btn btn-secondary btn-sm">Edit</a>';
    html += '<button type="button" class="btn btn-danger btn-sm" data-delete-watch="' + watchId + '">Delete</button>';
    html += '</div>';

    container.innerHTML = html;

    // Bind delete button
    var deleteBtn = container.querySelector('[data-delete-watch]');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        handleDelete(watchId);
      });
    }

    scheduleMasonryLayout();
  }

  function ensureMasonryResizeHandler() {
    if (_resizeBound) return;
    _resizeBound = true;
    window.addEventListener('resize', scheduleMasonryLayout);
  }

  function scheduleMasonryLayout() {
    if (_masonryFrame !== null) {
      cancelAnimationFrame(_masonryFrame);
    }

    _masonryFrame = requestAnimationFrame(function () {
      _masonryFrame = null;
      relayoutMasonry();
    });
  }

  function relayoutMasonry() {
    var listEl = document.getElementById('watch-list');
    if (!listEl) return;

    var styles = window.getComputedStyle(listEl);
    var rowHeight = parseFloat(styles.getPropertyValue('grid-auto-rows'));
    var rowGap = parseFloat(styles.getPropertyValue('row-gap')) || parseFloat(styles.getPropertyValue('gap')) || 0;
    if (!rowHeight) return;

    var cards = listEl.querySelectorAll('.watch-card');
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      card.style.gridRowEnd = 'span 1';
      var span = Math.max(1, Math.ceil((card.getBoundingClientRect().height + rowGap) / (rowHeight + rowGap)));
      card.style.gridRowEnd = 'span ' + span;
    }
  }

  function detailRow(label, value) {
    if (value == null || value === '') return '';
    return '<span class="detail-label">' + Utils.escapeHtml(label) + '</span>' +
           '<span class="detail-value">' + Utils.escapeHtml(String(value)) + '</span>';
  }

  function handleDelete(watchId) {
    if (!confirm('Delete this watch and all associated data? This cannot be undone.')) return;

    App.showLoading();
    Api.del('/watches/' + watchId)
      .then(function () {
        load(); // Refresh list
      })
      .catch(function () {
        alert('Failed to delete watch.');
      })
      .finally(function () {
        App.hideLoading();
      });
  }

  return {
    load: load
  };
})();
