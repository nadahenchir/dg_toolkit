from flask import Blueprint, request, jsonify
import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
from connection import get_connection, get_cursor

recommendations_bp = Blueprint('recommendations', __name__)


@recommendations_bp.route(
    '/assessments/<int:assessment_id>/recommendations',
    methods=['GET'],
)
def get_recommendations(assessment_id):
    # -- optional filters from query string -----------------------------------
    domain_id_filter       = request.args.get('domain_id',       type=int)
    category_filter        = request.args.get('action_category',  type=str)
    min_gap_filter         = request.args.get('min_gap',          type=int)

    conn = get_connection()
    try:
        # -- 1. validate assessment is complete --------------------------------
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
        if row['status'] not in ('complete',):
            return jsonify({
                'error':  'Recommendations not yet available',
                'status': row['status'],
            }), 409

        # -- 2. fetch recommendations with full context -----------------------
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
                   ds.maturity_level,
                   ds.target_level,
                   ds.gap,
                   r.was_implemented,
                   r.implementation_rating
            FROM   dg_toolkit.recommendations r
            JOIN   dg_toolkit.kpis            k  ON k.id  = r.kpi_id
            JOIN   dg_toolkit.domains         d  ON d.id  = k.domain_id
            JOIN   dg_toolkit.action_library  a  ON a.id  = r.base_action_id
            JOIN   dg_toolkit.domain_scores   ds ON ds.assessment_id = r.assessment_id
                                                AND ds.domain_id     = k.domain_id
            WHERE  r.assessment_id = %s
            ORDER  BY r.priority_score DESC,
                      ds.gap          DESC,
                      d.display_order ASC,
                      k.domain_order  ASC
            """,
            (assessment_id,),
        )
        rows = cur.fetchall()
        cur.close()

        # -- 3. apply optional filters in Python (simpler than dynamic SQL) ---
        results = []
        for r in rows:
            if domain_id_filter and r['domain_id'] != domain_id_filter:
                continue
            if category_filter and r['action_category'] != category_filter:
                continue
            if min_gap_filter is not None and (r['gap'] or 0) < min_gap_filter:
                continue

            results.append({
                'recommendation_id':   r['recommendation_id'],
                'kpi_id':              r['kpi_id'],
                'kpi_name':            r['kpi_name'],
                'domain_id':           r['domain_id'],
                'domain_name':         r['domain_name'],
                'action_text':         r['action_text'],
                'impact':              r['impact'],
                'effort':              r['effort'],
                'from_level':          r['from_level'],
                'to_level':            r['from_level'] + 1,
                'action_category':     r['action_category'],
                'priority_score':      float(r['priority_score']),
                'rag_narrative':       r['rag_narrative'],  # NULL until Layer 3
                'maturity_level':      r['maturity_level'],
                'target_level':        r['target_level'],
                'gap':                 r['gap'],
                'was_implemented':     r['was_implemented'],
                'implementation_rating': r['implementation_rating'],
            })

        # -- 4. group by domain for frontend convenience ----------------------
        domains: dict = {}
        for rec in results:
            did = rec['domain_id']
            if did not in domains:
                domains[did] = {
                    'domain_id':   did,
                    'domain_name': rec['domain_name'],
                    'recommendations': [],
                }
            domains[did]['recommendations'].append(rec)

        # -- 5. summary counts ------------------------------------------------
        total        = len(results)
        quick_wins   = sum(1 for r in results if r['action_category'] == 'Quick Win')
        strategic    = sum(1 for r in results if r['action_category'] == 'Strategic')
        fill_in      = sum(1 for r in results if r['action_category'] == 'Fill In')
        rag_ready    = row['layer3_status'] == 'done'

        return jsonify({
            'assessment_id': assessment_id,
            'layer2_status': row['layer2_status'],
            'layer3_status': row['layer3_status'],
            'rag_ready':     rag_ready,
            'summary': {
                'total':      total,
                'quick_wins': quick_wins,
                'strategic':  strategic,
                'fill_in':    fill_in,
            },
            'by_domain':         list(domains.values()),
            'recommendations':   results,
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()