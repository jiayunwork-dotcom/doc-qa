from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from ..database import get_db, Document, KnowledgeBase, CompareTask
from ..schemas import CompareRequest, CompareTaskResponse, CompareResultResponse
from ..services.compare import (
    start_compare_task,
    find_cached_compare,
    get_compare_task_from_db
)
from ..services.task_queue import get_task_manager

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.post("", response_model=CompareTaskResponse)
def create_compare_task(request: CompareRequest, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == request.knowledge_base_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    doc_a = db.query(Document).filter(Document.id == request.doc_a_id).first()
    doc_b = db.query(Document).filter(Document.id == request.doc_b_id).first()

    if not doc_a or not doc_b:
        raise HTTPException(status_code=400, detail="文档不存在")

    if doc_a.knowledge_base_id != request.knowledge_base_id or doc_b.knowledge_base_id != request.knowledge_base_id:
        raise HTTPException(status_code=400, detail="两篇文档必须属于同一个知识库")

    if doc_a.status != "ready" or doc_b.status != "ready":
        raise HTTPException(status_code=400, detail="两篇文档都必须是已处理完成的状态")

    if request.doc_a_id == request.doc_b_id:
        raise HTTPException(status_code=400, detail="不能选择同一篇文档进行对比")

    cached = find_cached_compare(request.knowledge_base_id, request.doc_a_id, request.doc_b_id)
    if cached:
        return CompareTaskResponse(
            task_id=cached.id,
            status="completed",
            progress=100,
            message="对比结果已缓存"
        )

    task_id = start_compare_task(request.knowledge_base_id, request.doc_a_id, request.doc_b_id)

    return CompareTaskResponse(
        task_id=task_id,
        status="pending",
        progress=0,
        message="对比任务已创建"
    )


@router.get("/task/{task_id}", response_model=CompareResultResponse)
def get_compare_result(task_id: str, db: Session = Depends(get_db)):
    task_mgr = get_task_manager()
    mem_task = task_mgr.get_task(task_id)

    if mem_task and mem_task.get("status") not in ("completed", "error"):
        return CompareResultResponse(
            task_id=task_id,
            status=mem_task.get("status", "pending"),
            progress=mem_task.get("progress", 0),
            message=mem_task.get("message", "")
        )

    task = get_compare_task_from_db(task_id)
    if not task:
        if mem_task:
            return CompareResultResponse(
                task_id=task_id,
                status=mem_task.get("status", "pending"),
                progress=mem_task.get("progress", 0),
                message=mem_task.get("message", "")
            )
        raise HTTPException(status_code=404, detail="任务不存在")

    result = task.result or {}

    response = CompareResultResponse(
        task_id=task.id,
        status=task.status,
        progress=task.progress,
        message=task.message,
        error_message=task.error_message or ""
    )

    if task.status == "completed" and result:
        response.doc_a = result.get("doc_a")
        response.doc_b = result.get("doc_b")
        response.summary = result.get("summary")
        response.unique_a = result.get("unique_a", [])
        response.unique_b = result.get("unique_b", [])
        response.similar_pairs = result.get("similar_pairs", [])
        response.repeated_pairs = result.get("repeated_pairs", [])
        response.thresholds = result.get("thresholds")

    return response
