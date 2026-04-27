from app.services.layer3.retriever import retrieve_chunks

results = retrieve_chunks("data ownership accountability", top_k=3)
for r in results:
    print(r["similarity"], "|", r["chunk_text"][:80])