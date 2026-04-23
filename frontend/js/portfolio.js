/**
 * Portfolio module — portfolio summary view with filter and sort controls.
 * Shows total P&L, profitable/loss/unsold counts.
 * Provides filter and sort controls that reload the watch list.
 */
var Portfolio = (function () {
  'use strict';

  var MOVEMENT_TYPES = ['automatic', 'manual', 'quartz'];
  var CONDITIONS = ['new', 'excellent', 'good', 'fair', 'poor'];
  var STATUSES = ['in_collection', 'for_sale', 'sold'];
  var FEATURES = [
    'chronograph', 'date', 'day-date', 'GMT', 'moon phase', 'tourbillon',
    'minute repeater', 'perpetual calendar', 'annual calendar', 'diving bezel',
    'power reserve indicator', 'alarm', 'world timer', 'flyback chronograph',
    'split-seconds chronograph', 'regulator dial', 'skeleton dial',
    'small seconds', 'jumping hour', 'retrograde display',
    'equation of time', 'sunrise/sunset indicator', 'tide indicator',
    'dual time zone', 'big date', 'digital display',
    'tachymeter', 'telemeter', 'pulsometer',
    'luminous hands', 'luminous indices', 'super-luminova',
    'sapphire caseback', 'screw-down crown', 'helium escape valve',
    'rotating bezel', 'slide rule bezel', 'countdown bezel',
    'water resistant 100m+', 'water resistant 200m+', 'water resistant 300m+',
    'shock resistant', 'anti-magnetic',
    'COSC certified', 'METAS certified', 'Geneva seal',
    'hacking seconds', 'hand-wind capability', 'quick-set date',
    'micro-rotor', 'column wheel', 'vertical clutch',
    'enamel dial', 'guilloché dial', 'meteorite dial',
    'gem-set bezel', 'gem-set dial'
  ];
  var SORT_FIELDS = [
    { value: 'pnl', label: 'Profit / Loss' },
    { value: 'acquisitionDate', label: 'Acquisition Date' },
    { value: 'maker', label: 'Maker' },
    { value: 'yearOfProduction', label: 'Year' }
  ];

  function load() {
    var container = document.getElementById('portfolio-container');
    if (!container) return;

    container.innerHTML = '';
    App.showLoading();

    // Load summary and watches in parallel
    Promise.all([
      Api.get('/portfolio/summary'),
      Api.get('/watches')
    ]).then(function (results) {
      var summary = results[0];
      var watchData = results[1];
      var watches = watchData.watches || watchData || [];

      renderSummary(container, summary);
      renderControls(container, watches);
      renderWatchTable(container, watches);
    }).catch(function () {
      container.innerHTML = '<p class="empty-state">Failed to load portfolio data.</p>';
    }).finally(function () {
      App.hideLoading();
    });
  }

  function renderSummary(container, summary) {
    var totalPnl = summary.totalPnlCents || 0;
    var profitable = summary.profitableCount || 0;
    var lossCount = summary.lossCount || 0;
    var unsold = summary.unsoldCount || 0;

    var html = '<div class="portfolio-stats">';

    html += '<div class="stat-card">';
    html += '<div class="stat-value ' + Utils.pnlClass(totalPnl) + '">' + Utils.formatPnl(totalPnl) + '</div>';
    html += '<div class="stat-label">Total P&L</div>';
    html += '</div>';

    html += '<div class="stat-card">';
    html += '<div class="stat-value pnl-profit">' + profitable + '</div>';
    html += '<div class="stat-label">Profit</div>';
    html += '</div>';

    html += '<div class="stat-card">';
    html += '<div class="stat-value pnl-loss">' + lossCount + '</div>';
    html += '<div class="stat-label">Loss</div>';
    html += '</div>';

    html += '<div class="stat-card">';
    html += '<div class="stat-value">' + unsold + '</div>';
    html += '<div class="stat-label">Holding</div>';
    html += '</div>';

    html += '</div>';

    container.insertAdjacentHTML('beforeend', html);
  }

  function renderControls(container, watches) {
    // Extract unique makers for filter dropdown
    var makers = [];
    var caseMaterials = [];
    watches.forEach(function (w) {
      if (w.maker && makers.indexOf(w.maker) === -1) makers.push(w.maker);
      if (w.caseMaterial && caseMaterials.indexOf(w.caseMaterial) === -1) caseMaterials.push(w.caseMaterial);
    });
    makers.sort();
    caseMaterials.sort();

    var html = '<details class="controls-bar" id="portfolio-controls">';
    html += '<summary>Filters &amp; Sort</summary>';
    html += '<div class="controls-grid">';

    // Maker filter
    html += filterSelect('filter-maker', 'Maker', makers);

    // Status filter
    html += filterSelect('filter-status', 'Status', STATUSES.map(function (s) { return s; }), true);

    // Condition filter
    html += filterSelect('filter-condition', 'Condition', CONDITIONS);

    // Movement type filter
    html += filterSelect('filter-movementType', 'Movement Type', MOVEMENT_TYPES);

    // Case material filter
    html += filterSelect('filter-caseMaterial', 'Case Material', caseMaterials);

    // Year range
    html += '<div class="form-group">';
    html += '<label for="filter-yearMin">Year From</label>';
    html += '<input type="number" id="filter-yearMin" placeholder="e.g. 1960">';
    html += '</div>';

    html += '<div class="form-group">';
    html += '<label for="filter-yearMax">Year To</label>';
    html += '<input type="number" id="filter-yearMax" placeholder="e.g. 2024">';
    html += '</div>';

    // Features filter
    html += '<div class="form-group" style="grid-column:1/-1">';
    html += '<label>Features</label>';
    html += '<div class="checkbox-group">';
    FEATURES.forEach(function (f) {
      html += '<label><input type="checkbox" name="filter-features" value="' + Utils.escapeHtml(f) + '"> ' + Utils.escapeHtml(f) + '</label>';
    });
    html += '</div></div>';

    // Sort controls
    html += '<div class="form-group">';
    html += '<label for="sort-field">Sort By</label>';
    html += '<select id="sort-field">';
    SORT_FIELDS.forEach(function (sf) {
      var sel = sf.value === 'acquisitionDate' ? ' selected' : '';
      html += '<option value="' + sf.value + '"' + sel + '>' + Utils.escapeHtml(sf.label) + '</option>';
    });
    html += '</select></div>';

    html += '<div class="form-group">';
    html += '<label for="sort-direction">Direction</label>';
    html += '<select id="sort-direction">';
    html += '<option value="desc" selected>Descending</option>';
    html += '<option value="asc">Ascending</option>';
    html += '</select></div>';

    html += '</div>'; // controls-grid

    html += '<div class="controls-actions">';
    html += '<button type="button" id="btn-apply-filters" class="btn btn-primary btn-sm">Apply</button>';
    html += '<button type="button" id="btn-clear-filters" class="btn btn-secondary btn-sm">Clear</button>';
    html += '</div>';

    html += '</details>';

    container.insertAdjacentHTML('beforeend', html);

    // Bind filter events
    document.getElementById('btn-apply-filters').addEventListener('click', applyFilters);
    document.getElementById('btn-clear-filters').addEventListener('click', clearFilters);
  }

  function filterSelect(id, label, options, formatAsStatus) {
    var html = '<div class="form-group">';
    html += '<label for="' + id + '">' + Utils.escapeHtml(label) + '</label>';
    html += '<select id="' + id + '">';
    html += '<option value="">All</option>';
    options.forEach(function (opt) {
      var display = formatAsStatus ? Utils.formatStatus(opt) : Utils.capitalize(opt);
      html += '<option value="' + Utils.escapeHtml(opt) + '">' + Utils.escapeHtml(display) + '</option>';
    });
    html += '</select></div>';
    return html;
  }

  function applyFilters() {
    var params = {};

    var maker = getVal('filter-maker');
    if (maker) params.maker = maker;

    var status = getVal('filter-status');
    if (status) params.status = status;

    var condition = getVal('filter-condition');
    if (condition) params.condition = condition;

    var movementType = getVal('filter-movementType');
    if (movementType) params.movementType = movementType;

    var caseMaterial = getVal('filter-caseMaterial');
    if (caseMaterial) params.caseMaterial = caseMaterial;

    var yearMin = getVal('filter-yearMin');
    if (yearMin) params.yearMin = yearMin;

    var yearMax = getVal('filter-yearMax');
    if (yearMax) params.yearMax = yearMax;

    // Features
    var featureEls = document.querySelectorAll('[name="filter-features"]:checked');
    var features = [];
    for (var i = 0; i < featureEls.length; i++) {
      features.push(featureEls[i].value);
    }
    if (features.length > 0) params.features = features;

    // Sort
    var sortField = getVal('sort-field');
    if (sortField) params.sortBy = sortField;

    var sortDir = getVal('sort-direction');
    if (sortDir) params.sortDirection = sortDir;

    var qs = Utils.buildQueryString(params);

    App.showLoading();
    Api.get('/watches' + qs)
      .then(function (data) {
        var watches = data.watches || data || [];
        var tableContainer = document.getElementById('portfolio-watch-table');
        if (tableContainer) {
          tableContainer.remove();
        }
        var container = document.getElementById('portfolio-container');
        renderWatchTable(container, watches);
      })
      .catch(function () {
        alert('Failed to apply filters.');
      })
      .finally(function () {
        App.hideLoading();
      });
  }

  function clearFilters() {
    var selects = ['filter-maker', 'filter-status', 'filter-condition', 'filter-movementType', 'filter-caseMaterial'];
    selects.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = '';
    });

    var inputs = ['filter-yearMin', 'filter-yearMax'];
    inputs.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = '';
    });

    var featureEls = document.querySelectorAll('[name="filter-features"]');
    for (var i = 0; i < featureEls.length; i++) {
      featureEls[i].checked = false;
    }

    var sortField = document.getElementById('sort-field');
    if (sortField) sortField.value = 'acquisitionDate';

    var sortDir = document.getElementById('sort-direction');
    if (sortDir) sortDir.value = 'desc';

    applyFilters();
  }

  function getVal(id) {
    var el = document.getElementById(id);
    return el ? el.value : '';
  }

  function renderWatchTable(container, watches) {
    // Remove existing table if present
    var existing = document.getElementById('portfolio-watch-table');
    if (existing) existing.remove();

    var wrapper = document.createElement('div');
    wrapper.id = 'portfolio-watch-table';

    if (watches.length === 0) {
      wrapper.innerHTML = '<p class="empty-state">No watches match the current filters.</p>';
      container.appendChild(wrapper);
      return;
    }

    var html = '<table class="expense-table" style="margin-top:0">';
    html += '<thead><tr>';
    html += '<th>Maker</th><th>Model</th><th>Status</th><th>Year</th><th>P&L</th>';
    html += '</tr></thead><tbody>';

    watches.forEach(function (w) {
      var status = w.status || 'in_collection';
      var pnlCents = w.pnlCents || 0;
      var pnlHtml = '';
      if (status === 'sold') {
        var pnlClass = Utils.pnlClass(pnlCents);
        pnlHtml = '<td class="' + pnlClass + '">' + Utils.formatPnl(pnlCents) + '</td>';
      } else {
        pnlHtml = '<td style="color:var(--color-text-muted)">—</td>';
      }
      html += '<tr>';
      html += '<td>' + Utils.escapeHtml(w.maker) + '</td>';
      html += '<td><a href="#/watches/' + w.watchId + '/edit">' + Utils.escapeHtml(w.model) + '</a></td>';
      html += '<td>' + Utils.formatStatus(w.status) + '</td>';
      html += '<td>' + (w.yearOfProduction || '—') + '</td>';
      html += pnlHtml;
      html += '</tr>';
    });

    html += '</tbody></table>';
    html += '<p style="font-size:0.8125rem;color:var(--color-text-muted);margin-top:0.5rem">' + watches.length + ' watch(es)</p>';

    wrapper.innerHTML = html;
    container.appendChild(wrapper);
  }

  return {
    load: load
  };
})();
