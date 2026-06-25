"""
자비스 대화 이력 관리
- 대화 저장
- 이전 대화 불러오기
- 대화 통계
"""

import json
from pathlib import Path

from .paths import MEMORY_DIR
from datetime import datetime

HISTORY_FILE = MEMORY_DIR / "conversations.json"

class ConversationManager:
    def __init__(self):
        self.conversations = self._load_conversations()

    def _load_conversations(self):
        """저장된 대화 불러오기"""
        try:
            if HISTORY_FILE.exists():
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[대화 이력] 로드 오류: {e}")
        return {"history": [], "stats": {"total": 0, "by_type": {}}}

    def _save_conversations(self):
        """대화 저장"""
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.conversations, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[대화 이력] 저장 오류: {e}")

    def add_conversation(self, user_input: str, response: str, response_type: str = "general"):
        """새로운 대화 추가"""
        conversation = {
            "timestamp": datetime.now().isoformat(),
            "user": user_input,
            "response": response,
            "type": response_type
        }

        self.conversations["history"].append(conversation)

        # 통계 업데이트
        self.conversations["stats"]["total"] += 1
        if response_type not in self.conversations["stats"]["by_type"]:
            self.conversations["stats"]["by_type"][response_type] = 0
        self.conversations["stats"]["by_type"][response_type] += 1

        # 저장 (최근 1000개만 유지)
        if len(self.conversations["history"]) > 1000:
            self.conversations["history"] = self.conversations["history"][-1000:]

        self._save_conversations()

    def get_recent_context(self, n: int = 5) -> str:
        """최근 대화 n개를 claude 프롬프트에 사용할 수 있는 형식으로 반환"""
        recent = self.conversations["history"][-n:]

        if not recent:
            return ""

        context = "\n【 최근 대화 이력 】\n"
        for conv in recent:
            context += f"사용자: {conv['user']}\n"
            context += f"자비스: {conv['response']}\n\n"

        return context

    def get_stats(self) -> dict:
        """대화 통계"""
        return self.conversations["stats"]

    def get_user_preferences(self) -> dict:
        """사용자 선호도 분석"""
        stats = self.conversations["stats"]["by_type"]
        preferences = {
            "가장 많이 사용": max(stats, key=stats.get) if stats else "없음",
            "총 대화 수": self.conversations["stats"]["total"],
            "대화 유형": stats
        }
        return preferences

    def clear_history(self):
        """대화 이력 초기화"""
        self.conversations = {"history": [], "stats": {"total": 0, "by_type": {}}}
        self._save_conversations()
        print("[대화 이력] 초기화 완료")

if __name__ == "__main__":
    manager = ConversationManager()

    # 테스트
    print("\n" + "="*60)
    print("📚 자비스 대화 이력 관리")
    print("="*60)

    stats = manager.get_stats()
    print(f"\n📊 통계:")
    print(f"  총 대화 수: {stats['total']}")
    print(f"  대화 유형: {stats['by_type']}")

    prefs = manager.get_user_preferences()
    print(f"\n💡 사용자 선호도:")
    print(f"  가장 자주 사용: {prefs['가장 많이 사용']}")

    # 최근 대화 표시
    if stats['total'] > 0:
        print(f"\n📜 최근 대화:")
        recent = manager.conversations["history"][-3:]
        for conv in recent:
            print(f"  Q: {conv['user'][:30]}...")
            print(f"  A: {conv['response'][:30]}...\n")
