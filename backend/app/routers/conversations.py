from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db, Conversation, Message, Feedback
from ..schemas import ConversationResponse, MessageResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=List[ConversationResponse])
def list_conversations(kb_id: str = None, db: Session = Depends(get_db)):
    query = db.query(Conversation)
    if kb_id:
        query = query.filter(Conversation.knowledge_base_id == kb_id)
    convs = query.order_by(Conversation.updated_at.desc()).all()
    result = []
    for conv in convs:
        msg_count = db.query(Message).filter(Message.conversation_id == conv.id).count()
        resp = ConversationResponse.model_validate(conv)
        resp.message_count = msg_count
        result.append(resp)
    return result


@router.get("/{conv_id}", response_model=List[MessageResponse])
def get_conversation_messages(conv_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    message_ids = [m.id for m in messages]
    feedbacks = {}
    if message_ids:
        fb_list = db.query(Feedback).filter(Feedback.message_id.in_(message_ids)).all()
        feedbacks = {fb.message_id: fb.score for fb in fb_list}

    result = []
    for msg in messages:
        sources = []
        if msg.sources:
            from ..schemas import SourceInfo
            try:
                sources = [SourceInfo(**s) for s in (msg.sources if isinstance(msg.sources, list) else [])]
            except Exception:
                sources = []
        resp = MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            sources=sources,
            created_at=msg.created_at,
            feedback_score=feedbacks.get(msg.id)
        )
        result.append(resp)
    return result


@router.delete("/{conv_id}")
def delete_conversation(conv_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(conv)
    db.commit()
    return {"message": "会话已删除"}
