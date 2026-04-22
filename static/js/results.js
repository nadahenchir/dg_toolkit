/* ============================================================
   results.js — Results page logic
   ============================================================ */

const MATURITY_LABELS = { 1: 'Initial', 2: 'Managed', 3: 'Defined', 4: 'Quantified', 5: 'Optimized' };

let assessmentId = null;
let scoresData   = null;

/* ── Init ── */
window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(window.location.search);
  assessmentId = parseInt(params.get('assessment_id'));

  if (!assessmentId) { showError('No assessment ID provided.'); return; }

  try {
    // Load assessment info + scores in parallel
    const [assessment, scores] = await Promise.all([
      apiFetch(`/assessments/${assessmentId}`),
      apiFetch(`/assessments/${assessmentId}/scores`),
    ]);

    scoresData = scores;
    render(assessment, scores);

  } catch (err) {
    showError(err.message || 'Failed to load results.');
  }
});

/* ── Render ── */
function render(assessment, scores) {
  const overall   = scores.overall;
  const domains   = scores.domains;
  const pct       = Math.round(overall.overall_score * 100);
  const level     = overall.overall_level;
  const domainsAt = domains.filter(d => d.gap === 0).length;
  const avgGap    = (domains.reduce((s, d) => s + d.gap, 0) / domains.length).toFixed(1);

  // Page header
  document.getElementById('org-name').textContent    = assessment.organization_name;
  document.getElementById('consultant-name').textContent = assessment.consultant_name;
  document.getElementById('scored-at').textContent   =
    new Date(overall.computed_at).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' });

  // Summary cards
  document.getElementById('overall-score').textContent  = pct + '%';
  document.getElementById('overall-level').textContent  = 'L' + level;
  document.getElementById('level-label').textContent    = MATURITY_LABELS[level] || '';
  document.getElementById('domains-at-target').textContent = `${domainsAt} / ${domains.length}`;
  document.getElementById('avg-gap').textContent        = avgGap;
  document.getElementById('domains-scored').textContent = overall.domains_scored;

  // Domain cards
  renderDomains(domains, scores.kpis);

  // Radar chart
  renderRadar(domains);

  // Hide loading
  document.getElementById('loading-screen').style.display = 'none';
  document.getElementById('results-content').style.display = 'flex';
}

/* ── Domain + KPI breakdown ── */
function renderDomains(domains, kpis) {
  const grid = document.getElementById('domains-grid');
  grid.innerHTML = '';

  domains.forEach(d => {
    const domainKpis = kpis.filter(k => k.domain_id === d.domain_id);

    const section = document.createElement('div');
    section.className = 'domain-section';

    const onTarget = d.gap === 0;
    section.innerHTML = `
      <div class="domain-section-header">
        <div class="domain-section-left">
          <span class="domain-section-name">${d.domain_name}</span>
          <span class="level-badge current">L${d.maturity_level}</span>
          <span class="gap-badge gap-${Math.min(d.gap, 3)}">
            ${d.gap === 0 ? '✓ On target' : `Gap ${d.gap}`}
          </span>
        </div>
        <div class="domain-section-right">
          Target L${d.target_level} · ${Math.round(d.raw_score * 100)}% · ${d.kpis_scored} KPIs
        </div>
      </div>
      <table class="kpi-table">
        <thead>
          <tr>
            <th>KPI</th>
            <th>Score</th>
            <th>Level</th>
          </tr>
        </thead>
        <tbody>
          ${domainKpis.map(k => `
            <tr class="${k.is_excluded ? 'excluded' : ''}">
              <td class="kpi-name-cell">${k.kpi_name}${k.is_excluded ? ' <span class="excluded-tag">Excluded</span>' : ''}</td>
              <td>
                <div class="kpi-mini-bar-wrap">
                  <div class="kpi-mini-bar" style="width:${Math.round(k.raw_score * 100)}%"></div>
                  <span class="kpi-mini-pct">${Math.round(k.raw_score * 100)}%</span>
                </div>
              </td>
              <td><span class="level-badge current ml-${k.maturity_level}">L${k.maturity_level}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
    grid.appendChild(section);
  });
}

/* ── Radar chart ── */
function renderRadar(domains) {
  const canvas = document.getElementById('radarChart');
  if (!canvas) return;

  const labels  = domains.map(d => d.domain_name);
  const current = domains.map(d => d.maturity_level);
  const targets = domains.map(d => d.target_level);

  new Chart(canvas, {
    type: 'radar',
    data: {
      labels,
      datasets: [
        {
          label: 'Current',
          data: current,
          backgroundColor: 'rgba(0, 51, 141, 0.10)',
          borderColor: '#00338D',
          borderWidth: 2,
          pointBackgroundColor: '#00338D',
          pointRadius: 4,
        },
        {
          label: 'Target',
          data: targets,
          backgroundColor: 'rgba(0, 145, 218, 0.07)',
          borderColor: '#0091DA',
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointBackgroundColor: '#0091DA',
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        r: {
          min: 0, max: 5,
          ticks: {
            stepSize: 1,
            color: '#718096',
            font: { size: 10, family: 'Arial' },
            backdropColor: 'transparent',
          },
          grid:        { color: '#D0D9E8' },
          angleLines:  { color: '#D0D9E8' },
          pointLabels: {
            color: '#4A5568',
            font: { size: 10, family: 'Arial' },
          },
        },
      },
      plugins: {
        legend: {
          labels: {
            color: '#4A5568',
            font: { size: 11, family: 'Arial' },
            boxWidth: 12,
          },
        },
        tooltip: {
          backgroundColor: '#FFFFFF',
          borderColor: '#D0D9E8',
          borderWidth: 1,
          titleColor: '#1A1A2E',
          bodyColor: '#718096',
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: L${ctx.raw}`,
          },
        },
      },
    },
  });
}

function showError(msg) {
  document.getElementById('loading-screen').innerHTML =
    `<p style="color:var(--error-color);font-size:13px;font-weight:700">${msg}</p>`;
}