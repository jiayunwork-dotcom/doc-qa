from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseBase(BaseModel):
    name: str
    description: Optional[str] = ""
    chunk_strategy: Optional[str] = "fixed"
    chunk_size: Optional[int] = 500
    chunk_overlap: Optional[int] = 100
    top_k: Optional[int] = 20
    enable_rerank: Optional[bool] = True


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    chunk_strategy: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    top_k: Optional[int] = None
    enable_rerank: Optional[bool] = None


class KnowledgeBaseResponse(KnowledgeBaseBase):
    id: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    file_size: int
    file_type: str
    status: str
    task_id: str
    chunk_count: int
    error_message: str = ""
    uploaded_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    message: str = ""
    document_id: Optional[str] = None


class SourceInfo(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    page_number: Optional[int] = None
    paragraph_number: Optional[int] = None
    score: float = 0.0
    chunk_index: int = 0


class AskRequest(BaseModel):
    question: str
    knowledge_base_id: str
    conversation_id: Optional[str] = None
    top_k: Optional[int] = None


class AskResponse(BaseModel):
    answer: str
    conversation_id: str
    message_id: str
    sources: List[SourceInfo] = []


class SearchRequest(BaseModel):
    query: str
    knowledge_base_id: str
    top_k: Optional[int] = None
    enable_rerank: Optional[bool] = None


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    page_number: Optional[int] = None
    paragraph_number: Optional[int] = None
    score: float = 0.0
    chunk_index: int = 0


class SearchResponse(BaseModel):
    results: List[SearchResult] = []
    debug_info: Optional[dict] = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: List[SourceInfo] = []
    created_at: datetime
    feedback_score: Optional[int] = None

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: str
    knowledge_base_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    class Config:
        from_attributes = True


class FeedbackCreate(BaseModel):
    message_id: str
    score: int = Field(..., description="1表示有用, -1表示无用")


class FeedbackResponse(BaseModel):
    id: str
    message_id: str
    score: int
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackStatsResponse(BaseModel):
    knowledge_base_id: str
    total_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    positive_rate: float = 0.0


class CompareRequest(BaseModel):
    knowledge_base_id: str
    doc_a_id: str
    doc_b_id: str


class CompareTaskResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    message: str = ""


class CompareChunkInfo(BaseModel):
    chunk_id: str
    content: str
    page_number: Optional[int] = None
    chunk_index: int = 0
    similarity: Optional[float] = None


class ComparePair(BaseModel):
    chunk_a: CompareChunkInfo
    chunk_b: CompareChunkInfo
    similarity: float


class CompareDiffPair(ComparePair):
    diff_a: str = ""
    diff_b: str = ""


class CompareDocInfo(BaseModel):
    id: str
    filename: str
    chunk_count: int = 0
    unique_count: int = 0


class CompareSummary(BaseModel):
    total_chunks_a: int = 0
    total_chunks_b: int = 0
    unique_a_count: int = 0
    unique_b_count: int = 0
    similar_count: int = 0
    repeated_count: int = 0


class CompareResultResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    message: str = ""
    doc_a: Optional[CompareDocInfo] = None
    doc_b: Optional[CompareDocInfo] = None
    summary: Optional[CompareSummary] = None
    unique_a: List[CompareChunkInfo] = []
    unique_b: List[CompareChunkInfo] = []
    similar_pairs: List[CompareDiffPair] = []
    repeated_pairs: List[ComparePair] = []
    thresholds: Optional[dict] = None
    error_message: str = ""
