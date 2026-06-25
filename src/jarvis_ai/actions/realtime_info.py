"""인증키 없이 사용할 수 있는 실시간 정보 및 빠른 계산 도구."""

import ast
import html
import math
import operator
import re
from datetime import date, datetime

import requests

from .weather_report import _geocode


HEADERS = {"User-Agent": "JarvisAssistant/1.0"}
CURRENCY_NAMES = {
    "KRW": "원", "USD": "미국 달러", "EUR": "유로", "JPY": "일본 엔",
    "CNY": "중국 위안", "GBP": "영국 파운드", "AUD": "호주 달러",
    "CAD": "캐나다 달러", "CHF": "스위스 프랑", "HKD": "홍콩 달러",
    "SGD": "싱가포르 달러", "THB": "태국 바트", "VND": "베트남 동",
}


def exchange_rate(parameters: dict, player=None) -> str:
    params = parameters or {}
    base = str(params.get("base", "USD")).upper()
    quote = str(params.get("quote", "KRW")).upper()
    amount = float(params.get("amount", 1))
    try:
        response = requests.get(
            f"https://api.frankfurter.dev/v2/rate/{base}/{quote}",
            headers=HEADERS,
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        rate = float(data["rate"])
        converted = amount * rate
        result = (
            f"{data.get('date', '최근 기준')} 기준 {amount:,.2f} "
            f"{CURRENCY_NAMES.get(base, base)}는 약 {converted:,.2f} "
            f"{CURRENCY_NAMES.get(quote, quote)}입니다. "
            f"환율은 1 {base}당 {rate:,.4f} {quote}입니다."
        )
        if player:
            player.write_log(f"[환율] {result}")
        return result
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        print(f"[환율] 조회 오류: {exc}")
        return "실시간 환율 정보를 가져오지 못했습니다."


def air_quality(parameters: dict, player=None) -> str:
    params = parameters or {}
    city = str(params.get("city") or "서울").strip()
    try:
        display_name, latitude, longitude = _geocode(city)
        response = requests.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "us_aqi,pm10,pm2_5,uv_index",
                "timezone": "auto",
            },
            headers=HEADERS,
            timeout=12,
        )
        response.raise_for_status()
        current = response.json()["current"]
        aqi = float(current.get("us_aqi", 0))
        if aqi <= 50:
            grade = "좋음"
        elif aqi <= 100:
            grade = "보통"
        elif aqi <= 150:
            grade = "민감군에게 나쁨"
        elif aqi <= 200:
            grade = "나쁨"
        elif aqi <= 300:
            grade = "매우 나쁨"
        else:
            grade = "위험"
        result = (
            f"{display_name} 현재 대기질은 {grade}입니다. "
            f"미세먼지 PM10 {current.get('pm10', 0):.1f}, "
            f"초미세먼지 PM2.5 {current.get('pm2_5', 0):.1f} "
            f"마이크로그램, 자외선 지수는 {current.get('uv_index', 0):.1f}입니다."
        )
        if player:
            player.write_log(f"[대기질] {result}")
        return result
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        print(f"[대기질] 조회 오류: {exc}")
        return "실시간 대기질 정보를 가져오지 못했습니다."


def public_holidays(parameters: dict, player=None) -> str:
    params = parameters or {}
    year = int(params.get("year") or datetime.now().year)
    country = str(params.get("country") or "KR").upper()
    mode = str(params.get("mode") or "next")
    try:
        response = requests.get(
            f"https://date.nager.at/api/v3/publicholidays/{year}/{country}",
            headers=HEADERS,
            timeout=12,
        )
        response.raise_for_status()
        holidays = response.json()
        if mode == "next":
            today = date.today()
            future = [h for h in holidays if date.fromisoformat(h["date"]) >= today]
            if not future and year == today.year:
                return public_holidays(
                    {"year": year + 1, "country": country, "mode": "next"}, player
                )
            holidays = future[:3]
            prefix = "다가오는 공휴일은 "
        else:
            holidays = holidays[:20]
            prefix = f"{year}년 공휴일은 "
        if not holidays:
            return "공휴일 정보를 찾지 못했습니다."
        items = [
            f"{datetime.fromisoformat(h['date']).strftime('%m월 %d일')} {h['localName']}"
            for h in holidays
        ]
        result = prefix + ", ".join(items) + "입니다."
        if player:
            player.write_log(f"[공휴일] {result}")
        return result
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        print(f"[공휴일] 조회 오류: {exc}")
        return "공휴일 정보를 가져오지 못했습니다."


def encyclopedia(parameters: dict, player=None) -> str:
    query = str((parameters or {}).get("query") or "").strip()
    if not query:
        return "찾아볼 주제를 알려주세요."
    try:
        response = requests.get(
            "https://ko.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": query, "limit": 1},
            headers=HEADERS,
            timeout=12,
        )
        response.raise_for_status()
        pages = response.json().get("pages") or []
        if not pages:
            return f"{query}에 대한 백과사전 항목을 찾지 못했습니다."
        page = pages[0]
        excerpt = html.unescape(
            re.sub(r"<[^>]+>", "", page.get("excerpt") or "")
        ).strip()
        description = page.get("description") or ""
        result = f"{page['title']}: {description}. {excerpt}".strip()
        if player:
            player.write_log(f"[백과사전] {result}")
        return result
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        print(f"[백과사전] 조회 오류: {exc}")
        return "백과사전 정보를 가져오지 못했습니다."


def recent_earthquakes(parameters: dict, player=None) -> str:
    params = parameters or {}
    minimum = float(params.get("minimum_magnitude", 4.5))
    try:
        response = requests.get(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
            "4.5_day.geojson",
            headers=HEADERS,
            timeout=12,
        )
        response.raise_for_status()
        features = [
            feature for feature in response.json().get("features", [])
            if float(feature.get("properties", {}).get("mag") or 0) >= minimum
        ][:5]
        if not features:
            return f"최근 24시간 규모 {minimum:g} 이상 지진은 보고되지 않았습니다."
        items = []
        for feature in features:
            prop = feature["properties"]
            occurred = datetime.fromtimestamp(prop["time"] / 1000).strftime("%m월 %d일 %H시")
            items.append(f"{occurred}, {prop.get('place', '위치 미상')} 규모 {prop['mag']:.1f}")
        result = "최근 주요 지진은 " + "; ".join(items) + "입니다."
        if player:
            player.write_log(f"[지진] {result}")
        return result
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        print(f"[지진] 조회 오류: {exc}")
        return "실시간 지진 정보를 가져오지 못했습니다."


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 10:
            raise ValueError("지수가 너무 큽니다.")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("지원하지 않는 계산식입니다.")


def calculate(parameters: dict, player=None) -> str:
    expression = str((parameters or {}).get("expression") or "").strip()
    expression = (
        expression.replace("×", "*").replace("÷", "/")
        .replace("^", "**").replace(",", "")
    )
    try:
        value = _safe_eval(ast.parse(expression, mode="eval"))
        if not math.isfinite(float(value)):
            raise ValueError("유효하지 않은 결과입니다.")
        shown = f"{value:,.10g}" if isinstance(value, float) else f"{value:,}"
        return f"계산 결과는 {shown}입니다."
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        return f"계산할 수 없습니다: {exc}"


def unit_convert(parameters: dict, player=None) -> str:
    params = parameters or {}
    value = float(params.get("value", 0))
    source = str(params.get("from", "")).lower()
    target = str(params.get("to", "")).lower()
    aliases = {
        "킬로미터": "km", "키로미터": "km", "미터": "m", "센티미터": "cm",
        "밀리미터": "mm", "마일": "mi", "킬로그램": "kg", "키로그램": "kg",
        "그램": "g", "파운드": "lb", "리터": "l", "밀리리터": "ml",
        "섭씨": "c", "화씨": "f",
    }
    source, target = aliases.get(source, source), aliases.get(target, target)
    factors = {
        "m": 1, "km": 1000, "cm": 0.01, "mm": 0.001, "mi": 1609.344,
        "kg": 1, "g": 0.001, "lb": 0.45359237,
        "l": 1, "ml": 0.001,
    }
    try:
        if source in ("c", "f") and target in ("c", "f"):
            result = value if source == target else (
                value * 9 / 5 + 32 if source == "c" else (value - 32) * 5 / 9
            )
        elif source in factors and target in factors:
            categories = [
                {"m", "km", "cm", "mm", "mi"}, {"kg", "g", "lb"}, {"l", "ml"}
            ]
            if not any(source in group and target in group for group in categories):
                raise ValueError("서로 다른 종류의 단위입니다.")
            result = value * factors[source] / factors[target]
        else:
            raise ValueError("지원하지 않는 단위입니다.")
        return f"{value:g} {source}는 {result:,.6g} {target}입니다."
    except ValueError as exc:
        return f"단위 변환을 할 수 없습니다: {exc}"
