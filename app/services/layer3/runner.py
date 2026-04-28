import logging
import os
from openai import OpenAI
from app.db.connection import get_connection
from app.services.layer3.retriever import retrieve_chunks
from app.services.layer3.prompter import build_prompt

logger = logging.getLogger(__name__)

SCHEMA = "dg_toolkit"
OPENAI_MODEL = "gpt-4o-mini"


def get_similar_org_implementations(cur, kpi_id: int, assessment_id: int, industry: str) -> list[dict]:
    """
    Fetches top rated implementations of this KPI from similar past organizations.
    Filters by same industry first, falls back to all industries if fewer than 2 results.
    """
    def fetch(industry_filter):
        industry_clause = "AND o.industry = %s" if industry_filter else ""
        params = [kpi_id, assessment_id]
        if industry_filter:
            params.append(industry_filter)
        params.append(3)

        cur.execute(f"""
            SELECT
                o.industry,
                o.size_band,
                ks.maturity_level,
                r.implementation_rating,
                r.implementation_notes
            FROM {SCHEMA}.recommendations r
            JOIN {SCHEMA}.assessments a     ON a.id = r.assessment_id
            JOIN {SCHEMA}.organizations o   ON o.id = a.organization_id
            JOIN {SCHEMA}.kpi_scores ks     ON ks.assessment_id = r.assessment_id
                                           AND ks.kpi_id = r.kpi_id
            WHERE r.kpi_id = %s
            AND r.assessment_id != %s
            AND r.was_implemented = true
            AND r.implementation_rating >= 4
            AND r.implementation_notes IS NOT NULL
            AND r.implementation_notes != ''
            {industry_clause}
            ORDER BY r.implementation_rating DESC
            LIMIT %s
        """, params)
        return cur.fetchall()

    rows = fetch(industry)
    if len(rows) < 2:
        rows = fetch(None)  # fallback: all industries

    results = []
    for row in rows:
        ind, size, maturity, rating, notes = row
        results.append({
            "industry":  ind,
            "size":      size,
            "maturity":  maturity,
            "rating":    rating,
            "notes":     notes or ""
        })
    return results


def run_layer3(assessment_id: int) -> dict:
    """
    Orchestrates the full RAG pipeline for all pending recommendations
    of a given assessment.

    For each recommendation where rag_status = 'pending':
        1. Retrieve top-5 relevant chunks from kb_chunks
        2. Fetch similar org implementations (learning loop)
        3. Build prompt with org context + retrieved chunks + similarity data
        4. Generate rag_narrative via OpenAI
        5. Write narrative back to recommendations table
        6. Update rag_status to 'done' (or 'failed' on error)

    Returns a summary dict with counts of done/failed recommendations.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    conn = get_connection()
    try:
        with conn.cursor() as cur:

            # Load org context for this assessment
            cur.execute(f"""
                SELECT
                    o.industry,
                    o.size_band,
                    o.name,
                    o.industry_other,
                    a.id AS assessment_id
                FROM {SCHEMA}.assessments a
                JOIN {SCHEMA}.organizations o ON o.id = a.organization_id
                WHERE a.id = %s
            """, (assessment_id,))
            assessment_row = cur.fetchone()

            if not assessment_row:
                raise ValueError(f"Assessment {assessment_id} not found")

            industry, size_band, org_name, industry_other, _ = assessment_row
            if industry == 'Other' and industry_other:
                industry = industry_other

            # Mark assessment layer3 as running
            cur.execute(f"""
                UPDATE {SCHEMA}.assessments
                SET layer3_status = 'running'
                WHERE id = %s
            """, (assessment_id,))
            conn.commit()

            # Load all pending recommendations for this assessment
            cur.execute(f"""
                SELECT
                    r.id              AS rec_id,
                    r.kpi_id,
                    k.name            AS kpi_name,
                    d.name            AS domain_name,
                    al.action_text,
                    ks.maturity_level
                FROM {SCHEMA}.recommendations r
                JOIN {SCHEMA}.kpis k            ON k.id = r.kpi_id
                JOIN {SCHEMA}.domains d         ON d.id = k.domain_id
                JOIN {SCHEMA}.action_library al ON al.id = r.base_action_id
                JOIN {SCHEMA}.kpi_scores ks     ON ks.kpi_id = r.kpi_id
                                               AND ks.assessment_id = %s
                WHERE r.assessment_id = %s
                AND r.rag_status = 'pending'
                ORDER BY r.id
            """, (assessment_id, assessment_id))
            recommendations = cur.fetchall()

            logger.info(
                "Layer 3 starting for assessment %d — %d pending recommendations",
                assessment_id, len(recommendations)
            )

            done = 0
            failed = 0

            for rec in recommendations:
                rec_id, kpi_id, kpi_name, domain_name, action_text, maturity_level = rec

                # Mark as running
                cur.execute(f"""
                    UPDATE {SCHEMA}.recommendations
                    SET rag_status = 'running'
                    WHERE id = %s
                """, (rec_id,))
                conn.commit()

                try:
                    # Step 1 — Retrieve relevant chunks
                    query_text = f"{kpi_name}: {action_text}"
                    chunks = retrieve_chunks(
                        query_text=query_text,
                        top_k=5,
                        filters={"kpi_id": kpi_id}
                    )
                    if not chunks:
                        chunks = retrieve_chunks(query_text=query_text, top_k=5)

                    # Step 2 — Fetch similar org implementations
                    similar_orgs = get_similar_org_implementations(
                        cur, kpi_id, assessment_id, industry
                    )

                    # Step 3 — Build prompt
                    org_context = {
                        "industry":       industry,
                        "size":           size_band,
                        "maturity_level": maturity_level,
                        "domain_name":    domain_name,
                        "org_name":       org_name
                    }
                    messages = build_prompt(
                        kpi_name=kpi_name,
                        action_text=action_text,
                        org_context=org_context,
                        retrieved_chunks=chunks,
                        similar_orgs=similar_orgs
                    )

                    # Step 4 — Generate narrative
                    response = client.chat.completions.create(
                        model=OPENAI_MODEL,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=450
                    )
                    narrative = response.choices[0].message.content.strip()

                    # Step 5 — Write back to DB
                    cur.execute(f"""
                        UPDATE {SCHEMA}.recommendations
                        SET rag_narrative = %s,
                            rag_status   = 'done'
                        WHERE id = %s
                    """, (narrative, rec_id))
                    conn.commit()

                    done += 1
                    logger.info("rec_id=%d done (%s)", rec_id, kpi_name)

                except Exception as e:
                    conn.rollback()
                    cur.execute(f"""
                        UPDATE {SCHEMA}.recommendations
                        SET rag_status = 'failed'
                        WHERE id = %s
                    """, (rec_id,))
                    conn.commit()
                    failed += 1
                    logger.error("rec_id=%d failed: %s", rec_id, e)

            # Mark assessment layer3 as done (or partial if some failed)
            final_status = 'done' if failed == 0 else 'partial'
            cur.execute(f"""
                UPDATE {SCHEMA}.assessments
                SET layer3_status = %s
                WHERE id = %s
            """, (final_status, assessment_id))
            conn.commit()

            summary = {"assessment_id": assessment_id, "done": done, "failed": failed}
            logger.info("Layer 3 complete: %s", summary)
            return summary

    except Exception as e:
        try:
            conn2 = get_connection()
            with conn2.cursor() as c:
                c.execute(f"""
                    UPDATE {SCHEMA}.assessments
                    SET layer3_status = 'failed'
                    WHERE id = %s
                """, (assessment_id,))
                conn2.commit()
            conn2.close()
        except Exception:
            pass
        logger.error("Layer 3 runner failed: %s", e)
        raise
    finally:
        conn.close()