// history.js — DG Toolkit History Page

const DOMAIN_LABELS = [
  'Data Governance', 'Data Quality', 'Data Architecture',
  'Data Modeling & Design', 'Data Storage & Operations', 'Data Security',
  'Master & Reference Data', 'Data Warehousing & BI', 'Data Integration',
  'Document & Content', 'Metadata Management'
];

let allAssessments = [];

async function loadAssessments() {
  try {
    const res  = await fetch('/api/assessments?limit=200');
    if (!res.ok) throw new Error('Failed to load');
    const data = await res.json();
    // Only show completed assessments on history page
    allAssessments = (data.assessments || data || []).filter(a => a.status === 'complete');
    await enrichWithScores(allAssessments);
    renderCards(allAssessments);
  } catch (err) {
    document.getElementById('hist-grid').innerHTML =
      '<div class="hist-empty">Could not load assessments.</div>';
  }
}

async function enrichWithScores(list) {
  await Promise.allSettled(list.map(async (a) => {
    try {
      const res  = await fetch(`/api/assessments/${a.id}/scores`);
      if (!res.ok) return;
      const data = await res.json();
      a._scores = data;
    } catch (_) {}
  }));
}

function getOverallScore(assessment) {
  const s = assessment._scores;
  if (!s || !s.overall) return null;
  return parseFloat(s.overall.overall_score) * 100; // 0.73 → 73
}

function getOverallLevel(assessment) {
  const s = assessment._scores;
  if (!s || !s.overall) return '—';
  const level = s.overall.overall_level;
  if (level === null || level === undefined) return '—';
  return String(level).startsWith('L') ? level : `L${level}`;
}

function getAvgTargetLevel(assessment) {
  const s = assessment._scores;
  if (!s || !s.domains || !s.domains.length) return null;
  const avg = s.domains.reduce((sum, d) => sum + (d.target_level || 0), 0) / s.domains.length;
  return Math.round(avg);
}

function getCurrentScores(assessment) {
  const s = assessment._scores;
  if (!s || !s.domains || !s.domains.length) return null;
  return s.domains.map(d => d.maturity_level || 0);
}

function getTargetScores(assessment) {
  const s = assessment._scores;
  if (!s || !s.domains || !s.domains.length) return null;
  return s.domains.map(d => d.target_level || 0);
}

function renderCards(list) {
  const grid = document.getElementById('hist-grid');
  if (!list.length) {
    grid.innerHTML = '<div class="hist-empty">No completed assessments found.</div>';
    return;
  }

  grid.innerHTML = list.map((a, idx) => {
    const date        = a.created_at
      ? new Date(a.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
      : '—';
    const score       = getOverallScore(a);
    const level       = getOverallLevel(a);
    const targetLevel = getAvgTargetLevel(a);

    const scoreHtml = score !== null
      ? `<div class="hist-score-value">${Math.round(score)}%</div>
         <div class="hist-score-label">Overall</div>
         <div class="hist-score-level">${level}</div>
         ${targetLevel ? `<div class="hist-score-target">Target L${targetLevel}</div>` : ''}`
      : `<div class="hist-score-value" style="font-size:20px;color:var(--text-muted)">—</div>
         <div class="hist-score-label">No Score</div>`;

    const hasScores = score !== null && getCurrentScores(a) && getTargetScores(a);
    const radarHtml = hasScores
      ? `<div class="hist-radar-wrap"><canvas id="radar-${idx}"></canvas></div>`
      : `<div class="hist-no-score">Complete the assessment<br>to see domain scores.</div>`;

    return `
      <a class="hist-card" href="/results?assessment_id=${a.id}"
         data-org="${(a.organization_name || '').toLowerCase()}">
        <div class="hist-card-header">
          <div class="hist-card-org">${a.organization_name || '—'}</div>
          <div class="hist-card-meta">
            <span>${a.consultant_name || '—'}</span>
            <span>·</span>
            <span>${date}</span>
            <span class="hist-card-status complete">Complete</span>
          </div>
        </div>
        <div class="hist-card-body">
          <div class="hist-score-badge">${scoreHtml}</div>
          <div class="hist-card-divider"></div>
          ${radarHtml}
        </div>
      </a>
    `;
  }).join('');

  // Draw radars after DOM is updated
  list.forEach((a, idx) => {
    const current = getCurrentScores(a);
    const targets = getTargetScores(a);
    if (!current || !targets) return;
    const canvas = document.getElementById(`radar-${idx}`);
    if (!canvas) return;
    drawMiniRadar(canvas, current, targets);
  });
}

function drawMiniRadar(canvas, current, targets) {
  new Chart(canvas, {
    type: 'radar',
    data: {
      labels: DOMAIN_LABELS,
      datasets: [
        {
          label: 'Current',
          data: current,
          backgroundColor: 'rgba(0, 51, 141, 0.10)',
          borderColor: '#00338D',
          borderWidth: 2,
          pointBackgroundColor: '#00338D',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1,
          pointRadius: 3,
        },
        {
          label: 'Target',
          data: targets,
          backgroundColor: 'rgba(0, 145, 218, 0.07)',
          borderColor: '#0091DA',
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointBackgroundColor: '#0091DA',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1,
          pointRadius: 2,
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: false,
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: '#4A5568',
            font: { size: 9, family: 'Arial' },
            boxWidth: 10,
            padding: 8,
          }
        },
        tooltip: { enabled: false }
      },
      scales: {
        r: {
          min: 0,
          max: 5,
          ticks: { display: false, stepSize: 1 },
          grid: { color: '#D0D9E8' },
          angleLines: { color: '#D0D9E8' },
          pointLabels: {
            font: { size: 8, family: 'Arial' },
            color: '#4A5568',
          }
        }
      }
    }
  });
}

function filterCards() {
  const q = (document.getElementById('hist-search').value || '').toLowerCase().trim();
  const filtered = allAssessments.filter(a =>
    !q || (a.organization_name || '').toLowerCase().includes(q)
  );
  renderCards(filtered);
}

// Init
loadAssessments();