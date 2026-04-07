from flask import Blueprint, jsonify
import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
from connection import get_connection, get_cursor

scores_bp = Blueprint('scores', __name__)


# ---------------------------------------------------------------------------
# GET /api/assessments/<assessment_id>/scores
#
# Returns a single JSON envelope with three sections:
#   - overall   : assessment_scores row
#   - domains   : domain_scores joined with domains + domain_targets
#   - kpis      : kpi_scores joined with kpis + domains
#
# Only available once scoring_status = 'done'.
# ---------------------------------------------------------------------------

@scores_bp.route('/assessments/<int:assessment_id>/scores', methods=['GET'])
def get_scores(assessment_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        # -- 1. validate assessment exists and is scored -----------------------
        cur.execute(
            """
            SELECT status, scoring_status
            FROM   dg_toolkit.assessments
            WHERE  id = %s AND deleted_at IS NULL
            """,
            (assessment_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({'error': 'Assessment not found'}), 404

        if row['scoring_status'] != 'done':
            return jsonify({
                'error':          'Scores not yet available',
                'status':         row['status'],
                'scoring_status': row['scoring_status'],
            }), 409

        # -- 2. overall score --------------------------------------------------
        cur.execute(
            """
            SELECT s.overall_score,
                   s.overall_level,
                   s.domains_scored,
                   s.computed_at
            FROM   dg_toolkit.assessment_scores s
            WHERE  s.assessment_id = %s
            """,
            (assessment_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({'error': 'Score record missing — try resubmitting'}), 500

        overall = {
            'overall_score':  float(row['overall_score']),
            'overall_level':  row['overall_level'],
            'domains_scored': row['domains_scored'],
            'computed_at':    row['computed_at'].isoformat() if row['computed_at'] else None,
        }

        # -- 3. domain scores --------------------------------------------------
        cur.execute(
            """
            SELECT d.id                  AS domain_id,
                   d.name                AS domain_name,
                   d.weight              AS domain_weight,
                   d.display_order,
                   ds.raw_score,
                   ds.maturity_level,
                   ds.target_level,
                   ds.gap,
                   ds.kpis_scored,
                   ds.computed_at
            FROM   dg_toolkit.domain_scores ds
            JOIN   dg_toolkit.domains d ON d.id = ds.domain_id
            WHERE  ds.assessment_id = %s
            ORDER  BY d.display_order
            """,
            (assessment_id,),
        )
        domains = [
            {
                'domain_id':      r['domain_id'],
                'domain_name':    r['domain_name'],
                'domain_weight':  float(r['domain_weight']),
                'display_order':  r['display_order'],
                'raw_score':      float(r['raw_score']) if r['raw_score'] is not None else None,
                'maturity_level': r['maturity_level'],
                'target_level':   r['target_level'],
                'gap':            r['gap'],
                'kpis_scored':    r['kpis_scored'],
                'computed_at':    r['computed_at'].isoformat() if r['computed_at'] else None,
            }
            for r in cur.fetchall()
        ]

        # -- 4. KPI scores -----------------------------------------------------
        cur.execute(
            """
            SELECT k.id                  AS kpi_id,
                   k.name                AS kpi_name,
                   k.domain_id,
                   d.name                AS domain_name,
                   k.domain_order,
                   k.weight              AS kpi_weight,
                   k.is_inverted,
                   ks.raw_score,
                   ks.maturity_level,
                   ks.is_excluded,
                   ks.computed_at
            FROM   dg_toolkit.kpi_scores ks
            JOIN   dg_toolkit.kpis k  ON k.id  = ks.kpi_id
            JOIN   dg_toolkit.domains d ON d.id = k.domain_id
            WHERE  ks.assessment_id = %s
            ORDER  BY d.display_order, k.domain_order
            """,
            (assessment_id,),
        )
        kpis = [
            {
                'kpi_id':         r['kpi_id'],
                'kpi_name':       r['kpi_name'],
                'domain_id':      r['domain_id'],
                'domain_name':    r['domain_name'],
                'domain_order':   r['domain_order'],
                'kpi_weight':     float(r['kpi_weight']),
                'is_inverted':    r['is_inverted'],
                'raw_score':      float(r['raw_score']) if r['raw_score'] is not None else None,
                'maturity_level': r['maturity_level'],
                'is_excluded':    r['is_excluded'],
                'computed_at':    r['computed_at'].isoformat() if r['computed_at'] else None,
            }
            for r in cur.fetchall()
        ]

        # -- 5. assemble envelope ----------------------------------------------
        return jsonify({
            'assessment_id': assessment_id,
            'overall':       overall,
            'domains':       domains,
            'kpis':          kpis,
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
