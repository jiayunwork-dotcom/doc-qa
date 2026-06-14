import numpy as np
import uuid
import threading
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher

from ..config import settings
from ..database import SessionLocal, Document, Chunk, CompareTask
from .vector_index import get_vector_index
from .task_queue import get_task_manager


SIMILARITY_THRESHOLD_UNIQUE = 0.6
SIMILARITY_THRESHOLD_DIFF = 0.85


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    if np.linalg.norm(v1) == 0 or np.linalg.norm(v2) == 0:
        return 0.0
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


def compute_chunk_similarities(
    chunks_a: List[Chunk],
    chunks_b: List[Chunk],
    vectors_a: Dict[str, np.ndarray],
    vectors_b: Dict[str, np.ndarray]
) -> Tuple[Dict[str, Tuple[str, float]], Dict[str, Tuple[str, float]]]:
    best_match_a: Dict[str, Tuple[str, float]] = {}
    best_match_b: Dict[str, Tuple[str, float]] = {}

    for ca in chunks_a:
        best_score = 0.0
        best_id = ""
        va = vectors_a.get(ca.id)
        if va is None:
            best_match_a[ca.id] = ("", 0.0)
            continue
        for cb in chunks_b:
            vb = vectors_b.get(cb.id)
            if vb is None:
                continue
            score = cosine_similarity(va, vb)
            if score > best_score:
                best_score = score
                best_id = cb.id
        best_match_a[ca.id] = (best_id, best_score)

    for cb in chunks_b:
        best_score = 0.0
        best_id = ""
        vb = vectors_b.get(cb.id)
        if vb is None:
            best_match_b[cb.id] = ("", 0.0)
            continue
        for ca in chunks_a:
            va = vectors_a.get(ca.id)
            if va is None:
                continue
            score = cosine_similarity(va, vb)
            if score > best_score:
                best_score = score
                best_id = ca.id
        best_match_b[cb.id] = (best_id, best_score)

    return best_match_a, best_match_b


def build_diff_html(text_a: str, text_b: str) -> Dict[str, str]:
    matcher = SequenceMatcher(None, text_a, text_b)
    opcodes = matcher.get_opcodes()

    html_a = []
    html_b = []

    for tag, i1, i2, j1, j2 in opcodes:
        seg_a = text_a[i1:i2]
        seg_b = text_b[j1:j2]
        if tag == "equal":
            html_a.append(f'<span class="diff-equal">{seg_a}</span>')
            html_b.append(f'<span class="diff-equal">{seg_b}</span>')
        elif tag == "replace":
            html_a.append(f'<span class="diff-del">{seg_a}</span>')
            html_b.append(f'<span class="diff-add">{seg_b}</span>')
        elif tag == "delete":
            html_a.append(f'<span class="diff-del">{seg_a}</span>')
        elif tag == "insert":
            html_b.append(f'<span class="diff-add">{seg_b}</span>')

    return {"diff_a": "".join(html_a), "diff_b": "".join(html_b)}


def compare_documents(
    kb_id: str,
    doc_a_id: str,
    doc_b_id: str,
    task_id: str
) -> Dict:
    task_mgr = get_task_manager()
    db = SessionLocal()

    try:
        task_mgr.update_task(task_id, "loading", 10, "正在加载文档数据...")

        doc_a = db.query(Document).filter(Document.id == doc_a_id).first()
        doc_b = db.query(Document).filter(Document.id == doc_b_id).first()

        if not doc_a or not doc_b:
            raise ValueError("文档不存在")

        chunks_a = db.query(Chunk).filter(
            Chunk.document_id == doc_a_id,
            Chunk.is_deleted == False
        ).order_by(Chunk.chunk_index).all()

        chunks_b = db.query(Chunk).filter(
            Chunk.document_id == doc_b_id,
            Chunk.is_deleted == False
        ).order_by(Chunk.chunk_index).all()

        task_mgr.update_task(task_id, "loading", 30, "正在加载嵌入向量...")

        from .embedding import get_embedding_service
        embed_service = get_embedding_service()
        vector_index = get_vector_index(kb_id, embed_service.dimension)

        chunk_ids_a = [c.id for c in chunks_a]
        chunk_ids_b = [c.id for c in chunks_b]

        vectors_a = vector_index.get_vectors_by_ids(chunk_ids_a)
        vectors_b = vector_index.get_vectors_by_ids(chunk_ids_b)

        missing_a = [cid for cid in chunk_ids_a if cid not in vectors_a]
        missing_b = [cid for cid in chunk_ids_b if cid not in vectors_b]

        if missing_a:
            missing_chunks_a = [c for c in chunks_a if c.id in missing_a]
            texts_a = [c.content for c in missing_chunks_a]
            if texts_a:
                new_vecs_a = embed_service.encode(texts_a, batch_size=32)
                for i, c in enumerate(missing_chunks_a):
                    vectors_a[c.id] = new_vecs_a[i]

        if missing_b:
            missing_chunks_b = [c for c in chunks_b if c.id in missing_b]
            texts_b = [c.content for c in missing_chunks_b]
            if texts_b:
                new_vecs_b = embed_service.encode(texts_b, batch_size=32)
                for i, c in enumerate(missing_chunks_b):
                    vectors_b[c.id] = new_vecs_b[i]

        task_mgr.update_task(task_id, "computing", 50, "正在计算语义相似度...")

        best_match_a, best_match_b = compute_chunk_similarities(
            chunks_a, chunks_b, vectors_a, vectors_b
        )

        task_mgr.update_task(task_id, "analyzing", 75, "正在分析对比结果...")

        unique_a = []
        unique_b = []
        similar_pairs = []
        repeated_pairs = []

        chunk_a_map = {c.id: c for c in chunks_a}
        chunk_b_map = {c.id: c for c in chunks_b}

        matched_b_ids = set()

        for ca in chunks_a:
            best_b_id, score = best_match_a.get(ca.id, ("", 0.0))
            if score < SIMILARITY_THRESHOLD_UNIQUE:
                unique_a.append({
                    "chunk_id": ca.id,
                    "content": ca.content,
                    "page_number": ca.page_number,
                    "chunk_index": ca.chunk_index,
                    "similarity": round(score, 4)
                })
            elif score < SIMILARITY_THRESHOLD_DIFF:
                cb = chunk_b_map.get(best_b_id)
                diff = build_diff_html(ca.content, cb.content) if cb else {"diff_a": ca.content, "diff_b": ""}
                similar_pairs.append({
                    "chunk_a": {
                        "chunk_id": ca.id,
                        "content": ca.content,
                        "page_number": ca.page_number,
                        "chunk_index": ca.chunk_index
                    },
                    "chunk_b": {
                        "chunk_id": best_b_id,
                        "content": cb.content if cb else "",
                        "page_number": cb.page_number if cb else None,
                        "chunk_index": cb.chunk_index if cb else 0
                    },
                    "similarity": round(score, 4),
                    "diff_a": diff["diff_a"],
                    "diff_b": diff["diff_b"]
                })
                matched_b_ids.add(best_b_id)
            else:
                cb = chunk_b_map.get(best_b_id)
                repeated_pairs.append({
                    "chunk_a": {
                        "chunk_id": ca.id,
                        "content": ca.content,
                        "page_number": ca.page_number,
                        "chunk_index": ca.chunk_index
                    },
                    "chunk_b": {
                        "chunk_id": best_b_id,
                        "content": cb.content if cb else "",
                        "page_number": cb.page_number if cb else None,
                        "chunk_index": cb.chunk_index if cb else 0
                    },
                    "similarity": round(score, 4)
                })
                matched_b_ids.add(best_b_id)

        for cb in chunks_b:
            if cb.id in matched_b_ids:
                continue
            best_a_id, score = best_match_b.get(cb.id, ("", 0.0))
            if score < SIMILARITY_THRESHOLD_UNIQUE:
                unique_b.append({
                    "chunk_id": cb.id,
                    "content": cb.content,
                    "page_number": cb.page_number,
                    "chunk_index": cb.chunk_index,
                    "similarity": round(score, 4)
                })

        task_mgr.update_task(task_id, "saving", 95, "正在保存结果...")

        result = {
            "doc_a": {
                "id": doc_a.id,
                "filename": doc_a.filename,
                "chunk_count": len(chunks_a),
                "unique_count": len(unique_a)
            },
            "doc_b": {
                "id": doc_b.id,
                "filename": doc_b.filename,
                "chunk_count": len(chunks_b),
                "unique_count": len(unique_b)
            },
            "summary": {
                "total_chunks_a": len(chunks_a),
                "total_chunks_b": len(chunks_b),
                "unique_a_count": len(unique_a),
                "unique_b_count": len(unique_b),
                "similar_count": len(similar_pairs),
                "repeated_count": len(repeated_pairs)
            },
            "unique_a": unique_a,
            "unique_b": unique_b,
            "similar_pairs": similar_pairs,
            "repeated_pairs": repeated_pairs,
            "thresholds": {
                "unique": SIMILARITY_THRESHOLD_UNIQUE,
                "diff": SIMILARITY_THRESHOLD_DIFF
            }
        }

        compare_task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
        if compare_task:
            compare_task.status = "completed"
            compare_task.progress = 100
            compare_task.message = "对比分析完成"
            compare_task.result = result
            compare_task.completed_at = datetime.now()
            db.commit()

        task_mgr.update_task(task_id, "completed", 100, "对比分析完成")

        return result

    except Exception as e:
        import traceback
        error_msg = f"对比分析失败: {str(e)}"
        task_mgr.update_task(task_id, "error", 0, error_msg)
        compare_task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
        if compare_task:
            compare_task.status = "error"
            compare_task.error_message = error_msg
            db.commit()
        traceback.print_exc()
        raise
    finally:
        db.close()


def process_compare_task(task_id: str, kb_id: str, doc_a_id: str, doc_b_id: str):
    try:
        compare_documents(kb_id, doc_a_id, doc_b_id, task_id)
    except Exception as e:
        pass


def start_compare_task(kb_id: str, doc_a_id: str, doc_b_id: str) -> str:
    task_mgr = get_task_manager()
    task_id = task_mgr.create_task()
    task_mgr.update_task(task_id, "pending", 0, "正在排队等待...")

    db = SessionLocal()
    try:
        doc_a = db.query(Document).filter(Document.id == doc_a_id).first()
        doc_b = db.query(Document).filter(Document.id == doc_b_id).first()

        doc_a_version = str(doc_a.processed_at.timestamp()) if doc_a and doc_a.processed_at else ""
        doc_b_version = str(doc_b.processed_at.timestamp()) if doc_b and doc_b.processed_at else ""

        compare_task = CompareTask(
            id=task_id,
            knowledge_base_id=kb_id,
            doc_a_id=doc_a_id,
            doc_b_id=doc_b_id,
            status="pending",
            progress=0,
            message="正在排队等待...",
            doc_a_version=doc_a_version,
            doc_b_version=doc_b_version
        )
        db.add(compare_task)
        db.commit()
    finally:
        db.close()

    thread = threading.Thread(
        target=process_compare_task,
        args=(task_id, kb_id, doc_a_id, doc_b_id),
        daemon=True
    )
    thread.start()

    return task_id


def find_cached_compare(kb_id: str, doc_a_id: str, doc_b_id: str) -> Optional[CompareTask]:
    db = SessionLocal()
    try:
        doc_a = db.query(Document).filter(Document.id == doc_a_id).first()
        doc_b = db.query(Document).filter(Document.id == doc_b_id).first()
        if not doc_a or not doc_b:
            return None

        doc_a_version = str(doc_a.processed_at.timestamp()) if doc_a.processed_at else ""
        doc_b_version = str(doc_b.processed_at.timestamp()) if doc_b.processed_at else ""

        task = db.query(CompareTask).filter(
            CompareTask.knowledge_base_id == kb_id,
            CompareTask.status == "completed",
            CompareTask.doc_a_id == doc_a_id,
            CompareTask.doc_b_id == doc_b_id,
            CompareTask.doc_a_version == doc_a_version,
            CompareTask.doc_b_version == doc_b_version
        ).order_by(CompareTask.completed_at.desc()).first()

        return task
    finally:
        db.close()


def get_compare_task_from_db(task_id: str) -> Optional[CompareTask]:
    db = SessionLocal()
    try:
        task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
        return task
    finally:
        db.close()


def invalidate_compare_cache_for_document(doc_id: str):
    db = SessionLocal()
    try:
        tasks = db.query(CompareTask).filter(
            (CompareTask.doc_a_id == doc_id) | (CompareTask.doc_b_id == doc_id)
        ).all()
        for task in tasks:
            task.status = "stale"
        db.commit()
    finally:
        db.close()
