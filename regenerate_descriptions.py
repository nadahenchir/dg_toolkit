"""
One-time script to regenerate company_description for all existing
organizations using Groq LLM.
Use case: we recently improved the prompt and want to refresh descriptions to get better Layer 2 recommendations.
"""

import logging
import sys
import os
import time

from dotenv import load_dotenv
load_dotenv()

# add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.connection import get_connection
from app.services.layer2.normalizer import generate_company_description

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def regenerate_all():
    conn = get_connection()
    try:
        # fetch all active organizations
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, industry, industry_other, size_band, country
                FROM dg_toolkit.organizations
                WHERE deleted_at IS NULL
                ORDER BY id
            """)
            orgs = cur.fetchall()

        logger.info(f"Found {len(orgs)} organizations to process\n")

        updated = 0
        failed  = 0

        for (org_id, name, industry, industry_other, size_band, country) in orgs:
            try:
                logger.info(f"[{org_id}] Generating description for: {name} ({industry})")

                description = generate_company_description(
                    name           = name,
                    industry       = industry,
                    industry_other = industry_other,
                    size_band      = size_band or "SME",
                    country        = country or "Tunisia",
                )

                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE dg_toolkit.organizations
                        SET company_description = %s
                        WHERE id = %s
                    """, (description, org_id))
                conn.commit()

                logger.info(f"    → {description[:80]}...")
                updated += 1

                # small delay to avoid Groq rate limits
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"    ✗ Failed for {name}: {e}")
                failed += 1
                conn.rollback()

        logger.info(f"\nDone. Updated: {updated} | Failed: {failed}")

    finally:
        conn.close()


if __name__ == "__main__":
    regenerate_all()