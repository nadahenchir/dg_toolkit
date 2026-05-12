"""
app/routes/reports.py
----------------------
POST /api/assessments/<assessment_id>/report
Generates a PDF report for a completed assessment.
Receives the radar chart PNG (base64) from the frontend canvas capture.
Returns the PDF as a file download.
"""

from flask import Blueprint, request, jsonify, Response
from app.db.connection import get_connection, get_cursor
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import os
import re
from datetime import datetime

reports_bp = Blueprint('reports', __name__)

MATURITY_LABELS = {
    1: 'Initial',
    2: 'Managed',
    3: 'Defined',
    4: 'Quantified',
    5: 'Optimized',
}


def fetch_report_data(assessment_id: int) -> dict:
    """Fetch all data needed to render the PDF report."""
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        # ── Assessment + org + consultant ────────────────────────────────────
        cur.execute("""
            SELECT
                a.id              AS assessment_id,
                a.engagement_date,
                a.scored_at,
                a.layer3_status,
                o.name            AS org_name,
                o.industry,
                o.industry_other,
                o.size_band,
                o.country,
                c.full_name       AS consultant_name,
                c.email           AS consultant_email
            FROM dg_toolkit.assessments a
            JOIN dg_toolkit.organizations o ON o.id = a.organization_id
            JOIN dg_toolkit.consultants   c ON c.id = a.consultant_id
            WHERE a.id = %s AND a.deleted_at IS NULL
        """, [assessment_id])
        assessment = cur.fetchone()
        if not assessment:
            raise ValueError(f"Assessment {assessment_id} not found")

        # ── Overall score ────────────────────────────────────────────────────
        cur.execute("""
            SELECT overall_score, overall_level, domains_scored, computed_at
            FROM dg_toolkit.assessment_scores
            WHERE assessment_id = %s
        """, [assessment_id])
        overall = cur.fetchone()
        if not overall:
            raise ValueError("Scores not yet computed")

        # ── Domain scores ────────────────────────────────────────────────────
        cur.execute("""
            SELECT
                d.id            AS domain_id,
                d.name          AS domain_name,
                d.display_order,
                ds.raw_score,
                ds.maturity_level,
                ds.target_level,
                ds.gap,
                ds.kpis_scored
            FROM dg_toolkit.domain_scores ds
            JOIN dg_toolkit.domains d ON d.id = ds.domain_id
            WHERE ds.assessment_id = %s
            ORDER BY d.display_order
        """, [assessment_id])
        domains = [dict(r) for r in cur.fetchall()]

        # ── KPI scores ───────────────────────────────────────────────────────
        cur.execute("""
            SELECT
                k.id            AS kpi_id,
                k.name          AS kpi_name,
                k.domain_id,
                k.domain_order  AS kpi_order,
                ks.raw_score,
                ks.maturity_level,
                ks.is_excluded
            FROM dg_toolkit.kpi_scores ks
            JOIN dg_toolkit.kpis k ON k.id = ks.kpi_id
            WHERE ks.assessment_id = %s
            ORDER BY k.domain_id, k.domain_order
        """, [assessment_id])
        kpis = [dict(r) for r in cur.fetchall()]

        # ── Recommendations ──────────────────────────────────────────────────
        cur.execute("""
            SELECT
                r.id                AS recommendation_id,
                r.kpi_id,
                k.name              AS kpi_name,
                k.domain_id,
                d.name              AS domain_name,
                d.display_order     AS domain_order,
                al.action_text,
                al.impact,
                al.effort,
                al.from_level,
                al.from_level + 1   AS to_level,
                r.action_category,
                r.priority_score,
                r.rag_narrative,
                ks.maturity_level,
                ds.target_level,
                ds.gap
            FROM dg_toolkit.recommendations r
            JOIN dg_toolkit.kpis k            ON k.id  = r.kpi_id
            JOIN dg_toolkit.domains d         ON d.id  = k.domain_id
            JOIN dg_toolkit.action_library al ON al.id = r.base_action_id
            JOIN dg_toolkit.kpi_scores ks     ON ks.assessment_id = r.assessment_id
                                             AND ks.kpi_id        = r.kpi_id
            JOIN dg_toolkit.domain_scores ds  ON ds.assessment_id = r.assessment_id
                                             AND ds.domain_id     = k.domain_id
            WHERE r.assessment_id = %s
            ORDER BY d.display_order, r.priority_score DESC
        """, [assessment_id])
        recommendations = [dict(r) for r in cur.fetchall()]

        return {
            'assessment':      dict(assessment),
            'overall':         dict(overall),
            'domains':         domains,
            'kpis':            kpis,
            'recommendations': recommendations,
        }

    finally:
        cur.close()
        conn.close()


def build_template_context(data: dict, radar_chart_b64: str) -> dict:
    """Transform raw DB data into template-ready context."""
    overall    = data['overall']
    domains    = data['domains']
    recs       = data['recommendations']
    assessment = data['assessment']

    # ── Summary stats ────────────────────────────────────────────────────────
    overall_pct      = round(float(overall['overall_score']) * 100)
    overall_level    = overall['overall_level']
    domains_at_above = sum(1 for d in domains if d['gap'] is not None and d['gap'] <= 0)
    avg_gap          = round(
        sum(d['gap'] if d['gap'] is not None else 0 for d in domains) / len(domains), 1
    ) if domains else 0

    # ── Domain enrichment ────────────────────────────────────────────────────
    kpis_by_domain = {}
    for k in data['kpis']:
        kpis_by_domain.setdefault(k['domain_id'], []).append(k)

    enriched_domains = []
    for d in domains:
        domain_kpis = [
            k for k in kpis_by_domain.get(d['domain_id'], [])
            if not k['is_excluded']
        ]
        enriched_domains.append({
            **d,
            'raw_score_pct':  round(float(d['raw_score']) * 100) if d['raw_score'] is not None else 0,
            'maturity_label': MATURITY_LABELS.get(d['maturity_level'], ''),
            'gap_class':      (
                'above'     if d['gap'] is not None and d['gap'] < 0 else
                'on-target' if d['gap'] == 0 else
                'below'
            ),
            'kpis': [{
                **k,
                'raw_score_pct':  round(float(k['raw_score']) * 100) if k['raw_score'] is not None else 0,
                'maturity_label': MATURITY_LABELS.get(k['maturity_level'], ''),
            } for k in domain_kpis],
        })

    # ── Recommendations grouped by category then domain ──────────────────────
    quick_wins = [r for r in recs if r['action_category'] == 'Quick Win']
    strategic  = [r for r in recs if r['action_category'] == 'Strategic']
    fill_in    = [r for r in recs if r['action_category'] == 'Fill In']

    def group_by_domain(rec_list):
        grouped = {}
        for r in rec_list:
            did = r['domain_id']
            if did not in grouped:
                grouped[did] = {
                    'domain_name':  r['domain_name'],
                    'domain_order': r['domain_order'],
                    'recommendations':        [],
                }
            grouped[did]['recommendations'].append({
                **r,
                'maturity_path': _build_path(r['from_level'], r['to_level'], r['target_level']),
            })
        return sorted(grouped.values(), key=lambda x: x['domain_order'])

    # ── Dates ────────────────────────────────────────────────────────────────
    engagement_date = assessment.get('engagement_date')
    if engagement_date:
        if hasattr(engagement_date, 'strftime'):
            engagement_date = engagement_date.strftime('%d %B %Y')
        else:
            engagement_date = str(engagement_date)

    generated_at = datetime.now().strftime('%d %B %Y')

    # ── Industry: resolve industry_other for "Other" orgs ────────────────────
    industry = (
        assessment['industry_other']
        if assessment['industry'] == 'Other' and assessment['industry_other']
        else assessment['industry']
    )

    return {
        'org_name':         assessment['org_name'],
        'industry':         industry,
        'size_band':        assessment['size_band'],
        'country':          assessment['country'],
        'consultant_name':  assessment['consultant_name'],
        'consultant_email': assessment['consultant_email'],
        'engagement_date':  engagement_date,
        'generated_at':     generated_at,
        'overall_pct':      overall_pct,
        'overall_level':    overall_level,
        'overall_label':    MATURITY_LABELS.get(overall_level, ''),
        'domains_scored':   overall['domains_scored'],
        'domains_at_above': domains_at_above,
        'avg_gap':          avg_gap,
        'domains':          enriched_domains,
        'quick_wins':       group_by_domain(quick_wins),
        'strategic':        group_by_domain(strategic),
        'fill_in':          group_by_domain(fill_in),
        'total_recs':       len(recs),
        'quick_wins_count': len(quick_wins),
        'strategic_count':  len(strategic),
        'fill_in_count':    len(fill_in),
        'radar_chart':      radar_chart_b64,
    }


def _build_path(from_level, to_level, target_level) -> str:
    """Build incremental path string e.g. L1→L2, then L2→L3."""
    if from_level is None or to_level is None or target_level is None:
        return ''
    if to_level >= target_level:
        return f'L{from_level}→L{to_level}'
    steps = [f'L{from_level}→L{to_level}']
    level = to_level
    while level < target_level:
        steps.append(f'L{level}→L{level+1}')
        level += 1
    return ', then '.join(steps)


@reports_bp.route('/assessments/<int:assessment_id>/report', methods=['POST'])
def generate_report(assessment_id):
    """
    Generate PDF report for a completed assessment.
    Body: { "radar_chart": "data:image/png;base64,..." }
    Returns: PDF file download.
    """
    data = request.get_json() or {}
    radar_chart_b64 = data.get('radar_chart', '')

    try:
        report_data = fetch_report_data(assessment_id)
        context     = build_template_context(report_data, radar_chart_b64)

        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'templates'
        )
        env      = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template('report_template.html')
        html_str = template.render(**context)

        base_url  = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static'
        )
        pdf_bytes = HTML(string=html_str, base_url=base_url).write_pdf()

        org_slug = re.sub(r'[^A-Za-z0-9]+', '_', context['org_name'])[:30].strip('_')
        filename = f"DG_Report_{org_slug}_{datetime.now().strftime('%Y%m%d')}.pdf"

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(pdf_bytes)),
            }
        )

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': f'Report generation failed: {str(e)}'}), 500
