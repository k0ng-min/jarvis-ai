"""Verified external action routing tests."""

import json
from types import SimpleNamespace

from jarvis_ai.actions.gmail import _send, gmail_action
from jarvis_ai import main as main_module
from jarvis_ai.main import (
    _block_unverified_success,
    _fast_route,
    _finalize_tool_result,
    _is_stop_speech,
)


def run():
    class FakeRequest:
        def execute(self):
            return {"id": "msg-123", "threadId": "thread-456"}

    class FakeMessages:
        def send(self, **kwargs):
            assert kwargs["userId"] == "me"
            assert kwargs["body"]["raw"]
            return FakeRequest()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    receipt = _send(FakeService(), "test@example.com", "제목", "본문")
    assert "msg-123" in receipt
    assert "thread-456" in receipt

    tool, params, answer = _fast_route(
        "지메일 들어가서 test@example.com으로 테스트입니다 보내줘"
    )
    assert tool == "gmail"
    assert params["action"] == "send"
    assert params["to"] == "test@example.com"
    assert params["body"]
    assert answer is None

    tool, params, _ = _fast_route("지메일 안 읽은 메일 찾아줘")
    assert tool == "gmail"
    assert params["action"] == "search"
    assert params["query"] == "is:unread in:inbox"

    tool, params, _ = _fast_route("구글 지도에서 서울역 찾아줘")
    assert tool == "browser_control"
    assert params["action"] == "open_service"
    assert params["service"] == "maps"
    assert "서울역" in params["query"]

    blocked = _block_unverified_success(
        "지메일로 메일 보내줘",
        "Gmail에 접속해서 이메일을 보내드리겠습니다.",
    )
    assert "실제 도구의 성공 결과가 없어" in blocked
    assert _is_stop_speech("자비스 그만")
    assert _is_stop_speech("자비스, 멈춰!")

    original_run = main_module.subprocess.run

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "result": (
                    "손흥민의 최근 경기는 체코전입니다.\n"
                    "- 공식 출처: https://example.com/match"
                )
            }, ensure_ascii=False),
            stderr="",
        )

    main_module.subprocess.run = fake_run
    try:
        finalized = _finalize_tool_result(
            "손흥민 최근 경기 알려줘",
            "web_search",
            "검색 결과 원문 https://example.com/match",
        )
    finally:
        main_module.subprocess.run = original_run
    assert "최근 경기는" in finalized
    assert "https://example.com/match" in finalized

    status = gmail_action({"action": "setup_status"})
    assert "Gmail" in status
    assert "google_credentials.json" in status or "준비" in status

    print("외부 작업 실제 실행 라우팅 및 허위 성공 차단 통과")


if __name__ == "__main__":
    run()
