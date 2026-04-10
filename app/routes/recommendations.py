"""
app/routes/recommendations.py
------------------------------
GET  /api/assessments/<assessment_id>/recommendations
POST /api/recommendations/<recommendation_id>/rate
"""

from flask import Blueprint, request, jsonify
import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
from connection import get_connection, get_cursor

recommendations_bp = Blueprint('recommendations', __name__)

VALID_SORT_FIELDS   = {'priority_score', 'gap', 'maturity_level', 'impact', 'effort'}
VALID_SORT_ORDERS   = {'asc', 'desc'}
IMPACT_EFFORT_ORDER = {'High': 3, 'Medium': 2, 'Low': 1}


# ---------------------------------------------------------------------------
# GET /assessments/<assessment_id>/recommendations
# ---------------------------------------------------------------------------

@recommendations_bp.route(
    '/assessments/<int:assessment_id>/recommendations',
    methods=['GET'],
)
def get_recommendations(assessment_id):
    domain_id_filter      = request.args.get('domain_id',       type=int)
    category_filter       = request.args.get('action_category', type=str)
    impact_filter         = request.args.get('impact',          type=str)
    effort_filter         = request.args.get('effort',          type=str)
    maturity_level_filter = request.args.get('maturity_level',  type=int)
    kpi_id_filter         = request.args.get('kpi_id',          type=int)
    min_gap_filter        = request.args.get('min_gap',         type=int)
    sort_by               = request.args.get('sort_by',         type=str, default='priority_score')
    sort_order            = request.args.get('sort_order',      type=str, default='desc')

    if sort_by not in VALID_SORT_FIELDS:
        return jsonify({
            'error': f"Invalid sort_by '{sort_by}'. Valid values: {', '.join(VALID_SORT_FIELDS)}"
        }), 400
    if sort_order not in VALID_SORT_ORDERS:
        return jsonify({
            'error': f"Invalid sort_order '{sort_order}'. Use 'asc' or 'desc'."
        }), 400

    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT status, layer2_status, layer3_status
            FROM   dg_toolkit.assessments
            WHERE  id = %s AND deleted_at IS NULL
            """,
            (assessment_id,),
        )
        row = cur.fetchone()
        cur.close()

        if not row:
            return jsonify({'error': 'Assessment not found'}), 404
        if row['status'] != 'complete':
            return jsonify({
                'error':  'Recommendations not yet available',
                'status': row['status'],
            }), 409

        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT r.id                  AS recommendation_id,
                   r.kpi_id,
                   k.name                AS kpi_name,
                   k.domain_id,
                   d.name                AS domain_name,
                   d.display_order       AS domain_order,
                   k.domain_order        AS kpi_order,
                   a.action_text,
                   a.impact,
                   a.effort,
                   a.from_level,
                   r.action_category,
                   r.priority_score,
                   r.rag_narrative,
                   ks.maturity_level,
                   ds.target_level,
                   ds.gap,
                   r.was_implemented,
                   r.implementation_rating
            FROM   dg_toolkit.recommendations r
            JOIN   dg_toolkit.kpis            k  ON k.id  = r.kpi_id
            JOIN   dg_toolkit.domains         d  ON d.id  = k.domain_id
            JOIN   dg_toolkit.action_library  a  ON a.id  = r.base_action_id
            JOIN   dg_toolkit.kpi_scores      ks ON ks.assessment_id = r.assessment_id
                                                AND ks.kpi_id        = r.kpi_id
            JOIN   dg_toolkit.domain_scores   ds ON ds.assessment_id = r.assessment_id
                                                AND ds.domain_id     = k.domain_id
            WHERE  r.assessment_id = %s
            """,
            (assessment_id,),
        )
        rows = cur.fetchall()
        cur.close()

        results = []
        for r in rows:
            if domain_id_filter      and r['domain_id']      != domain_id_filter:
                continue
            if category_filter       and r['action_category'] != category_filter:
                continue
            if impact_filter         and r['impact']          != impact_filter:
                continue
            if effort_filter         and r['effort']          != effort_filter:
                continue
            if maturity_level_filter and r['maturity_level']  != maturity_level_filter:
                continue
            if kpi_id_filter         and r['kpi_id']          != kpi_id_filter:
                continue
            if min_gap_filter is not None and (r['gap'] or 0) < min_gap_filter:
                continue

            results.append({
                'recommendation_id':     r['recommendation_id'],
                'kpi_id':                r['kpi_id'],
                'kpi_name':              r['kpi_name'],
                'domain_id':             r['domain_id'],
                'domain_name':           r['domain_name'],
                'action_text':           r['action_text'],
                'impact':                r['impact'],
                'effort':                r['effort'],
                'from_level':            r['from_level'],
                'to_level':              r['from_level'] + 1,
                'action_category':       r['action_category'],
                'priority_score':        float(r['priority_score']),
                'rag_narrative':         r['rag_narrative'],
                'maturity_level':        r['maturity_level'],
                'target_level':          r['target_level'],
                'gap':                   r['gap'],
                'was_implemented':       r['was_implemented'],
                'implementation_rating': r['implementation_rating'],
            })

        reverse = (sort_order == 'desc')
        if sort_by == 'priority_score':
            results.sort(key=lambda x: x['priority_score'], reverse=reverse)
        elif sort_by == 'gap':
            results.sort(key=lambda x: (x['gap'] or 0), reverse=reverse)
        elif sort_by == 'maturity_level':
            results.sort(key=lambda x: (x['maturity_level'] or 0), reverse=reverse)
        elif sort_by == 'impact':
            results.sort(key=lambda x: IMPACT_EFFORT_ORDER.get(x['impact'], 0), reverse=reverse)
        elif sort_by == 'effort':
            results.sort(key=lambda x: IMPACT_EFFORT_ORDER.get(x['effort'], 0), reverse=reverse)

        domains: dict = {}
        for rec in results:
            did = rec['domain_id']
            if did not in domains:
                domains[did] = {
                    'domain_id':       did,
                    'domain_name':     rec['domain_name'],
                    'recommendations': [],
                }
            domains[did]['recommendations'].append(rec)

        total       = len(results)
        quick_wins  = sum(1 for r in results if r['action_category'] == 'Quick Win')
        strategic   = sum(1 for r in results if r['action_category'] == 'Strategic')
        fill_in     = sum(1 for r in results if r['action_category'] == 'Fill In')
        high_impact = sum(1 for r in results if r['impact'] == 'High')
        low_effort  = sum(1 for r in results if r['effort'] == 'Low')

        return jsonify({
            'assessment_id': assessment_id,
            'layer2_status': row['layer2_status'],
            'layer3_status': row['layer3_status'],
            'rag_ready':     row['layer3_status'] == 'done',
            'filters_applied': {
                'domain_id':       domain_id_filter,
                'action_category': category_filter,
                'impact':          impact_filter,
                'effort':          effort_filter,
                'maturity_level':  maturity_level_filter,
                'kpi_id':          kpi_id_filter,
                'min_gap':         min_gap_filter,
                'sort_by':         sort_by,
                'sort_order':      sort_order,
            },
            'summary': {
                'total':       total,
                'quick_wins':  quick_wins,
                'strategic':   strategic,
                'fill_in':     fill_in,
                'high_impact': high_impact,
                'low_effort':  low_effort,
            },
            'by_domain':       list(domains.values()),
            'recommendations': results,
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /recommendations/<recommendation_id>/rate
#
# Post-engagement learning loop.
# Consultant rates whether a recommendation was implemented and how well it worked.
# This data feeds Layer 2 similarity matching in future assessments.
# ---------------------------------------------------------------------------

@recommendations_bp.route(
    '/recommendations/<int:recommendation_id>/rate',
    methods=['POST'],
)
def rate_recommendation(recommendation_id):
    data = request.get_json(force=True) or {}

    was_implemented       = data.get('was_implemented')
    implementation_rating = data.get('implementation_rating')
    implementation_notes  = data.get('implementation_notes')

    # -- validate ----------------------------------------------------------
    if was_implemented is None:
        return jsonify({'error': 'was_implemented is required (true or false)'}), 400
    if not isinstance(was_implemented, bool):
        return jsonify({'error': 'was_implemented must be a boolean'}), 400

    if was_implemented:
        if implementation_rating is None:
            return jsonify({'error': 'implementation_rating is required when was_implemented is true'}), 400
        if not isinstance(implementation_rating, int) or not (1 <= implementation_rating <= 5):
            return jsonify({'error': 'implementation_rating must be an integer between 1 and 5'}), 400

    conn = get_connection()
    try:
        # -- verify recommendation exists ------------------------------------
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT id, assessment_id, kpi_id
            FROM   dg_toolkit.recommendations
            WHERE  id = %s
            """,
            (recommendation_id,),
        )
        rec = cur.fetchone()
        cur.close()

        if not rec:
            return jsonify({'error': 'Recommendation not found'}), 404

        # -- save rating -----------------------------------------------------
        cur = get_cursor(conn)
        cur.execute(
            """
            UPDATE dg_toolkit.recommendations
            SET    was_implemented       = %s,
                   implementation_rating = %s,
                   implementation_notes  = %s,
                   rated_at              = NOW()
            WHERE  id = %s
            RETURNING id, assessment_id, kpi_id,
                      was_implemented, implementation_rating,
                      implementation_notes, rated_at
            """,
            (
                was_implemented,
                implementation_rating if was_implemented else None,
                implementation_notes,
                recommendation_id,
            ),
        )
        row = cur.fetchone()
        cur.close()
        conn.commit()

        return jsonify({
            'message':               'Rating saved successfully',
            'recommendation_id':     row['id'],
            'assessment_id':         row['assessment_id'],
            'kpi_id':                row['kpi_id'],
            'was_implemented':       row['was_implemented'],
            'implementation_rating': row['implementation_rating'],
            'implementation_notes':  row['implementation_notes'],
            'rated_at':              row['rated_at'].isoformat() if row['rated_at'] else None,
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()