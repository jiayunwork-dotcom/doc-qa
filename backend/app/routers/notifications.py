from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db, Notification
from ..schemas import NotificationResponse, MarkNotificationsReadRequest

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=List[NotificationResponse])
def list_notifications(
    knowledge_base_id: Optional[str] = None,
    only_unread: Optional[bool] = False,
    db: Session = Depends(get_db)
):
    query = db.query(Notification)
    if knowledge_base_id:
        query = query.filter(Notification.knowledge_base_id == knowledge_base_id)
    if only_unread:
        query = query.filter(Notification.is_read == False)
    notifications = query.order_by(Notification.created_at.desc()).all()
    return notifications


@router.get("/unread-count")
def get_unread_count(
    knowledge_base_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Notification).filter(Notification.is_read == False)
    if knowledge_base_id:
        query = query.filter(Notification.knowledge_base_id == knowledge_base_id)
    count = query.count()
    return {"unread_count": count}


@router.post("/{notification_id}/read")
def mark_notification_read(notification_id: str, db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    notification.is_read = True
    db.commit()
    return {"message": "已标记为已读"}


@router.post("/read-all")
def mark_all_notifications_read(
    request: MarkNotificationsReadRequest,
    db: Session = Depends(get_db)
):
    query = db.query(Notification).filter(Notification.is_read == False)
    if request.notification_ids and not request.all:
        query = query.filter(Notification.id.in_(request.notification_ids))
    notifications = query.all()
    for n in notifications:
        n.is_read = True
    db.commit()
    return {"message": f"已标记 {len(notifications)} 条通知为已读"}


@router.delete("/{notification_id}")
def delete_notification(notification_id: str, db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    db.delete(notification)
    db.commit()
    return {"message": "通知已删除"}
