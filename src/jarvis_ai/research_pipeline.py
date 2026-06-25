"""Multi-source research with Claude and optional Gemini editorial review."""

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
from .paths import CONFIG_DIR


CLAUDE_RESEARCH_MODEL = os.getenv("CLAUDE_RESEARCH_MODEL", "haiku")
CLAUDE_REVIEW_MODEL = os.getenv("CLAUDE_REVIEW_MODEL", "haiku")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
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
    if any(marker in domain for marker in trusted_domains):
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
    if any(marker in domain for marker in low_quality):
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
    for result in search_results:
        url = _normalize_url(result.get("url", ""))
        domain = _source_domain(url)
        if not url or url in seen_urls or not domain:
            continue
        if not _is_relevant_result(question, result):
            continue
        if domain in seen_domains:
            continue
        if _source_trust_score(result) < -50:
            continue
        selected.append({**result, "url": url})
        seen_urls.add(url)
        seen_domains.add(domain)
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


def _load_gemini_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        if key.startswith("AIza") and len(key) >= 30:
            return key
        print("[Gemini] API 키 형식이 올바르지 않아 Claude 검수만 사용합니다.")
        return ""
    config_path = CONFIG_DIR / "api_keys.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        key = str(data.get("gemini_api_key") or "").strip()
        if key and not (key.startswith("AIza") and len(key) >= 30):
            print("[Gemini] 저장된 API 키 형식이 올바르지 않습니다.")
            return ""
        return key
    except (OSError, ValueError, TypeError):
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

[조사 규칙]
1. WebSearch와 WebFetch를 사용해 서로 독립적인 대표 출처를 최소 3개 확인하세요.
2. 위키백과만으로 답하지 마세요. 위키백과를 사용했다면 반드시 공식 사이트,
   신뢰도 높은 언론, 기관·대학·전문 자료 중 최소 2개를 추가로 대조하세요.
3. 인물 정보는 공식 약력/소속기관, 주요 언론, 전문 자료를 우선하세요.
4. 출처끼리 내용이 다르면 차이를 숨기지 말고 명시하세요.
5. 확인되지 않은 추측은 제외하세요.
6. 한국어로 간결하게 정리하고 마지막에 아래 형식으로 URL을 남기세요.

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


def _review_with_gemini(question: str, draft: str) -> str | None:
    """Return a Gemini-edited answer, or None when Gemini is unavailable."""
    if not draft.strip():
        return None
    api_key = _load_gemini_api_key()
    if not api_key:
        print("[Gemini] API 키 없음 - Claude 최종 정리로 전환합니다.")
        return None

    instruction = f"""
당신은 사실을 새로 만드는 답변자가 아니라 한국어 편집 검수자입니다.

[사용자 질문]
{question}

[Claude 조사 초안]
{draft}

[엄격한 검수 규칙]
1. 초안에 없는 사실, 해석, 숫자, 날짜, 인물, 출처를 절대 추가하지 마세요.
2. 숫자·고유명사·URL을 임의로 변경하거나 삭제하지 마세요.
3. 문장 흐름, 한국어 어조, 중복 표현만 다듬으세요.
4. 출처로 뒷받침되지 않는 단정은 완화하거나 제거하세요.
5. 출처 간 충돌이나 불확실성은 그대로 표시하세요.
6. 마지막 [출처] 목록을 반드시 보존하세요.
7. 검수 설명은 쓰지 말고 최종 답변만 출력하세요.
""".strip()

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": instruction}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1600,
        },
    }
    print(f"[Gemini] 최종 문장 검수 시작 (모델: {GEMINI_MODEL})")
    started = time.monotonic()
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        reviewed = "".join(str(part.get("text") or "") for part in parts).strip()
        if not reviewed:
            raise ValueError("Gemini 응답이 비어 있습니다.")
        print(f"[Gemini] 검수 완료 ({time.monotonic() - started:.1f}초)")
        return reviewed
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        print(f"[Gemini] HTTP {status} - Claude 최종 정리로 전환합니다.")
        return None
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as exc:
        print(f"[Gemini] 검수 실패 - Claude 최종 정리로 전환: {type(exc).__name__}")
        return None


def review_with_gemini(question: str, draft: str) -> str:
    """Compatibility wrapper: return the draft if Gemini cannot review it."""
    return _review_with_gemini(question, draft) or draft


def finalize_with_claude(question: str, draft: str) -> str:
    """Turn research notes into a clean, source-preserving final answer."""
    if not draft.strip():
        return ""

    prompt = f"""
당신은 자비스의 최종 답변 편집자입니다. 아래 웹 조사 초안을 사용해 사용자가
바로 읽고 들을 수 있는 자연스러운 한국어 답변으로 다시 작성하세요.

[사용자 질문]
{question}

[웹 조사 초안]
{draft}

[편집 규칙]
1. 초안에 없는 사실을 추가하지 마세요.
2. 출처에서 명확히 뒷받침되지 않는 최신 수치·날짜·직함·재산·이적 정보는
   삭제하거나 "출처별로 차이가 있다"고 표현하세요.
3. "최다", "최초", "역대", "세계 최고" 같은 최상급 표현은 공식 출처가
   해당 표현을 명확히 뒷받침할 때만 유지하고, 아니면 중립적으로 바꾸세요.
4. 같은 내용을 반복하지 말고 핵심부터 설명하세요.
5. 전체 본문은 보통 6~10문장으로 간결하게 작성하세요.
6. Markdown 제목 기호(##, ###), 굵은 글씨 기호(**), 표는 쓰지 마세요.
7. 마지막에는 정확히 "출처"라는 줄을 쓰고, 대표 출처 3~5개만 아래처럼
   깨끗한 형식으로 남기세요. 중첩 링크 문법은 금지합니다.
   - 출처명: https://example.com
8. URL은 초안에 실제로 존재하는 URL만 사용하고 변형하지 마세요.
9. 논쟁적이거나 출처가 충돌하는 내용은 한 문장으로 짧게 명시하세요.
10. 검수 과정 설명 없이 최종 답변만 출력하세요.
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
            timeout=90,
        )
        if result.returncode != 0:
            print("[Claude 검수] 실패 - 조사 초안을 정리해서 사용합니다.")
            return clean_research_output(draft)
        data = json.loads(result.stdout.strip())
        final = clean_research_output(str(data.get("result") or "").strip())
        if not final or len(re.findall(r"https?://\S+", final)) < 3:
            print("[Claude 검수] 출처 보존 실패 - 조사 초안을 정리해서 사용합니다.")
            return clean_research_output(draft)
        print(f"[Claude 검수] 완료 ({time.monotonic() - started:.1f}초)")
        return final
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError) as exc:
        print(f"[Claude 검수] 오류 - 조사 초안 사용: {type(exc).__name__}")
        return clean_research_output(draft)


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

    # Fast path: collect websites in parallel, then ask Claude to write once.
    sources = collect_sources(question)
    draft = synthesize_sources_with_claude(question, sources)

    # Reliability fallback: Claude's built-in web tools when direct collection fails.
    if not draft:
        print("[빠른 조사] 직접 수집 실패 - Claude 웹 검색 폴백")
        researched = research_with_claude(question)
        if not researched:
            return ""
        draft = finalize_with_claude(question, researched)

    gemini_result = _review_with_gemini(question, draft)
    if gemini_result:
        final = clean_research_output(gemini_result)
    else:
        # Fast path already produced a polished final answer, so no second Claude call.
        final = clean_research_output(draft)

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
