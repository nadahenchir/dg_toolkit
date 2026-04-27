import logging
import json
from sentence_transformers import SentenceTransformer
from app.db.connection import get_connection

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SCHEMA = "dg_toolkit"


def seed_kb_from_action_library():
    """
    Reads all rows from action_library, embeds each action_text using
    all-MiniLM-L6-v2, and inserts into kb_chunks (skips already-seeded rows).
    Safe to run multiple times — will not duplicate existing chunks.
    """
    logger.info("Loading embedding model: %s", MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Fetch all action_library rows
            cur.execute(f"""
                SELECT id, kpi_id, from_level, action_text, impact, effort
                FROM {SCHEMA}.action_library
                ORDER BY id
            """)
            rows = cur.fetchall()
            logger.info("Found %d rows in action_library", len(rows))

            inserted = 0
            skipped = 0

            for row in rows:
                action_id, kpi_id, from_level, action_text, impact, effort = row

                # Skip if this source row is already in kb_chunks
                cur.execute(f"""
                    SELECT id FROM {SCHEMA}.kb_chunks
                    WHERE source_table = 'action_library'
                    AND source_id = %s
                """, (action_id,))
                if cur.fetchone():
                    skipped += 1
                    continue

                # Generate embedding
                embedding = model.encode(action_text, normalize_embeddings=True).tolist()

                # Build metadata for pre-filtering at retrieval time
                metadata = {
                    "kpi_id": kpi_id,
                    "from_level": from_level,
                    "impact": impact,
                    "effort": effort
                }

                # Insert into kb_chunks
                cur.execute(f"""
                    INSERT INTO {SCHEMA}.kb_chunks
                        (chunk_type, source_table, source_id, chunk_text, embedding, metadata)
                    VALUES
                        ('static', 'action_library', %s, %s, %s::vector, %s)
                """, (
                    action_id,
                    action_text,
                    str(embedding),
                    json.dumps(metadata)
                ))
                inserted += 1

            conn.commit()
            logger.info("Seeding complete — inserted: %d, skipped (already exist): %d", inserted, skipped)
            return {"inserted": inserted, "skipped": skipped}

    except Exception as e:
        conn.rollback()
        logger.error("Seeding failed: %s", e)
        raise
    finally:
        conn.close()