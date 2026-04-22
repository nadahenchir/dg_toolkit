/* ============================================================
   rating.js — Post-engagement Rating page logic
   ============================================================ */

let assessmentId = null;
let recommendations = [];
let ratings = {}; // { rec_id: { was_implemented, rating, notes } }

/* ── Init ── */
window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(window.location.search);
  assessmentId = parseInt(params.get('assessment_id'));

  if (!assessmentId) { showError('No assessment ID provided.'); return; }

  try {
    const [assessment, data] = await Promise.all([
      apiFetch(`/assessments/${assessmentId}`),
      apiFetch(`/assessments/${assessmentId}/recommendations`),
    ]);

    document.getElementById('org-name').textContent = assessment.organization_name;

    recommendations = data.recommendations;

    // Pre-populate existing ratings
    recommendations.forEach(r => {
      if (r.was_implemented !== null) {
        ratings[r.recommendation_id] = {
          was_implemented: r.was_implemented,
          rating: r.implementation_rating,
          notes: '',
        };
      }
    });

    renderPage(data);

    document.getElementById('loading-screen').style.display = 'none';
    document.getElementById('rating-content').style.display = 'flex';

  } catch (err) {
    showError(err.message || 'Failed to load recommendations.');
  }
});

/* ── Render ── */
function renderPage(data) {
  const container = document.getElementById('domains-container');
  container.innerHTML = '';

  updateProgress();

  data.by_domain.forEach(domain => {
    const section = document.createElement('div');
    section.className = 'domain-section';
    section.innerHTML = `<div class="domain-section-title">${domain.domain_name}</div>`;

    domain.recommendations.forEach(rec => {
      section.appendChild(buildRecCard(rec));
    });

    container.appendChild(section);
  });
}

/* ── Build recommendation card ── */
function buildRecCard(rec) {
  const rid      = rec.recommendation_id;
  const existing = ratings[rid];
  const isRated  = existing !== undefined;

  const catClass = { 'Quick Win': 'cat-qw', 'Strategic': 'cat-st', 'Fill In': 'cat-fi' }[rec.action_category] || '';
  const impClass = { High: 'imp-h', Medium: 'imp-m', Low: 'imp-l' }[rec.impact] || '';
  const effClass = { High: 'eff-h', Medium: 'eff-m', Low: 'eff-l' }[rec.effort] || '';

  const card = document.createElement('div');
  card.className = `rec-card ${isRated ? 'rated' : ''}`;
  card.id = `rec-${rid}`;

  const yesActive = existing?.was_implemented === true  ? 'active' : '';
  const noActive  = existing?.was_implemented === false ? 'active' : '';
  const starVisible = existing?.was_implemented === true ? 'visible' : '';
  const notesVisible = existing?.was_implemented === true ? 'visible' : '';

  card.innerHTML = `
    <div class="rec-card-header">
      <div class="rec-card-main">
        <div class="rec-action-text">${rec.action_text}</div>
        <div class="rec-meta">
          <span class="rec-badge kpi">${rec.kpi_name}</span>
          <span class="rec-badge ${catClass}">${rec.action_category}</span>
          <span class="rec-badge ${impClass}">Impact: ${rec.impact}</span>
          <span class="rec-badge ${effClass}">Effort: ${rec.effort}</span>
        </div>
      </div>
      <div class="rec-level-info">L${rec.from_level} → L${rec.to_level}</div>
    </div>

    <div class="rec-rating-body">

      <div class="impl-toggle-row">
        <span class="impl-toggle-label">Was this implemented?</span>
        <div class="toggle-group">
          <button class="toggle-btn yes ${yesActive}" onclick="setImplemented(${rid}, true)">Yes</button>
          <button class="toggle-btn no ${noActive}"  onclick="setImplemented(${rid}, false)">No</button>
        </div>
      </div>

      <div class="star-rating-row ${starVisible}" id="stars-row-${rid}">
        <span class="star-label">How effective was it? (1 = poor, 5 = excellent)</span>
        <div class="stars" id="stars-${rid}">
          ${[1,2,3,4,5].map(i => `
            <span class="star ${existing?.rating >= i ? 'active' : ''}"
                  onclick="setRating(${rid}, ${i})"
                  onmouseover="hoverStars(${rid}, ${i})"
                  onmouseout="resetStars(${rid})">★</span>
          `).join('')}
        </div>
      </div>

      <div class="notes-row ${notesVisible}" id="notes-row-${rid}">
        <span class="notes-label">Implementation notes (optional)</span>
        <textarea class="notes-input" id="notes-${rid}"
                  placeholder="What worked well? Any challenges?">${existing?.notes || ''}</textarea>
      </div>

      <div class="save-row">
        <div class="saved-indicator ${isRated ? 'visible' : ''}" id="saved-${rid}">
          ✓ Saved
        </div>
        <button class="btn btn-primary" style="font-size:12px;padding:7px 16px"
                onclick="saveRating(${rid})">
          Save
        </button>
      </div>

    </div>
  `;

  return card;
}

/* ── Implemented toggle ── */
function setImplemented(recId, value) {
  if (!ratings[recId]) ratings[recId] = { was_implemented: null, rating: null, notes: '' };
  ratings[recId].was_implemented = value;

  // Update toggle UI
  const card = document.getElementById(`rec-${recId}`);
  card.querySelector('.toggle-btn.yes').classList.toggle('active', value === true);
  card.querySelector('.toggle-btn.no').classList.toggle('active',  value === false);

  // Show/hide stars and notes
  const starsRow = document.getElementById(`stars-row-${recId}`);
  const notesRow = document.getElementById(`notes-row-${recId}`);
  starsRow.classList.toggle('visible', value === true);
  notesRow.classList.toggle('visible', value === true);

  // Clear rating if switching to No
  if (!value) {
    ratings[recId].rating = null;
    resetStars(recId);
    document.querySelectorAll(`#stars-${recId} .star`).forEach(s => s.classList.remove('active'));
  }
}

/* ── Star rating ── */
function setRating(recId, value) {
  if (!ratings[recId]) ratings[recId] = { was_implemented: true, rating: null, notes: '' };
  ratings[recId].rating = value;
  updateStars(recId, value);
}

function hoverStars(recId, value) {
  document.querySelectorAll(`#stars-${recId} .star`).forEach((s, i) => {
    s.style.color = i < value ? 'var(--cyan)' : '';
  });
}

function resetStars(recId) {
  const current = ratings[recId]?.rating || 0;
  document.querySelectorAll(`#stars-${recId} .star`).forEach((s, i) => {
    s.style.color = '';
    s.classList.toggle('active', i < current);
  });
}

function updateStars(recId, value) {
  document.querySelectorAll(`#stars-${recId} .star`).forEach((s, i) => {
    s.classList.toggle('active', i < value);
  });
}

/* ── Save rating ── */
async function saveRating(recId) {
  const r = ratings[recId];
  if (!r || r.was_implemented === null) {
    toast('Please select Yes or No first.', 'error');
    return;
  }
  if (r.was_implemented && !r.rating) {
    toast('Please select a star rating.', 'error');
    return;
  }

  const notes = document.getElementById(`notes-${recId}`)?.value || '';

  try {
    await apiFetch(`/recommendations/${recId}/rate`, {
      method: 'POST',
      body: JSON.stringify({
        was_implemented:       r.was_implemented,
        implementation_rating: r.was_implemented ? r.rating : null,
        implementation_notes:  notes || null,
      }),
    });

    ratings[recId].notes = notes;

    // Mark card as rated
    const card = document.getElementById(`rec-${recId}`);
    card.classList.add('rated');
    document.getElementById(`saved-${recId}`).classList.add('visible');

    updateProgress();
    toast('Rating saved.', 'success');

  } catch (err) {
    toast(err.message || 'Failed to save rating.', 'error');
  }
}

/* ── Progress ── */
function updateProgress() {
  const total  = recommendations.length;
  const rated  = Object.keys(ratings).filter(id => ratings[id].was_implemented !== null).length;
  const pct    = total ? Math.round((rated / total) * 100) : 0;

  document.getElementById('progress-label').textContent  = `${rated} / ${total} rated`;
  document.getElementById('progress-pct').textContent    = pct + '%';
  document.getElementById('progress-fill').style.width   = pct + '%';

  if (rated === total && total > 0) {
    document.getElementById('done-banner').classList.add('visible');
  }
}

function showError(msg) {
  document.getElementById('loading-screen').innerHTML =
    `<p style="color:var(--pink);font-size:13px">${msg}</p>`;
}