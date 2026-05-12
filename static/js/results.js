/* ============================================================
   results.js — Results page logic
   ============================================================ */

const MATURITY_LABELS = { 1: 'Initial', 2: 'Managed', 3: 'Defined', 4: 'Quantified', 5: 'Optimized' };

let assessmentId = null;
let scoresData   = null;
let radarChartInstance = null;  // keep reference for PDF capture

/* ── Init ── */
window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(window.location.search);
  assessmentId = parseInt(params.get('assessment_id'));

  if (!assessmentId) { showError('No assessment ID provided.'); return; }

  try {
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
  const domainsAt = domains.filter(d => d.gap <= 0).length;
  const avgGap    = (domains.reduce((s, d) => s + (d.gap ?? 0), 0) / domains.length).toFixed(1);

  // Page header
  document.getElementById('org-name').textContent         = assessment.organization_name;
  document.getElementById('consultant-name').textContent  = assessment.consultant_name;
  document.getElementById('scored-at').textContent        =
    new Date(overall.computed_at).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' });

  // Summary cards
  document.getElementById('overall-score').textContent    = pct + '%';
  document.getElementById('overall-level').textContent    = 'L' + level;
  document.getElementById('level-label').textContent      = MATURITY_LABELS[level] || '';
  document.getElementById('domains-at-target').textContent = `${domainsAt} / ${domains.length}`;
  document.getElementById('avg-gap').textContent          = avgGap;
  document.getElementById('domains-scored').textContent   = overall.domains_scored;

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
    // Only show non-excluded KPIs
    const domainKpis = kpis.filter(k => k.domain_id === d.domain_id && !k.is_excluded);

    const section = document.createElement('div');
    section.className = 'domain-section';

    const tableId = `kpi-table-${d.domain_id}`;

    section.innerHTML = `
      <div class="domain-section-header" onclick="toggleDomain('${tableId}', this)" style="cursor:pointer;">
        <div class="domain-section-left">
          <span class="domain-section-name">${d.domain_name}</span>
          <span class="level-badge current">L${d.maturity_level}</span>
          ${d.gap > 0
            ? `<span class="gap-badge gap-${Math.min(d.gap, 3)}">Gap +${d.gap}</span>`
            : d.gap === 0
              ? `<span class="gap-badge gap-0">✓ On target</span>`
              : ''}
        </div>
        <div style="display:flex;align-items:center;gap:14px;">
          <div class="domain-section-right">
            Target L${d.target_level} · ${Math.round(d.raw_score * 100)}% · ${domainKpis.length} KPIs
          </div>
          <svg class="domain-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" style="transition:transform 0.2s;flex-shrink:0;">
            <path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
      </div>
      <div id="${tableId}" style="display:none;">
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
              <tr>
                <td class="kpi-name-cell">${k.kpi_name}</td>
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
      </div>
    `;

    grid.appendChild(section);
  });
}

/* ── Toggle domain expand/collapse ── */
function toggleDomain(tableId, header) {
  const table   = document.getElementById(tableId);
  const chevron = header.querySelector('.domain-chevron');
  const isOpen  = table.style.display !== 'none';

  table.style.display  = isOpen ? 'none' : 'block';
  chevron.style.transform = isOpen ? '' : 'rotate(180deg)';
}

/* ── Radar chart ── */
function renderRadar(domains) {
  const canvas = document.getElementById('radarChart');
  if (!canvas) return;

  const labels  = domains.map(d => d.domain_name);
  const current = domains.map(d => d.maturity_level);
  const targets = domains.map(d => d.target_level);

  radarChartInstance = new Chart(canvas, {
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
      animation: {
        onComplete: () => {
          // Mark chart as ready for PDF capture once animation finishes
          canvas.dataset.ready = 'true';
        }
      },
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

/* ── PDF Download ─────────────────────────────────────────────────────────── */
async function downloadPDF() {
  const btn = document.getElementById('download-pdf-btn');
  if (!btn) return;

  // Show loading state
  const originalText = btn.innerHTML;
  btn.innerHTML = `
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" style="animation:spin 1s linear infinite">
      <circle cx="6.5" cy="6.5" r="5" stroke="white" stroke-width="1.5" stroke-dasharray="20" stroke-dashoffset="10"/>
    </svg>
    Generating PDF...
  `;
  btn.disabled = true;

  try {
    // Capture radar chart as base64 PNG — only after animation completes
    let radarBase64 = '';
    const canvas = document.getElementById('radarChart');
    if (canvas) {
      if (canvas.dataset.ready !== 'true') {
        toast('Chart is still loading, please try again in a moment.', 'error');
        btn.innerHTML = originalText;
        btn.disabled  = false;
        return;
      }
      radarBase64 = canvas.toDataURL('image/png');
    }

    // POST to report generation endpoint
    const response = await fetch(`/api/assessments/${assessmentId}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ radar_chart: radarBase64 }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || 'Report generation failed');
    }

    // Trigger file download from response blob
    const blob     = await response.blob();
    const url      = URL.createObjectURL(blob);
    const a        = document.createElement('a');
    const orgName  = document.getElementById('org-name').textContent.trim().replace(/\s+/g, '_');
    a.href         = url;
    a.download     = `DG_Report_${orgName}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

  } catch (err) {
    toast(err.message || 'Failed to generate PDF', 'error');
  } finally {
    btn.innerHTML = originalText;
    btn.disabled  = false;
  }
}

function showError(msg) {
  document.getElementById('loading-screen').innerHTML =
    `<p style="color:var(--error-color);font-size:13px;font-weight:700">${msg}</p>`;
}