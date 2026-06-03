"""机构 / 作者级体检 (corpus scan).

给一个机构名 / 作者名 / OpenAlex ID(或一份离线 DOI 清单),
用 OpenAlex 的 is_retracted 标记 + 本地 Retraction Watch 库做交叉验证,
产出"撤稿 / 被质疑记录 + 发文画像"报告 —— 复用 paperguard 既有的 Report 契约。

只查公开撤稿记录,输出一律"疑似 / 记录"而非"定罪"。
"""
from __future__ import annotations

from .scan import scan_corpus

__all__ = ["scan_corpus"]
