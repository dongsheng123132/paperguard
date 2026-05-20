"""案例 JSON 的 pydantic schema."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    RETRACTED = "retracted"
    DISPUTED = "disputed"
    CLEAN_CONTROL = "clean_control"
    SYNTHETIC = "synthetic"  # 我们自己合成的演示样本


class Source(BaseModel):
    type: Literal["pubpeer", "retraction_watch", "doi", "preprint", "other"]
    url: str


class KnownIssue(BaseModel):
    category: str  # 对应 detector 名,或自由文本
    desc: str


class Case(BaseModel):
    id: str
    title: str
    doi: str | None = None
    year: int | None = None
    journal: str | None = None
    verdict: Verdict
    sources: list[Source] = Field(default_factory=list)
    known_issues: list[KnownIssue] = Field(default_factory=list)
    expected_detectors: list[str] = Field(default_factory=list)
    pdf_path: str | None = None  # 相对项目根
    text_path: str | None = None  # 也支持 .txt 输入
    notes: str = ""

    def input_path(self) -> str | None:
        return self.pdf_path or self.text_path
