from typing import List, Optional
from dataclasses import dataclass
import re
import uuid


@dataclass
class ChunkResult:
    content: str
    chunk_index: int
    page_number: Optional[int] = None
    paragraph_number: Optional[int] = None
    heading_path: str = ""


def chunk_fixed_length(
    pages,
    chunk_size: int = 500,
    overlap: int = 100
) -> List[ChunkResult]:
    chunks: List[ChunkResult] = []
    chunk_index = 0

    full_text_parts = []
    page_map = []

    for page in pages:
        full_text_parts.append(page.text)
        page_map.extend([page.page_number] * len(page.text))

    full_text = "\n\n".join(full_text_parts)

    if not full_text.strip():
        return chunks

    step = chunk_size - overlap
    start = 0

    while start < len(full_text):
        end = min(start + chunk_size, len(full_text))

        if end < len(full_text):
            last_space = full_text.rfind(" ", start, end)
            if last_space > start + chunk_size // 2:
                end = last_space

        chunk_text = full_text[start:end].strip()
        if chunk_text:
            mid_pos = (start + end) // 2
            page_num = page_map[min(mid_pos, len(page_map) - 1)] if page_map else None
            chunks.append(ChunkResult(
                content=chunk_text,
                chunk_index=chunk_index,
                page_number=page_num
            ))
            chunk_index += 1

        if end >= len(full_text):
            break

        start = end - overlap
        if start <= 0:
            start = end

    return chunks


def chunk_semantic(
    pages,
    target_size: int = 500,
    overlap: int = 100
) -> List[ChunkResult]:
    chunks: List[ChunkResult] = []
    chunk_index = 0

    paragraphs: List[tuple] = []

    for page in pages:
        text = page.text
        if not text.strip():
            continue
        paras = re.split(r'\n\s*\n', text)
        for i, para in enumerate(paras):
            stripped = para.strip()
            if stripped:
                paragraphs.append((stripped, page.page_number, i + 1))

    if not paragraphs:
        return chunks

    current_chunk = []
    current_length = 0
    current_page = None
    para_start = 1

    for text, page_num, para_num in paragraphs:
        text_len = len(text)

        if current_length + text_len > target_size and current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(ChunkResult(
                content=chunk_text,
                chunk_index=chunk_index,
                page_number=current_page,
                paragraph_number=para_start
            ))
            chunk_index += 1

            overlap_texts = []
            overlap_len = 0
            for t in reversed(current_chunk):
                if overlap_len + len(t) <= overlap:
                    overlap_texts.insert(0, t)
                    overlap_len += len(t)
                else:
                    break
            current_chunk = overlap_texts
            current_length = overlap_len
            para_start = para_num

        current_chunk.append(text)
        current_length += text_len
        current_page = page_num

    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        chunks.append(ChunkResult(
            content=chunk_text,
            chunk_index=chunk_index,
            page_number=current_page,
            paragraph_number=para_start
        ))

    return chunks


def chunk_by_headings(
    pages,
    min_chunk_size: int = 200
) -> List[ChunkResult]:
    chunks: List[ChunkResult] = []
    chunk_index = 0

    heading_stack: List[tuple] = []
    current_content: List[str] = []
    current_page = None
    current_heading_path = ""
    start_para_num = 1
    para_counter = 0

    all_paragraphs: List[tuple] = []

    for page in pages:
        text = page.text
        if not text.strip():
            continue
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                para_counter += 1
                all_paragraphs.append((stripped, page.page_number, para_counter, 0))
                continue

            level = 0
            h_match = re.match(r'^(#+)\s+', stripped)
            if h_match:
                level = len(h_match.group(1))
            elif stripped.isupper() and len(stripped.split()) <= 10:
                level = 2
            else:
                import re as _re
                if _re.match(r'^\d+(\.\d+)*\s+', stripped) and len(stripped) < 80:
                    dots = stripped.split()[0].count('.')
                    level = min(dots + 1, 3)

            para_counter += 1
            all_paragraphs.append((stripped, page.page_number, para_counter, level))

    def save_chunk():
        nonlocal chunk_index, current_content, current_page, current_heading_path, start_para_num
        if not current_content:
            return
        content_text = "\n".join(current_content).strip()
        if not content_text or len(content_text) < 50:
            return
        chunks.append(ChunkResult(
            content=content_text,
            chunk_index=chunk_index,
            page_number=current_page,
            paragraph_number=start_para_num,
            heading_path=current_heading_path
        ))
        chunk_index += 1

    for text, page_num, para_num, level in all_paragraphs:
        if level > 0:
            save_chunk()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
            current_heading_path = " > ".join([h for _, h in heading_stack])
            current_content = [text]
            current_page = page_num
            start_para_num = para_num
        else:
            if current_content:
                current_content.append(text)
                current_page = current_page or page_num
            else:
                current_content = [text]
                current_page = page_num
                start_para_num = para_num

    save_chunk()

    if not chunks:
        return chunk_fixed_length(pages, chunk_size=min_chunk_size * 2, overlap=min_chunk_size // 2)

    return chunks


def chunk_document(
    pages,
    strategy: str = "fixed",
    chunk_size: int = 500,
    overlap: int = 100
) -> List[ChunkResult]:
    if strategy == "fixed":
        return chunk_fixed_length(pages, chunk_size, overlap)
    elif strategy == "semantic":
        return chunk_semantic(pages, chunk_size, overlap)
    elif strategy == "heading":
        return chunk_by_headings(pages, min_chunk_size=chunk_size // 2)
    else:
        return chunk_fixed_length(pages, chunk_size, overlap)
