from __future__ import annotations

from io import BytesIO

from docx import Document as DocxDocument
from openpyxl import Workbook

from campusmind.knowledge.ingestion import DocxParser
from campusmind.knowledge.ingestion import ExcelParser
from campusmind.knowledge.ingestion import MarkdownParser
from campusmind.knowledge.ingestion import PdfParser
from campusmind.knowledge.ingestion import ParserRegistry, UnsupportedDocumentType
from campusmind.knowledge.ingestion import TextParser


def _minimal_pdf(text: str = "CampusMind PDF ingestion 160 credits") -> bytes:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin1")
    objects.append(
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    )
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def test_registry_supports_ingestion_formats():
    registry = ParserRegistry()
    for filename in (
        "policy.pdf",
        "guide.docx",
        "notice.txt",
        "training.md",
        "courses.xlsx",
        "legacy.xls",
    ):
        assert registry.get(filename)
    try:
        registry.get("image.png")
    except UnsupportedDocumentType:
        pass
    else:
        raise AssertionError("png should not be supported in document ingestion")


def test_markdown_preserves_chapter_and_section():
    parsed = MarkdownParser().parse(
        "# 培养方案\n\n## 毕业要求\n\n最低需要160学分。\n".encode("utf-8"),
        filename="plan.md",
    )
    assert len(parsed.blocks) == 1
    block = parsed.blocks[0]
    assert block.chapter == "培养方案"
    assert block.section == "毕业要求"
    assert "160" in block.text


def test_text_parser_accepts_utf8():
    parsed = TextParser().parse("CampusMind ingestion text".encode(), filename="a.txt")
    assert parsed.blocks[0].text == "CampusMind ingestion text"


def test_pdf_parser_extracts_page_number_and_text():
    parsed = PdfParser().parse(_minimal_pdf(), filename="test.pdf")
    assert parsed.metadata["page_count"] == 1
    assert parsed.blocks[0].page == 1
    assert "160 credits" in parsed.blocks[0].text


def test_docx_parser_preserves_heading_structure():
    doc = DocxDocument()
    doc.add_heading("培养方案", level=1)
    doc.add_heading("毕业要求", level=2)
    doc.add_paragraph("软件工程专业最低需要160学分。")
    buf = BytesIO()
    doc.save(buf)
    parsed = DocxParser().parse(buf.getvalue(), filename="plan.docx")
    assert parsed.blocks[0].chapter == "培养方案"
    assert parsed.blocks[0].section == "毕业要求"
    assert "160" in parsed.blocks[0].text


def test_excel_parser_turns_rows_into_structured_blocks():
    wb = Workbook()
    ws = wb.active
    ws.title = "课程"
    ws.append(["课程", "学分"])
    ws.append(["机器学习", 3])
    buf = BytesIO()
    wb.save(buf)
    parsed = ExcelParser().parse(buf.getvalue(), filename="courses.xlsx")
    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].chapter == "课程"
    assert "机器学习" in parsed.blocks[0].text
    assert "学分: 3" in parsed.blocks[0].text
