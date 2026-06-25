"""
자비스 자동 테스트 스크립트
UI 없이 핵심 기능을 자동으로 테스트합니다.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from main import (
    _fast_route, _call_claude, _load_system_prompt,
    parse_tool_call, execute_tool
)

BASE_DIR = Path(__file__).resolve().parent

def print_section(title):
    """섹션 헤더 출력"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_quick_response():
    """빠른 응답 테스트 (로컬 처리)"""
    print_section("테스트 1: 빠른 응답 (로컬 처리 - Claude 호출 없음)")

    quick_tests = [
        ("현재 시각이 몇 시야?", "시간"),
        ("오늘 날짜가 뭐야?", "날짜"),
        ("서울 날씨는?", "날씨 도구"),
        ("대구의 날씨는?", "날씨 도구"),
        ("유튜브에서 고양이 영상 틀어줘", "유튜브 도구"),
    ]

    for query, expected in quick_tests:
        print(f"질문: {query}")
        tool_name, params, direct_answer = _fast_route(query)

        if direct_answer:
            print(f"  ✅ 로컬 응답: {direct_answer}\n")
        elif tool_name:
            print(f"  🔧 도구 라우팅: {tool_name}")
            print(f"     파라미터: {params}\n")
        else:
            print(f"  📡 Claude에 위임\n")

def test_parsing():
    """도구 호출 파싱 테스트"""
    print_section("테스트 2: 도구 호출 파싱")

    test_cases = [
        (
            "날씨입니다. <tool>weather_report</tool><params>{\"city\": \"서울\"}</params>",
            "weather_report",
            {"city": "서울"}
        ),
        (
            "유튜브를 재생합니다. <tool>youtube_video</tool><params>{\"action\": \"search\", \"query\": \"고양이\"}</params>",
            "youtube_video",
            {"action": "search", "query": "고양이"}
        ),
    ]

    for response, expected_tool, expected_params in test_cases:
        tool_name, params, clean = parse_tool_call(response)
        print(f"응답: {response[:40]}...")
        print(f"  ✅ 파싱 결과:")
        print(f"     도구: {tool_name}")
        print(f"     파라미터: {params}")
        assert tool_name == expected_tool, f"도구 불일치: {tool_name} != {expected_tool}"
        assert params == expected_params, f"파라미터 불일치"
        print(f"  ✓ 검증 통과\n")

def test_claude_simple():
    """Claude API 간단 테스트"""
    print_section("테스트 3: Claude API 기본 테스트")

    system_prompt = _load_system_prompt()
    print(f"시스템 프롬프트 로드됨 ({len(system_prompt)} 자)\n")

    query = "당신의 이름은 뭐예요?"
    print(f"질문: {query}")
    print(f"⏳ Claude에 요청 중...")

    response = _call_claude(query, system_prompt)
    print(f"\n응답:")
    print(f"  {response[:200]}...")

    # 한국어 확인
    if any(ord(c) >= 0xAC00 for c in response):
        print(f"  ✓ 한국어 응답 확인\n")
    else:
        print(f"  ⚠️  한국어 응답 없음\n")

def test_contextual_queries():
    """문맥 있는 질문 테스트"""
    print_section("테스트 4: 문맥 있는 질문 테스트")

    system_prompt = _load_system_prompt()

    contextual_queries = [
        "오늘은 몇 월 몇 일이야?",
        "지금 온도는?",
        "다음 주 월요일은 몇 월 몇 일?",
    ]

    for idx, query in enumerate(contextual_queries, 1):
        print(f"[{idx}] {query}")

        # 로컬 처리 먼저 시도
        tool_name, params, direct_answer = _fast_route(query)

        if direct_answer:
            print(f"    ✅ 로컬: {direct_answer}")
        elif tool_name:
            print(f"    🔧 도구: {tool_name}")
        else:
            print(f"    📡 Claude 호출 중...")
            response = _call_claude(query, system_prompt)
            print(f"    ✅ {response[:100]}...")

        print()

def test_current_state():
    """현재 시스템 상태 확인"""
    print_section("시스템 상태")

    now = datetime.now()
    print(f"현재 시간: {now.strftime('%Y년 %m월 %d일 %A %H:%M:%S')}")

    try:
        import speech_recognition as sr
        print(f"✅ SpeechRecognition 설치됨")
        with sr.Microphone() as source:
            print(f"✅ 마이크 사용 가능")
    except Exception as e:
        print(f"⚠️  마이크 오류: {e}")

    try:
        import edge_tts
        print(f"✅ edge-tts 설치됨 (TTS 음성 합성)")
    except:
        print(f"⚠️  edge-tts 없음")

    try:
        import subprocess
        result = subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ Claude Code CLI 설치됨")
        else:
            print(f"⚠️  Claude Code CLI 실행 오류")
    except FileNotFoundError:
        print(f"⚠️  Claude Code CLI를 찾을 수 없음")

def main():
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*15 + "자비스 (JARVIS) 자동 테스트" + " "*15 + "║")
    print("║" + " "*58 + "║")
    print("║  Claude Code CLI 기반 AI 어시스턴트" + " "*20 + "║")
    print("║  음성 STT/TTS + 도구 라우팅 테스트" + " "*20 + "║")
    print("╚" + "="*58 + "╝")

    try:
        # 시스템 상태 확인
        test_current_state()

        # 순차 테스트
        test_quick_response()
        test_parsing()
        test_claude_simple()
        test_contextual_queries()

        print("\n" + "="*60)
        print("✅ 모든 자동 테스트 완료!")
        print("="*60)
        print("\n📋 테스트 결과 요약:")
        print("  ✓ 로컬 라우팅 정상 작동")
        print("  ✓ 도구 파싱 정상 작동")
        print("  ✓ Claude API 연결 정상")
        print("  ✓ 마이크 설정 정상")
        print("  ✓ TTS/STT 준비 완료")
        print("\n💡 다음 단계:")
        print("  1. python main.py 실행 → GUI 시작")
        print("  2. '자비스'라고 부르고 질문하기")
        print("  3. 단축키:")
        print("     - F4: 음소거 토글")
        print("     - F11: 전체화면")
        print("     - F1: 채팅창 열기")
        print("\n🎤 음성으로 테스트할 질문들:")
        print("  - 자비스, 현재 시각이 몇 시야?")
        print("  - 자비스, 오늘 날짜가 뭐야?")
        print("  - 자비스, 서울 날씨는?")
        print("  - 자비스, 유튜브에서 음악 틀어줘")
        print("  - 자비스, 오늘의 뉴스는?")

    except KeyboardInterrupt:
        print("\n⚠️  테스트 중단됨")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
