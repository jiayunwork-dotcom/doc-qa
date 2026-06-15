import uuid
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    ForeignKey, Float, Boolean, JSON, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

from .config import settings

Base = declarative_base()


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    chunk_strategy = Column(String(50), default="fixed")
    chunk_size = Column(Integer, default=500)
    chunk_overlap = Column(Integer, default=100)
    top_k = Column(Integer, default=20)
    enable_rerank = Column(Boolean, default=True)
    enable_change_notification = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    knowledge_base_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=False)
    filename = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)
    file_path = Column(String(1000), default="")
    file_type = Column(String(20), default="")
    status = Column(String(50), default="uploaded")
    task_id = Column(String, default="")
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text, default="")
    uploaded_at = Column(DateTime, default=func.now())
    processed_at = Column(DateTime, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    upload_remark = Column(String(500), default="")
    parent_document_id = Column(String, default="")

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    knowledge_base_id = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    page_number = Column(Integer, nullable=True)
    paragraph_number = Column(Integer, nullable=True)
    heading_path = Column(String(500), default="")
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    document = relationship("Document", back_populates="chunks")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    knowledge_base_id = Column(String, nullable=False)
    title = Column(String(500), default="New Conversation")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(JSON, default=list)
    created_at = Column(DateTime, default=func.now())

    conversation = relationship("Conversation", back_populates="messages")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id"), nullable=False, unique=True)
    score = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.now())


class CompareTask(Base):
    __tablename__ = "compare_tasks"

    id = Column(String, primary_key=True)
    knowledge_base_id = Column(String, nullable=False)
    doc_a_id = Column(String, ForeignKey("documents.id"), nullable=False)
    doc_b_id = Column(String, ForeignKey("documents.id"), nullable=False)
    status = Column(String(50), default="pending")
    progress = Column(Integer, default=0)
    message = Column(Text, default="")
    result = Column(JSON, nullable=True)
    error_message = Column(Text, default="")
    doc_a_version = Column(String, default="")
    doc_b_version = Column(String, default="")
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    doc_a = relationship("Document", foreign_keys=[doc_a_id])
    doc_b = relationship("Document", foreign_keys=[doc_b_id])


class CompareIgnore(Base):
    __tablename__ = "compare_ignores"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_a_id = Column(String, ForeignKey("documents.id"), nullable=False)
    doc_b_id = Column(String, ForeignKey("documents.id"), nullable=False)
    chunk_a_id = Column(String, ForeignKey("chunks.id"), nullable=False)
    chunk_b_id = Column(String, ForeignKey("chunks.id"), nullable=False)
    ignore_type = Column(String(20), default="pair")
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('doc_a_id', 'doc_b_id', 'chunk_a_id', 'chunk_b_id', name='uq_ignore_pair'),
    )


class DocumentVersionEvent(Base):
    __tablename__ = "document_version_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    knowledge_base_id = Column(String, nullable=False)
    version = Column(Integer, default=1)
    event_type = Column(String(20), default="upload")
    change_summary = Column(JSON, default=dict)
    change_type = Column(String(20), default="format")
    rollback_from_version = Column(Integer, nullable=True)
    rollback_to_version = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_base_id = Column(String, nullable=False)
    document_id = Column(String, nullable=False)
    document_name = Column(String(500), default="")
    version = Column(Integer, default=1)
    change_summary = Column(JSON, default=dict)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())


class BatchCompareTask(Base):
    __tablename__ = "batch_compare_tasks"

    id = Column(String, primary_key=True)
    knowledge_base_id = Column(String, nullable=False)
    document_ids = Column(JSON, default=list)
    status = Column(String(50), default="pending")
    progress = Column(Integer, default=0)
    message = Column(Text, default="")
    total_pairs = Column(Integer, default=0)
    completed_pairs = Column(Integer, default=0)
    task_results = Column(JSON, default=list)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)


engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
