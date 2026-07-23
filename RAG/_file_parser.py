from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from ._errors import FileParsingError, UnsupportedFileTypeError


@dataclass(slots=True, frozen=True)
class ExtractedFileText:
    text: str
    source_type: str
    original_name: str


_SOURCE_TYPES_BY_EXTENSION = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "md",
    ".markdown": "md",
    ".html": "html",
    ".htm": "html",
}


def extract_file_text(file_name: str, content: bytes) -> ExtractedFileText:
    normalized_name = Path(file_name.strip().replace("\\", "/")).name
    extension = Path(normalized_name).suffix.lower()
    source_type = _SOURCE_TYPES_BY_EXTENSION.get(extension)
    if source_type is None:
        raise UnsupportedFileTypeError(
            f"unsupported file type {extension or '<none>'}; "
            "expected docx, pdf, txt, md, or html"
        )
    if not content:
        raise FileParsingError("file is empty")

    parser = {
        "docx": _extract_docx,
        "pdf": _extract_pdf,
        "text": _extract_plain_text,
        "md": _extract_plain_text,
        "html": _extract_html,
    }[source_type]
    try:
        text = _normalize_text(parser(content))
    except FileParsingError:
        raise
    except Exception as error:
        raise FileParsingError(f"failed to parse {extension} file") from error

    if not text:
        raise FileParsingError("file contains no extractable text")
    return ExtractedFileText(
        text=text,
        source_type=source_type,
        original_name=normalized_name,
    )


def _extract_plain_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise FileParsingError("text file must use UTF-8 encoding") from error


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted:
        raise FileParsingError("encrypted PDF files are not supported")
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    document = Document(BytesIO(content))
    blocks: list[str] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            blocks.append(block.text)
        elif isinstance(block, Table):
            for row in block.rows:
                blocks.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(blocks)


def _extract_html(content: bytes) -> str:
    parser = _VisibleHTMLTextExtractor()
    parser.feed(_extract_plain_text(content))
    parser.close()
    return parser.text


class _VisibleHTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
    _HIDDEN_TAGS = {"head", "noscript", "script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._hidden_depth = 0

    @property
    def text(self) -> str:
        return "".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._HIDDEN_TAGS:
            self._hidden_depth += 1
        elif not self._hidden_depth and tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if not self._hidden_depth and tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._HIDDEN_TAGS:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        elif not self._hidden_depth and tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self._parts.append(data)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", "\n".join(lines)).strip()
