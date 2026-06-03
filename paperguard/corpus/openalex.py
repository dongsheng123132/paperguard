"""极简 OpenAlex 客户端 —— 纯标准库,不引入新依赖.

设计参考 Google DeepMind `science-skills` 里的 OpenAlex skill:
先 resolve(名字→实体 ID),再 filter(按实体拉作品),输出供上层判读。

- 走代理: 显式 `proxy=` 参数优先,否则沿用环境变量 HTTP(S)_PROXY(urllib 默认行为)。
- polite pool: 传 `mailto=`(或环境变量 OPENALEX_MAILTO)进入礼貌池,更稳。
- 失败抛 OpenAlexError,由上层 scan 捕获转成"体检未完成"提示,绝不静默当成"干净"。
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

API = "https://api.openalex.org"

# 拉作品时取的字段(open_access / best_oa_location 留给 Phase B 的 OA 深扫复用)
_WORK_SELECT = "id,doi,title,publication_year,is_retracted,open_access,best_oa_location"

_ID_RE = re.compile(r"(?:openalex\.org/)?([AaIi]\d{4,})\b")


class OpenAlexError(RuntimeError):
    """OpenAlex 请求失败(网络 / 代理 / 限流 / 4xx-5xx)。"""


def _opener(proxy: str | None) -> urllib.request.OpenerDirector:
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    # 不传 proxy 时,build_opener() 默认带一个读取环境变量/系统代理的 ProxyHandler
    return urllib.request.build_opener()


def _get(path: str, params: dict[str, Any], *, mailto: str | None, proxy: str | None,
         timeout: float = 30.0) -> dict:
    params = {k: v for k, v in params.items() if v is not None}
    mailto = mailto or os.environ.get("OPENALEX_MAILTO")
    if mailto:
        params["mailto"] = mailto
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": f"PaperGuard/0.4 (mailto:{mailto or 'n/a'})"})
    try:
        with _opener(proxy).open(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        raise OpenAlexError(f"OpenAlex 请求失败: {e}  ({url})") from e


def short_id(oid: str) -> str:
    """`https://openalex.org/I4210144430` / `i4210144430` -> `I4210144430`."""
    m = _ID_RE.search(oid or "")
    if not m:
        return oid or ""
    sid = m.group(1)
    return sid[0].upper() + sid[1:]


def looks_like_id(query: str) -> str | None:
    """识别用户是否直接传了 OpenAlex ID;返回规范化短 ID 或 None。"""
    m = _ID_RE.fullmatch(query.strip()) or _ID_RE.search(query.strip())
    if not m:
        return None
    sid = m.group(1)
    return sid[0].upper() + sid[1:]


def _entity_kind(sid: str) -> str:
    return "institution" if sid[:1].upper() == "I" else "author"


def resolve_entity(query: str, kind: str = "auto", *, mailto: str | None = None,
                   proxy: str | None = None) -> dict | None:
    """名字 / ID -> 实体。返回 {id(短), kind, display_name, works_count, cited_by_count} 或 None。

    kind: institution / author / auto(先按机构搜,无果再按作者)。
    """
    query = (query or "").strip()
    if not query:
        return None

    sid = looks_like_id(query)
    if sid:
        ek = _entity_kind(sid)
        coll = "institutions" if ek == "institution" else "authors"
        data = _get(f"{coll}/{sid}", {"select": "id,display_name,works_count,cited_by_count"},
                    mailto=mailto, proxy=proxy)
        return {
            "id": short_id(data["id"]),
            "kind": ek,
            "display_name": data.get("display_name", sid),
            "works_count": data.get("works_count", 0),
            "cited_by_count": data.get("cited_by_count", 0),
        }

    order = (["institution", "author"] if kind == "auto"
             else [kind] if kind in ("institution", "author") else ["institution", "author"])
    for ek in order:
        coll = "institutions" if ek == "institution" else "authors"
        data = _get(coll, {"search": query, "per-page": 1,
                           "select": "id,display_name,works_count,cited_by_count"},
                    mailto=mailto, proxy=proxy)
        results = data.get("results") or []
        if results:
            top = results[0]
            return {
                "id": short_id(top["id"]),
                "kind": ek,
                "display_name": top.get("display_name", query),
                "works_count": top.get("works_count", 0),
                "cited_by_count": top.get("cited_by_count", 0),
            }
    return None


def fetch_works(entity_id: str, kind: str, *, max_works: int = 500,
                mailto: str | None = None, proxy: str | None = None) -> tuple[list[dict], int]:
    """按实体拉作品(cursor 分页)。返回 (works, total_count)。

    works 每项含 _WORK_SELECT 的字段。最多取 max_works 篇;total_count 是该实体作品总数。
    """
    sid = short_id(entity_id)
    field = "institutions.id" if kind == "institution" else "authorships.author.id"
    works: list[dict] = []
    total = 0
    cursor = "*"
    while cursor and len(works) < max_works:
        data = _get("works", {
            "filter": f"{field}:{sid}",
            "select": _WORK_SELECT,
            "per-page": min(200, max_works - len(works)),
            "cursor": cursor,
            "sort": "publication_date:desc",
        }, mailto=mailto, proxy=proxy)
        total = data.get("meta", {}).get("count", total)
        batch = data.get("results") or []
        works.extend(batch)
        cursor = data.get("meta", {}).get("next_cursor")
        if not batch:
            break
    return works[:max_works], total
