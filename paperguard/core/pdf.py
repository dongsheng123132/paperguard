"""PDF / TXT 文本抽取 — 保留页码,合并因换行被切碎的句子。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageText:
    page: int
    text: str


@dataclass
class Document:
    source: str
    pages: list[PageText]

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def word_count(self) -> int:
        return len(re.findall(r"\w+", self.full_text))

    def locate_page(self, snippet: str) -> int | None:
        for p in self.pages:
            if snippet in p.text:
                return p.page
        return None


_HYPHEN_BREAK = re.compile(r"-\s*\n\s*")
_LINE_JOIN = re.compile(r"(?<=[a-zA-Z,;])\n(?=[a-z])")


def _clean(text: str) -> str:
    text = _HYPHEN_BREAK.sub("", text)
    text = _LINE_JOIN.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def load(path: str | Path) -> Document:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(p)
    if suffix in {".txt", ".md"}:
        return Document(source=str(p), pages=[PageText(1, _clean(p.read_text(encoding="utf-8")))])
    raise ValueError(f"暂不支持的格式: {suffix}")


def _load_pdf(path: Path) -> Document:
    import fitz  # PyMuPDF

    pages: list[PageText] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            pages.append(PageText(page=i, text=_clean(page.get_text("text"))))
    return Document(source=str(path), pages=pages)
