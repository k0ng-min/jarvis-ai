# actions/web_search.py
# 자비스 — 웹 검색 (Claude CLI 기반)

import json
import html
import re
import subprocess
from urllib.parse import unquote

import requests


def _claude_search(query: str) -> str:
    """Claude CLI로 검색 수행"""
    prompt = f"다음에 대해 최신 정보를 바탕으로 간결하게 답변하세요: {query}"
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[WebSearch] Claude 오류: {e}")
    return ""


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    """DuckDuckGo 검색 폴백"""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url":     r.get("href", ""),
                })
        return results
    except Exception as e:
        print(f"[WebSearch] DDG 라이브러리 오류: {e}")

    # 추가 패키지가 없어도 DuckDuckGo 웹페이지를 직접 조회한다.
    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "kr-kr"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        response.raise_for_status()
        source = response.text
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
            r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            source,
            flags=re.DOTALL,
        )
        results = []
        for url, title, snippet in blocks[:max_results]:
            clean = lambda value: html.unescape(
                re.sub(r"<[^>]+>", "", value)
            ).strip()
            results.append({
                "title": clean(title),
                "snippet": clean(snippet),
                "url": unquote(url),
            })
        return results
    except Exception as e:
        print(f"[WebSearch] DDG 웹 조회 오류: {e}")
        return []


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"'{query}'에 대한 검색 결과가 없습니다."
    lines = [f"'{query}' 검색 결과:\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):   lines.append(f"{i}. {r['title']}")
        if r.get("snippet"): lines.append(f"   {r['snippet']}")
        if r.get("url"):     lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def web_search(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    query  = params.get("query", "").strip()

    if not query:
        return "검색어를 입력해주세요."

    if player:
        player.write_log(f"[검색] {query}")

    print(f"[WebSearch] 🔍 검색: {query}")

    # 실제 검색 엔진을 먼저 조회한다. Claude의 학습 데이터에 의존하지 않는다.
    ddg_results = _ddg_search(query, int(params.get("max_results", 6)))
    if ddg_results:
        print("[WebSearch] ✅ DuckDuckGo 실시간 검색 성공")
        return _format_ddg(query, ddg_results)

    # 검색 엔진 연결 실패 시에만 Claude를 마지막 폴백으로 사용한다.
    result = _claude_search(query)
    if result:
        print("[WebSearch] ⚠️ Claude 폴백 응답")
        return result
    return f"'{query}'에 대한 실시간 검색 결과를 가져오지 못했습니다."
