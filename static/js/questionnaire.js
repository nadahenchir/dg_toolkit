/* ============================================================
   questionnaire.js — Questionnaire page logic
   ============================================================ */

const OPTION_KEYS = ['Fully', 'Mostly', 'Partially', 'Slightly', 'Not'];
const OPTION_LEVELS = { Fully: 'L5', Mostly: 'L4', Partially: 'L3', Slightly: 'L2', Not: 'L1' };

let assessmentId   = null;
let questionnaire  = [];       // full nested structure from API
let pendingSaves   = {};       // { kpi_id: { question_id: selected_option } }
let activeDomainId = null;
let saveTimer      = null;

/* ── Init ── */
window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(window.location.search);
  assessmentId = parseInt(params.get('assessment_id'));

  if (!assessmentId) {
    showError('No assessment ID provided.');
    return;
  }

  try {
    // Load assessment info for sidebar header
    const assessment = await apiFetch(`/assessments/${assessmentId}`);
    document.getElementById('sidebar-org').textContent = assessment.organization_name;

    // Load full questionnaire structure
    questionnaire = await apiFetch(`/assessments/${assessmentId}/questionnaire`);

    renderSidebar();
    // Activate first incomplete domain, or first domain if all complete
    const firstIncomplete = questionnaire.find(d => !isDomainComplete(d));
    activateDomain((firstIncomplete || questionnaire[0]).domain_id);

    document.getElementById('loading-screen').style.display = 'none';
    document.getElementById('q-content').style.display = 'flex';

  } catch (err) {
    showError(err.message || 'Failed to load questionnaire.');
  }
});

/* ── Sidebar ── */
function renderSidebar() {
  const list = document.getElementById('domain-list');
  list.innerHTML = '';

  const totalKpis     = questionnaire.reduce((s, d) => s + d.kpis.length, 0);
  const completedKpis = questionnaire.reduce((s, d) => s + d.kpis.filter(isKpiComplete).length, 0);

  // Overall progress
  const pct = totalKpis ? Math.round((completedKpis / totalKpis) * 100) : 0;
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-pct').textContent  = pct + '%';
  document.getElementById('progress-label-text').textContent = `${completedKpis} / ${totalKpis} KPIs`;

  questionnaire.forEach(domain => {
    const completedInDomain = domain.kpis.filter(isKpiComplete).length;
    const total             = domain.kpis.length;
    const isComplete        = completedInDomain === total;
    const isPartial         = completedInDomain > 0 && !isComplete;
    const isActive          = domain.domain_id === activeDomainId;

    const item = document.createElement('div');
    item.className = `domain-item ${isComplete ? 'complete' : ''} ${isPartial ? 'partial' : ''} ${isActive ? 'active' : ''}`;
    item.id = `domain-item-${domain.domain_id}`;
    item.onclick = () => activateDomain(domain.domain_id);
    item.innerHTML = `
      <div class="domain-status-dot"></div>
      <div class="domain-item-name">${domain.domain_name}</div>
      <div class="domain-item-count">${completedInDomain}/${total}</div>
    `;
    list.appendChild(item);
  });
}

/* ── Domain activation ── */
function activateDomain(domainId) {
  activeDomainId = domainId;
  const domain = questionnaire.find(d => d.domain_id === domainId);
  if (!domain) return;

  // Update sidebar active state
  document.querySelectorAll('.domain-item').forEach(el => el.classList.remove('active'));
  const item = document.getElementById(`domain-item-${domainId}`);
  if (item) item.classList.add('active');

  // Update topbar
  document.getElementById('q-domain-label').textContent = domain.domain_name;
  document.getElementById('q-domain-badge').textContent = `D${String(domainId).padStart(2, '0')}`;

  // Update bottom nav
  const idx     = questionnaire.findIndex(d => d.domain_id === domainId);
  const hasPrev = idx > 0;
  const hasNext = idx < questionnaire.length - 1;
  document.getElementById('nav-prev').style.visibility = hasPrev ? 'visible' : 'hidden';
  document.getElementById('nav-next').style.visibility = hasNext ? 'visible' : 'hidden';
  document.getElementById('nav-info').innerHTML =
    `Domain <strong>${idx + 1}</strong> of <strong>${questionnaire.length}</strong>`;

  // Render KPIs
  renderKpis(domain);
}

/* ── KPI rendering ── */
function renderKpis(domain) {
  const area = document.getElementById('kpi-area');
  area.innerHTML = `
    <div class="domain-heading">
      <h2>${domain.domain_name}</h2>
      <p>${domain.kpis.length} KPIs · ${domain.kpis.filter(isKpiComplete).length} completed</p>
    </div>
  `;

  domain.kpis.forEach((kpi, idx) => {
    const card = buildKpiCard(kpi, idx);
    area.appendChild(card);
  });

  // Auto-open first incomplete KPI
  const firstIncomplete = domain.kpis.find(k => !isKpiComplete(k));
  if (firstIncomplete) {
    const card = document.getElementById(`kpi-card-${firstIncomplete.kpi_id}`);
    if (card) openKpi(card, firstIncomplete.kpi_id);
  }

  area.scrollTop = 0;
}

function buildKpiCard(kpi, idx) {
  const complete = isKpiComplete(kpi);

  const card = document.createElement('div');
  card.className = `kpi-card ${complete ? 'complete' : ''}`;
  card.id = `kpi-card-${kpi.kpi_id}`;
  card.style.animationDelay = `${idx * 0.04}s`;

  card.innerHTML = `
    <div class="kpi-card-header" onclick="toggleKpi(${kpi.kpi_id})">
      <div class="kpi-number">KPI ${String(idx + 1).padStart(2, '0')}</div>
      <div class="kpi-title">${kpi.kpi_name}</div>
      <div class="kpi-check">${complete ? '✓' : ''}</div>
      <svg class="kpi-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <div class="kpi-body">
      ${buildQuestionsHtml(kpi)}
      <div class="kpi-footer">
        <button class="btn btn-primary" style="font-size:12px;padding:8px 18px"
                onclick="saveKpi(${kpi.kpi_id})">
          Save & Continue
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2 6h8M6 2l4 4-4 4" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </div>
  `;

  return card;
}

function buildQuestionsHtml(kpi) {
  const isInverted = kpi.is_inverted;
  const gateOption = isInverted ? 'Fully' : 'Not';

  // Determine gate state from existing answers
  const q1 = kpi.questions.find(q => q.question_number === 1);
  let gateTriggered = false;
  if (q1) {
    gateTriggered = (q1.selected_option === gateOption) || (q1.is_na === true);
  }

  let html = '';
  kpi.questions.forEach(q => {
    const isGated  = q.question_number > 1 && gateTriggered;
    const isHidden = q.is_hidden === true;

    html += `
      <div class="question-block ${isHidden ? 'hidden-q' : ''} ${isGated ? 'gated' : ''}"
           id="q-block-${q.id}" data-kpi="${kpi.kpi_id}" data-qnum="${q.question_number}">
        <div class="question-header">
          <div class="q-num-badge">Q${q.question_number}</div>
          <div class="question-text">${q.question_text}</div>
        </div>
        <div class="options-list">
          ${buildOptionsHtml(q, kpi.kpi_id, isInverted)}
        </div>
        ${q.question_number === 1 ? `<div class="gate-notice" id="gate-notice-${kpi.kpi_id}">
          Q2–Q4 are hidden because this practice is not applicable or not present.
        </div>` : ''}
      </div>
    `;
  });

  // Show gate notice if already triggered
  if (gateTriggered) {
    html = html.replace(
      `id="gate-notice-${kpi.kpi_id}"`,
      `id="gate-notice-${kpi.kpi_id}" class="gate-notice visible"`
    );
  }

  return html;
}

function buildOptionsHtml(q, kpiId, isInverted) {
  let html = '';
  const current = q.is_na ? 'N.A' : q.selected_option;

  OPTION_KEYS.forEach((key, i) => {
    const optText = [
      q.opt_fully_text,
      q.opt_mostly_text,
      q.opt_partially_text,
      q.opt_slightly_text,
      q.opt_not_text,
    ][i];
    const isSelected = current === key;
    html += `
      <div class="option-item ${isSelected ? 'selected' : ''}"
           id="opt-${q.id}-${key}"
           onclick="selectOption(${kpiId}, ${q.id}, '${key}', ${q.question_number}, ${q.is_gatekeeper}, ${isInverted})">
        <div class="option-radio"></div>
        <div class="option-label">${optText || key}</div>
        <div class="option-level">${OPTION_LEVELS[key]}</div>
      </div>
    `;
  });

  // N/A option if allowed
  if (q.allows_na) {
    const isNaSelected = current === 'N.A';
    html += `
      <div class="option-item ${isNaSelected ? 'selected-na' : ''}"
           id="opt-${q.id}-NA"
           onclick="selectOption(${kpiId}, ${q.id}, 'N.A', ${q.question_number}, ${q.is_gatekeeper}, ${isInverted})">
        <div class="option-radio"></div>
        <div class="option-label">Not Applicable — this domain/practice does not apply to this organization</div>
        <div class="option-level" style="color:var(--muted)">N/A</div>
      </div>
    `;
  }

  return html;
}

/* ── Option selection ── */
function selectOption(kpiId, questionId, option, questionNumber, isGatekeeper, isInverted) {
  // Update visual selection
  const container = document.getElementById(`q-block-${questionId}`);
  container.querySelectorAll('.option-item').forEach(el => {
    el.classList.remove('selected', 'selected-na');
  });
  const optEl = document.getElementById(`opt-${questionId}-${option === 'N.A' ? 'NA' : option}`);
  if (optEl) optEl.classList.add(option === 'N.A' ? 'selected-na' : 'selected');

  // Store in pending
  if (!pendingSaves[kpiId]) pendingSaves[kpiId] = {};
  pendingSaves[kpiId][questionId] = option;

  // Gate logic — Q1 only
  if (questionNumber === 1 && isGatekeeper) {
    applyGateLogic(kpiId, option, isInverted);
  }

  // Update KPI card question data in memory
  const domain = questionnaire.find(d => d.kpis.some(k => k.kpi_id === kpiId));
  if (domain) {
    const kpi = domain.kpis.find(k => k.kpi_id === kpiId);
    if (kpi) {
      const q = kpi.questions.find(q => q.id === questionId);
      if (q) {
        q.selected_option = option === 'N.A' ? null : option;
        q.is_na = option === 'N.A';
      }
    }
  }
}

function applyGateLogic(kpiId, q1Option, isInverted) {
  const gateOption = isInverted ? 'Fully' : 'Not';
  const triggered  = q1Option === gateOption || q1Option === 'N.A';
  const notice     = document.getElementById(`gate-notice-${kpiId}`);

  document.querySelectorAll(`[data-kpi="${kpiId}"]`).forEach(block => {
    const qnum = parseInt(block.dataset.qnum);
    if (qnum > 1) {
      if (triggered) {
        block.classList.add('gated');
        block.querySelectorAll('.option-item').forEach(el => {
          el.classList.remove('selected', 'selected-na');
        });
      } else {
        block.classList.remove('gated');
      }
    }
  });

  if (notice) notice.classList.toggle('visible', triggered);
}

/* ── KPI toggle ── */
function toggleKpi(kpiId) {
  const card = document.getElementById(`kpi-card-${kpiId}`);
  if (!card) return;
  const isOpen = card.classList.contains('open');
  // Close all
  document.querySelectorAll('.kpi-card.open').forEach(c => c.classList.remove('open'));
  if (!isOpen) openKpi(card, kpiId);
}

function openKpi(card, kpiId) {
  card.classList.add('open', 'active');
  document.querySelectorAll('.kpi-card').forEach(c => {
    if (c.id !== `kpi-card-${kpiId}`) c.classList.remove('active');
  });
}

/* ── Save KPI ── */
async function saveKpi(kpiId) {
  const domain = questionnaire.find(d => d.kpis.some(k => k.kpi_id === kpiId));
  if (!domain) return;
  const kpi = domain.kpis.find(k => k.kpi_id === kpiId);
  if (!kpi) return;

  // Build answers array from current state
  const pending = pendingSaves[kpiId] || {};

  // Merge pending with existing answers
  const answers = kpi.questions.map(q => {
    const pendingOption = pending[q.id];
    const existingOption = q.is_na ? 'N.A' : q.selected_option;
    const option = pendingOption !== undefined ? pendingOption : existingOption;
    return option ? { question_id: q.id, selected_option: option } : null;
  }).filter(Boolean);

  // Validate Q1 is answered
  const q1 = kpi.questions.find(q => q.question_number === 1);
  const q1Answer = answers.find(a => a.question_id === q1.id);
  if (!q1Answer) {
    toast('Please answer Q1 before saving.', 'error');
    return;
  }

  // Validate all non-gated questions are answered
  const q1Option = q1Answer.selected_option;
  const gateOption = kpi.is_inverted ? 'Fully' : 'Not';
  const gateTriggered = q1Option === gateOption || q1Option === 'N.A';
  if (!gateTriggered) {
    const allAnswered = kpi.questions.every(q => {
      const ans = answers.find(a => a.question_id === q.id);
      return ans && ans.selected_option;
    });
    if (!allAnswered) {
      toast('Please answer all questions before saving.', 'error');
      return;
    }
  }

  setSaveStatus('saving');

  try {
    await apiFetch(`/assessments/${assessmentId}/answers/kpi/${kpiId}`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    });

    // Update in-memory state
    answers.forEach(a => {
      const q = kpi.questions.find(q => q.id === a.question_id);
      if (q) {
        q.selected_option = a.selected_option === 'N.A' ? null : a.selected_option;
        q.is_na = a.selected_option === 'N.A';
        q.is_hidden = gateTriggered && q.question_number > 1;
      }
    });

    delete pendingSaves[kpiId];
    setSaveStatus('saved');

    // Update KPI card to complete
    const card = document.getElementById(`kpi-card-${kpiId}`);
    if (card) {
      card.classList.add('complete');
      card.classList.remove('open', 'active');
      card.querySelector('.kpi-check').textContent = '✓';
      card.querySelector('.kpi-number').style.color = '#00b04f';
    }

    // Update sidebar
    renderSidebar();
    // Re-mark active domain
    const activeItem = document.getElementById(`domain-item-${activeDomainId}`);
    if (activeItem) activeItem.classList.add('active');

    // Auto-open next incomplete KPI
    const nextKpi = domain.kpis.find(k => !isKpiComplete(k));
    if (nextKpi) {
      const nextCard = document.getElementById(`kpi-card-${nextKpi.kpi_id}`);
      if (nextCard) {
        setTimeout(() => {
          openKpi(nextCard, nextKpi.kpi_id);
          nextCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 200);
      }
    } else {
      // All KPIs in domain complete — check if all domains done
      const allComplete = questionnaire.every(d => isDomainComplete(d));
      if (allComplete) {
        submitAssessment();
      } else {
        // Move to next incomplete domain
        const nextDomain = questionnaire.find(d => !isDomainComplete(d));
        if (nextDomain) {
          setTimeout(() => activateDomain(nextDomain.domain_id), 400);
          toast(`Domain complete! Moving to ${nextDomain.domain_name}.`, 'success');
        }
      }
    }

  } catch (err) {
    setSaveStatus('');
    toast(err.message || 'Failed to save answers.', 'error');
  }
}

/* ── Submit assessment ── */
async function submitAssessment() {
  setSaveStatus('saving');
  try {
    loading(true, 'Submitting assessment and running scoring engine…');
    await apiFetch(`/assessments/${assessmentId}/submit`, { method: 'POST' });
    loading(false);
    toast('Assessment complete! Redirecting to results…', 'success');
    setTimeout(() => {
      window.location.href = `/results?assessment_id=${assessmentId}`;
    }, 1200);
  } catch (err) {
    loading(false);
    toast(err.message || 'Submission failed.', 'error');
  }
}

/* ── Domain navigation ── */
function navDomain(dir) {
  const idx = questionnaire.findIndex(d => d.domain_id === activeDomainId);
  const next = questionnaire[idx + dir];
  if (next) activateDomain(next.domain_id);
}

/* ── Helpers ── */
function isKpiComplete(kpi) {
  const q1 = kpi.questions.find(q => q.question_number === 1);
  if (!q1) return false;
  // KPI is complete if Q1 has an answer
  const q1Answered = q1.selected_option !== null || q1.is_na === true;
  if (!q1Answered) return false;
  // If gate triggered, Q1 alone is enough
  const gateOpt = kpi.is_inverted ? 'Fully' : 'Not';
  if (q1.selected_option === gateOpt || q1.is_na === true) return true;
  // Otherwise all questions must be answered
  return kpi.questions.every(q =>
    q.is_hidden === true || q.selected_option !== null || q.is_na === true
  );
}

function isDomainComplete(domain) {
  return domain.kpis.every(isKpiComplete);
}

function setSaveStatus(state) {
  const el = document.getElementById('save-status');
  if (!el) return;
  el.className = `save-status ${state}`;
  if (state === 'saving') el.innerHTML = `<div class="save-dot"></div> Saving…`;
  else if (state === 'saved') el.innerHTML = `<div class="save-dot"></div> Saved`;
  else el.innerHTML = '';
  if (state === 'saved') setTimeout(() => setSaveStatus(''), 2500);
}

function showError(msg) {
  document.getElementById('loading-screen').innerHTML = `
    <p style="color:var(--pink)">${msg}</p>
  `;
}