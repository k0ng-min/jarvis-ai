"""Chat display and microphone cancellation integration tests."""

import os
import tempfile
from array import array
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from jarvis_ai import main as main_module
from jarvis_ai.conversation_history import ConversationManager
from jarvis_ai.main import ChatModeActivated, _LevelMonitoringStream
from jarvis_ai.ui import MainWindow


class FakeStream:
    def read(self, size):
        return array("h", [500, -500] * size).tobytes()

    def close(self):
        return None


def run():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert not window._chat_mode_event.is_set()
    window._toggle_chat()
    assert window._chat_mode_event.is_set()
    assert not window._chat_panel.isHidden()
    assert window._chat_btn.text() == "CLOSE"

    long_answer = (
        "첫 번째 문장입니다.\n"
        + "긴 답변 내용 " * 80
        + "\n출처: https://example.com/source"
    )
    window._chat_log_sig.emit(("jarvis", long_answer))
    app.processEvents()
    displayed = window._chat_panel._log.toPlainText()
    assert "첫 번째 문장입니다." in displayed
    assert "example.com/source" in displayed
    assert len(displayed) > 500

    monitored = _LevelMonitoringStream(
        FakeStream(),
        lambda level: None,
        2,
        cancel_check=lambda: True,
    )
    try:
        monitored.read(8)
    except ChatModeActivated:
        pass
    else:
        raise AssertionError("채팅 모드에서 마이크 스트림이 취소되지 않았습니다.")

    window._toggle_chat()
    assert not window._chat_mode_event.is_set()
    assert window._chat_btn.text() == "CHAT"

    window._apply_state("LISTENING")
    window._on_mic_level(1.0)
    for _ in range(16):
        window.hud._step()
    assert 1.75 <= window.hud._tgt_scale <= 1.80

    window._apply_state("THINKING")
    thinking_scales = []
    for _ in range(80):
        window.hud._step()
        thinking_scales.append(window.hud._tgt_scale)
    assert min(thinking_scales) <= 0.74
    assert max(thinking_scales) >= 0.95

    window._apply_state("SPEAKING")
    assert window.hud.speaking

    class FakeUI:
        chat_active = True
        muted = False

        def __init__(self):
            self.logs = []

        def set_state(self, state):
            self.state = state

        def write_log(self, text):
            self.logs.append(text)

    fake_ui = FakeUI()
    original_speak_async = main_module._speak_async

    async def fail_if_called(text):
        raise AssertionError("채팅 모드에서 TTS가 호출됐습니다.")

    main_module._speak_async = fail_if_called
    try:
        main_module.speak_text("채팅 즉시 응답", fake_ui)
    finally:
        main_module._speak_async = original_speak_async
    assert fake_ui.logs == ["자비스: 채팅 즉시 응답"]

    import jarvis_ai.conversation_history as history_module
    original_history_file = history_module.HISTORY_FILE
    with tempfile.TemporaryDirectory() as temp_dir:
        history_module.HISTORY_FILE = Path(temp_dir) / "conversations.json"
        manager = ConversationManager()
        manager.add_conversation("음성 질문", "음성 답변", source="voice")
        manager.add_conversation("채팅 질문", "채팅 답변", source="chat")
        saved = manager.conversations["history"]
        assert [item["source"] for item in saved] == ["voice", "chat"]
        assert "채팅 질문" in manager.get_recent_context(2)
    history_module.HISTORY_FILE = original_history_file

    print("채팅 전체 출력 및 마이크 즉시 중지 테스트 통과")


if __name__ == "__main__":
    run()
