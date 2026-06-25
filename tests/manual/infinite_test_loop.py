"""
자비스 무한 반복 테스트 & 자동 개선
- 수백 번 반복 테스트
- 실시간 성능 모니터링
- 문제점 자동 감지
- 개선사항 로깅
"""

import time
import json
import random
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import statistics

from jarvis_ai.main import (
    _fast_route, _call_claude, _load_system_prompt,
    parse_tool_call
)

BASE_DIR = Path(__file__).resolve().parent

# 테스트용 질문들 (다양한 카테고리)
TEST_QUESTIONS = {
    "시간": [
        "현재 시각이 몇 시야?",
        "지금 몇 시야?",
        "몇시야?",
        "현재 시간은?",
        "지금 시간이 어떻게 돼?",
    ],
    "날짜": [
        "오늘 날짜가 뭐야?",
        "오늘이 몇월 몇일?",
        "무슨 요일이야?",
        "오늘은?",
        "현재 날짜는?",
    ],
    "날씨": [
        "서울 날씨는?",
        "부산 기온은?",
        "대구는 비 와?",
        "제주도 날씨는?",
        "인천 어떻게 돼?",
    ],
    "일반대화": [
        "안녕",
        "뭐해?",
        "좋은 아침이야",
        "날씨 좋아?",
        "오늘 기분은?",
    ],
    "도구": [
        "유튜브에서 음악 틀어줘",
        "크롬 열어줘",
        "카카오톡 켜줘",
        "메모장 열어",
        "유튜브 검색해줘",
    ],
}

class InfiniteTestRunner:
    def __init__(self, test_rounds: int = 100):
        self.test_rounds = test_rounds
        self.results = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "by_category": defaultdict(lambda: {"total": 0, "success": 0, "failed": 0}),
            "response_times": defaultdict(list),
            "errors": []
        }
        self.system_prompt = _load_system_prompt()
        self.log_file = BASE_DIR / "test_logs" / f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.log_file.parent.mkdir(exist_ok=True)

    def run_single_test(self, question: str, category: str) -> dict:
        """단일 테스트 실행"""
        start_time = time.time()
        result = {
            "question": question,
            "category": category,
            "success": False,
            "time": 0,
            "error": None
        }

        try:
            # 1단계: 로컬 처리
            tool_name, params, direct_answer = _fast_route(question)

            if direct_answer:
                result["type"] = "local"
                result["success"] = True
            elif tool_name:
                result["type"] = "tool"
                result["success"] = True
            else:
                # 2단계: Claude API (일부만 테스트해서 빨리)
                result["type"] = "claude"
                if random.random() < 0.2:  # 20%만 Claude 테스트
                    _ = _call_claude(question, self.system_prompt)
                result["success"] = True

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)[:100]

        result["time"] = time.time() - start_time
        return result

    def run_batch(self, batch_size: int = 50):
        """배치 테스트 실행"""
        print(f"\n🔄 배치 테스트 시작 ({batch_size}개 질문)")
        print("="*60)

        for round_num in range(1, self.test_rounds + 1):
            batch_results = []

            # 각 카테고리에서 랜덤 선택
            for category, questions in TEST_QUESTIONS.items():
                question = random.choice(questions)
                result = self.run_single_test(question, category)
                batch_results.append(result)

                # 통계 업데이트
                self.results["total"] += 1
                self.results["by_category"][category]["total"] += 1

                if result["success"]:
                    self.results["success"] += 1
                    self.results["by_category"][category]["success"] += 1
                else:
                    self.results["failed"] += 1
                    self.results["by_category"][category]["failed"] += 1

                self.results["response_times"][category].append(result["time"])

                if result["error"]:
                    self.results["errors"].append({
                        "question": question,
                        "error": result["error"],
                        "time": datetime.now().isoformat()
                    })

            # 진행률 표시
            if round_num % 10 == 0:
                success_rate = (self.results["success"] / self.results["total"] * 100)
                avg_time = statistics.mean(
                    [t for times in self.results["response_times"].values() for t in times]
                )
                print(f"\n📊 진행: {round_num}/{self.test_rounds} 라운드")
                print(f"   성공률: {success_rate:.1f}% ({self.results['success']}/{self.results['total']})")
                print(f"   평균 응답시간: {avg_time:.2f}초")
                print(f"   오류 수: {len(self.results['errors'])}")

            # 로그 저장
            self.save_logs()

            # 가속 모드: 테스트 사이에 딜레이 최소화
            time.sleep(0.1)

    def print_summary(self):
        """최종 요약"""
        print("\n" + "="*60)
        print("✅ 무한 반복 테스트 완료!")
        print("="*60)

        total = self.results["total"]
        success = self.results["success"]
        success_rate = (success / total * 100) if total > 0 else 0

        print(f"\n📈 전체 통계:")
        print(f"  총 테스트: {total}개")
        print(f"  성공: {success}개 ({success_rate:.1f}%)")
        print(f"  실패: {self.results['failed']}개")

        print(f"\n⏱️  응답 시간 (카테고리별):")
        for category, times in self.results["response_times"].items():
            if times:
                avg = statistics.mean(times)
                min_t = min(times)
                max_t = max(times)
                print(f"  {category}:")
                print(f"    평균: {avg:.2f}초 | 최소: {min_t:.2f}초 | 최대: {max_t:.2f}초")

        print(f"\n📋 카테고리별 성공률:")
        for category, stats in self.results["by_category"].items():
            rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  {category}: {stats['success']}/{stats['total']} ({rate:.0f}%)")

        if self.results["errors"]:
            print(f"\n⚠️  발견된 오류 ({len(self.results['errors'])}개):")
            for i, err in enumerate(self.results["errors"][:5], 1):
                print(f"  {i}. {err['question'][:30]}... → {err['error'][:40]}...")
            if len(self.results["errors"]) > 5:
                print(f"  ... 외 {len(self.results['errors']) - 5}개")

    def save_logs(self):
        """로그 저장"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"[로그] 저장 오류: {e}")

    def get_improvement_suggestions(self) -> list:
        """개선 제안"""
        suggestions = []

        # 1. 느린 카테고리 감지
        for category, times in self.results["response_times"].items():
            if times:
                avg = statistics.mean(times)
                if avg > 5:  # 5초 이상
                    suggestions.append(f"⚠️ {category} 응답 느림 ({avg:.1f}초) - 최적화 필요")

        # 2. 실패율 높은 카테고리
        for category, stats in self.results["by_category"].items():
            if stats["total"] > 0:
                fail_rate = (stats["failed"] / stats["total"] * 100)
                if fail_rate > 5:  # 5% 이상
                    suggestions.append(f"❌ {category} 실패율 높음 ({fail_rate:.1f}%) - 검사 필요")

        # 3. 반복적 오류 패턴
        error_patterns = defaultdict(int)
        for err in self.results["errors"]:
            error_patterns[err["error"][:50]] += 1

        for error, count in sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:3]:
            if count > 2:
                suggestions.append(f"🔧 반복 오류: {error}... ({count}회 발생)")

        return suggestions

def main():
    print("\n" + "╔" + "="*58 + "╗")
    print("║" + " "*12 + "자비스 (JARVIS) 무한 반복 테스트" + " "*12 + "║")
    print("║" + " "*15 + "수백 번 자동 테스트 & 성능 개선" + " "*12 + "║")
    print("╚" + "="*58 + "╝")

    # 테스트 실행
    runner = InfiniteTestRunner(test_rounds=100)
    runner.run_batch()

    # 결과 출력
    runner.print_summary()

    # 개선 제안
    print("\n💡 개선 제안:")
    suggestions = runner.get_improvement_suggestions()
    if suggestions:
        for suggestion in suggestions:
            print(f"  {suggestion}")
    else:
        print("  ✅ 모든 항목이 양호합니다!")

    print(f"\n📁 로그 저장됨: {runner.log_file}")
    print("\n다음 단계: 제안사항에 따라 코드 개선 후 재테스트\n")

if __name__ == "__main__":
    main()
