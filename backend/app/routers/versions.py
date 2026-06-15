from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import io
import re

from ..database import get_db, Document, KnowledgeBase, Chunk, VersionReview
from ..services.compare import compare_documents_internal, build_diff_html_internal
from ..schemas import (
    VersionReviewUpdateRequest, VersionReviewsResponse
)

router = APIRouter(prefix="/api/versions", tags=["versions"])


@router.get("/diff")
def compare_versions(
    old_version_id: str,
    new_version_id: str,
    db: Session = Depends(get_db)
):
    old_doc = db.query(Document).filter(Document.id == old_version_id).first()
    new_doc = db.query(Document).filter(Document.id == new_version_id).first()

    if not old_doc or not new_doc:
        raise HTTPException(status_code=404, detail="版本不存在")

    if old_doc.knowledge_base_id != new_doc.knowledge_base_id or old_doc.filename != new_doc.filename:
        raise HTTPException(status_code=400, detail="两个版本不属于同一文档")

    if old_doc.status != "ready" or new_doc.status != "ready":
        raise HTTPException(status_code=400, detail="两个版本都必须是已处理完成的状态")

    if old_doc.version > new_doc.version:
        old_doc, new_doc = new_doc, old_doc

    result = compare_documents_internal(
        old_doc.knowledge_base_id,
        old_doc.id,
        new_doc.id
    )

    return {
        "doc_old": result.get("doc_a"),
        "doc_new": result.get("doc_b"),
        "summary": result.get("summary"),
        "unique_old": result.get("unique_a", []),
        "unique_new": result.get("unique_b", []),
        "similar_pairs": result.get("similar_pairs", []),
        "repeated_pairs": result.get("repeated_pairs", []),
        "thresholds": result.get("thresholds")
    }


@router.get("/diff/export-pdf")
def export_version_diff_pdf(
    old_version_id: str,
    new_version_id: str,
    db: Session = Depends(get_db)
):
    old_doc = db.query(Document).filter(Document.id == old_version_id).first()
    new_doc = db.query(Document).filter(Document.id == new_version_id).first()

    if not old_doc or not new_doc:
        raise HTTPException(status_code=404, detail="版本不存在")

    if old_doc.knowledge_base_id != new_doc.knowledge_base_id or old_doc.filename != new_doc.filename:
        raise HTTPException(status_code=400, detail="两个版本不属于同一文档")

    if old_doc.status != "ready" or new_doc.status != "ready":
        raise HTTPException(status_code=400, detail="两个版本都必须是已处理完成的状态")

    if old_doc.version > new_doc.version:
        old_doc, new_doc = new_doc, old_doc

    result = compare_documents_internal(
        old_doc.knowledge_base_id,
        old_doc.id,
        new_doc.id
    )

    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == old_doc.knowledge_base_id).first()
    kb_name = kb.name if kb else ""

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        import os
        import re

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
                            return 'ChineseFont', fp
                        except Exception:
                            try:
                                pdfmetrics.registerFont(TTFont('ChineseFont', fp))
                                return 'ChineseFont', fp
                            except Exception:
                                continue
                    else:
                        pdfmetrics.registerFont(TTFont('ChineseFont', fp))
                        return 'ChineseFont', fp
                except Exception:
                    continue
            try:
                pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                return 'STSong-Light', None
            except Exception:
                pass
            return 'Helvetica', None

        cn_font, font_file = register_chinese_font()

        buffer = io.BytesIO()
        doc_pdf = SimpleDocTemplate(buffer, pagesize=A4,
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
        story.append(Paragraph("版本差异报告", title_style))
        story.append(Spacer(1, 2 * cm))

        compare_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cover_data = [
            [Paragraph("文档名称:", center_style), Paragraph(old_doc.filename, center_style)],
            [Paragraph("知识库名称:", center_style), Paragraph(kb_name or "-", center_style)],
            [Paragraph("旧版本:", center_style), Paragraph(f"v{old_doc.version}", center_style)],
            [Paragraph("新版本:", center_style), Paragraph(f"v{new_doc.version}", center_style)],
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

        summary_data = [
            [Paragraph("<b>类别</b>", center_style), Paragraph("<b>数量</b>", center_style)],
            [Paragraph("旧版本独有内容（已删除）", normal_style), Paragraph(str(summary.get("unique_a_count", 0)), center_style)],
            [Paragraph("新版本独有内容（已新增）", normal_style), Paragraph(str(summary.get("unique_b_count", 0)), center_style)],
            [Paragraph("相似但有差异（已修改）", normal_style), Paragraph(str(similar_count), center_style)],
            [Paragraph("高度重复（未变化）", normal_style), Paragraph(str(repeated_count), center_style)]
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
        story.append(Paragraph("二、删除内容（旧版本独有）", h1_style))
        unique_old = result.get("unique_a", [])
        if not unique_old:
            story.append(Paragraph("（无）", small_style))
        else:
            for idx, chunk in enumerate(unique_old[:50], 1):
                content = chunk.get("content", "")[:300].replace('\n', '<br/>')
                header = f"<b>第 {idx} 条</b>（分块 #{chunk.get('chunk_index', 0) + 1}）："
                story.append(Paragraph(header, small_style))
                story.append(p(content, normal_style))
                story.append(Spacer(1, 0.2 * cm))

        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("三、新增内容（新版本独有）", h1_style))
        unique_new = result.get("unique_b", [])
        if not unique_new:
            story.append(Paragraph("（无）", small_style))
        else:
            for idx, chunk in enumerate(unique_new[:50], 1):
                content = chunk.get("content", "")[:300].replace('\n', '<br/>')
                header = f"<b>第 {idx} 条</b>（分块 #{chunk.get('chunk_index', 0) + 1}）："
                story.append(Paragraph(header, small_style))
                story.append(p(content, normal_style))
                story.append(Spacer(1, 0.2 * cm))

        story.append(PageBreak())
        story.append(Paragraph("四、差异内容（相似但有修改）", h1_style))
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
                    [Paragraph(f"<b>旧版本 v{old_doc.version}</b>（分块 #{ca.get('chunk_index', 0) + 1}）", small_style),
                     Paragraph(f"<b>新版本 v{new_doc.version}</b>（分块 #{cb.get('chunk_index', 0) + 1}）", small_style)],
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

        doc_pdf.build(story)
        buffer.seek(0)

        filename = f"版本差异报告_{old_doc.filename[:20]}_v{old_doc.version}_vs_v{new_doc.version}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"

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


@router.get("/reviews", response_model=VersionReviewsResponse)
def get_version_reviews(
    old_version_id: str,
    new_version_id: str,
    db: Session = Depends(get_db)
):
    old_doc = db.query(Document).filter(Document.id == old_version_id).first()
    new_doc = db.query(Document).filter(Document.id == new_version_id).first()

    if not old_doc or not new_doc:
        raise HTTPException(status_code=404, detail="版本不存在")

    if old_doc.version > new_doc.version:
        old_doc, new_doc = new_doc, old_doc

    reviews = db.query(VersionReview).filter(
        VersionReview.old_version_id == old_doc.id,
        VersionReview.new_version_id == new_doc.id
    ).all()

    review_dict = {}
    for r in reviews:
        review_dict[r.diff_key] = {
            "status": r.review_status,
            "diff_type": r.diff_type,
            "updated_at": r.updated_at
        }

    return VersionReviewsResponse(
        old_version_id=old_doc.id,
        new_version_id=new_doc.id,
        reviews=review_dict
    )


@router.post("/reviews")
def update_version_review(
    request: VersionReviewUpdateRequest,
    db: Session = Depends(get_db)
):
    old_doc = db.query(Document).filter(Document.id == request.old_version_id).first()
    new_doc = db.query(Document).filter(Document.id == request.new_version_id).first()

    if not old_doc or not new_doc:
        raise HTTPException(status_code=404, detail="版本不存在")

    if old_doc.version > new_doc.version:
        old_doc, new_doc = new_doc, old_doc

    review = db.query(VersionReview).filter(
        VersionReview.old_version_id == old_doc.id,
        VersionReview.new_version_id == new_doc.id,
        VersionReview.diff_key == request.diff_key
    ).first()

    if review:
        review.review_status = request.review_status
        review.updated_at = datetime.now()
    else:
        review = VersionReview(
            old_version_id=old_doc.id,
            new_version_id=new_doc.id,
            diff_key=request.diff_key,
            diff_type=request.diff_type,
            review_status=request.review_status
        )
        db.add(review)

    db.commit()
    db.refresh(review)

    return {
        "success": True,
        "review": {
            "id": review.id,
            "diff_key": review.diff_key,
            "status": review.review_status,
            "updated_at": review.updated_at
        }
    }


@router.get("/diff/export-md")
def export_version_diff_markdown(
    old_version_id: str,
    new_version_id: str,
    db: Session = Depends(get_db)
):
    old_doc = db.query(Document).filter(Document.id == old_version_id).first()
    new_doc = db.query(Document).filter(Document.id == new_version_id).first()

    if not old_doc or not new_doc:
        raise HTTPException(status_code=404, detail="版本不存在")

    if old_doc.knowledge_base_id != new_doc.knowledge_base_id or old_doc.filename != new_doc.filename:
        raise HTTPException(status_code=400, detail="两个版本不属于同一文档")

    if old_doc.status != "ready" or new_doc.status != "ready":
        raise HTTPException(status_code=400, detail="两个版本都必须是已处理完成的状态")

    if old_doc.version > new_doc.version:
        old_doc, new_doc = new_doc, old_doc

    result = compare_documents_internal(
        old_doc.knowledge_base_id,
        old_doc.id,
        new_doc.id
    )

    lines = []
    lines.append(f"# {old_doc.filename} - v{old_doc.version} vs v{new_doc.version} 版本差异报告")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("## 一、删除内容（旧版本独有）")
    lines.append("")
    unique_old = result.get("unique_a", [])
    if not unique_old:
        lines.append("_（无删除内容）_")
    else:
        for idx, chunk in enumerate(unique_old, 1):
            content = chunk.get("content", "").strip()
            lines.append(f"### {idx}. 分块 #{chunk.get('chunk_index', 0) + 1}")
            lines.append("")
            lines.append(f"~~{content}~~")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 二、新增内容（新版本独有）")
    lines.append("")
    unique_new = result.get("unique_b", [])
    if not unique_new:
        lines.append("_（无新增内容）_")
    else:
        for idx, chunk in enumerate(unique_new, 1):
            content = chunk.get("content", "").strip()
            lines.append(f"### {idx}. 分块 #{chunk.get('chunk_index', 0) + 1}")
            lines.append("")
            lines.append(f"**{content}**")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 三、修改内容（相似但有差异）")
    lines.append("")
    similar = result.get("similar_pairs", [])
    if not similar:
        lines.append("_（无修改内容）_")
    else:
        def md_diff(diff_html, is_old=True):
            if not diff_html:
                return ""
            text = diff_html
            text = re.sub(r'<span class="diff-equal">', '', text)
            if is_old:
                text = re.sub(r'<span class="diff-del">', '~~', text)
                text = re.sub(r'<span class="diff-add">', '', text)
            else:
                text = re.sub(r'<span class="diff-del">', '', text)
                text = re.sub(r'<span class="diff-add">', '**', text)
            if is_old:
                text = text.replace('</span>', '~~')
            else:
                text = text.replace('</span>', '**')
            return text.strip()

        for idx, pair in enumerate(similar, 1):
            ca = pair.get("chunk_a", {})
            cb = pair.get("chunk_b", {})
            sim = f"{(pair.get('similarity', 0) * 100):.1f}%"

            lines.append(f"### 差异对 #{idx}（相似度：{sim}）")
            lines.append("")
            lines.append(f"**旧版本 v{old_doc.version}** · 分块 #{ca.get('chunk_index', 0) + 1}")
            lines.append("")
            lines.append(f"> {md_diff(pair.get('diff_a', ''), is_old=True)}")
            lines.append("")
            lines.append(f"**新版本 v{new_doc.version}** · 分块 #{cb.get('chunk_index', 0) + 1}")
            lines.append("")
            lines.append(f"> {md_diff(pair.get('diff_b', ''), is_old=False)}")
            lines.append("")

    md_content = "\n".join(lines)
    buffer = io.BytesIO(md_content.encode('utf-8'))

    filename = f"版本差异报告_{old_doc.filename[:20]}_v{old_doc.version}_vs_v{new_doc.version}_{datetime.now().strftime('%Y%m%d%H%M%S')}.md"

    return StreamingResponse(
        buffer,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )
