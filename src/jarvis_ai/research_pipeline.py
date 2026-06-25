"""Multi-source web research with two-stage Claude synthesis and review."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import requests

from .actions.web_search import _ddg_search
CLAUDE_RESEARCH_MODEL = os.getenv("CLAUDE_RESEARCH_MODEL", "haiku")
CLAUDE_REVIEW_MODEL = os.getenv("CLAUDE_REVIEW_MODEL", "haiku")
_RESEARCH_CACHE_TTL = 30 * 60
_research_cache: dict[str, tuple[float, str]] = {}
_research_cache_lock = threading.Lock()


class _VisibleTextParser(HTMLParser):
    """Small dependency-free visible text extractor."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)

    def handle_data(self, data):
        if self._hidden_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if len(text) >= 2:
            self.parts.append(text)

    def text(self, limit: int = 5200) -> str:
        return " ".join(self.parts)[:limit]


def _normalize_url(url: str) -> str:
    """Resolve DuckDuckGo redirects and remove malformed wrapper characters."""
    value = unescape(unquote(str(url or ""))).strip(" []()\\")
    parsed = urlparse(value)
    if "duckduckgo.com" in parsed.netloc:
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            value = unquote(target)
    return value.strip(" []()\\")


def _source_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _domain_matches(domain: str, marker: str) -> bool:
    if marker.startswith("."):
        return domain.endswith(marker)
    return domain == marker or domain.endswith(f".{marker}")


def _question_keywords(question: str) -> list[str]:
    cleaned = question.lower()
    for phrase in (
        "에 대해서 알려줘", "에 대해 알려줘", "에 대해서 알려 줘",
        "에 대해 알려 줘", "알려줘", "알려 줘", "조사해줘", "조사해 줘",
        "설명해줘", "설명해 줘", "누구야", "누구인지",
    ):
        cleaned = cleaned.replace(phrase, " ")
    words = re.findall(r"[0-9a-zA-Z가-힣]{2,}", cleaned)
    particles = (
        "에서는", "에게서", "으로", "에서", "에게", "부터", "까지",
        "처럼", "보다", "하고", "이며", "이고", "의", "은", "는",
        "이", "가", "을", "를", "와", "과", "에",
    )
    keywords = []
    for word in words:
        for particle in particles:
            if word.endswith(particle) and len(word) - len(particle) >= 2:
                word = word[:-len(particle)]
                break
        if len(word) >= 2 and word not in keywords:
            keywords.append(word)
    return keywords[:5]


def _is_relevant_result(question: str, result: dict) -> bool:
    keywords = _question_keywords(question)
    if not keywords:
        return True
    haystack = " ".join(
        (
            str(result.get("title") or ""),
            str(result.get("snippet") or ""),
            unquote(str(result.get("url") or "")),
        )
    ).lower()
    return any(keyword in haystack for keyword in keywords)


def _source_trust_score(result: dict) -> int:
    domain = _source_domain(_normalize_url(result.get("url", "")))
    title = str(result.get("title") or "").lower()
    score = 0

    trusted_domains = (
        ".go.kr", ".gov", ".edu", ".ac.kr",
        "fifa.com", "uefa.com", "olympics.com", "premierleague.com",
        "tottenhamhotspur.com", "lafc.com", "the-afc.com",
        "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
        "nytimes.com", "theguardian.com", "britannica.com",
        "biography.com", "history.go.kr", "aks.ac.kr",
        "yna.co.kr", "kbs.co.kr", "imbc.com", "sbs.co.kr",
        "donga.com", "joins.com", "chosun.com", "hani.co.kr",
    )
    if any(_domain_matches(domain, marker) for marker in trusted_domains):
        score += 100
    if any(word in title for word in ("공식", "official", "프로필", "약력", "인터뷰")):
        score += 24
    if "wikipedia.org" in domain:
        score += 25
    low_quality = (
        "tistory.com", "blog.naver.com", "brunch.co.kr", "namu.wiki",
        "blogspot.com", "wordpress.com", "medium.com", "youtube.com",
        "youtu.be", "tiktok.com", "instagram.com", "facebook.com",
        "fanmaum.com", "dcinside.com", "fmkorea.com", "ruliweb.com",
        "jwiki.kr",
    )
    if any(_domain_matches(domain, marker) for marker in low_quality):
        score -= 120
    if not domain:
        score -= 200
    return score


def _fetch_source(result: dict) -> dict:
    url = _normalize_url(result.get("url", ""))
    source = {
        "title": str(result.get("title") or "").strip(),
        "url": url,
        "snippet": str(result.get("snippet") or "").strip(),
        "text": "",
        "trust_score": _source_trust_score(result),
    }
    if not url.startswith(("http://", "https://")):
        return source
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                )
            },
            timeout=8,
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type:
            return source
        parser = _VisibleTextParser()
        parser.feed(response.text)
        source["url"] = response.url
        source["text"] = parser.text()
    except (requests.RequestException, ValueError):
        pass
    return source


def collect_sources(question: str, max_sources: int = 5) -> list[dict]:
    """Search multiple query angles and fetch independent sources in parallel."""
    queries = [
        question,
        f"{question} 공식 프로필 소속 기관",
        (
            f"{question} site:reuters.com OR site:bbc.com "
            "OR site:apnews.com OR site:yna.co.kr"
        ),
        (
            f"{question} site:fifa.com OR site:olympics.com "
            "OR site:premierleague.com OR site:britannica.com"
        ),
        f"{question} site:wikipedia.org",
    ]
    search_results: list[dict] = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(queries)) as executor:
        futures = {
            executor.submit(_ddg_search, query, 6): query
            for query in queries
        }
        for future in as_completed(futures):
            try:
                search_results.extend(future.result())
            except Exception as exc:
                print(f"[빠른 조사] 검색 실패: {type(exc).__name__}")

    # Prefer official organizations, institutions and established news sources.
    search_results.sort(key=_source_trust_score, reverse=True)
    selected: list[dict] = []
    seen_urls: set[str] = set()
    seen_domains: set[str] = set()
    seen_titles: set[str] = set()
    for result in search_results:
        url = _normalize_url(result.get("url", ""))
        domain = _source_domain(url)
        normalized_title = re.sub(
            r"[^0-9a-zA-Z가-힣]+", " ", str(result.get("title") or "").lower()
        ).strip()
        if not url or url in seen_urls or not domain:
            continue
        if not _is_relevant_result(question, result):
            continue
        if domain in seen_domains:
            continue
        if normalized_title and normalized_title in seen_titles:
            continue
        if _source_trust_score(result) < -50:
            continue
        selected.append({**result, "url": url})
        seen_urls.add(url)
        seen_domains.add(domain)
        if normalized_title:
            seen_titles.add(normalized_title)
        if len(selected) >= max_sources + 2:
            break

    with ThreadPoolExecutor(max_workers=min(6, len(selected) or 1)) as executor:
        fetched = list(executor.map(_fetch_source, selected))

    useful = [
        source for source in fetched
        if source["url"] and (source["text"] or source["snippet"])
    ]
    useful.sort(
        key=lambda source: (
            -source["trust_score"],
            0 if source["text"] else 1,
            -len(source["text"]),
        )
    )
    result = useful[:max_sources]
    trusted_count = sum(source["trust_score"] >= 80 for source in result)
    if len(result) < 3 or trusted_count < 2:
        print(
            f"[빠른 조사] 신뢰 출처 부족 "
            f"(전체 {len(result)}개, 신뢰 {trusted_count}개)"
        )
        return []
    print(
        f"[빠른 조사] 병렬 검색·수집 완료 "
        f"({time.monotonic() - started:.1f}초, {len(result)}개 출처)"
    )
    return result


def synthesize_sources_with_claude(question: str, sources: list[dict]) -> str:
    """Create the final sourced answer in one Claude call."""
    if len(sources) < 3:
        return ""

    source_blocks = []
    for index, source in enumerate(sources, 1):
        evidence = source["text"] or source["snippet"]
        source_blocks.append(
            f"[출처 {index}]\n"
            f"제목: {source['title']}\n"
            f"URL: {source['url']}\n"
            f"내용: {evidence[:2800]}"
        )
    evidence_bundle = "\n\n".join(source_blocks)
    prompt = f"""
다음 사용자 질문에 대해 제공된 웹 자료만 근거로 자비스의 최종 답변을 작성하세요.

[사용자 질문]
{question}

[현재 날짜]
{date.today().isoformat()}

[수집된 독립 출처]
{evidence_bundle}

[작성 규칙]
1. 자료에 없는 사실은 추가하지 마세요.
2. 서로 일치하는 핵심 사실을 우선하고, 충돌하는 최신 수치·직함·소속은
   확정하지 말고 출처별 차이가 있다고 짧게 밝히세요.
3. "최초", "최다", "역대", "세계 최고"는 공식 자료가 명확히 뒷받침할 때만 쓰세요.
4. 자연스러운 한국어로 핵심부터 6~10문장으로 답하세요.
5. "올해", "현재", "최근"처럼 출처 작성 시점에 따라 달라지는 표현 대신
   2025년처럼 확인 가능한 절대 날짜를 쓰세요.
6. Markdown 제목, 굵은 글씨, 표를 사용하지 마세요.
7. 출처 목록과 URL은 프로그램이 별도로 붙이므로 본문만 작성하세요.
8. 편집 과정 설명 없이 최종 답변만 출력하세요.
""".strip()
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", CLAUDE_REVIEW_MODEL,
        "--effort", "low",
        "--tools", "",
        "--permission-mode", "dontAsk",
        "--no-chrome",
        "--disable-slash-commands",
        "--prompt-suggestions", "false",
        "--no-session-persistence",
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"[빠른 조사] Claude 단일 정리 시작 (모델: {CLAUDE_REVIEW_MODEL})")
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=90,
        )
        if result.returncode != 0:
            print(
                "[빠른 조사] Claude 정리 실패: "
                f"{(result.stderr or result.stdout).strip()[:300]}"
            )
            return ""
        data = json.loads(result.stdout.strip())
        body = clean_research_output(str(data.get("result") or "").strip())
        body = re.split(
            r"\n\s*(?:#{1,6}\s*)?\[?출처\]?\s*:?\s*\n",
            body,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        if len(body) < 80:
            print("[빠른 조사] Claude 본문이 너무 짧아 폴백합니다.")
            return ""
        source_lines = [
            f"- {source['title'] or _source_domain(source['url'])}: {source['url']}"
            for source in sources[:5]
        ]
        final = f"{body}\n\n출처\n" + "\n".join(source_lines)
        print(f"[빠른 조사] Claude 정리 완료 ({time.monotonic() - started:.1f}초)")
        return final
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError):
        return ""


def needs_verified_research(text: str) -> bool:
    """Return True for questions that benefit from multi-source research."""
    query = text.lower().strip()
    if not query:
        return False

    # Dedicated local tools are faster and more authoritative for these.
    local_topics = (
        "날씨", "기온", "미세먼지", "초미세먼지", "자외선", "환율",
        "공휴일", "지진", "몇 시", "몇시", "날짜", "요일", "계산",
        "단위 변환", "볼륨", "밝기", "유튜브", "알림",
    )
    if any(topic in query for topic in local_topics):
        return False

    research_markers = (
        "누구야", "누구인지", "어떤 사람이", "인물", "생애", "업적",
        "논란", "에 대해 알려", "에 대해서 알려", "조사해", "조사해서",
        "자료 찾아", "여러 출처", "비교해서", "사건 정리", "기업 분석",
        "정책 분석", "최신 이슈", "팩트체크",
    )
    return any(marker in query for marker in research_markers)


def research_with_claude(question: str) -> str:
    """Ask Claude CLI to search and synthesize at least three sources."""
    prompt = f"""
다음 질문을 웹에서 직접 조사하세요.

[질문]
{question}

[현재 날짜]
{date.today().isoformat()}

[조사 규칙]
1. WebSearch와 WebFetch를 사용해 서로 독립적인 대표 출처를 최소 3개 확인하세요.
2. 위키백과만으로 답하지 마세요. 위키백과를 사용했다면 반드시 공식 사이트,
   신뢰도 높은 언론, 기관·대학·전문 자료 중 최소 2개를 추가로 대조하세요.
3. 인물 정보는 공식 약력/소속기관, 주요 언론, 전문 자료를 우선하세요.
4. 출처끼리 내용이 다르면 차이를 숨기지 말고 명시하세요.
5. 확인되지 않은 추측은 제외하세요.
6. 답변을 내기 전에 이름, 날짜, 수치, 현재 소속이 출처와 일치하는지 스스로 검수하세요.
7. 한국어로 5~8문장으로 간결하게 정리하고 마지막에 아래 형식으로 URL을 남기세요.
8. "올해", "현재", "최근" 대신 확인 가능한 절대 날짜를 사용하세요.
9. Markdown 링크가 아니라 출처명과 원본 URL을 일반 텍스트로 출력하세요.

[답변]
핵심 요약
주요 내용
주의하거나 논쟁적인 부분

[출처]
- 출처명: URL
- 출처명: URL
- 출처명: URL
""".strip()

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", CLAUDE_RESEARCH_MODEL,
        "--effort", "low",
        "--tools", "WebSearch,WebFetch",
        "--allowedTools", "WebSearch,WebFetch",
        "--permission-mode", "auto",
        "--no-chrome",
        "--disable-slash-commands",
        "--prompt-suggestions", "false",
        "--no-session-persistence",
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    print(f"[조사] Claude 다중 출처 검색 시작 (모델: {CLAUDE_RESEARCH_MODEL})")
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=180,
        )
        elapsed = time.monotonic() - started
        if result.returncode != 0:
            print(f"[조사] Claude 검색 실패: {result.stdout or result.stderr}")
            return ""
        data = json.loads(result.stdout.strip())
        answer = str(data.get("result") or "").strip()
        source_count = len(re.findall(r"https?://\S+", answer))
        if source_count < 3:
            print(f"[조사] 출처 부족 ({source_count}개) - 조사 결과를 사용하지 않습니다.")
            return ""
        print(f"[조사] Claude 검색 완료 ({elapsed:.1f}초, {len(answer)}자)")
        return answer
    except subprocess.TimeoutExpired:
        print("[조사] Claude 검색이 180초를 초과했습니다.")
        return ""
    except (OSError, ValueError, TypeError) as exc:
        print(f"[조사] Claude 검색 오류: {exc}")
        return ""


def _split_research_answer(draft: str) -> tuple[str, list[str]]:
    """Separate readable body from normalized, source-preserving URL lines."""
    cleaned = clean_research_output(draft)
    parts = re.split(
        r"\n\s*(?:#{1,6}\s*)?\[?출처\]?\s*:?\s*\n",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    body = parts[0].strip()
    source_text = parts[1] if len(parts) > 1 else cleaned
    source_lines: list[str] = []
    seen_urls: set[str] = set()
    for line in source_text.splitlines():
        match = re.search(r"https?://[^\s)\]]+", line)
        if not match:
            continue
        url = match.group(0).rstrip(".,;:")
        if url in seen_urls:
            continue
        label = line[:match.start()].strip(" -:[]()")
        label = label.replace("[", "").replace("]", "")
        label = re.sub(r"\s+", " ", label) or _source_domain(url)
        source_lines.append(f"- {label}: {url}")
        seen_urls.add(url)
        if len(source_lines) >= 5:
            break
    return body, source_lines


def finalize_with_claude(question: str, draft: str) -> str:
    """Turn research notes into a clean, source-preserving final answer."""
    if not draft.strip():
        return ""
    draft_body, source_lines = _split_research_answer(draft)
    safe_fallback = draft_body
    if source_lines:
        safe_fallback += "\n\n출처\n" + "\n".join(source_lines)

    prompt = f"""
아래 Claude 웹 조사 초안을 최종 검수해 자연스러운 한국어 본문만 출력하세요.

[사용자 질문]
{question}

[현재 날짜]
{date.today().isoformat()}

[검수할 본문]
{draft_body}

[편집 규칙]
1. 초안에 없는 사실을 추가하지 마세요.
2. 현재 시점으로 확정할 수 없는 수치·직함·소속은 단정하지 마세요.
3. 출처 작성 시점의 "올해", "현재", "최근"은 절대 연도로 고치세요.
4. 반복을 제거하고 핵심부터 5~8문장으로 간결하게 정리하세요.
5. Markdown, 제목, 목록, URL, 출처, 검수 설명은 출력하지 마세요.
""".strip()

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", CLAUDE_REVIEW_MODEL,
        "--effort", "low",
        "--tools", "",
        "--permission-mode", "dontAsk",
        "--no-chrome",
        "--disable-slash-commands",
        "--prompt-suggestions", "false",
        "--no-session-persistence",
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"[Claude 검수] 조사 결과 최종 정리 시작 (모델: {CLAUDE_REVIEW_MODEL})")
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=60,
        )
        if result.returncode != 0:
            print("[Claude 검수] 실패 - 정제된 안전 초안을 사용합니다.")
            return safe_fallback
        data = json.loads(result.stdout.strip())
        final_body = clean_research_output(str(data.get("result") or "").strip())
        final_body = re.split(
            r"\n\s*(?:#{1,6}\s*)?\[?출처\]?\s*:?\s*\n",
            final_body,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        if len(final_body) < 80:
            print("[Claude 검수] 결과 부족 - 정제된 안전 초안을 사용합니다.")
            return safe_fallback
        final = final_body
        if source_lines:
            final += "\n\n출처\n" + "\n".join(source_lines)
        print(f"[Claude 검수] 완료 ({time.monotonic() - started:.1f}초)")
        return final
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError) as exc:
        print(f"[Claude 검수] 오류 - 정제된 안전 초안 사용: {type(exc).__name__}")
        return safe_fallback


def clean_research_output(text: str) -> str:
    """Normalize malformed nested Markdown links and excessive decoration."""
    cleaned = text.strip()
    # [label]([url](url\)) 같은 Claude 도구 출력의 중첩 링크를 단순 출처로 변환.
    cleaned = re.sub(
        r"\[([^\]]+)\]\(\[(https?://[^\]]+)\]\(https?://[^)]+\)(?:\\)?\)",
        r"\1: \2",
        cleaned,
    )
    cleaned = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)(?:\\)?\)",
        r"\1: \2",
        cleaned,
    )
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*\[답변\]\s*$", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*---+\s*$", "", cleaned)
    cleaned = re.sub(
        r"^\s*(?:충분한 출처를 확인했습니다|조사를 완료했습니다)[^.。\n]*[.。]?\s*",
        "",
        cleaned,
    )
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def run_research_pipeline(question: str) -> str:
    cache_key = re.sub(r"\s+", " ", question.strip().lower())
    with _research_cache_lock:
        cached = _research_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _RESEARCH_CACHE_TTL:
        print("[빠른 조사] 캐시 응답 사용")
        return cached[1]

    # Best measured path: collect trusted sources in parallel, then have Claude
    # synthesize and self-review in one request. This averaged ~35 seconds in
    # local tests, versus ~78 seconds for Claude's fully agentic search.
    sources = collect_sources(question)
    final = synthesize_sources_with_claude(question, sources)

    # Reliability fallback: use Claude's native agentic search if direct
    # collection cannot secure enough trusted sources.
    if not final:
        print("[빠른 조사] 신뢰 출처 직접 수집 실패 - Claude 기본 웹 검색 폴백")
        researched = research_with_claude(question)
        if not researched:
            return ""
        body, source_lines = _split_research_answer(researched)
        final = body
        if source_lines:
            final += "\n\n출처\n" + "\n".join(source_lines)

    with _research_cache_lock:
        _research_cache[cache_key] = (time.monotonic(), final)
    return final


def research_text_for_speech(answer: str) -> str:
    """Read only a concise opening summary and never speak URLs."""
    body = re.split(
        r"\n\s*(?:#{1,6}\s*)?\[?출처\]?\s*:?\s*\n",
        answer,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    body = re.sub(r"https?://\S+", "", body)
    body = re.sub(r"(?m)^\s*[-*]\s*", "", body)
    body = body.replace("**", "").replace("#", "")
    sentences = re.split(r"(?<=[.!?다요])\s+", body.strip())
    concise = " ".join(sentence for sentence in sentences[:4] if sentence).strip()
    return concise or body.strip() or answer
