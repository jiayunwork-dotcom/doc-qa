from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import uuid
import os
import threading
from datetime import datetime

from ..database import get_db, Document, KnowledgeBase, Chunk
from ..schemas import DocumentResponse, TaskStatusResponse
from ..config import settings
from ..services.task_queue import get_task_manager, process_document_task
from ..services.vector_index import get_vector_index

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/knowledge-base/{kb_id}", response_model=List[DocumentResponse])
def list_documents(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    docs = db.query(Document).filter(Document.knowledge_base_id == kb_id).order_by(Document.uploaded_at.desc()).all()
    return docs


@router.post("/upload", response_model=TaskStatusResponse)
async def upload_document(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    doc_count = db.query(Document).filter(Document.knowledge_base_id == kb_id).count()
    if doc_count >= settings.MAX_DOCS_PER_KB:
        raise HTTPException(status_code=400, detail=f"知识库最多只能包含{settings.MAX_DOCS_PER_KB}篇文档")

    if not file.filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt", ".md", ".markdown"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式，仅支持PDF、DOCX、TXT和Markdown")

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"文件大小超过限制（最大{settings.MAX_FILE_SIZE // 1024 // 1024}MB）")

    doc_id = str(uuid.uuid4())
    kb_upload_dir = os.path.join(settings.UPLOAD_DIR, kb_id)
    os.makedirs(kb_upload_dir, exist_ok=True)

    saved_filename = f"{doc_id}{ext}"
    file_path = os.path.join(kb_upload_dir, saved_filename)
    with open(file_path, "wb") as f:
        f.write(content)

    task_mgr = get_task_manager()
    task_id = task_mgr.create_task(doc_id)

    file_type_map = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".txt": "txt",
        ".md": "markdown",
        ".markdown": "markdown"
    }

    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=file.filename,
        file_size=len(content),
        file_path=file_path,
        file_type=file_type_map.get(ext, "unknown"),
        status="parsing",
        task_id=task_id
    )
    db.add(doc)
    db.commit()

    thread = threading.Thread(
        target=process_document_task,
        args=(task_id, file_path, kb_id, doc_id, file.filename),
        daemon=True
    )
    thread.start()

    return TaskStatusResponse(
        task_id=task_id,
        status="parsing",
        progress=0,
        message="文档已上传，正在处理...",
        document_id=doc_id
    )


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    task_mgr = get_task_manager()
    task = task_mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(
        task_id=task.get("task_id", task_id),
        status=task.get("status", "unknown"),
        progress=task.get("progress", 0),
        message=task.get("message", ""),
        document_id=task.get("document_id")
    )


@router.delete("/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    kb_id = doc.knowledge_base_id

    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception:
            pass

    chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
    chunk_ids = [c.id for c in chunks]

    if chunk_ids:
        try:
            from ..services.embedding import get_embedding_service
            embed_service = get_embedding_service()
            vector_index = get_vector_index(kb_id, embed_service.dimension)
            vector_index.mark_deleted(chunk_ids)
            vector_index.save()
        except Exception:
            pass

    db.delete(doc)
    db.commit()

    return {"message": "文档已删除"}
