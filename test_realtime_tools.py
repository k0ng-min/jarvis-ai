"""신규 실시간 도구와 라우팅 통합 테스트."""

import main
from actions.realtime_info import (
    air_quality,
    calculate,
    encyclopedia,
    exchange_rate,
    public_holidays,
    recent_earthquakes,
    unit_convert,
)
from actions.weather_report import weather_action


ROUTES = {
    "100달러 원으로 환율 얼마야": "exchange_rate",
    "서울 미세먼지 어때": "air_quality",
    "다음 공휴일 언제야": "public_holidays",
    "최근 지진 알려줘": "recent_earthquakes",
    "12 곱하기 8 계산해줘": "calculate",
    "10킬로미터를 마일로 변환해줘": "unit_convert",
    "위키백과에서 양자 컴퓨터 찾아줘": "encyclopedia",
    "3일 뒤 날씨 어때": "weather_report",
    "120만원 노트북 추천해줘": "web_search",
}


def run():
    for text, expected in ROUTES.items():
        actual = main._fast_route(text)[0]
        assert actual == expected, f"{text}: {actual} != {expected}"

    outputs = [
        exchange_rate({"base": "USD", "quote": "KRW", "amount": 10}),
        air_quality({"city": "서울"}),
        public_holidays({"year": 2026, "country": "KR", "mode": "next"}),
        recent_earthquakes({"minimum_magnitude": 4.5}),
        encyclopedia({"query": "양자 컴퓨터"}),
        weather_action({"city": "서울", "time": "3일 뒤"}),
        calculate({"expression": "(12+3)*4"}),
        unit_convert({"value": 10, "from": "km", "to": "mi"}),
    ]
    assert all(outputs), "빈 도구 응답이 있습니다."
    assert "60" in outputs[-2]
    assert "6.21371" in outputs[-1]
    print(f"라우팅 {len(ROUTES)}개, 도구 {len(outputs)}개 통과")
    for output in outputs:
        print("-", output[:180])


if __name__ == "__main__":
    run()
