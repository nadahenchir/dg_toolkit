import logging
from sentence_transformers import SentenceTransformer
from app.db.connection import get_connection

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SCHEMA = "dg_toolkit"

# Singleton — load model once, reuse across calls
_model = None

def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def retrieve_chunks(query_text: str, top_k: int = 5, filters: dict = None) -> list[dict]:
    """
    Embeds query_text and retrieves the top_k most similar chunks from kb_chunks
    using pgvector cosine similarity.

    Optional filters (applied as metadata pre-filters):
        - kpi_id: int
        - from_level: int

    Returns a list of dicts with keys: id, chunk_text, metadata, similarity
    """
    model = _get_model()
    query_embedding = model.encode(query_text, normalize_embeddings=True).tolist()

    # Build optional WHERE clauses from filters
    filter_clauses = []
    filter_values = []

    if filters:
        if "kpi_id" in filters:
            filter_clauses.append("(metadata->>'kpi_id')::int = %s")
            filter_values.append(filters["kpi_id"])
        if "from_level" in filters:
            filter_clauses.append("(metadata->>'from_level')::int = %s")
            filter_values.append(filters["from_level"])

    where_sql = ""
    if filter_clauses:
        where_sql = "WHERE " + " AND ".join(filter_clauses)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            query_sql = f"""
                SELECT
                    id,
                    chunk_text,
                    metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {SCHEMA}.kb_chunks
                {where_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            params = [str(query_embedding)] + filter_values + [str(query_embedding), top_k]
            cur.execute(query_sql, params)
            rows = cur.fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "chunk_text": row[1],
                    "metadata": row[2],
                    "similarity": round(float(row[3]), 4)
                })

            logger.debug("Retrieved %d chunks for query: %.60s...", len(results), query_text)
            return results

    except Exception as e:
        logger.error("Retrieval failed: %s", e)
        raise
    finally:
        conn.close()