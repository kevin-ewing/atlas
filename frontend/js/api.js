/**
 * API client — fetch wrapper with JWT Bearer token attachment.
 * All API calls go through this module.
 *
 * ── Configuring the API Base URL ──
 *
 * After deploying with `sam deploy`, the API Gateway endpoint URL is printed
 * in the stack outputs as "ApiEndpoint".  Set it in one of two ways:
 *
 *   1. Before the <script> tag that loads this file, add:
 *        <script>window.ATLAS_API_URL = "https://<api-id>.execute-api.<region>.amazonaws.com/prod";</script>
 *
 *   2. Or set it at runtime in the browser console:
 *        window.ATLAS_API_URL = "https://...";
 *
 * When running the frontend locally against a SAM local API (`sam local start-api`),
 * set the URL to "http://127.0.0.1:3000".
 *
 * If left empty, all API calls use relative paths (suitable when the frontend
 * is served from the same origin as the API, e.g. behind a reverse proxy).
 */
var Api = (function () {
  'use strict';

  var _token = null; // JWT stored in memory and sessionStorage

  var BASE_URL = window.ATLAS_API_URL || '';

  function setToken(token) {
    _token = token;
    try { sessionStorage.setItem('atlas_token', token); } catch (e) { /* ignore */ }
  }

  function getToken() {
    return _token;
  }

  function clearToken() {
    _token = null;
    try { sessionStorage.removeItem('atlas_token'); } catch (e) { /* ignore */ }
  }

  function isAuthenticated() {
    if (_token) return true;
    // Restore from sessionStorage on page refresh
    try {
      var stored = sessionStorage.getItem('atlas_token');
      if (stored) {
        _token = stored;
        return true;
      }
    } catch (e) { /* ignore */ }
    return false;
  }

  /**
   * Core fetch wrapper.
   * Attaches Authorization header when a token is present.
   * Redirects to login on 401 responses.
   */
  function request(method, path, body, options) {
    options = options || {};
    var url = BASE_URL + path;
    var headers = options.headers || {};
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';

    if (_token) {
      headers['Authorization'] = 'Bearer ' + _token;
    }

    var fetchOptions = {
      method: method,
      headers: headers
    };

    if (body && method !== 'GET') {
      fetchOptions.body = JSON.stringify(body);
    }

    return fetch(url, fetchOptions)
      .then(function (response) {
        if (response.status === 401) {
          clearToken();
          return Promise.reject(new Error('Unauthorized'));
        }
        return response;
      })
      .then(function (response) {
        var contentType = response.headers.get('content-type') || '';
        if (contentType.indexOf('application/json') !== -1) {
          return response.json().then(function (data) {
            if (!response.ok) {
              var err = new Error((data.error && data.error.message) || 'Request failed');
              err.status = response.status;
              err.data = data;
              return Promise.reject(err);
            }
            return data;
          });
        }
        if (!response.ok) {
          var err = new Error('Request failed');
          err.status = response.status;
          return Promise.reject(err);
        }
        return response;
      });
  }

  function get(path) {
    return request('GET', path);
  }

  function post(path, body) {
    return request('POST', path, body);
  }

  function put(path, body) {
    return request('PUT', path, body);
  }

  function del(path) {
    return request('DELETE', path);
  }

  /**
   * Upload a file directly to S3 using a pre-signed URL.
   * Does NOT attach JWT — the pre-signed URL provides auth.
   * Returns an XMLHttpRequest so callers can track upload progress.
   */
  function uploadToS3(presignedUrl, file, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open('PUT', presignedUrl, true);
      xhr.setRequestHeader('Content-Type', file.type);

      if (onProgress) {
        xhr.upload.addEventListener('progress', function (e) {
          if (e.lengthComputable) {
            onProgress(e.loaded / e.total);
          }
        });
      }

      xhr.addEventListener('load', function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
        } else {
          reject(new Error('Upload failed with status ' + xhr.status));
        }
      });

      xhr.addEventListener('error', function () {
        reject(new Error('Upload failed'));
      });

      xhr.send(file);
    });
  }

  return {
    setToken: setToken,
    getToken: getToken,
    clearToken: clearToken,
    isAuthenticated: isAuthenticated,
    get: get,
    post: post,
    put: put,
    del: del,
    uploadToS3: uploadToS3
  };
})();
