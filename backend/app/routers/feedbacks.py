from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import uuid

from ..database import get_db, Feedback, Message, Conversation
from ..schemas import FeedbackCreate, FeedbackResponse, FeedbackStatsResponse

router = APIRouter(prefix="/api/feedbacks", tags=["feedbacks"])


@router.post("", response_model=FeedbackResponse)
def create_feedback(req: FeedbackCreate, db: Session = Depends(get_db)):
    if req.score not in (1, -1):
        raise HTTPException(status_code=400, detail="score 只能是 1 或 -1")

    message = db.query(Message).filter(Message.id == req.message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    existing = db.query(Feedback).filter(Feedback.message_id == req.message_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="该消息已评价过")

    feedback = Feedback(
        id=str(uuid.uuid4()),
        message_id=req.message_id,
        score=req.score
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@router.get("/stats/{kb_id}", response_model=FeedbackStatsResponse)
def get_feedback_stats(kb_id: str, db: Session = Depends(get_db)):
    stmt = (
        db.query(
            func.count(Feedback.id).label("total"),
            func.sum(func.IIF(Feedback.score == 1, 1, 0)).label("positive"),
            func.sum(func.IIF(Feedback.score == -1, 1, 0)).label("negative"),
        )
        .join(Message, Message.id == Feedback.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.knowledge_base_id == kb_id)
    )

    row = stmt.first()
    total = int(row[0] or 0)
    positive = int(row[1] or 0)
    negative = int(row[2] or 0)
    rate = (positive / total * 100) if total > 0 else 0.0

    return FeedbackStatsResponse(
        knowledge_base_id=kb_id,
        total_count=total,
        positive_count=positive,
        negative_count=negative,
        positive_rate=rate
    )
