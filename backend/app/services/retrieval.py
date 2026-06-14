from typing import List, Tuple, Dict, Optional
import numpy as np
import time

from ..database import get_db, Chunk, Document
from ..schemas import SearchResult
from .embedding import get_embedding_service
from .vector_index import get_vector_index
from ..config import settings


def mmr_filter(
    doc_vectors: np.ndarray,
    query_vector: np.ndarray,
    scores: np.ndarray,
    top_n: int = 5,
    lambda_: float = 0.7
) -> List[int]:
    if len(doc_vectors) == 0:
        return []
    if len(doc_vectors) <= top_n:
        return list(range(len(doc_vectors)))

    selected = []
    remaining = list(range(len(doc_vectors)))

    if query_vector.ndim == 1:
        query_vector = query_vector.reshape(1, -1)

    doc_norms = np.linalg.norm(doc_vectors, axis=1, keepdims=True)
    doc_norms = np.where(doc_norms == 0, 1, doc_norms)
    doc_normalized = doc_vectors / doc_norms

    for _ in range(min(top_n, len(doc_vectors))):
        if not remaining:
            break

        best_idx = -1
        best_score = -float("inf")

        for idx in remaining:
            relevance = scores[idx]

            diversity = 0.0
            if selected:
                sims = np.dot(doc_normalized[idx], doc_normalized[selected].T)
                diversity = float(np.max(sims)) if len(sims) > 0 else 0.0

            mmr_score = lambda_ * relevance - (1 - lambda_) * diversity

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        if best_idx >= 0:
            selected.append(best_idx)
            remaining.remove(best_idx)

    return selected


def search_chunks(
    knowledge_base_id: str,
    query: str,
    top_k: Optional[int] = None,
    enable_rerank: Optional[bool] = None,
    top_n: int = 5,
    return_debug: bool = False
) -> Tuple[List[SearchResult], Optional[Dict]]:
    db = next(get_db())
    embed_service = get_embedding_service()
    vector_index = get_vector_index(knowledge_base_id, embed_service.dimension)

    if top_k is None:
        top_k = settings.DEFAULT_TOP_K
    if enable_rerank is None:
        enable_rerank = True

    debug_info = {}
    start_time = time.time()

    query_vector = embed_service.encode_single(query)
    vector_time = (time.time() - start_time) * 1000

    if return_debug:
        debug_info["embedding_time_ms"] = round(vector_time, 2)

    start_search = time.time()
    chunk_ids, initial_scores = vector_index.search(query_vector, top_k=top_k)
    search_time = (time.time() - start_search) * 1000

    if return_debug:
        debug_info["search_time_ms"] = round(search_time, 2)
        debug_info["initial_recall_count"] = len(chunk_ids)
        initial_results = []
        if chunk_ids:
            chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
            chunk_map = {c.id: c for c in chunks}
            for cid, score in zip(chunk_ids, initial_scores):
                if cid in chunk_map:
                    c = chunk_map[cid]
                    doc = db.query(Document).filter(Document.id == c.document_id).first()
                    initial_results.append({
                        "chunk_id": cid,
                        "document_name": doc.filename if doc else "",
                        "score": round(float(score), 4),
                        "content_summary": c.content[:100] + "..." if len(c.content) > 100 else c.content
                    })
        debug_info["initial_recall"] = initial_results

    if not chunk_ids:
        if return_debug:
            debug_info["final_count"] = 0
        return [], debug_info if return_debug else []

    chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
    chunk_map = {c.id: c for c in chunks}

    ordered_chunks = []
    ordered_scores = []
    for cid, score in zip(chunk_ids, initial_scores):
        if cid in chunk_map:
            ordered_chunks.append(chunk_map[cid])
            ordered_scores.append(score)

    if not ordered_chunks:
        return [], debug_info if return_debug else None

    if enable_rerank and len(ordered_chunks) > 1:
        start_rerank = time.time()
        passages = [c.content for c in ordered_chunks]
        rerank_scores = embed_service.rerank(query, passages)

        alpha = 0.5
        initial_arr = np.array(ordered_scores, dtype=np.float32)
        if initial_arr.max() > initial_arr.min():
            initial_norm = (initial_arr - initial_arr.min()) / (initial_arr.max() - initial_arr.min())
        else:
            initial_norm = np.ones_like(initial_arr)

        rerank_arr = np.array(rerank_scores, dtype=np.float32)
        if rerank_arr.max() > rerank_arr.min():
            rerank_norm = (rerank_arr - rerank_arr.min()) / (rerank_arr.max() - rerank_arr.min())
        else:
            rerank_norm = np.ones_like(rerank_arr)

        combined_scores = alpha * initial_norm + (1 - alpha) * rerank_norm
        rerank_time = (time.time() - start_rerank) * 1000

        if return_debug:
            debug_info["rerank_time_ms"] = round(rerank_time, 2)
            rerank_indices = np.argsort(-combined_scores)
            reranked_debug = []
            for rank, idx in enumerate(rerank_indices[:top_n]):
                c = ordered_chunks[idx]
                doc = db.query(Document).filter(Document.id == c.document_id).first()
                reranked_debug.append({
                    "rank": rank + 1,
                    "chunk_id": c.id,
                    "document_name": doc.filename if doc else "",
                    "combined_score": round(float(combined_scores[idx]), 4),
                    "initial_score": round(float(initial_scores[idx]), 4),
                    "rerank_score": round(float(rerank_scores[idx]), 4),
                    "content_summary": c.content[:100] + "..." if len(c.content) > 100 else c.content
                })
            debug_info["reranked_top_n"] = reranked_debug
    else:
        combined_scores = np.array(ordered_scores, dtype=np.float32)

    start_mmr = time.time()
    passage_texts = [c.content for c in ordered_chunks]
    doc_vectors = embed_service.encode(passage_texts)
    selected_indices = mmr_filter(
        doc_vectors=doc_vectors,
        query_vector=query_vector,
        scores=combined_scores,
        top_n=top_n,
        lambda_=settings.MMR_LAMBDA
    )
    mmr_time = (time.time() - start_mmr) * 1000

    if return_debug:
        debug_info["mmr_time_ms"] = round(mmr_time, 2)
        mmr_debug = []
        for rank, idx in enumerate(selected_indices):
            c = ordered_chunks[idx]
            doc = db.query(Document).filter(Document.id == c.document_id).first()
            mmr_debug.append({
                "rank": rank + 1,
                "chunk_id": c.id,
                "document_name": doc.filename if doc else "",
                "final_score": round(float(combined_scores[idx]), 4),
                "content_summary": c.content[:100] + "..." if len(c.content) > 100 else c.content
            })
        debug_info["mmr_filtered"] = mmr_debug
        debug_info["final_count"] = len(selected_indices)

    results = []
    for idx in selected_indices:
        c = ordered_chunks[idx]
        doc = db.query(Document).filter(Document.id == c.document_id).first()
        results.append(SearchResult(
            chunk_id=c.id,
            document_id=c.document_id,
            document_name=doc.filename if doc else "",
            content=c.content,
            page_number=c.page_number,
            paragraph_number=c.paragraph_number,
            score=float(combined_scores[idx]),
            chunk_index=c.chunk_index
        ))

    return results, debug_info if return_debug else None
