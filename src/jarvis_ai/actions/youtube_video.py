# actions/youtube_video.py — 자비스 유튜브 제어

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _TRANSCRIPT_OK = True
except ImportError:
    _TRANSCRIPT_OK = False

import platform

_OS = platform.system()
_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _open_url(url: str) -> None:
    try:
        if _OS == "Darwin":      subprocess.Popen(["open", url])
        elif _OS == "Linux":     subprocess.Popen(["xdg-open", url])
        else:                    subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception as e:
        print(f"[YouTube] URL 열기 실패: {e}")


def _scrape_first_video_url(query: str) -> str | None:
    if not _REQUESTS_OK:
        return None
    try:
        url  = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={_YT_VIDEO_FILTER}"
        r    = requests.get(url, headers=HEADERS, timeout=10)
        html = r.text
        seen = set()
        for vid in re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html):
            if vid in seen: continue
            seen.add(vid)
            if f'/shorts/{vid}' not in html:
                return f"https://www.youtube.com/watch?v={vid}"
    except Exception as e:
        print(f"[YouTube] 스크래핑 실패: {e}")
    return None


def _extract_video_id(url: str) -> str | None:
    match = re.search(r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})", url)
    return match.group(1) if match else None


def _get_transcript(video_id: str) -> str | None:
    if not _TRANSCRIPT_OK:
        return None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        lang_priority   = ["ko", "en", "ja", "zh"]
        transcript      = None
        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break
        if not transcript:
            return None
        fetched = transcript.fetch()
        return " ".join(e["text"] for e in fetched)
    except Exception as e:
        print(f"[YouTube] 트랜스크립트 오류: {e}")
        return None


def _summarize_with_claude(transcript: str, video_url: str) -> str:
    """Claude CLI로 유튜브 영상 요약"""
    max_chars = 60000
    truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")
    prompt = (
        f"다음 유튜브 영상 트랜스크립트를 요약해주세요:\n\n{truncated}\n\n"
        f"1문장 개요 + 3~5가지 핵심 포인트로 간결하게 한국어로 요약하세요."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=90, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[YouTube] Claude 요약 실패: {e}")
    return "요약을 생성하지 못했습니다."


def _handle_play(params: dict, player) -> str:
    query = params.get("query", "").strip()
    if not query:
        return "어떤 영상을 볼지 알려주세요."
    if player:
        player.write_log(f"[유튜브] 검색: {query}")
    video_url = _scrape_first_video_url(query)
    if video_url:
        _open_url(video_url)
        return f"유튜브에서 '{query}' 재생 중입니다."
    fallback = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={_YT_VIDEO_FILTER}"
    _open_url(fallback)
    return f"유튜브에서 '{query}'를 검색했습니다."


def _handle_summarize(params: dict, player, speak) -> str:
    if not _TRANSCRIPT_OK:
        return "youtube-transcript-api가 설치되지 않았습니다: pip install youtube-transcript-api"

    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk._default_root
        if root is None:
            root = tk.Tk(); root.withdraw()
        url = simpledialog.askstring("자비스", "유튜브 영상 URL을 입력하세요:", parent=root)
        url = url.strip() if url else None
    except Exception:
        url = None

    if not url:
        return "URL이 입력되지 않았습니다."

    video_id = _extract_video_id(url)
    if not video_id:
        return "유효한 유튜브 URL이 아닙니다."

    if speak:
        speak("트랜스크립트를 가져오는 중입니다.")

    transcript = _get_transcript(video_id)
    if not transcript:
        return "해당 영상의 트랜스크립트를 가져올 수 없습니다."

    if speak:
        speak("요약을 생성하고 있습니다.")

    summary = _summarize_with_claude(transcript, url)

    if params.get("save", False):
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = Path.home() / "Desktop" / f"유튜브_요약_{ts}.txt"
        filepath.write_text(f"URL: {url}\n\n{summary}", encoding="utf-8")
        return f"요약이 완료되어 바탕화면에 저장되었습니다: {filepath.name}\n\n{summary}"

    return summary


def _handle_trending(params: dict, player, speak) -> str:
    region = params.get("region", "KR").upper()
    if player:
        player.write_log(f"[유튜브] 인기 동영상: {region}")

    if not _REQUESTS_OK:
        url = f"https://www.youtube.com/feed/trending?gl={region}"
        _open_url(url)
        return f"{region} 인기 동영상 페이지를 열었습니다."

    try:
        url  = f"https://www.youtube.com/feed/trending?gl={region}"
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text

        titles   = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
        channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"', html)

        results, seen = [], set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5: continue
            seen.add(title)
            channel = channels[i] if i < len(channels) else "알 수 없음"
            results.append({"rank": len(results) + 1, "title": title, "channel": channel})
            if len(results) >= 8: break

        if not results:
            _open_url(url)
            return f"{region} 인기 동영상 페이지를 열었습니다."

        lines  = [f"{region} 인기 동영상:"]
        lines += [f"{v['rank']}. {v['title']} — {v['channel']}" for v in results]
        return "\n".join(lines)
    except Exception as e:
        print(f"[YouTube] 인기 동영상 오류: {e}")
        _open_url(f"https://www.youtube.com/feed/trending?gl={region}")
        return f"{region} 인기 동영상 페이지를 열었습니다."


def youtube_video(parameters: dict, response=None, player=None, session_memory=None, speak=None) -> str:
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if player:
        player.write_log(f"[유튜브] 액션: {action}")

    try:
        if action == "play":
            return _handle_play(params, player) or "완료"
        elif action == "summarize":
            return _handle_summarize(params, player, speak) or "완료"
        elif action == "trending":
            return _handle_trending(params, player, speak) or "완료"
        else:
            return f"알 수 없는 유튜브 액션: '{action}'"
    except Exception as e:
        print(f"[YouTube] ❌ {action} 오류: {e}")
        return f"유튜브 {action} 오류: {e}"
