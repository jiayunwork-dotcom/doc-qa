import json
import uuid
import threading
import os
from datetime import datetime
from typing import Dict, Optional

from ..config import settings

try:
    import redis
    _redis_available = True
except ImportError:
    _redis_available = False


class TaskManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._redis = None
        self._fallback_store: Dict[str, Dict] = {}
        self._fallback_lock = threading.RLock()

        if _redis_available:
            try:
                self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_key(self, task_id: str) -> str:
        return f"task:{task_id}"

    def create_task(self, document_id: str = None) -> str:
        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "document_id": document_id or "",
            "status": "parsing",
            "progress": 0,
            "message": "正在解析文档...",
            "created_at": datetime.now().isoformat()
        }
        self._save_task(task_id, task_data)
        return task_id

    def _save_task(self, task_id: str, task_data: Dict):
        if self._redis:
            try:
                self._redis.setex(
                    self._get_key(task_id),
                    3600,
                    json.dumps(task_data, ensure_ascii=False)
                )
            except Exception:
                with self._fallback_lock:
                    self._fallback_store[task_id] = task_data
        else:
            with self._fallback_lock:
                self._fallback_store[task_id] = task_data

    def get_task(self, task_id: str) -> Optional[Dict]:
        if self._redis:
            try:
                data = self._redis.get(self._get_key(task_id))
                if data:
                    return json.loads(data)
            except Exception:
                pass
        with self._fallback_lock:
            return self._fallback_store.get(task_id)

    def update_task(self, task_id: str, status: str, progress: int, message: str, document_id: str = None):
        task = self.get_task(task_id)
        if not task:
            task = {
                "task_id": task_id,
                "document_id": document_id or "",
                "created_at": datetime.now().isoformat()
            }
        task["status"] = status
        task["progress"] = progress
        task["message"] = message
        if document_id:
            task["document_id"] = document_id
        task["updated_at"] = datetime.now().isoformat()
        self._save_task(task_id, task)

    def update_document_id(self, task_id: str, document_id: str):
        task = self.get_task(task_id) or {}
        task["document_id"] = document_id
        self._save_task(task_id, task)


def get_task_manager() -> TaskManager:
    return TaskManager.get_instance()


def process_document_task(task_id: str, file_path: str, knowledge_base_id: str, document_id: str, filename: str):
    from ..database import SessionLocal, Document, Chunk
    from .document_parser import parse_document
    from .text_chunker import chunk_document
    from .embedding import get_embedding_service
    from .vector_index import get_vector_index

    task_mgr = get_task_manager()
    db = SessionLocal()

    try:
        task_mgr.update_task(task_id, "parsing", 10, "正在解析文档内容...", document_id)

        parsed = parse_document(file_path)

        task_mgr.update_task(task_id, "chunking", 30, "正在进行文本分块...", document_id)

        kb = None
        from ..database import KnowledgeBase
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        strategy = kb.chunk_strategy if kb else settings.DEFAULT_CHUNK_STRATEGY
        chunk_size = kb.chunk_size if kb else settings.DEFAULT_CHUNK_SIZE
        overlap = kb.chunk_overlap if kb else settings.DEFAULT_CHUNK_OVERLAP

        chunks = chunk_document(
            parsed.pages,
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=overlap
        )

        task_mgr.update_task(task_id, "embedding", 50, f"正在生成向量（共{len(chunks)}个分块）...", document_id)

        embed_service = get_embedding_service()
        chunk_texts = [c.content for c in chunks]
        vectors = embed_service.encode(chunk_texts, batch_size=32)

        task_mgr.update_task(task_id, "embedding", 75, "正在写入数据库...", document_id)

        chunk_ids = []
        for i, chunk_result in enumerate(chunks):
            cid = str(uuid.uuid4())
            db_chunk = Chunk(
                id=cid,
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                content=chunk_result.content,
                chunk_index=chunk_result.chunk_index,
                page_number=chunk_result.page_number,
                paragraph_number=chunk_result.paragraph_number,
                heading_path=chunk_result.heading_path
            )
            db.add(db_chunk)
            chunk_ids.append(cid)

        db.commit()

        task_mgr.update_task(task_id, "embedding", 85, "正在建立向量索引...", document_id)

        vector_index = get_vector_index(knowledge_base_id, embed_service.dimension)
        vector_index.add_vectors(vectors, chunk_ids)
        vector_index.save()

        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "ready"
            doc.chunk_count = len(chunks)
            doc.processed_at = datetime.now()
            db.commit()

        task_mgr.update_task(task_id, "ready", 100, "文档处理完成", document_id)

    except Exception as e:
        import traceback
        error_msg = f"文档处理失败: {str(e)}"
        task_mgr.update_task(task_id, "error", 0, error_msg, document_id)
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "error"
            doc.error_message = error_msg
            db.commit()
        traceback.print_exc()
    finally:
        db.close()
