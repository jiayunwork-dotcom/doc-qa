from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime

from ..database import get_db, KnowledgeBase, Document
from ..schemas import (
    KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeBaseResponse,
    DocumentResponse
)
from ..services.vector_index import remove_vector_index

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


@router.get("", response_model=List[KnowledgeBaseResponse])
def list_knowledge_bases(db: Session = Depends(get_db)):
    kbs = db.query(KnowledgeBase).order_by(KnowledgeBase.updated_at.desc()).all()
    result = []
    for kb in kbs:
        doc_count = db.query(Document).filter(Document.knowledge_base_id == kb.id).count()
        resp = KnowledgeBaseResponse.model_validate(kb)
        resp.document_count = doc_count
        result.append(resp)
    return result


@router.post("", response_model=KnowledgeBaseResponse)
def create_knowledge_base(data: KnowledgeBaseCreate, db: Session = Depends(get_db)):
    kb = KnowledgeBase(
        id=str(uuid.uuid4()),
        name=data.name,
        description=data.description,
        chunk_strategy=data.chunk_strategy,
        chunk_size=data.chunk_size,
        chunk_overlap=data.chunk_overlap,
        top_k=data.top_k,
        enable_rerank=data.enable_rerank
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    resp = KnowledgeBaseResponse.model_validate(kb)
    resp.document_count = 0
    return resp


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_base(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    doc_count = db.query(Document).filter(Document.knowledge_base_id == kb.id).count()
    resp = KnowledgeBaseResponse.model_validate(kb)
    resp.document_count = doc_count
    return resp


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(kb_id: str, data: KnowledgeBaseUpdate, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(kb, key, value)
    kb.updated_at = datetime.now()
    db.commit()
    db.refresh(kb)

    doc_count = db.query(Document).filter(Document.knowledge_base_id == kb.id).count()
    resp = KnowledgeBaseResponse.model_validate(kb)
    resp.document_count = doc_count
    return resp


@router.delete("/{kb_id}")
def delete_knowledge_base(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    import os
    import shutil
    from ..config import settings

    kb_upload_dir = os.path.join(settings.UPLOAD_DIR, kb_id)
    if os.path.exists(kb_upload_dir):
        try:
            shutil.rmtree(kb_upload_dir)
        except Exception:
            pass

    db.delete(kb)
    db.commit()
    remove_vector_index(kb_id)

    return {"message": "知识库已删除"}
