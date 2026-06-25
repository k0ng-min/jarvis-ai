"""Chat display and microphone cancellation integration tests."""

import os
from array import array

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

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
    print("채팅 전체 출력 및 마이크 즉시 중지 테스트 통과")


if __name__ == "__main__":
    run()
