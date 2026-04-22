/**
 * WatchForm module — add/edit watch form with all attributes,
 * inline expense management, sale details, and image upload.
 */
var WatchForm = (function () {
  'use strict';

  var _watchId = null;
  var _expenses = [];
  var _sale = null;
  var _existingImages = [];

  var MOVEMENT_TYPES = ['automatic', 'manual', 'quartz'];
  var CONDITIONS = ['new', 'excellent', 'good', 'fair', 'poor'];
  var STATUSES = ['in_collection', 'for_sale', 'sold'];
  var FEATURES = [
    'chronograph', 'date', 'GMT', 'moon phase', 'tourbillon',
    'minute repeater', 'perpetual calendar', 'diving bezel',
    'power reserve indicator', 'alarm'
  ];

  function load(watchId) {
    _watchId = watchId;
    _expenses = [];
    _sale = null;
    _existingImages = [];

    var container = document.getElementById('watch-form-container');
    if (!container) return;

    if (watchId) {
      App.showLoading();
      Promise.all([
        Api.get('/watches/' + watchId),
        Api.get('/watches/' + watchId + '/expenses').catch(function () { return { expenses: [] }; }),
        Api.get('/watches/' + watchId + '/sale').catch(function () { return null; }),
        Api.get('/watches/' + watchId + '/images').catch(function () { return { images: [] }; })
      ]).then(function (results) {
        var watch = results[0];
        var expData = results[1];
        var saleData = results[2];
        var imgData = results[3];

        _expenses = expData.expenses || expData || [];
        _sale = (saleData && !saleData.error) ? saleData : null;
        _existingImages = imgData.images || imgData || [];

        renderForm(container, watch);
      }).catch(function () {
        container.innerHTML = '<p class="empty-state">Failed to load watch data.</p>';
      }).finally(function () {
        App.hideLoading();
      });
    } else {
      renderForm(container, null);
    }
  }

  function renderForm(container, watch) {
    var data = watch || {};
    var html = '';

    html += '<form id="watch-form" novalidate>';

    // ---- Watch Attributes ----
    html += '<fieldset><legend class="detail-section-title">Watch Details</legend>';

    html += '<div class="form-row">';
    html += textField('maker', 'Maker *', data.maker, true);
    html += textField('model', 'Model *', data.model, true);
    html += '</div>';

    html += '<div class="form-row">';
    html += textField('referenceNumber', 'Reference Number', data.referenceNumber);
    html += textField('serialNumber', 'Serial Number', data.serialNumber);
    html += '</div>';

    html += '<div class="form-row">';
    html += numberField('yearOfProduction', 'Year of Production', data.yearOfProduction);
    html += numberField('caseDiameterMm', 'Case Diameter (mm)', data.caseDiameterMm);
    html += '</div>';

    html += '<div class="form-row">';
    html += textField('caseMaterial', 'Case Material', data.caseMaterial);
    html += selectField('movementType', 'Movement Type', MOVEMENT_TYPES, data.movementType);
    html += '</div>';

    html += '<div class="form-row">';
    html += textField('dialColor', 'Dial Color', data.dialColor);
    html += textField('bandMaterial', 'Band Material', data.bandMaterial);
    html += '</div>';

    html += '<div class="form-row">';
    html += textField('bandColor', 'Band Color', data.bandColor);
    html += selectField('condition', 'Condition', CONDITIONS, data.condition);
    html += '</div>';

    html += '<div class="form-row">';
    html += boolField('boxIncluded', 'Box Included', data.boxIncluded);
    html += boolField('papersIncluded', 'Papers Included', data.papersIncluded);
    html += '</div>';

    html += '<div class="form-row">';
    html += textField('acquisitionDate', 'Acquisition Date', data.acquisitionDate ? data.acquisitionDate.substring(0, 10) : '', false, 'date');
    html += textField('acquisitionSource', 'Acquisition Source', data.acquisitionSource);
    html += '</div>';

    html += '<div class="form-row">';
    html += selectField('status', 'Status', STATUSES, data.status || 'in_collection');
    html += '</div>';

    // Features checkboxes
    html += '<div class="form-group">';
    html += '<label>Features</label>';
    html += '<div class="checkbox-group">';
    var selectedFeatures = data.features || [];
    FEATURES.forEach(function (f) {
      var checked = selectedFeatures.indexOf(f) !== -1 ? ' checked' : '';
      html += '<label><input type="checkbox" name="features" value="' + Utils.escapeHtml(f) + '"' + checked + '> ' + Utils.escapeHtml(f) + '</label>';
    });
    html += '</div></div>';

    // Notes
    html += '<div class="form-group">';
    html += '<label for="field-notes">Notes</label>';
    html += '<textarea id="field-notes" name="notes" rows="3">' + Utils.escapeHtml(data.notes || '') + '</textarea>';
    html += '</div>';

    html += '</fieldset>';

    // ---- Expenses Section ----
    html += '<hr class="section-divider">';
    html += '<fieldset><legend class="detail-section-title">Expenses</legend>';
    html += '<div id="expense-list" class="inline-expense-list"></div>';
    html += '<button type="button" id="btn-add-expense" class="btn btn-secondary btn-sm">+ Add Expense</button>';
    html += '</fieldset>';

    // ---- Sale Section ----
    html += '<hr class="section-divider">';
    html += '<fieldset><legend class="detail-section-title">Sale Details</legend>';
    html += '<div class="form-row">';
    html += numberField('salePriceCents', 'Sale Price ($)', _sale ? (_sale.salePriceCents / 100).toFixed(2) : '');
    html += textField('saleDate', 'Sale Date', _sale && _sale.saleDate ? _sale.saleDate.substring(0, 10) : '', false, 'date');
    html += '</div>';
    html += '<div class="form-row">';
    html += textField('buyerOrPlatform', 'Buyer / Platform', _sale ? _sale.buyerOrPlatform : '');
    html += textField('saleNotes', 'Sale Notes', _sale ? _sale.notes : '');
    html += '</div>';
    html += '</fieldset>';

    // ---- Images Section ----
    if (_watchId) {
      html += '<hr class="section-divider">';
      html += '<fieldset><legend class="detail-section-title">Images</legend>';
      html += '<div id="existing-images" class="upload-preview-list"></div>';
      html += '<div id="image-upload-container"></div>';
      html += '</fieldset>';
    }

    // ---- Form Error & Actions ----
    html += '<div id="watch-form-error" class="form-error" role="alert"></div>';
    html += '<div class="form-actions">';
    html += '<button type="submit" class="btn btn-primary">' + (_watchId ? 'Save Changes' : 'Create Watch') + '</button>';
    html += '<button type="button" class="btn btn-secondary" id="btn-cancel-form">Cancel</button>';
    if (_watchId) {
      html += '<button type="button" class="btn btn-danger" id="btn-delete-watch">Delete Watch</button>';
    }
    html += '</div>';

    html += '</form>';

    container.innerHTML = html;

    // Render expenses
    renderExpenses();

    // Render existing images
    if (_watchId) {
      renderExistingImages();
      ImageUpload.init('image-upload-container', _watchId, _existingImages.length);
    }

    // Bind events
    bindFormEvents();
  }

  // ---- Field Helpers ----

  function textField(name, label, value, required, type) {
    type = type || 'text';
    var req = required ? ' required aria-required="true"' : '';
    var reqMark = required ? ' *' : '';
    return '<div class="form-group">' +
      '<label for="field-' + name + '">' + Utils.escapeHtml(label) + '</label>' +
      '<input type="' + type + '" id="field-' + name + '" name="' + name + '" value="' + Utils.escapeHtml(value || '') + '"' + req + '>' +
      '<span class="field-error" id="error-' + name + '" role="alert"></span>' +
      '</div>';
  }

  function numberField(name, label, value) {
    return '<div class="form-group">' +
      '<label for="field-' + name + '">' + Utils.escapeHtml(label) + '</label>' +
      '<input type="number" id="field-' + name + '" name="' + name + '" value="' + Utils.escapeHtml(value != null ? String(value) : '') + '" step="any">' +
      '<span class="field-error" id="error-' + name + '" role="alert"></span>' +
      '</div>';
  }

  function selectField(name, label, options, selected) {
    var html = '<div class="form-group">';
    html += '<label for="field-' + name + '">' + Utils.escapeHtml(label) + '</label>';
    html += '<select id="field-' + name + '" name="' + name + '">';
    html += '<option value="">— Select —</option>';
    options.forEach(function (opt) {
      var sel = opt === selected ? ' selected' : '';
      var display = opt.replace(/_/g, ' ');
      html += '<option value="' + Utils.escapeHtml(opt) + '"' + sel + '>' + Utils.escapeHtml(display) + '</option>';
    });
    html += '</select>';
    html += '<span class="field-error" id="error-' + name + '" role="alert"></span>';
    html += '</div>';
    return html;
  }

  function boolField(name, label, value) {
    var html = '<div class="form-group">';
    html += '<label for="field-' + name + '">' + Utils.escapeHtml(label) + '</label>';
    html += '<select id="field-' + name + '" name="' + name + '">';
    html += '<option value="">— Select —</option>';
    html += '<option value="true"' + (value === true ? ' selected' : '') + '>Yes</option>';
    html += '<option value="false"' + (value === false ? ' selected' : '') + '>No</option>';
    html += '</select>';
    html += '</div>';
    return html;
  }

  // ---- Expense Management ----

  function renderExpenses() {
    var listEl = document.getElementById('expense-list');
    if (!listEl) return;

    listEl.innerHTML = '';
    _expenses.forEach(function (exp, index) {
      listEl.appendChild(createExpenseRow(exp, index));
    });
  }

  function createExpenseRow(exp, index) {
    var row = document.createElement('div');
    row.className = 'inline-expense-item';
    row.dataset.index = index;

    row.innerHTML =
      '<div class="form-group">' +
        '<label>Category *</label>' +
        '<input type="text" name="exp-category" value="' + Utils.escapeHtml(exp.category || '') + '" required aria-required="true">' +
        '<span class="field-error" role="alert"></span>' +
      '</div>' +
      '<div class="form-group">' +
        '<label>Amount ($) *</label>' +
        '<input type="number" name="exp-amount" value="' + (exp.amountCents != null ? (exp.amountCents / 100).toFixed(2) : '') + '" step="0.01" min="0.01" required aria-required="true">' +
        '<span class="field-error" role="alert"></span>' +
      '</div>' +
      '<div class="form-group">' +
        '<label>Date</label>' +
        '<input type="date" name="exp-date" value="' + Utils.escapeHtml(exp.expenseDate ? exp.expenseDate.substring(0, 10) : '') + '">' +
      '</div>' +
      '<div class="form-group">' +
        '<label>Description</label>' +
        '<input type="text" name="exp-description" value="' + Utils.escapeHtml(exp.description || '') + '">' +
      '</div>' +
      '<button type="button" class="btn btn-danger btn-sm exp-remove" aria-label="Remove expense">✕</button>';

    row.querySelector('.exp-remove').addEventListener('click', function () {
      _expenses.splice(index, 1);
      renderExpenses();
    });

    return row;
  }

  // ---- Existing Images ----

  function renderExistingImages() {
    var container = document.getElementById('existing-images');
    if (!container) return;

    container.innerHTML = '';
    _existingImages.forEach(function (img) {
      var item = document.createElement('div');
      item.className = 'upload-preview-item';
      var url = img.url || img.s3Url || '';
      item.innerHTML =
        '<img src="' + Utils.escapeHtml(url) + '" alt="Watch image">' +
        '<button type="button" class="remove-btn" aria-label="Remove image" data-image-id="' + Utils.escapeHtml(img.imageId) + '">✕</button>';

      item.querySelector('.remove-btn').addEventListener('click', function () {
        if (!confirm('Delete this image?')) return;
        Api.del('/watches/' + _watchId + '/images/' + img.imageId)
          .then(function () {
            _existingImages = _existingImages.filter(function (i) { return i.imageId !== img.imageId; });
            renderExistingImages();
            ImageUpload.updateCount(_existingImages.length);
          })
          .catch(function () {
            alert('Failed to delete image.');
          });
      });

      container.appendChild(item);
    });
  }

  // ---- Form Events ----

  function bindFormEvents() {
    var form = document.getElementById('watch-form');
    if (!form) return;

    form.addEventListener('submit', handleSubmit);

    var addExpBtn = document.getElementById('btn-add-expense');
    if (addExpBtn) {
      addExpBtn.addEventListener('click', function () {
        _expenses.push({ category: '', amountCents: null, expenseDate: '', description: '' });
        renderExpenses();
      });
    }

    var cancelBtn = document.getElementById('btn-cancel-form');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        App.navigateTo('/dashboard');
      });
    }

    var deleteBtn = document.getElementById('btn-delete-watch');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', function () {
        if (!confirm('Delete this watch and all associated data?')) return;
        App.showLoading();
        Api.del('/watches/' + _watchId)
          .then(function () {
            App.navigateTo('/dashboard');
          })
          .catch(function () {
            alert('Failed to delete watch.');
          })
          .finally(function () {
            App.hideLoading();
          });
      });
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    clearFormErrors();

    var form = document.getElementById('watch-form');
    if (!form) return;

    // Collect watch data
    var watchData = collectWatchData(form);

    // Validate required fields
    var errors = [];
    if (!watchData.maker || !watchData.maker.trim()) {
      showFieldError('maker', 'Maker is required');
      errors.push('maker');
    }
    if (!watchData.model || !watchData.model.trim()) {
      showFieldError('model', 'Model is required');
      errors.push('model');
    }

    // Validate expenses
    var expenseRows = document.querySelectorAll('.inline-expense-item');
    var collectedExpenses = collectExpenses(expenseRows, errors);

    if (errors.length > 0) return;

    // Collect sale data
    var saleData = collectSaleData(form);

    App.showLoading();

    var watchPromise;
    if (_watchId) {
      watchPromise = Api.put('/watches/' + _watchId, watchData);
    } else {
      watchPromise = Api.post('/watches', watchData);
    }

    watchPromise
      .then(function (savedWatch) {
        var wId = savedWatch.watchId || _watchId;
        return syncExpenses(wId, collectedExpenses)
          .then(function () { return syncSale(wId, saleData); })
          .then(function () { return wId; });
      })
      .then(function () {
        App.navigateTo('/dashboard');
      })
      .catch(function (err) {
        var msg = (err.data && err.data.error && err.data.error.message) || 'Failed to save watch.';
        setFormError(msg);
      })
      .finally(function () {
        App.hideLoading();
      });
  }

  function collectWatchData(form) {
    var data = {};
    var fields = ['maker', 'model', 'referenceNumber', 'serialNumber', 'caseMaterial',
      'dialColor', 'bandMaterial', 'bandColor', 'acquisitionSource', 'notes'];

    fields.forEach(function (f) {
      var el = form.querySelector('[name="' + f + '"]');
      if (el && el.value.trim()) data[f] = el.value.trim();
    });

    // Number fields
    var yearEl = form.querySelector('[name="yearOfProduction"]');
    if (yearEl && yearEl.value) data.yearOfProduction = parseInt(yearEl.value, 10);

    var diamEl = form.querySelector('[name="caseDiameterMm"]');
    if (diamEl && diamEl.value) data.caseDiameterMm = parseFloat(diamEl.value);

    // Select fields
    var selects = ['movementType', 'condition', 'status'];
    selects.forEach(function (f) {
      var el = form.querySelector('[name="' + f + '"]');
      if (el && el.value) data[f] = el.value;
    });

    // Boolean fields
    var bools = ['boxIncluded', 'papersIncluded'];
    bools.forEach(function (f) {
      var el = form.querySelector('[name="' + f + '"]');
      if (el && el.value !== '') data[f] = el.value === 'true';
    });

    // Date
    var dateEl = form.querySelector('[name="acquisitionDate"]');
    if (dateEl && dateEl.value) data.acquisitionDate = dateEl.value;

    // Features
    var featureEls = form.querySelectorAll('[name="features"]:checked');
    var features = [];
    for (var i = 0; i < featureEls.length; i++) {
      features.push(featureEls[i].value);
    }
    if (features.length > 0) data.features = features;

    // Notes textarea
    var notesEl = form.querySelector('[name="notes"]');
    if (notesEl && notesEl.value.trim()) data.notes = notesEl.value.trim();

    return data;
  }

  function collectExpenses(rows, errors) {
    var result = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var catEl = row.querySelector('[name="exp-category"]');
      var amtEl = row.querySelector('[name="exp-amount"]');
      var dateEl = row.querySelector('[name="exp-date"]');
      var descEl = row.querySelector('[name="exp-description"]');

      var cat = catEl ? catEl.value.trim() : '';
      var amt = amtEl ? amtEl.value : '';

      if (!cat) {
        if (catEl) catEl.classList.add('invalid');
        var errSpan = row.querySelectorAll('.field-error')[0];
        if (errSpan) errSpan.textContent = 'Category is required';
        errors.push('expense-category-' + i);
      }
      if (!amt || parseFloat(amt) <= 0) {
        if (amtEl) amtEl.classList.add('invalid');
        var errSpan2 = row.querySelectorAll('.field-error')[1];
        if (errSpan2) errSpan2.textContent = 'Valid amount is required';
        errors.push('expense-amount-' + i);
      }

      result.push({
        expenseId: _expenses[i] ? _expenses[i].expenseId : null,
        category: cat,
        amountCents: Math.round(parseFloat(amt) * 100) || 0,
        expenseDate: dateEl ? dateEl.value : '',
        description: descEl ? descEl.value.trim() : ''
      });
    }
    return result;
  }

  function collectSaleData(form) {
    var priceEl = form.querySelector('[name="salePriceCents"]');
    var dateEl = form.querySelector('[name="saleDate"]');
    var buyerEl = form.querySelector('[name="buyerOrPlatform"]');
    var notesEl = form.querySelector('[name="saleNotes"]');

    var price = priceEl ? priceEl.value : '';
    var date = dateEl ? dateEl.value : '';

    if (!price && !date) return null; // No sale data entered

    return {
      salePriceCents: Math.round(parseFloat(price) * 100) || 0,
      saleDate: date || '',
      buyerOrPlatform: buyerEl ? buyerEl.value.trim() : '',
      notes: notesEl ? notesEl.value.trim() : ''
    };
  }

  function syncExpenses(watchId, collectedExpenses) {
    // Determine which expenses to create, update, or delete
    var existingIds = _expenses.map(function (e) { return e.expenseId; }).filter(Boolean);
    var newIds = collectedExpenses.map(function (e) { return e.expenseId; }).filter(Boolean);

    // Delete removed expenses
    var toDelete = existingIds.filter(function (id) { return newIds.indexOf(id) === -1; });
    var deletePromises = toDelete.map(function (id) {
      return Api.del('/watches/' + watchId + '/expenses/' + id);
    });

    // Create or update
    var upsertPromises = collectedExpenses.map(function (exp) {
      var payload = {
        category: exp.category,
        amountCents: exp.amountCents,
        expenseDate: exp.expenseDate,
        description: exp.description
      };
      if (exp.expenseId) {
        return Api.put('/watches/' + watchId + '/expenses/' + exp.expenseId, payload);
      } else {
        return Api.post('/watches/' + watchId + '/expenses', payload);
      }
    });

    return Promise.all(deletePromises.concat(upsertPromises));
  }

  function syncSale(watchId, saleData) {
    if (!saleData) {
      // If there was an existing sale and user cleared it, delete
      if (_sale && _sale.salePriceCents != null) {
        return Api.del('/watches/' + watchId + '/sale');
      }
      return Promise.resolve();
    }

    if (_sale && _sale.salePriceCents != null) {
      return Api.put('/watches/' + watchId + '/sale', saleData);
    } else {
      return Api.post('/watches/' + watchId + '/sale', saleData);
    }
  }

  function showFieldError(name, message) {
    var input = document.getElementById('field-' + name);
    var errorEl = document.getElementById('error-' + name);
    if (input) input.classList.add('invalid');
    if (errorEl) errorEl.textContent = message;
  }

  function clearFormErrors() {
    var invalids = document.querySelectorAll('#watch-form .invalid');
    for (var i = 0; i < invalids.length; i++) {
      invalids[i].classList.remove('invalid');
    }
    var errors = document.querySelectorAll('#watch-form .field-error');
    for (var j = 0; j < errors.length; j++) {
      errors[j].textContent = '';
    }
    setFormError('');
  }

  function setFormError(msg) {
    var el = document.getElementById('watch-form-error');
    if (el) el.textContent = msg || '';
  }

  return {
    load: load
  };
})();
