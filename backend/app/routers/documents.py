from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import os
import threading
from datetime import datetime

from ..database import get_db, Document, KnowledgeBase, Chunk, DocumentVersionEvent, Notification
from ..schemas import DocumentResponse, TaskStatusResponse, DocumentVersionResponse
from ..config import settings
from ..services.task_queue import get_task_manager, process_document_task
from ..services.vector_index import get_vector_index

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_next_version(db: Session, kb_id: str, filename: str) -> int:
    max_version = db.query(Document).filter(
        Document.knowledge_base_id == kb_id,
        Document.filename == filename
    ).with_entities(Document.version).order_by(Document.version.desc()).first()
    return (max_version[0] + 1) if max_version else 1


def deactivate_other_versions(db: Session, kb_id: str, filename: str, active_doc_id: str):
    others = db.query(Document).filter(
        Document.knowledge_base_id == kb_id,
        Document.filename == filename,
        Document.id != active_doc_id,
        Document.is_active == True
    ).all()
    for doc in others:
        doc.is_active = False
    db.commit()


@router.get("/knowledge-base/{kb_id}", response_model=List[DocumentResponse])
def list_documents(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    docs = db.query(Document).filter(
        Document.knowledge_base_id == kb_id,
        Document.is_active == True
    ).order_by(Document.uploaded_at.desc()).all()
    return docs


@router.post("/upload", response_model=TaskStatusResponse)
async def upload_document(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    remark: Optional[str] = Form(""),
    db: Session = Depends(get_db)
):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    if not file.filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt", ".md", ".markdown"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式，仅支持PDF、DOCX、TXT和Markdown")

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"文件大小超过限制（最大{settings.MAX_FILE_SIZE // 1024 // 1024}MB）")

    version = get_next_version(db, kb_id, file.filename)

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

    existing_active = db.query(Document).filter(
        Document.knowledge_base_id == kb_id,
        Document.filename == file.filename,
        Document.is_active == True
    ).first()
    parent_id = existing_active.id if existing_active else ""

    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=file.filename,
        file_size=len(content),
        file_path=file_path,
        file_type=file_type_map.get(ext, "unknown"),
        status="parsing",
        task_id=task_id,
        version=version,
        is_active=True,
        upload_remark=remark or "",
        parent_document_id=parent_id
    )
    db.add(doc)
    deactivate_other_versions(db, kb_id, file.filename, doc_id)
    db.commit()

    thread = threading.Thread(
        target=process_document_with_version,
        args=(task_id, file_path, kb_id, doc_id, file.filename, version),
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


def process_document_with_version(task_id: str, file_path: str, knowledge_base_id: str, document_id: str, filename: str, version: int):
    process_document_task(task_id, file_path, knowledge_base_id, document_id, filename)

    from ..database import SessionLocal
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc and doc.status == "ready":
            prev_doc = db.query(Document).filter(
                Document.knowledge_base_id == knowledge_base_id,
                Document.filename == filename,
                Document.version == version - 1
            ).first()

            change_summary = {
                "added": 0,
                "deleted": 0,
                "modified": 0,
                "total_current": doc.chunk_count
            }
            change_type = "format"

            if prev_doc and prev_doc.status == "ready":
                total_chunks = max(prev_doc.chunk_count, doc.chunk_count)
                if total_chunks > 0:
                    change_ratio = abs(doc.chunk_count - prev_doc.chunk_count) / total_chunks
                    if change_ratio > 0.3:
                        change_type = "major"
                    elif change_ratio >= 0.1:
                        change_type = "minor"
                    else:
                        change_type = "format"

                change_summary["total_previous"] = prev_doc.chunk_count
                change_summary["added"] = max(0, doc.chunk_count - prev_doc.chunk_count)
                change_summary["deleted"] = max(0, prev_doc.chunk_count - doc.chunk_count)

            event = DocumentVersionEvent(
                id=str(uuid.uuid4()),
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                version=version,
                event_type="upload",
                change_summary=change_summary,
                change_type=change_type
            )
            db.add(event)
            db.commit()

            kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
            if kb and kb.enable_change_notification:
                notification = Notification(
                    id=str(uuid.uuid4()),
                    knowledge_base_id=knowledge_base_id,
                    document_id=document_id,
                    document_name=filename,
                    version=version,
                    change_summary=change_summary,
                    is_read=False
                )
                db.add(notification)
                db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()


@router.get("/{doc_id}/versions", response_model=List[DocumentVersionResponse])
def list_document_versions(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    versions = db.query(Document).filter(
        Document.knowledge_base_id == doc.knowledge_base_id,
        Document.filename == doc.filename
    ).order_by(Document.version.desc()).all()

    return versions


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

    try:
        from ..services.compare import invalidate_compare_cache_for_document
        invalidate_compare_cache_for_document(doc_id)
    except Exception:
        pass

    versions = db.query(Document).filter(
        Document.knowledge_base_id == kb_id,
        Document.filename == doc.filename
    ).order_by(Document.version.desc()).all()

    if len(versions) > 1 and doc.is_active:
        next_active = None
        for v in versions:
            if v.id != doc_id:
                next_active = v
                break
        if next_active:
            next_active.is_active = True

    db.query(DocumentVersionEvent).filter(DocumentVersionEvent.document_id == doc_id).delete()
    db.query(Notification).filter(Notification.document_id == doc_id).delete()

    db.delete(doc)
    db.commit()

    return {"message": "文档已删除"}


@router.post("/{doc_id}/rollback/{version_id}")
def rollback_to_version(doc_id: str, version_id: str, db: Session = Depends(get_db)):
    current_doc = db.query(Document).filter(Document.id == doc_id).first()
    if not current_doc:
        raise HTTPException(status_code=404, detail="当前文档不存在")

    target_doc = db.query(Document).filter(Document.id == version_id).first()
    if not target_doc:
        raise HTTPException(status_code=404, detail="目标版本不存在")

    if target_doc.knowledge_base_id != current_doc.knowledge_base_id or target_doc.filename != current_doc.filename:
        raise HTTPException(status_code=400, detail="目标版本不属于同一文档")

    if target_doc.status != "ready":
        raise HTTPException(status_code=400, detail="目标版本未处理完成，无法回退")

    kb_id = current_doc.knowledge_base_id
    filename = current_doc.filename
    from_version = current_doc.version
    to_version = target_doc.version

    all_versions = db.query(Document).filter(
        Document.knowledge_base_id == kb_id,
        Document.filename == filename
    ).all()

    for v in all_versions:
        v.is_active = (v.id == version_id)

    task_mgr = get_task_manager()
    task_id = task_mgr.create_task(target_doc.id)

    import shutil
    ext = os.path.splitext(target_doc.file_path)[1]
    new_doc_id = str(uuid.uuid4())
    kb_upload_dir = os.path.join(settings.UPLOAD_DIR, kb_id)
    os.makedirs(kb_upload_dir, exist_ok=True)
    new_saved_filename = f"{new_doc_id}{ext}"
    new_file_path = os.path.join(kb_upload_dir, new_saved_filename)
    shutil.copy2(target_doc.file_path, new_file_path)

    max_version = db.query(Document).filter(
        Document.knowledge_base_id == kb_id,
        Document.filename == filename
    ).with_entities(Document.version).order_by(Document.version.desc()).first()
    new_version = (max_version[0] + 1) if max_version else 1

    new_doc = Document(
        id=new_doc_id,
        knowledge_base_id=kb_id,
        filename=filename,
        file_size=target_doc.file_size,
        file_path=new_file_path,
        file_type=target_doc.file_type,
        status="parsing",
        task_id=task_id,
        version=new_version,
        is_active=True,
        upload_remark=f"回退到 v{to_version}",
        parent_document_id=target_doc.id
    )
    db.add(new_doc)

    for v in all_versions:
        if v.id != new_doc_id:
            v.is_active = False

    db.commit()

    thread = threading.Thread(
        target=process_rollback_task,
        args=(task_id, new_file_path, kb_id, new_doc_id, filename, new_version, from_version, to_version, target_doc),
        daemon=True
    )
    thread.start()

    return TaskStatusResponse(
        task_id=task_id,
        status="parsing",
        progress=0,
        message="正在回退版本并重新处理文档...",
        document_id=new_doc_id
    )


def process_rollback_task(task_id, file_path, knowledge_base_id, document_id, filename, new_version, from_version, to_version, target_doc):
    process_document_task(task_id, file_path, knowledge_base_id, document_id, filename)

    from ..database import SessionLocal
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc and doc.status == "ready":
            change_summary = {
                "rollback": True,
                "from_version": from_version,
                "to_version": to_version,
                "total_current": doc.chunk_count
            }

            event = DocumentVersionEvent(
                id=str(uuid.uuid4()),
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                version=new_version,
                event_type="rollback",
                change_summary=change_summary,
                change_type="format",
                rollback_from_version=from_version,
                rollback_to_version=to_version
            )
            db.add(event)
            db.commit()

            kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
            if kb and kb.enable_change_notification:
                notification = Notification(
                    id=str(uuid.uuid4()),
                    knowledge_base_id=knowledge_base_id,
                    document_id=document_id,
                    document_name=filename,
                    version=new_version,
                    change_summary=change_summary,
                    is_read=False
                )
                db.add(notification)
                db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()


@router.get("/{doc_id}/timeline")
def get_document_timeline(
    doc_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    change_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    all_versions = db.query(Document).filter(
        Document.knowledge_base_id == doc.knowledge_base_id,
        Document.filename == doc.filename
    ).all()
    version_ids = [v.id for v in all_versions]

    query = db.query(DocumentVersionEvent).filter(
        DocumentVersionEvent.document_id.in_(version_ids)
    )

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(DocumentVersionEvent.created_at >= start_dt)
        except Exception:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(DocumentVersionEvent.created_at <= end_dt)
        except Exception:
            pass

    if change_type:
        query = query.filter(DocumentVersionEvent.change_type == change_type)

    events = query.order_by(DocumentVersionEvent.created_at.desc()).all()

    result = []
    for event in events:
        version_doc = db.query(Document).filter(Document.id == event.document_id).first()
        result.append({
            "id": event.id,
            "document_id": event.document_id,
            "knowledge_base_id": event.knowledge_base_id,
            "version": event.version,
            "event_type": event.event_type,
            "change_summary": event.change_summary or {},
            "change_type": event.change_type,
            "rollback_from_version": event.rollback_from_version,
            "rollback_to_version": event.rollback_to_version,
            "created_at": event.created_at,
            "filename": version_doc.filename if version_doc else doc.filename,
            "file_size": version_doc.file_size if version_doc else 0,
            "upload_remark": version_doc.upload_remark if version_doc else ""
        })

    return result
