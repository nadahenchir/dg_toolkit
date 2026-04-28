/* ============================================================
   create_assessment.js — Create Assessment page logic
   ============================================================ */

const DOMAIN_FALLBACK = [
  { id:1,  name:'Data Governance' },
  { id:2,  name:'Data Architecture' },
  { id:3,  name:'Data Modeling & Design' },
  { id:4,  name:'Data Storage & Operations' },
  { id:5,  name:'Data Security' },
  { id:6,  name:'Data Integration & Interoperability' },
  { id:7,  name:'Document & Content Management' },
  { id:8,  name:'Reference & Master Data' },
  { id:9,  name:'Data Warehousing & Business Intelligence' },
  { id:10, name:'Metadata Management' },
  { id:11, name:'Data Quality' },
];

let domains = [];
let targets = {};

/* ── Industry "Other" toggle ── */
document.getElementById('industry').addEventListener('change', function () {
  const w = document.getElementById('industry-other-wrap');
  w.style.display = this.value === 'Other' ? 'flex' : 'none';
  if (this.value !== 'Other') document.getElementById('industry-other').value = '';
});

/* ── Generate description ── */
async function generateDescription() {
  const name     = document.getElementById('org-name').value.trim();
  const industry = document.getElementById('industry').value === 'Other'
    ? document.getElementById('industry-other').value.trim()
    : document.getElementById('industry').value;
  const country  = document.getElementById('country').value;
  const size     = document.getElementById('size-band').value;

  if (!name || !industry) {
    toast('Fill in Organization Name and Industry first.', 'error');
    return;
  }

  const btn     = document.getElementById('gen-btn');
  const btnText = document.getElementById('gen-btn-text');
  btn.disabled  = true;
  btn.classList.add('generating');
  btnText.textContent = 'Generating...';

  try {
    const data = await apiFetch('/generate/organization-description', {
      method: 'POST',
      body: JSON.stringify({ name, industry, country: country || null, size_band: size || null }),
    });
    document.getElementById('company-description').value = data.description;
    toast('Description generated. Feel free to edit it.', 'success');
  } catch (err) {
    toast(err.message || 'Could not generate description.', 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('generating');
    btnText.textContent = 'Generate with AI';
  }
}

/* ── Validate Step 1 ── */
function validate1() {
  let ok = true;
  const rules = [
    { el: 'org-name',            fid: 'f-org-name',           fn: v => v.trim() },
    { el: 'industry',            fid: 'f-industry',           fn: v => v },
    { el: 'country',             fid: 'f-country',            fn: v => v },
    { el: 'company-description', fid: 'f-company-description',fn: v => v.trim() },
    { el: 'con-name',            fid: 'f-con-name',           fn: v => v.trim() },
    { el: 'con-email',           fid: 'f-con-email',          fn: v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) },
  ];
  rules.forEach(({ el, fid, fn }) => {
    const f = document.getElementById(fid);
    f.classList.toggle('error', !fn(document.getElementById(el).value));
    if (!fn(document.getElementById(el).value)) ok = false;
  });
  if (document.getElementById('industry').value === 'Other') {
    const v = document.getElementById('industry-other').value.trim();
    const w = document.getElementById('industry-other-wrap');
    w.classList.toggle('error', !v);
    if (!v) ok = false;
  }
  return ok;
}

/* ── Step navigation ── */
async function goStep2() {
  if (!validate1()) { toast('Please fill in all required fields.', 'error'); return; }

  try {
    const data = await apiFetch('/domains');
    domains = Array.isArray(data) ? data : DOMAIN_FALLBACK;
  } catch { domains = DOMAIN_FALLBACK; }

  domains.forEach(d => { if (!targets[d.id]) targets[d.id] = 3; });
  renderDomains();

  document.getElementById('step1').style.display = 'none';
  document.getElementById('step2').style.display = 'block';
  document.getElementById('step2').style.animation = 'fadeUp 0.4s ease both';

  document.getElementById('si-1').classList.remove('active');
  document.getElementById('si-1').classList.add('done');
  document.getElementById('conn-1').classList.add('done');
  document.getElementById('si-2').classList.add('active');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goStep1() {
  document.getElementById('step2').style.display = 'none';
  document.getElementById('step1').style.display = 'block';
  document.getElementById('step1').style.animation = 'fadeUp 0.4s ease both';

  document.getElementById('si-1').classList.add('active');
  document.getElementById('si-1').classList.remove('done');
  document.getElementById('conn-1').classList.remove('done');
  document.getElementById('si-2').classList.remove('active');
}

/* ── Render domain cards ── */
function renderDomains() {
  const grid = document.getElementById('domains-grid');
  grid.innerHTML = '';
  domains.forEach(d => {
    const card = document.createElement('div');
    card.className = 'domain-card targeted';
    card.id = `dc-${d.id}`;
    card.innerHTML = `
      <div class="domain-card-top">
        <div class="domain-name">${d.name}</div>
        <div class="domain-id">D${String(d.id).padStart(2, '0')}</div>
      </div>
      <div class="level-selector">
        ${[1,2,3,4,5].map(l => `
          <button class="level-btn ${targets[d.id] === l ? 'active' : ''}"
                  onclick="setTarget(${d.id}, ${l}, this)">L${l}</button>
        `).join('')}
      </div>`;
    grid.appendChild(card);
  });
}

function setTarget(domainId, level, btn) {
  targets[domainId] = level;
  document.getElementById(`dc-${domainId}`)
    .querySelectorAll('.level-btn')
    .forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

/* ── Submit all ── */
async function submitAll() {
  const btn = document.getElementById('submit-btn');
  btn.disabled = true;

  const isOther = document.getElementById('industry').value === 'Other';

  try {
    loading(true, 'Creating organization...');
    const org = await apiFetch('/organizations', {
      method: 'POST',
      body: JSON.stringify({
        name:                document.getElementById('org-name').value.trim(),
        industry:            document.getElementById('industry').value,
        industry_other:      isOther ? document.getElementById('industry-other').value.trim() : null,
        country:             document.getElementById('country').value,
        size_band:           document.getElementById('size-band').value || null,
        company_description: document.getElementById('company-description').value.trim() || null,
      }),
    });

    loading(true, 'Creating consultant...');
    const consultant = await apiFetch('/consultants', {
      method: 'POST',
      body: JSON.stringify({
        full_name: document.getElementById('con-name').value.trim(),
        email:     document.getElementById('con-email').value.trim(),
      }),
    });

    loading(true, 'Creating assessment...');
    const assessment = await apiFetch('/assessments', {
      method: 'POST',
      body: JSON.stringify({ organization_id: org.id, consultant_id: consultant.id }),
    });

    loading(true, 'Setting domain targets...');
    await apiFetch(`/assessments/${assessment.id}/targets`, {
      method: 'POST',
      body: JSON.stringify({
        targets: domains.map(d => ({ domain_id: d.id, target_level: targets[d.id] || 3 })),
      }),
    });

    loading(true, 'Starting assessment...');
    await apiFetch(`/assessments/${assessment.id}/start`, { method: 'POST' });

    loading(true, 'Launching questionnaire...');
    toast('Assessment created. Launching questionnaire!', 'success');
    setTimeout(() => {
      window.location.href = `/questionnaire?assessment_id=${assessment.id}`;
    }, 900);

  } catch (err) {
    loading(false);
    toast(err.message || 'Something went wrong.', 'error');
    btn.disabled = false;
  }
}