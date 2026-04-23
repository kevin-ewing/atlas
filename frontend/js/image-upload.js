/**
 * ImageUpload module — handles image upload flow via pre-signed S3 URLs.
 * Validates file type (JPEG, PNG, WebP) client-side.
 * Compresses images client-side before upload for space savings.
 * Shows upload progress and thumbnail previews.
 */
var ImageUpload = (function () {
  'use strict';

  var MAX_IMAGES = 10;
  var ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
  var ACCEPTED_EXTENSIONS = '.jpg,.jpeg,.png,.webp';

  // Compression settings
  var MAX_DIMENSION = 2048; // Max width or height after resize
  var JPEG_QUALITY = 0.82;  // JPEG output quality (0–1)

  var _watchId = null;
  var _currentCount = 0;
  var _containerEl = null;

  function init(containerId, watchId, existingCount) {
    _watchId = watchId;
    _currentCount = existingCount || 0;
    _containerEl = document.getElementById(containerId);
    if (!_containerEl) return;

    render();
  }

  function updateCount(count) {
    _currentCount = count;
    render();
  }

  function render() {
    if (!_containerEl) return;

    if (_currentCount >= MAX_IMAGES) {
      _containerEl.innerHTML = '<p style="font-size:0.875rem;color:var(--color-text-muted)">Maximum of ' + MAX_IMAGES + ' images reached.</p>';
      return;
    }

    var html = '';
    html += '<div class="image-upload-area" id="upload-drop-zone" role="button" tabindex="0" aria-label="Upload images">';
    html += '<p>Click or drag images here to upload</p>';
    html += '<p style="font-size:0.75rem;margin-top:0.25rem">JPEG, PNG, or WebP — any size (auto-compressed)</p>';
    html += '<input type="file" id="upload-file-input" accept="' + ACCEPTED_EXTENSIONS + '" multiple hidden aria-hidden="true">';
    html += '</div>';
    html += '<div id="upload-queue" class="upload-preview-list"></div>';

    _containerEl.innerHTML = html;

    bindEvents();
  }

  function bindEvents() {
    var dropZone = document.getElementById('upload-drop-zone');
    var fileInput = document.getElementById('upload-file-input');
    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', function () {
      fileInput.click();
    });

    dropZone.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
      }
    });

    // Drag and drop
    dropZone.addEventListener('dragover', function (e) {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', function () {
      dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', function (e) {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer && e.dataTransfer.files) {
        handleFiles(e.dataTransfer.files);
      }
    });

    fileInput.addEventListener('change', function () {
      if (fileInput.files && fileInput.files.length > 0) {
        handleFiles(fileInput.files);
        fileInput.value = ''; // Reset so same file can be selected again
      }
    });
  }

  function handleFiles(fileList) {
    var files = Array.prototype.slice.call(fileList);
    var remaining = MAX_IMAGES - _currentCount;

    if (files.length > remaining) {
      alert('You can upload up to ' + remaining + ' more image(s). Maximum is ' + MAX_IMAGES + '.');
      files = files.slice(0, remaining);
    }

    files.forEach(function (file) {
      validateAndUpload(file);
    });
  }

  function validateAndUpload(file) {
    // Validate type
    if (ACCEPTED_TYPES.indexOf(file.type) === -1) {
      alert('"' + file.name + '" is not a supported format. Please use JPEG, PNG, or WebP.');
      return;
    }

    // No size limit — we compress client-side before upload
    compressAndUpload(file);
  }

  /**
   * Compress an image file using a canvas, then upload the result.
   * Resizes to fit within MAX_DIMENSION and outputs as JPEG.
   */
  function compressAndUpload(file) {
    var queueEl = document.getElementById('upload-queue');
    if (!queueEl) return;

    // Create preview item
    var item = document.createElement('div');
    item.className = 'upload-preview-item';

    var previewImg = document.createElement('img');
    previewImg.alt = 'Uploading ' + file.name;
    item.appendChild(previewImg);

    // Progress indicator
    var progressDiv = document.createElement('div');
    progressDiv.className = 'upload-progress';
    progressDiv.innerHTML =
      '<div class="progress-bar"><div class="progress-bar-fill"></div></div>' +
      '<span class="upload-status">Compressing…</span>';
    item.appendChild(progressDiv);

    queueEl.appendChild(item);

    var fillBar = progressDiv.querySelector('.progress-bar-fill');
    var statusEl = progressDiv.querySelector('.upload-status');

    // Load image into an Image element
    var reader = new FileReader();
    reader.onload = function (e) {
      previewImg.src = e.target.result;

      var img = new Image();
      img.onload = function () {
        // Determine new dimensions
        var width = img.width;
        var height = img.height;

        if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
          if (width > height) {
            height = Math.round(height * (MAX_DIMENSION / width));
            width = MAX_DIMENSION;
          } else {
            width = Math.round(width * (MAX_DIMENSION / height));
            height = MAX_DIMENSION;
          }
        }

        // Draw to canvas
        var canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        var ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);

        // Convert to JPEG blob
        canvas.toBlob(function (blob) {
          if (!blob) {
            statusEl.textContent = 'Compression failed';
            statusEl.style.color = 'var(--color-loss)';
            return;
          }

          // Create a File-like object with the compressed blob
          var compressedFile = new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), {
            type: 'image/jpeg'
          });

          statusEl.textContent = 'Requesting upload URL…';
          uploadFile(compressedFile, item, fillBar, statusEl);
        }, 'image/jpeg', JPEG_QUALITY);
      };

      img.onerror = function () {
        statusEl.textContent = 'Failed to read image';
        statusEl.style.color = 'var(--color-loss)';
      };

      img.src = e.target.result;
    };

    reader.onerror = function () {
      statusEl.textContent = 'Failed to read file';
      statusEl.style.color = 'var(--color-loss)';
    };

    reader.readAsDataURL(file);
  }

  function uploadFile(file, item, fillBar, statusEl) {
    // Step 1: Request pre-signed URL
    Api.post('/watches/' + _watchId + '/images/upload-url', {
      filename: file.name,
      contentType: file.type
    })
    .then(function (data) {
      statusEl.textContent = 'Uploading…';

      // Step 2: Upload to S3
      return Api.uploadToS3(data.uploadUrl, file, function (progress) {
        var pct = Math.round(progress * 100);
        fillBar.style.width = pct + '%';
        statusEl.textContent = 'Uploading… ' + pct + '%';
      }).then(function () {
        return data;
      });
    })
    .then(function (data) {
      statusEl.textContent = 'Confirming…';
      fillBar.style.width = '100%';

      // Step 3: Confirm upload
      return Api.post('/watches/' + _watchId + '/images/' + data.imageId + '/confirm');
    })
    .then(function () {
      statusEl.textContent = 'Done';
      _currentCount++;

      // Remove progress after a moment
      setTimeout(function () {
        var progressDiv = item.querySelector('.upload-progress');
        if (progressDiv) progressDiv.remove();
        // Add remove button
        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-btn';
        removeBtn.setAttribute('aria-label', 'Remove image');
        removeBtn.textContent = '✕';
        removeBtn.addEventListener('click', function () {
          item.remove();
        });
        item.appendChild(removeBtn);
      }, 800);

      // Update drop zone if at limit
      if (_currentCount >= MAX_IMAGES) {
        render();
      }
    })
    .catch(function (err) {
      statusEl.textContent = 'Failed';
      statusEl.style.color = 'var(--color-loss)';
      fillBar.style.width = '0%';
      fillBar.style.background = 'var(--color-loss)';
    });
  }

  return {
    init: init,
    updateCount: updateCount
  };
})();
