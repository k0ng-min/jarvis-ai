# actions/flight_finder.py — 자비스 항공편 검색 (Claude CLI 기반)

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from config import is_windows, is_mac, is_linux


_MONTH_MAP: dict[str, int] = {
    "january": 1,   "february": 2,  "march": 3,     "april": 4,
    "may": 5,       "june": 6,      "july": 7,       "august": 8,
    "september": 9, "october": 10,  "november": 11,  "december": 12,
    "1월": 1, "2월": 2, "3월": 3, "4월": 4, "5월": 5, "6월": 6,
    "7월": 7, "8월": 8, "9월": 9, "10월": 10, "11월": 11, "12월": 12,
}


def _call_claude(prompt: str) -> str:
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=45, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[항공편] Claude 오류: {e}")
    return ""


def _parse_date(raw: str) -> str:
    raw   = raw.strip()
    today = datetime.now()

    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    lower = raw.lower()
    relative = {
        "today": today, "오늘": today,
        "tomorrow": today + timedelta(days=1), "내일": today + timedelta(days=1),
    }
    for key, val in relative.items():
        if key in lower:
            return val.strftime("%Y-%m-%d")

    # Claude로 날짜 파싱
    try:
        result = _call_claude(
            f"오늘은 {today.strftime('%Y-%m-%d')}입니다.\n"
            f"이 날짜 표현을 YYYY-MM-DD 형식으로 변환하세요: '{raw}'\n"
            f"날짜 문자열만 반환하세요. 다른 것은 없이."
        )
        if result and re.match(r"\d{4}-\d{2}-\d{2}", result):
            return result
    except Exception as e:
        print(f"[항공편] ⚠️ 날짜 파싱 실패: {e}")

    for month_name, month_num in _MONTH_MAP.items():
        if month_name in lower:
            day_match = re.search(r"\d{1,2}", raw)
            if day_match:
                day  = int(day_match.group())
                year = today.year if month_num >= today.month else today.year + 1
                return f"{year}-{month_num:02d}-{day:02d}"

    print(f"[항공편] ⚠️ '{raw}' 날짜를 파싱할 수 없음 — 오늘 사용")
    return today.strftime("%Y-%m-%d")


_CABIN_CODE: dict[str, str] = {
    "economy":  "1",
    "premium":  "2",
    "business": "3",
    "first":    "4",
}


def _build_google_flights_url(
    origin: str, destination: str, date: str,
    return_date: str | None = None, passengers: int = 1, cabin: str = "economy"
) -> str:
    from urllib.parse import quote_plus

    cabin_code      = _CABIN_CODE.get(cabin.lower(), "1")
    origin_enc      = quote_plus(origin)
    destination_enc = quote_plus(destination)

    if return_date:
        trip = f"Flights+from+{origin_enc}+to+{destination_enc}+on+{date}+returning+{return_date}"
    else:
        trip = f"Flights+from+{origin_enc}+to+{destination_enc}+on+{date}"

    return (
        f"https://www.google.com/travel/flights"
        f"?q={trip}&curr=KRW&cabin={cabin_code}&adults={passengers}"
    )


def _search_flights_browser(
    origin: str, destination: str, date: str,
    return_date: str | None, passengers: int, cabin: str,
) -> tuple[str, str]:
    from actions.browser_control import browser_control

    url = _build_google_flights_url(origin, destination, date, return_date, passengers, cabin)

    print(f"[항공편] 🌐 열기: {url}")
    browser_control({"action": "go_to", "url": url})
    time.sleep(5)

    raw = browser_control({"action": "get_text"})
    return (raw or ""), url


def _parse_flights_with_claude(
    raw_text: str, origin: str, destination: str, date: str,
) -> list[dict]:
    prompt = (
        f"{origin}에서 {destination}까지 {date} 항공편 옵션을 이 Google 항공편 페이지 텍스트에서 추출하세요:\n\n"
        f"{raw_text[:12000]}\n\n"
        f"최대 5개의 항공편을 JSON 배열로 반환하세요:\n"
        f'[{{"airline":"항공사","departure":"HH:MM","arrival":"HH:MM",'
        f'"duration":"Xh Ym","stops":0,"price":"...","currency":"KRW"}}]\n'
        f"항공편이 없으면: []"
    )

    try:
        result = _call_claude(prompt)
        if not result:
            return []
        # JSON 추출
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return parsed if isinstance(parsed, list) else []
    except Exception as e:
        print(f"[항공편] ⚠️ 파싱 실패: {e}")
    return []


def _format_spoken(
    flights: list[dict], origin: str, destination: str, date: str,
) -> str:
    if not flights:
        return (
            f"{date}에 {origin}에서 {destination}까지 항공편을 찾을 수 없었습니다. "
            f"페이지가 올바르게 로드되지 않았을 수 있습니다."
        )

    lines = [f"{date}에 {origin}에서 {destination}까지의 항공편입니다."]

    for i, f in enumerate(flights[:5], 1):
        airline   = f.get("airline",   "항공사 미상")
        departure = f.get("departure", "--:--")
        arrival   = f.get("arrival",   "--:--")
        duration  = f.get("duration",  "")
        stops     = f.get("stops",     0)
        price     = f.get("price",     "")
        currency  = f.get("currency",  "")

        stop_str  = "직항" if stops == 0 else f"{stops}회 경유"
        price_str = f"{price} {currency}".strip() if price else "가격 미상"
        dur_str   = f", {duration}" if duration else ""

        lines.append(
            f"옵션 {i}: {airline}, 출발 {departure}, "
            f"도착 {arrival}{dur_str}, {stop_str}, {price_str}."
        )

    priced = [f for f in flights if f.get("price")]
    if priced:
        cheapest = min(
            priced,
            key=lambda x: int(re.sub(r"[^\d]", "", str(x["price"])) or "999999"),
        )
        lines.append(
            f"가장 저렴한 옵션은 {cheapest.get('airline')}으로 "
            f"{cheapest.get('price')} {cheapest.get('currency', '')}입니다."
        )

    return " ".join(lines)


def _format_text_report(
    flights: list[dict], origin: str, destination: str,
    date: str, return_date: str | None, page_url: str,
) -> str:
    lines = [
        "자비스 — 항공편 검색 결과",
        "─" * 50,
        f"경로     : {origin} → {destination}",
        f"날짜     : {date}",
    ]
    if return_date:
        lines.append(f"귀국일   : {return_date}")
    lines += [
        f"검색일시 : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"출처     : {page_url}",
        "─" * 50,
        "",
    ]

    if not flights:
        lines.append("항공편을 찾을 수 없습니다.")
    else:
        for i, f in enumerate(flights, 1):
            stops    = f.get("stops", 0)
            stop_str = "직항" if stops == 0 else f"{stops}회 경유"
            lines += [
                f"항공편 {i}:",
                f"  항공사   : {f.get('airline',   'N/A')}",
                f"  출발     : {f.get('departure', 'N/A')}",
                f"  도착     : {f.get('arrival',   'N/A')}",
                f"  소요시간 : {f.get('duration',  'N/A')}",
                f"  경유     : {stop_str}",
                f"  가격     : {f.get('price', 'N/A')} {f.get('currency', '')}",
                "",
            ]

    return "\n".join(lines)


def _save_to_desktop(content: str, origin: str, destination: str) -> str:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"항공편_{origin}_{destination}_{ts}.txt".replace(" ", "_")
    desktop  = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    filepath.write_text(content, encoding="utf-8")
    print(f"[항공편] 💾 저장됨: {filepath}")

    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[항공편] ⚠️ 텍스트 편집기를 열 수 없음: {e}")

    return str(filepath)


def flight_finder(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}

    origin      = params.get("origin",      "").strip()
    destination = params.get("destination", "").strip()
    date_raw    = params.get("date",        "").strip()
    return_raw  = (params.get("return_date") or "").strip()
    passengers  = max(1, int(params.get("passengers", 1)))
    cabin       = params.get("cabin", "economy").strip().lower()
    save        = bool(params.get("save", False))

    if not origin or not destination:
        return "출발지와 목적지를 모두 제공해주세요."
    if not date_raw:
        return "출발 날짜를 제공해주세요."

    if cabin not in _CABIN_CODE:
        cabin = "economy"

    date        = _parse_date(date_raw)
    return_date = _parse_date(return_raw) if return_raw else None

    if player:
        player.write_log(f"[항공편] {origin} → {destination} ({date})")

    if speak:
        speak(f"{date}에 {origin}에서 {destination}까지 항공편을 검색하고 있습니다.")

    print(
        f"[항공편] ▶️ {origin} → {destination} | {date}"
        f"{' → ' + return_date if return_date else ''}"
        f" | {cabin} | {passengers}명"
    )

    try:
        raw_text, page_url = _search_flights_browser(
            origin, destination, date, return_date, passengers, cabin
        )

        if not raw_text:
            return "항공편 데이터를 가져올 수 없었습니다. 페이지가 로드되지 않았을 수 있습니다."

        if speak:
            speak("결과를 분석하고 있습니다.")

        flights = _parse_flights_with_claude(raw_text, origin, destination, date)
        spoken  = _format_spoken(flights, origin, destination, date)

        if speak:
            speak(spoken)

        result = spoken

        if save and flights:
            report     = _format_text_report(flights, origin, destination, date, return_date, page_url)
            saved_path = _save_to_desktop(report, origin, destination)
            result    += f" 결과가 바탕화면에 저장되었습니다: {saved_path}"

        return result

    except Exception as e:
        print(f"[항공편] ❌ {e}")
        return f"항공편 검색 실패: {e}"
