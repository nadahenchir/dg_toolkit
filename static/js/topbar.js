// topbar.js — shared across all authenticated pages

// Active nav link
(function () {
  const page = '/' + (window.location.pathname.split('/')[1] || '');
  document.querySelectorAll('.topbar-nav-link').forEach(link => {
    if (link.getAttribute('href') === page) link.classList.add('active');
  });
})();

// User name + session guard
(async function loadTopbarSession() {
  try {
    const res = await fetch('/api/auth/session');
    if (!res.ok) { window.location.href = '/login'; return; }
    const data = await res.json();
    const el = document.getElementById('topbar-user-name');
    if (el) el.textContent = data.consultant_name;
  } catch (_) {
    window.location.href = '/login';
  }
})();

async function handleLogout() {
  try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (_) {}
  window.location.href = '/login';
}

// Search
let _searchTimer = null;

function handleSearch(val) {
  clearTimeout(_searchTimer);
  const q = val.trim();
  if (!q) { closeSearchDropdown(); return; }
  _searchTimer = setTimeout(() => _doSearch(q), 280);
}

async function _doSearch(q) {
  try {
    const res  = await fetch(`/api/assessments/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    _renderSearch(data);
  } catch (_) {
    closeSearchDropdown();
  }
}

function _renderSearch(results) {
  const dropdown = document.getElementById('search-dropdown');
  if (!results.length) {
    dropdown.innerHTML = '<div class="search-no-results">No assessments found</div>';
    openSearchDropdown();
    return;
  }
  dropdown.innerHTML = results.map(r => {
    const status = r.status || 'draft';
    const date   = r.created_at
      ? new Date(r.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
      : '';
    const target = status === 'complete'
      ? `/results?assessment_id=${r.id}`
      : `/questionnaire?assessment_id=${r.id}`;
    return `<a class="search-result-item" href="${target}">
      <div>
        <div class="search-result-name">${r.organization_name}</div>
        <div class="search-result-meta">${r.consultant_name} &middot; ${date}</div>
      </div>
      <span class="search-result-status ${status}">${status.replace('_', ' ')}</span>
    </a>`;
  }).join('');
  openSearchDropdown();
}

function openSearchDropdown() {
  const el = document.getElementById('search-dropdown');
  if (el) el.classList.add('open');
}

function closeSearchDropdown() {
  setTimeout(() => {
    const el = document.getElementById('search-dropdown');
    if (el) el.classList.remove('open');
  }, 180);
}