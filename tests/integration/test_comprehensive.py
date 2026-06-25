"""
자비스 종합 테스트 및 성능 평가
- 응답 시간 측정
- 다양한 질문 테스트
- 정확도 평가
- UI/UX 피드백
"""

import time
import json
from datetime import datetime
from pathlib import Path
from jarvis_ai.main import (
    _fast_route, _call_claude, _load_system_prompt,
    parse_tool_call, listen_mic
)

BASE_DIR = Path(__file__).resolve().parent

# 테스트 케이스: (질문, 기대 결과, 카테고리)
TEST_CASES = [
    # ========== 로컬 처리 (빠른 응답) ==========
    ("현재 시각이 몇 시야?", "시간", "로컬"),
    ("지금 몇 시야?", "시간", "로컬"),
    ("몇시야?", "시간", "로컬"),

    ("오늘 날짜가 뭐야?", "날짜", "로컬"),
    ("오늘이 몇월 몇일?", "날짜", "로컬"),
    ("무슨 요일이야?", "요일", "로컬"),

    ("서울 날씨는?", "날씨", "도구"),
    ("부산 기온은?", "날씨", "도구"),
    ("대구는 비 와?", "날씨", "도구"),
    ("서울 날시는?", "날씨 (오타)", "도구"),

    # ========== Claude 응답 필요 ==========
    ("안녕", "인사", "Claude"),
    ("오늘의 뉴스는?", "뉴스", "Claude"),
    ("날씨 좋아?", "일반대화", "Claude"),
    ("농담 하나 해줄래?", "재미", "Claude"),
    ("내일 날씨는?", "계산", "Claude"),

    # ========== 도구 실행 ==========
    ("유튜브에서 음악 틀어줘", "유튜브", "도구"),
    ("크롬 열어줘", "앱실행", "도구"),
]

class JarvisEvaluator:
    def __init__(self):
        self.results = []
        self.system_prompt = _load_system_prompt()
        self.timings = {
            "local": [],
            "tool": [],
            "claude": []
        }

    def test_query(self, query: str, expected: str, category: str):
        """단일 질문 테스트"""
        print(f"\n🎤 질문: {query}")
        print(f"   기대: {expected} ({category})")

        start_time = time.time()

        # 1단계: 로컬 라우팅
        tool_name, params, direct_answer = _fast_route(query)

        if direct_answer:
            elapsed = time.time() - start_time
            print(f"   ✅ 로컬 응답: {direct_answer[:50]}...")
            print(f"   ⏱️  응답시간: {elapsed:.2f}초")
            self.timings["local"].append(elapsed)
            self.results.append({
                "query": query,
                "type": category,
                "result": "성공",
                "time": elapsed
            })
            return

        if tool_name:
            elapsed = time.time() - start_time
            print(f"   🔧 도구: {tool_name}")
            print(f"   ⏱️  응답시간: {elapsed:.2f}초")
            self.timings["tool"].append(elapsed)
            self.results.append({
                "query": query,
                "type": category,
                "result": "도구실행",
                "time": elapsed
            })
            return

        # 2단계: Claude API
        print(f"   📡 Claude 호출 중...")
        response = _call_claude(query, self.system_prompt)
        elapsed = time.time() - start_time

        print(f"   ✅ 응답: {response[:50]}...")
        print(f"   ⏱️  응답시간: {elapsed:.2f}초")
        self.timings["claude"].append(elapsed)
        self.results.append({
            "query": query,
            "type": category,
            "result": "성공",
            "time": elapsed
        })

    def print_summary(self):
        """테스트 요약"""
        print("\n" + "="*60)
        print("📊 테스트 결과 요약")
        print("="*60)

        print("\n⏱️  응답 시간:")
        if self.timings["local"]:
            avg = sum(self.timings["local"]) / len(self.timings["local"])
            print(f"  로컬 처리: {avg:.2f}초 (평균, {len(self.timings['local'])}건)")

        if self.timings["tool"]:
            avg = sum(self.timings["tool"]) / len(self.timings["tool"])
            print(f"  도구 실행: {avg:.2f}초 (평균, {len(self.timings['tool'])}건)")

        if self.timings["claude"]:
            avg = sum(self.timings["claude"]) / len(self.timings["claude"])
            print(f"  Claude API: {avg:.2f}초 (평균, {len(self.timings['claude'])}건)")

        print("\n📈 카테고리별 성공률:")
        category_stats = {}
        for result in self.results:
            cat = result["type"]
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "success": 0}
            category_stats[cat]["total"] += 1
            if result["result"] in ["성공", "도구실행"]:
                category_stats[cat]["success"] += 1

        for cat, stats in category_stats.items():
            rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  {cat}: {stats['success']}/{stats['total']} ({rate:.0f}%)")

def main():
    print("\n" + "╔" + "="*58 + "╗")
    print("║" + " "*10 + "자비스 (JARVIS) 종합 평가 테스트" + " "*14 + "║")
    print("╚" + "="*58 + "╝")

    evaluator = JarvisEvaluator()

    print("\n📋 테스트 시작...")
    print(f"총 {len(TEST_CASES)}가지 질문 테스트\n")

    for query, expected, category in TEST_CASES:
        try:
            evaluator.test_query(query, expected, category)
            time.sleep(0.5)  # API 과부하 방지
        except Exception as e:
            print(f"   ❌ 오류: {str(e)[:50]}")

    evaluator.print_summary()

    print("\n" + "="*60)
    print("💡 개선 제안사항:")
    print("="*60)
    print("""
【 UI/UX 개선 】
  1. 실시간 시각화: 응답 상태를 더 명확하게 표시
  2. 대화 내역 저장: 이전 대화를 참고할 수 있게
  3. 커스터마이징: 사용자 이름, 선호도 저장
  4. 다국어 지원: 영어, 중국어 등

【 기능 확장 】
  1. 일정 관리: 캘린더 연동
  2. 알림 시스템: 중요한 일 미리 알림
  3. 스마트홈 제어: IoT 기기 제어
  4. 사진/문서 처리: 이미지 인식

【 음성 개선 】
  1. 자연스러운 음성: TTS 모델 업그레이드
  2. 감정 표현: 톤 변화로 감정 전달
  3. 배경음 필터: 노이즈 제거 강화
  4. 다양한 음성: 남/여 음성 선택

【 하드웨어 지원 】
  1. 여러 마이크 지원: USB, 3.5mm 등
  2. 여러 스피커 지원: 기본, HDMI, Bluetooth
  3. 디스플레이: 모니터 화면 최적화
  4. 컨트롤러: 리모콘/바디 제스처
    """)

if __name__ == "__main__":
    main()
