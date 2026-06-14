from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import uuid
from datetime import datetime

from ..database import get_db, KnowledgeBase, Conversation, Message
from ..schemas import (
    AskRequest, AskResponse, SourceInfo,
    SearchRequest, SearchResponse, SearchResult
)
from ..services.retrieval import search_chunks
from ..services.llm_service import (
    get_llm_service, build_chat_prompt
)
from ..services.conversation import (
    get_conversation_history, complete_question
)
from ..config import settings

router = APIRouter(tags=["qa", "search"])


@router.post("/api/search", response_model=SearchResponse)
def search_documents(req: SearchRequest, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == req.knowledge_base_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    top_k = req.top_k if req.top_k is not None else kb.top_k
    enable_rerank = req.enable_rerank if req.enable_rerank is not None else kb.enable_rerank

    results, debug_info = search_chunks(
        knowledge_base_id=req.knowledge_base_id,
        query=req.query,
        top_k=top_k,
        enable_rerank=enable_rerank,
        top_n=settings.DEFAULT_TOP_N,
        return_debug=True
    )

    return SearchResponse(results=results, debug_info=debug_info)


@router.post("/api/ask", response_model=AskResponse)
def ask_question(req: AskRequest, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == req.knowledge_base_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    conversation_id = req.conversation_id
    if not conversation_id:
        conv = Conversation(
            id=str(uuid.uuid4()),
            knowledge_base_id=req.knowledge_base_id,
            title=req.question[:50]
        )
        db.add(conv)
        db.commit()
        conversation_id = conv.id
    else:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            conv = Conversation(
                id=conversation_id,
                knowledge_base_id=req.knowledge_base_id,
                title=req.question[:50]
            )
            db.add(conv)
            db.commit()

    history = get_conversation_history(conversation_id)
    enhanced_question = complete_question(req.question, history)

    top_k = req.top_k if req.top_k is not None else kb.top_k
    search_results, _ = search_chunks(
        knowledge_base_id=req.knowledge_base_id,
        query=enhanced_question,
        top_k=top_k,
        enable_rerank=kb.enable_rerank,
        top_n=settings.DEFAULT_TOP_N,
        return_debug=False
    )

    sources = [
        SourceInfo(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            document_name=r.document_name,
            content=r.content,
            page_number=r.page_number,
            paragraph_number=r.paragraph_number,
            score=r.score,
            chunk_index=r.chunk_index
        )
        for r in search_results
    ]

    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=req.question
    )
    db.add(user_msg)

    if sources:
        messages = build_chat_prompt(enhanced_question, sources, history)
        try:
            llm = get_llm_service()
            answer = llm.generate(messages)
        except Exception as e:
            answer = f"（AI生成失败：{str(e)}）以下是检索到的相关段落："
            for i, src in enumerate(sources, 1):
                answer += f"\n\n[{i}] {src.content[:200]}..."
    else:
        answer = "根据提供的文档内容，无法回答该问题。知识库中可能没有包含相关信息。"
        sources = []

    sources_json = [s.model_dump() for s in sources]
    ai_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
        sources=sources_json
    )
    db.add(ai_msg)

    conv.updated_at = datetime.now()
    db.commit()

    return AskResponse(
        answer=answer,
        conversation_id=conversation_id,
        message_id=ai_msg.id,
        sources=sources
    )
