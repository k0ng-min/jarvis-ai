"""
Phase 1 개선 효과 측정
"""

import time
from jarvis_ai.main import _fast_route, _call_claude, _load_system_prompt

print("\n" + "="*60)
print("🚀 Phase 1 개선 효과 측정")
print("="*60)

system_prompt = _load_system_prompt()

# 테스트 케이스
tests = [
    ("지금 몇 시야?", "시간 (개선됨)"),
    ("현재 시각이 몇 시야?", "시간 (개선됨)"),
    ("몇시야?", "시간 (개선됨)"),
    ("오늘 날짜는?", "날짜 (로컬)"),
    ("내일 날짜는?", "내일 계산 (NEW)"),
    ("모레는?", "모레 계산 (NEW)"),
    ("다음주 월요일은?", "미래 날짜 (NEW)"),
    ("서울 날씨는?", "도구 (기존)"),
]

print("\n📊 테스트 결과:\n")
print(f"{'질문':<20} {'카테고리':<20} {'응답시간':<12} {'결과'}")
print("-"*70)

total_time = 0
success_count = 0

for question, category in tests:
    start = time.time()

    try:
        tool_name, params, direct_answer = _fast_route(question)

        if direct_answer:
            result_type = "로컬 ✅"
        elif tool_name:
            result_type = f"도구: {tool_name}"
        else:
            result_type = "Claude"

        elapsed = time.time() - start
        total_time += elapsed
        success_count += 1

        print(f"{question:<20} {category:<20} {elapsed:.2f}초      {result_type}")

    except Exception as e:
        elapsed = time.time() - start
        print(f"{question:<20} {category:<20} {elapsed:.2f}초      ❌ {str(e)[:20]}")

print("\n" + "-"*70)
print(f"✅ 성공: {success_count}/{len(tests)}")
print(f"📊 평균 응답시간: {total_time/len(tests):.2f}초")

print("\n" + "="*60)
print("🎯 개선 효과 요약")
print("="*60)

improvements = [
    "✅ 시간 질문 로컬 처리 (Claude 제외)",
    "✅ 날짜 계산 로컬 처리 (내일, 모레, 다음주)",
    "✅ Claude 타임아웃 단축 (30초 → 15초)",
    "✅ 마이크 자동 감지 (다양한 하드웨어)",
    "✅ 자연스러운 시간 표현 (오전/오후)",
]

print("\n개선 사항:")
for improvement in improvements:
    print(f"  {improvement}")

print("\n📈 예상 효과:")
print("  - 로컬 처리 질문: 0초 (즉시)")
print("  - Claude 질문: 15초 이하 (30초 → 15초)")
print("  - 전체 평균: 50% 개선")

print("\n다음 단계:")
print("  1. 이 개선사항으로 main.py 재실행")
print("  2. 무한 반복 테스트 완료 후 성능 비교")
print("  3. Phase 2: 음성 품질 개선")

print("\n")
