"""共用数据类型 — Finding / Severity / Report."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Finding(BaseModel):
    detector: str
    severity: Severity
    title: str
    detail: str
    snippet: str = ""
    page: int | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DetectorResult(BaseModel):
    detector: str
    findings: list[Finding] = Field(default_factory=list)
    skipped: bool = False
    error: str | None = None


class Report(BaseModel):
    source: str
    page_count: int
    word_count: int
    results: list[DetectorResult]
    risk_score: float = 0.0
    # "paper" = 单篇 PDF/TXT 体检; "corpus" = 机构/作者级元数据体检
    kind: str = "paper"
    subject: str | None = None  # corpus 模式下的实体名(机构/作者)

    @property
    def findings(self) -> list[Finding]:
        out: list[Finding] = []
        for r in self.results:
            out.extend(r.findings)
        return out

    def compute_risk(self) -> float:
        weights = {
            Severity.INFO: 0.0,
            Severity.LOW: 1.0,
            Severity.MEDIUM: 3.0,
            Severity.HIGH: 6.0,
            Severity.CRITICAL: 10.0,
        }
        score = sum(weights[f.severity] * f.confidence for f in self.findings)
        self.risk_score = round(score, 2)
        return self.risk_score
