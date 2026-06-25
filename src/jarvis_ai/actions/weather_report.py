"""Open-Meteo를 이용한 실시간 날씨 조회."""

import re
from datetime import datetime

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_CITY = "서울"
CITY_SEARCH_NAMES = {
    "서울": "Seoul",
    "부산": "Busan",
    "대구": "Daegu",
    "인천": "Incheon",
    "광주": "Gwangju",
    "대전": "Daejeon",
    "울산": "Ulsan",
    "수원": "Suwon",
    "청주": "Cheongju",
    "제주": "Jeju City",
    "강릉": "Gangneung",
    "전주": "Jeonju",
    "창원": "Changwon",
    "성남": "Seongnam",
    "고양": "Goyang",
    "천안": "Cheonan",
    "세종": "Sejong",
    "구미": "Gumi",
    "포항": "Pohang",
    "경주": "Gyeongju",
    "평택": "Pyeongtaek",
    "화성": "Hwaseong",
    "용인": "Yongin",
}

WEATHER_CODES = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "서리 안개",
    51: "약한 이슬비",
    53: "이슬비",
    55: "강한 이슬비",
    61: "약한 비",
    63: "비",
    65: "강한 비",
    66: "약한 어는 비",
    67: "강한 어는 비",
    71: "약한 눈",
    73: "눈",
    75: "강한 눈",
    77: "싸락눈",
    80: "약한 소나기",
    81: "소나기",
    82: "강한 소나기",
    85: "약한 눈 소나기",
    86: "강한 눈 소나기",
    95: "뇌우",
    96: "우박을 동반한 뇌우",
    99: "강한 우박 뇌우",
}


def _geocode(city: str) -> tuple[str, float, float]:
    search_name = CITY_SEARCH_NAMES.get(city, city)
    response = requests.get(
        GEOCODING_URL,
        params={
            "name": search_name,
            "count": 1,
            "language": "ko",
            "format": "json",
        },
        timeout=10,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ValueError(f"{city} 위치를 찾지 못했습니다.")
    place = results[0]
    display_name = city if city in CITY_SEARCH_NAMES else (place.get("name") or city)
    return display_name, float(place["latitude"]), float(place["longitude"])


def _forecast(latitude: float, longitude: float) -> dict:
    response = requests.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "timezone": "auto",
            "forecast_days": 7,
        },
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def _daily_sentence(city: str, daily: dict, index: int, label: str) -> str:
    dates = daily.get("time", [])
    if index >= len(dates):
        return f"{label} 예보가 아직 없습니다."
    code = daily.get("weather_code", [0] * len(dates))[index]
    high = daily.get("temperature_2m_max", [0] * len(dates))[index]
    low = daily.get("temperature_2m_min", [0] * len(dates))[index]
    rain = daily.get("precipitation_probability_max", [0] * len(dates))[index]
    condition = WEATHER_CODES.get(code, "날씨 정보 확인 중")
    date_text = datetime.fromisoformat(dates[index]).strftime("%m월 %d일")
    return (
        f"{city} {label} {date_text}은 {condition}, "
        f"최저 {low:.0f}도, 최고 {high:.0f}도, 강수 확률 {rain:.0f}%입니다."
    )


def weather_action(parameters: dict, player=None, session_memory=None):
    params = parameters or {}
    city = str(params.get("city") or params.get("location") or DEFAULT_CITY).strip()
    when = str(params.get("time") or params.get("query") or "오늘").strip()

    try:
        display_name, latitude, longitude = _geocode(city)
        data = _forecast(latitude, longitude)
        daily = data.get("daily", {})

        day_match = re.search(r"(\d+)\s*일\s*(?:뒤|후)", when)
        if day_match:
            offset = int(day_match.group(1))
            response = _daily_sentence(display_name, daily, offset, f"{offset}일 뒤")
        elif "내일" in when and "모레" in when:
            response = " ".join([
                _daily_sentence(display_name, daily, 1, "내일"),
                _daily_sentence(display_name, daily, 2, "모레"),
            ])
        elif "모레" in when:
            response = _daily_sentence(display_name, daily, 2, "모레")
        elif "내일" in when:
            response = _daily_sentence(display_name, daily, 1, "내일")
        elif any(word in when for word in ("주간", "이번 주", "일주일", "7일")):
            response = " ".join(
                _daily_sentence(display_name, daily, i, f"{i + 1}일차")
                for i in range(min(7, len(daily.get("time", []))))
            )
        else:
            current = data.get("current", {})
            code = current.get("weather_code", 0)
            condition = WEATHER_CODES.get(code, "날씨 정보 확인 중")
            response = (
                f"{display_name} 현재 날씨는 {condition}, "
                f"기온 {current.get('temperature_2m', 0):.0f}도, "
                f"체감 {current.get('apparent_temperature', 0):.0f}도, "
                f"습도 {current.get('relative_humidity_2m', 0):.0f}%, "
                f"바람 {current.get('wind_speed_10m', 0):.0f}킬로미터입니다."
            )

        if player:
            player.write_log(f"[실시간 날씨] {response}")
        print(f"[날씨] Open-Meteo 실시간 조회 성공: {display_name}")
        return response

    except requests.RequestException as exc:
        print(f"[날씨] 네트워크 오류: {exc}")
        return "실시간 날씨 서버에 연결하지 못했습니다. 인터넷 연결을 확인해주세요."
    except (ValueError, KeyError, TypeError) as exc:
        print(f"[날씨] 조회 오류: {exc}")
        return str(exc)
