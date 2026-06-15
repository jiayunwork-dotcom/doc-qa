from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
import io
import itertools
import threading
import uuid

from ..database import get_db, SessionLocal, Document, KnowledgeBase, CompareTask, CompareIgnore, BatchCompareTask, Chunk
from ..schemas import (
    CompareRequest, CompareTaskResponse, CompareResultResponse,
    IgnorePairRequest, IgnorePairResponse,
    BatchCompareRequest, BatchCompareTaskResponse, BatchCompareOverviewResponse, BatchCompareMatrixCell
)
from ..services.compare import (
    start_compare_task,
    find_cached_compare,
    get_compare_task_from_db
)
from ..services.task_queue import get_task_manager

router = APIRouter(prefix="/api/compare", tags=["compare"])


def get_ignored_pairs(db: Session, doc_a_id: str, doc_b_id: str) -> List[CompareIgnore]:
    return db.query(CompareIgnore).filter(
        ((CompareIgnore.doc_a_id == doc_a_id) & (CompareIgnore.doc_b_id == doc_b_id)) |
        ((CompareIgnore.doc_a_id == doc_b_id) & (CompareIgnore.doc_b_id == doc_a_id))
    ).all()


def is_pair_ignored(ignored_list: List[CompareIgnore], chunk_a_id: str, chunk_b_id: str) -> bool:
    for ig in ignored_list:
        if (ig.chunk_a_id == chunk_a_id and ig.chunk_b_id == chunk_b_id) or \
           (ig.chunk_a_id == chunk_b_id and ig.chunk_b_id == chunk_a_id):
            return True
    return False


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
def get_compare_result(task_id: str, include_ignored: bool = False, db: Session = Depends(get_db)):
    task_mgr = get_task_manager()
    mem_task = task_mgr.get_task(task_id)

    if mem_task and mem_task.get("status") not in ("completed", "error"):
        return CompareResultResponse(
            task_id=task_id,
            status=mem_task.get("status", "pending"),
            progress=mem_task.get("progress", 0),
            message=mem_task.get("message", "")
        )

    task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
    if not task:
        if mem_task:
            return CompareResultResponse(
                task_id=task_id,
                status=mem_task.get("status", "pending"),
                progress=mem_task.get("progress", 0),
                message=mem_task.get("message", "")
            )
        raise HTTPException(status_code=404, detail="任务不存在")

    import copy
    result = copy.deepcopy(task.result or {})
    if isinstance(result, str):
        import json
        try:
            result = json.loads(result)
        except Exception:
            result = {}

    try:
        ignored_list = get_ignored_pairs(db, task.doc_a_id, task.doc_b_id)
    except Exception as e:
        print(f"[Ignore] 查询忽略列表失败: {e}")
        ignored_list = []
    ignored_pairs = [{"chunk_a_id": ig.chunk_a_id, "chunk_b_id": ig.chunk_b_id} for ig in ignored_list]
    print(f"[Ignore] task_id={task_id}, include_ignored={include_ignored}, ignored_count={len(ignored_list)}, doc_a={task.doc_a_id}, doc_b={task.doc_b_id}")

    if task.status == "completed" and result:
        if not include_ignored and ignored_list:
            original_similar = len(result.get("similar_pairs", []))
            original_repeated = len(result.get("repeated_pairs", []))
            
            result["similar_pairs"] = [
                p for p in result.get("similar_pairs", [])
                if not is_pair_ignored(ignored_list, str(p.get("chunk_a", {}).get("chunk_id", "")), str(p.get("chunk_b", {}).get("chunk_id", "")))
            ]
            result["repeated_pairs"] = [
                p for p in result.get("repeated_pairs", [])
                if not is_pair_ignored(ignored_list, str(p.get("chunk_a", {}).get("chunk_id", "")), str(p.get("chunk_b", {}).get("chunk_id", "")))
            ]
            summary = result.get("summary", {})
            summary["similar_count"] = len(result["similar_pairs"])
            summary["repeated_count"] = len(result["repeated_pairs"])
            result["summary"] = summary
            
            print(f"[Ignore] 过滤前: similar={original_similar}, repeated={original_repeated}")
            print(f"[Ignore] 过滤后: similar={len(result['similar_pairs'])}, repeated={len(result['repeated_pairs'])}")

        response = CompareResultResponse(
            task_id=task.id,
            status=task.status,
            progress=task.progress,
            message=task.message,
            error_message=task.error_message or "",
            doc_a=result.get("doc_a"),
            doc_b=result.get("doc_b"),
            summary=result.get("summary"),
            unique_a=result.get("unique_a", []),
            unique_b=result.get("unique_b", []),
            similar_pairs=result.get("similar_pairs", []),
            repeated_pairs=result.get("repeated_pairs", []),
            thresholds=result.get("thresholds"),
            ignored_pairs=ignored_pairs
        )
    else:
        response = CompareResultResponse(
            task_id=task.id,
            status=task.status,
            progress=task.progress,
            message=task.message,
            error_message=task.error_message or "",
            ignored_pairs=ignored_pairs
        )

    return response


@router.post("/ignore", response_model=IgnorePairResponse)
def add_ignore_pair(request: IgnorePairRequest, db: Session = Depends(get_db)):
    task = db.query(CompareTask).filter(CompareTask.id == request.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        from ..database import Base, engine
        CompareIgnore.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"[Ignore] 确保表存在时出错: {e}")

    print(f"[Ignore] 添加忽略: task_id={request.task_id}, chunk_a={request.chunk_a_id}, chunk_b={request.chunk_b_id}")
    print(f"[Ignore] task.doc_a_id={task.doc_a_id}, task.doc_b_id={task.doc_b_id}")

    existing = db.query(CompareIgnore).filter(
        ((CompareIgnore.doc_a_id == task.doc_a_id) & (CompareIgnore.doc_b_id == task.doc_b_id) &
         (CompareIgnore.chunk_a_id == request.chunk_a_id) & (CompareIgnore.chunk_b_id == request.chunk_b_id)) |
        ((CompareIgnore.doc_a_id == task.doc_b_id) & (CompareIgnore.doc_b_id == task.doc_a_id) &
         (CompareIgnore.chunk_a_id == request.chunk_b_id) & (CompareIgnore.chunk_b_id == request.chunk_a_id))
    ).first()

    if existing:
        print(f"[Ignore] 忽略记录已存在: id={existing.id}")
        return IgnorePairResponse(
            id=existing.id,
            doc_a_id=existing.doc_a_id,
            doc_b_id=existing.doc_b_id,
            chunk_a_id=existing.chunk_a_id,
            chunk_b_id=existing.chunk_b_id,
            ignore_type=existing.ignore_type,
            created_at=existing.created_at
        )

    ignore = CompareIgnore(
        doc_a_id=task.doc_a_id,
        doc_b_id=task.doc_b_id,
        chunk_a_id=request.chunk_a_id,
        chunk_b_id=request.chunk_b_id,
        ignore_type=request.ignore_type
    )
    db.add(ignore)
    try:
        db.commit()
        db.refresh(ignore)
    except Exception as e:
        db.rollback()
        print(f"[Ignore] 保存忽略记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存忽略记录失败: {str(e)}")
    
    verify = db.query(CompareIgnore).filter(CompareIgnore.id == ignore.id).first()
    if not verify:
        print(f"[Ignore] 警告: 提交后未找到记录 id={ignore.id}")
    else:
        print(f"[Ignore] 忽略记录已保存并验证: id={ignore.id}, chunk_a={ignore.chunk_a_id}, chunk_b={ignore.chunk_b_id}")

    return IgnorePairResponse(
        id=ignore.id,
        doc_a_id=ignore.doc_a_id,
        doc_b_id=ignore.doc_b_id,
        chunk_a_id=ignore.chunk_a_id,
        chunk_b_id=ignore.chunk_b_id,
        ignore_type=ignore.ignore_type,
        created_at=ignore.created_at
    )


@router.delete("/ignore/{task_id}/{chunk_a_id}/{chunk_b_id}")
def remove_ignore_pair(task_id: str, chunk_a_id: str, chunk_b_id: str, db: Session = Depends(get_db)):
    task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    ignore = db.query(CompareIgnore).filter(
        ((CompareIgnore.doc_a_id == task.doc_a_id) & (CompareIgnore.doc_b_id == task.doc_b_id) &
         (CompareIgnore.chunk_a_id == chunk_a_id) & (CompareIgnore.chunk_b_id == chunk_b_id)) |
        ((CompareIgnore.doc_a_id == task.doc_b_id) & (CompareIgnore.doc_b_id == task.doc_a_id) &
         (CompareIgnore.chunk_a_id == chunk_b_id) & (CompareIgnore.chunk_b_id == chunk_a_id))
    ).first()

    if not ignore:
        raise HTTPException(status_code=404, detail="忽略记录不存在")

    db.delete(ignore)
    db.commit()
    return {"success": True}


@router.get("/ignore/list/{task_id}")
def list_ignore_pairs(task_id: str, db: Session = Depends(get_db)):
    task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    ignored = get_ignored_pairs(db, task.doc_a_id, task.doc_b_id)
    return [
        {
            "id": ig.id,
            "chunk_a_id": ig.chunk_a_id,
            "chunk_b_id": ig.chunk_b_id,
            "ignore_type": ig.ignore_type,
            "created_at": ig.created_at
        }
        for ig in ignored
    ]


def process_batch_compare(batch_task_id: str, kb_id: str, doc_ids: List[str]):
    db = SessionLocal()
    try:
        batch_task = db.query(BatchCompareTask).filter(BatchCompareTask.id == batch_task_id).first()
        if not batch_task:
            return

        pairs = list(itertools.combinations(doc_ids, 2))
        batch_task.total_pairs = len(pairs)
        batch_task.completed_pairs = 0
        batch_task.status = "processing"
        batch_task.message = "正在批量对比..."
        db.commit()

        task_mgr = get_task_manager()
        results = []

        for idx, (doc_a_id, doc_b_id) in enumerate(pairs):
            try:
                cached = find_cached_compare(kb_id, doc_a_id, doc_b_id)
                if cached:
                    task_id = cached.id
                else:
                    task_id = start_compare_task(kb_id, doc_a_id, doc_b_id)

                    while True:
                        t = get_compare_task_from_db(task_id)
                        if t and t.status in ("completed", "error"):
                            break
                        import time
                        time.sleep(1)

                results.append({
                    "doc_a_id": doc_a_id,
                    "doc_b_id": doc_b_id,
                    "task_id": task_id
                })
            except Exception as e:
                results.append({
                    "doc_a_id": doc_a_id,
                    "doc_b_id": doc_b_id,
                    "task_id": "",
                    "error": str(e)
                })

            batch_task.completed_pairs = idx + 1
            batch_task.progress = int((idx + 1) / len(pairs) * 100)
            batch_task.task_results = results
            db.commit()

        batch_task.status = "completed"
        batch_task.progress = 100
        batch_task.message = "批量对比完成"
        batch_task.completed_at = datetime.now()
        db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
        if batch_task:
            batch_task.status = "error"
            batch_task.error_message = str(e)
            db.commit()
    finally:
        db.close()


@router.post("/batch", response_model=BatchCompareTaskResponse)
def create_batch_compare(request: BatchCompareRequest, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == request.knowledge_base_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    if len(request.document_ids) < 3:
        raise HTTPException(status_code=400, detail="请至少选择3篇文档进行批量对比")

    for doc_id in request.document_ids:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=400, detail=f"文档 {doc_id} 不存在")
        if doc.knowledge_base_id != request.knowledge_base_id:
            raise HTTPException(status_code=400, detail="所有文档必须属于同一个知识库")
        if doc.status != "ready":
            raise HTTPException(status_code=400, detail=f"文档 {doc.filename} 未处理完成")

    batch_task_id = str(uuid.uuid4())
    pairs = list(itertools.combinations(request.document_ids, 2))

    batch_task = BatchCompareTask(
        id=batch_task_id,
        knowledge_base_id=request.knowledge_base_id,
        document_ids=request.document_ids,
        status="pending",
        progress=0,
        message="批量对比任务已创建",
        total_pairs=len(pairs),
        completed_pairs=0,
        task_results=[]
    )
    db.add(batch_task)
    db.commit()

    thread = threading.Thread(
        target=process_batch_compare,
        args=(batch_task_id, request.knowledge_base_id, request.document_ids),
        daemon=True
    )
    thread.start()

    return BatchCompareTaskResponse(
        task_id=batch_task_id,
        status="pending",
        progress=0,
        message="批量对比任务已创建",
        total_pairs=len(pairs),
        completed_pairs=0
    )


@router.get("/batch/{task_id}", response_model=BatchCompareTaskResponse)
def get_batch_compare_status(task_id: str, db: Session = Depends(get_db)):
    batch_task = db.query(BatchCompareTask).filter(BatchCompareTask.id == task_id).first()
    if not batch_task:
        raise HTTPException(status_code=404, detail="批量对比任务不存在")

    return BatchCompareTaskResponse(
        task_id=batch_task.id,
        status=batch_task.status,
        progress=batch_task.progress,
        message=batch_task.message,
        total_pairs=batch_task.total_pairs,
        completed_pairs=batch_task.completed_pairs
    )


@router.get("/batch/{task_id}/overview", response_model=BatchCompareOverviewResponse)
def get_batch_compare_overview(task_id: str, db: Session = Depends(get_db)):
    batch_task = db.query(BatchCompareTask).filter(BatchCompareTask.id == task_id).first()
    if not batch_task:
        raise HTTPException(status_code=404, detail="批量对比任务不存在")

    doc_ids = batch_task.document_ids or []
    doc_map = {}
    for did in doc_ids:
        d = db.query(Document).filter(Document.id == did).first()
        if d:
            doc_map[did] = d.filename

    doc_names = [doc_map.get(did, did) for did in doc_ids]

    n = len(doc_ids)
    matrix = []

    task_results = {f"{r.get('doc_a_id')}|{r.get('doc_b_id')}": r for r in (batch_task.task_results or [])}

    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                cell = BatchCompareMatrixCell(
                    doc_a_id=doc_ids[i],
                    doc_b_id=doc_ids[j],
                    doc_a_name=doc_names[i],
                    doc_b_name=doc_names[j],
                    repeat_rate=100.0,
                    repeated_count=0,
                    min_chunk_count=0,
                    task_id="",
                    status="self"
                )
            else:
                key_a = f"{doc_ids[i]}|{doc_ids[j]}"
                key_b = f"{doc_ids[j]}|{doc_ids[i]}"
                pair_info = task_results.get(key_a) or task_results.get(key_b)

                repeat_rate = 0.0
                repeated_count = 0
                min_chunk_count = 0
                pair_task_id = ""
                pair_status = "pending"

                if pair_info:
                    pair_task_id = pair_info.get("task_id", "")
                    if pair_task_id:
                        t = get_compare_task_from_db(pair_task_id)
                        if t and t.status == "completed" and t.result:
                            pair_status = "completed"
                            summary = t.result.get("summary", {})
                            repeated_count = summary.get("repeated_count", 0)
                            chunks_a = t.result.get("doc_a", {}).get("chunk_count", 0)
                            chunks_b = t.result.get("doc_b", {}).get("chunk_count", 0)
                            min_chunk_count = min(chunks_a, chunks_b) if chunks_a and chunks_b else 0
                            if min_chunk_count > 0:
                                raw_rate = repeated_count / min_chunk_count * 100
                                repeat_rate = round(min(raw_rate, 100.0), 1)
                            else:
                                repeat_rate = 0.0
                        elif t:
                            pair_status = t.status

                cell = BatchCompareMatrixCell(
                    doc_a_id=doc_ids[i],
                    doc_b_id=doc_ids[j],
                    doc_a_name=doc_names[i],
                    doc_b_name=doc_names[j],
                    repeat_rate=repeat_rate,
                    repeated_count=repeated_count,
                    min_chunk_count=min_chunk_count,
                    task_id=pair_task_id,
                    status=pair_status
                )
            row.append(cell)
        matrix.append(row)

    return BatchCompareOverviewResponse(
        task_id=batch_task.id,
        status=batch_task.status,
        progress=batch_task.progress,
        message=batch_task.message,
        document_ids=doc_ids,
        document_names=doc_names,
        matrix=matrix,
        error_message=batch_task.error_message or ""
    )


@router.get("/task/{task_id}/export-pdf")
def export_compare_pdf(task_id: str, db: Session = Depends(get_db)):
    task = get_compare_task_from_db(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed" or not task.result:
        raise HTTPException(status_code=400, detail="对比任务未完成，无法导出")

    import copy
    result = copy.deepcopy(task.result)
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == task.knowledge_base_id).first()
    kb_name = kb.name if kb else ""

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
            ListFlowable, ListItem
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.graphics.charts.piecharts import Pie
        from reportlab.graphics.widgets.markers import makeMarker
        from reportlab.graphics import Drawing
        from reportlab.graphics.labels import Label
        import os
        import re
        import math

        def find_chinese_font():
            font_candidates = []
            
            windows_fonts = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/msyhbd.ttc",
                "C:/Windows/Fonts/msyhl.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/simkai.ttf",
                "C:/Windows/Fonts/simli.ttf",
            ]
            for f in windows_fonts:
                if os.path.exists(f):
                    font_candidates.append(f)
            
            linux_fonts = [
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/arphic/uming.ttc",
                "/usr/share/fonts/truetype/arphic/ukai.ttc",
            ]
            for f in linux_fonts:
                if os.path.exists(f):
                    font_candidates.append(f)
            
            mac_fonts = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
            ]
            for f in mac_fonts:
                if os.path.exists(f):
                    font_candidates.append(f)
            
            app_font_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'fonts')
            if os.path.isdir(app_font_dir):
                for fname in os.listdir(app_font_dir):
                    if fname.lower().endswith(('.ttf', '.ttc')):
                        font_candidates.insert(0, os.path.join(app_font_dir, fname))
            
            return font_candidates

        def register_chinese_font():
            font_candidates = find_chinese_font()
            
            for fp in font_candidates:
                try:
                    if fp.lower().endswith('.ttc'):
                        try:
                            pdfmetrics.registerFont(TTFont('ChineseFont', fp, fontIndex=0))
                            print(f"[PDF] 成功注册中文字体: {fp} (fontIndex=0)")
                            return 'ChineseFont', fp
                        except Exception:
                            try:
                                pdfmetrics.registerFont(TTFont('ChineseFont', fp))
                                print(f"[PDF] 成功注册中文字体: {fp} (默认索引)")
                                return 'ChineseFont', fp
                            except Exception:
                                continue
                    else:
                        pdfmetrics.registerFont(TTFont('ChineseFont', fp))
                        print(f"[PDF] 成功注册中文字体: {fp}")
                        return 'ChineseFont', fp
                except Exception as e:
                    print(f"[PDF] 注册字体失败 {fp}: {e}")
                    continue
            
            try:
                pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                print("[PDF] 使用 UnicodeCIDFont STSong-Light 作为后备字体")
                return 'STSong-Light', None
            except Exception as e:
                print(f"[PDF] 注册 CID 字体失败: {e}")
            
            return 'Helvetica', None

        cn_font, font_file = register_chinese_font()
        font_registered = cn_font != 'Helvetica'
        print(f"[PDF] 最终使用字体: {cn_font}, 字体文件: {font_file}")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=2 * cm, rightMargin=2 * cm,
                                topMargin=2 * cm, bottomMargin=2 * cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle', parent=styles['Title'],
            fontName=cn_font, fontSize=24, leading=32, alignment=TA_CENTER,
            spaceAfter=30
        )
        h1_style = ParagraphStyle(
            'Heading1CN', parent=styles['Heading1'],
            fontName=cn_font, fontSize=18, leading=24, spaceAfter=16
        )
        h2_style = ParagraphStyle(
            'Heading2CN', parent=styles['Heading2'],
            fontName=cn_font, fontSize=14, leading=20, spaceAfter=10
        )
        normal_style = ParagraphStyle(
            'NormalCN', parent=styles['Normal'],
            fontName=cn_font, fontSize=11, leading=16
        )
        center_style = ParagraphStyle(
            'CenterCN', parent=styles['Normal'],
            fontName=cn_font, fontSize=12, leading=18, alignment=TA_CENTER
        )
        small_style = ParagraphStyle(
            'SmallCN', parent=styles['Normal'],
            fontName=cn_font, fontSize=10, leading=14
        )

        def p(text, style):
            safe_text = str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return Paragraph(safe_text, style)

        story = []

        story.append(Spacer(1, 4 * cm))
        story.append(Paragraph("文档对比分析报告", title_style))
        story.append(Spacer(1, 2 * cm))

        doc_a_name = result.get("doc_a", {}).get("filename", "文档 A")
        doc_b_name = result.get("doc_b", {}).get("filename", "文档 B")
        compare_time = task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else ""

        cover_data = [
            [Paragraph("知识库名称:", center_style), Paragraph(kb_name or "-", center_style)],
            [Paragraph("文档 A:", center_style), Paragraph(doc_a_name, center_style)],
            [Paragraph("文档 B:", center_style), Paragraph(doc_b_name, center_style)],
            [Paragraph("对比时间:", center_style), Paragraph(compare_time, center_style)]
        ]
        cover_table = Table(cover_data, colWidths=[4 * cm, 11 * cm])
        cover_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.grey)
        ]))
        story.append(cover_table)

        story.append(PageBreak())

        summary = result.get("summary", {})
        story.append(Paragraph("一、摘要统计", h1_style))

        unique_total = summary.get("unique_a_count", 0) + summary.get("unique_b_count", 0)
        similar_count = summary.get("similar_count", 0)
        repeated_count = summary.get("repeated_count", 0)

        try:
            pie_data = [unique_total, similar_count, repeated_count]
            pie_labels = ['独有内容', '相似内容', '重复内容']
            pie_colors_hex = ['#409eff', '#e6a23c', '#67c23a']
            pie_colors_rl = [colors.HexColor(c) for c in pie_colors_hex]

            if sum(pie_data) > 0:
                drawing_width = 400
                drawing_height = 280
                d = Drawing(drawing_width, drawing_height)

                pie = Pie()
                pie.x = 100
                pie.y = 30
                pie.width = 180
                pie.height = 180
                pie.data = pie_data
                pie.labels = pie_labels

                for i, clr in enumerate(pie_colors_rl):
                    pie.slices[i].fillColor = clr
                    pie.slices[i].strokeWidth = 0.5
                    pie.slices[i].strokeColor = colors.white
                    pie.slices[i].fontName = cn_font
                    pie.slices[i].fontSize = 11
                    pie.slices[i].labelRadius = 1.35

                pie.slices[0].popout = 5

                d.add(pie)

                title_label = Label()
                title_label.setText('内容分布')
                title_label.x = drawing_width / 2
                title_label.y = drawing_height - 20
                title_label.fontName = cn_font
                title_label.fontSize = 14
                title_label.textAnchor = 'middle'
                d.add(title_label)

                for i, (val, lbl) in enumerate(zip(pie_data, pie_labels)):
                    pct = val / sum(pie_data) * 100 if sum(pie_data) > 0 else 0
                    pct_label = Label()
                    pct_label.setText(f'{pct:.1f}%')
                    angle = sum(pie_data[:i]) + val / 2
                    angle_rad = math.radians(90 - angle / sum(pie_data) * 360 if i == 0 else
                                             90 - (sum(pie_data[:i]) + val / 2) / sum(pie_data) * 360)
                    r = 80
                    cx = pie.x + pie.width / 2
                    cy = pie.y + pie.height / 2
                    pct_label.x = cx + r * math.cos(angle_rad)
                    pct_label.y = cy + r * math.sin(angle_rad)
                    pct_label.fontName = cn_font
                    pct_label.fontSize = 9
                    pct_label.textAnchor = 'middle'
                    d.add(pct_label)

                story.append(d)
                story.append(Spacer(1, 0.3 * cm))

                legend_data = []
                row = []
                for i, (lbl, clr_hex) in enumerate(zip(pie_labels, pie_colors_hex)):
                    row.append(Paragraph(f'<font color="{clr_hex}">■</font> {lbl}: {pie_data[i]} ({pie_data[i]/sum(pie_data)*100:.1f}%)', small_style))
                    if len(row) == 2 or i == len(pie_labels) - 1:
                        while len(row) < 2:
                            row.append(Paragraph("", small_style))
                        legend_data.append(row)
                        row = []
                legend_table = Table(legend_data, colWidths=[7 * cm, 7 * cm])
                legend_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), cn_font),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(legend_table)
                story.append(Spacer(1, 0.5 * cm))
        except Exception as e:
            print(f"[PDF] 饼图生成失败: {e}")
            import traceback
            traceback.print_exc()

        summary_data = [
            [Paragraph("<b>类别</b>", center_style), Paragraph("<b>数量</b>", center_style)],
            [Paragraph("文档 A 独有内容", normal_style), Paragraph(str(summary.get("unique_a_count", 0)), center_style)],
            [Paragraph("文档 B 独有内容", normal_style), Paragraph(str(summary.get("unique_b_count", 0)), center_style)],
            [Paragraph("相似但有差异", normal_style), Paragraph(str(similar_count), center_style)],
            [Paragraph("高度重复", normal_style), Paragraph(str(repeated_count), center_style)]
        ]
        summary_table = Table(summary_data, colWidths=[9 * cm, 3 * cm])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f7fa')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
        ]))
        story.append(summary_table)

        story.append(PageBreak())

        story.append(Paragraph("二、独有内容列表", h1_style))

        story.append(Paragraph("2.1 文档 A 独有内容", h2_style))
        unique_a = result.get("unique_a", [])
        if not unique_a:
            story.append(Paragraph("（无）", small_style))
        else:
            for idx, chunk in enumerate(unique_a[:50], 1):
                content = chunk.get("content", "")[:300].replace('\n', '<br/>')
                page_info = f", 第 {chunk.get('page_number')} 页" if chunk.get('page_number') else ""
                header = f"<b>第 {idx} 条</b>（分块 #{chunk.get('chunk_index', 0) + 1}{page_info}）："
                story.append(Paragraph(header, small_style))
                story.append(p(content, normal_style))
                story.append(Spacer(1, 0.2 * cm))

        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("2.2 文档 B 独有内容", h2_style))
        unique_b = result.get("unique_b", [])
        if not unique_b:
            story.append(Paragraph("（无）", small_style))
        else:
            for idx, chunk in enumerate(unique_b[:50], 1):
                content = chunk.get("content", "")[:300].replace('\n', '<br/>')
                page_info = f", 第 {chunk.get('page_number')} 页" if chunk.get('page_number') else ""
                header = f"<b>第 {idx} 条</b>（分块 #{chunk.get('chunk_index', 0) + 1}{page_info}）："
                story.append(Paragraph(header, small_style))
                story.append(p(content, normal_style))
                story.append(Spacer(1, 0.2 * cm))

        story.append(PageBreak())

        story.append(Paragraph("三、重复内容对照表", h1_style))
        repeated = result.get("repeated_pairs", [])
        if not repeated:
            story.append(Paragraph("（无高度重复内容）", small_style))
        else:
            rep_header = [
                Paragraph("<b>#</b>", center_style),
                Paragraph("<b>文档 A 内容</b>", center_style),
                Paragraph("<b>文档 B 内容</b>", center_style),
                Paragraph("<b>相似度</b>", center_style)
            ]
            rep_data = [rep_header]
            for idx, pair in enumerate(repeated[:50], 1):
                ca = pair.get("chunk_a", {})
                cb = pair.get("chunk_b", {})
                text_a = ca.get("content", "")[:100].replace('\n', ' ')
                text_b = cb.get("content", "")[:100].replace('\n', ' ')
                sim = f"{(pair.get('similarity', 0) * 100):.1f}%"
                rep_data.append([
                    Paragraph(str(idx), small_style),
                    p(text_a, small_style),
                    p(text_b, small_style),
                    Paragraph(sim, center_style)
                ])

            rep_table = Table(rep_data, colWidths=[1 * cm, 5.5 * cm, 5.5 * cm, 2 * cm], repeatRows=1)
            rep_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), cn_font),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f7fa')),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
            ]))
            story.append(rep_table)

        story.append(PageBreak())

        story.append(Paragraph("四、差异内容（相似但有差异）", h1_style))
        similar = result.get("similar_pairs", [])
        if not similar:
            story.append(Paragraph("（无相似但有差异内容）", small_style))
        else:
            def process_diff_html(diff_text):
                if not diff_text:
                    return ""
                result_text = diff_text
                result_text = result_text.replace('&', '&amp;')
                result_text = re.sub(r'<span class="diff-equal">', '', result_text)
                result_text = re.sub(r'<span class="diff-del">', '<font color="#f56c6c"><s>', result_text)
                result_text = re.sub(r'<span class="diff-add">', '<font color="#67c23a"><u>', result_text)
                result_text = result_text.replace('</span>', '</s></u></font>')
                result_text = result_text.replace('\n', '<br/>')
                return result_text

            for idx, pair in enumerate(similar[:30], 1):
                ca = pair.get("chunk_a", {})
                cb = pair.get("chunk_b", {})
                sim = f"{(pair.get('similarity', 0) * 100):.1f}%"

                story.append(Paragraph(f"<b>差异对 #{idx}</b>（相似度：{sim}）", h2_style))

                diff_a = process_diff_html(pair.get("diff_a", "")[:500])
                diff_b = process_diff_html(pair.get("diff_b", "")[:500])

                diff_data = [
                    [Paragraph(f"<b>文档 A</b>（分块 #{ca.get('chunk_index', 0) + 1}）", small_style),
                     Paragraph(f"<b>文档 B</b>（分块 #{cb.get('chunk_index', 0) + 1}）", small_style)],
                    [Paragraph(diff_a, small_style),
                     Paragraph(diff_b, small_style)]
                ]
                diff_table = Table(diff_data, colWidths=[7.5 * cm, 7.5 * cm])
                diff_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), cn_font),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf5ff')),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
                ]))
                story.append(diff_table)
                story.append(Spacer(1, 0.3 * cm))

        doc.build(story)
        buffer.seek(0)

        filename = f"对比报告_{doc_a_name[:20]}_vs_{doc_b_name[:20]}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"缺少PDF生成依赖: {str(e)}。请安装 reportlab")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF生成失败: {str(e)}")
