"""
자비스 AI 어시스턴트
Claude Code CLI 기반 버전 (claude -p 서브프로세스)
음성: SpeechRecognition(STT) + edge-tts(TTS)
"""

import asyncio
import threading
import time
import json
import subprocess
import re
import sys
import io
import math
import traceback
import warnings
from array import array
from pathlib import Path
from datetime import datetime
from enum import Enum
from difflib import SequenceMatcher

# stderr 인코딩 오류 무시 (배경 스레드의 UTF-8 디코딩 오류)
warnings.filterwarnings("ignore", category=RuntimeWarning)

import speech_recognition as sr
import sounddevice as sd
import soundfile as sf

from .ui import JarvisUI
from .memory.memory_manager import (
    extract_memory, format_memory_for_prompt, load_memory, update_memory
)
from .conversation_history import ConversationManager

from .actions.file_processor     import file_processor
from .actions.flight_finder      import flight_finder
from .actions.open_app           import open_app
from .actions.weather_report     import weather_action
from .actions.send_message       import send_message
from .actions.reminder           import reminder
from .actions.computer_settings  import computer_settings
from .actions.screen_processor   import screen_process
from .actions.youtube_video      import youtube_video
from .actions.desktop            import desktop_control
from .actions.browser_control    import browser_control
from .actions.file_controller    import file_controller
from .actions.code_helper        import code_helper
from .actions.dev_agent          import dev_agent
from .actions.web_search         import web_search as web_search_action
from .actions.computer_control   import computer_control
from .actions.game_updater       import game_updater
from .actions.realtime_info      import (
    exchange_rate, air_quality, public_holidays, encyclopedia,
    calculate, unit_convert, recent_earthquakes,
)
from .paths import PACKAGE_DIR, PROMPT_PATH
from .research_pipeline import (
    needs_verified_research,
    research_text_for_speech,
    run_research_pipeline,
)


BASE_DIR = PACKAGE_DIR

# edge-tts 한국어 음성 설정
TTS_VOICE = "ko-KR-SunHiNeural"   # 여성 음성
# TTS_VOICE = "ko-KR-InJoonNeural"  # 남성 음성

# Claude 응답 속도 설정
CLAUDE_MODEL = "haiku"
CLAUDE_EFFORT = "low"

# ── 마이크 설정 ──────────────────────────────────────────────────────────────
# None = 자동 감지 (최고 품질 마이크)
# 숫자 = check_microphones.py 실행 후 원하는 마이크 번호 입력

USE_MIC_INDEX = None  # ← 자동 감지 사용

def _auto_detect_mic_index():
    """SpeechRecognition(PyAudio) 기준으로 사용할 마이크를 고른다."""
    try:
        names = sr.Microphone.list_microphone_names()
        if not names:
            print("[마이크] 입력 장치 없음 - 시스템 기본값 사용")
            return None

        # sounddevice와 PyAudio는 장치 인덱스가 다를 수 있으므로 반드시
        # SpeechRecognition이 실제로 사용하는 PyAudio 목록에서 선택한다.
        bad_keywords = ("stereo mix", "스테레오 믹스", "output", "speaker", "스피커")
        priorities = (
            ("usb", "웹캠", "webcam"),
            ("microphone", "마이크", "mic", "input"),
            ("bluetooth", "headset", "헤드셋"),
        )

        candidates = [
            (i, name) for i, name in enumerate(names)
            if name and not any(word in name.lower() for word in bad_keywords)
        ]
        for keywords in priorities:
            for i, name in candidates:
                if any(word in name.lower() for word in keywords):
                    print(f"[마이크] 자동 감지: {name} (PyAudio 인덱스: {i})")
                    return i

        # 적절한 이름을 찾지 못하면 운영체제 기본 입력 장치를 쓰는 편이 안전하다.
        print("[마이크] 자동 감지 후보 없음 - 시스템 기본 마이크 사용")
        return None
    except Exception as e:
        print(f"[마이크] 감지 오류: {e}")
        return None

MIC_INDEX: int | None = (
    USE_MIC_INDEX if USE_MIC_INDEX is not None else _auto_detect_mic_index()
)

# ─────────────────────────────────────────────
# Status Enums
# ─────────────────────────────────────────────

class STTStatus(Enum):
    """음성 인식 상태"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    UNRECOGNIZED = "unrecognized"
    MICROPHONE_ERROR = "mic_error"
    NETWORK_ERROR = "network_error"

class TTSStatus(Enum):
    """음성 합성 상태"""
    SUCCESS = "success"
    EDGE_TTS_FAILED = "edge_tts_failed"
    PYTTSX3_FALLBACK = "pyttsx3_fallback"
    ALL_FAILED = "all_failed"

# ─────────────────────────────────────────────
# Wake Word Detector
# ─────────────────────────────────────────────

class WakeWordDetector:
    """Wake word 감지 및 명령어 추출"""

    WAKE_WORDS = {
        "primary": ["자비스", "자비", "재비스", "재비", "자비스야", "자비야",
                    "더비", "더비스", "제비", "제비스"],  # 유사 발음 추가
        "english": ["jarvis", "javis", "javice"],
        "prefix": ["헤이", "안녕", "어이", "이봐", "어", "이"],
    }

    FUZZY_THRESHOLD = 0.65  # 더 관대함 (65% → 이전 75%)

    @staticmethod
    def find_wake_word(text):
        """문장 맨 앞의 wake word만 찾기."""
        text_lower = text.lower().strip()

        # "자비스, 날씨 알려줘"처럼 호출어가 문장 앞에 있을 때만 활성화한다.
        # 일반 문장 중간에 자비스라는 단어가 들어간 경우에는 호출로 보지 않는다.
        for word_type in ("primary", "english"):
            words = WakeWordDetector.WAKE_WORDS[word_type]
            for word in words:
                if text_lower.startswith(word):
                    return 0, word

        # "헤이 자비스" 같은 짧은 호출 접두사도 허용한다.
        for prefix in WakeWordDetector.WAKE_WORDS["prefix"]:
            remainder = text_lower[len(prefix):].lstrip(" ,.!?~")
            if not text_lower.startswith(prefix) or not remainder:
                continue
            for word in (
                WakeWordDetector.WAKE_WORDS["primary"]
                + WakeWordDetector.WAKE_WORDS["english"]
            ):
                if remainder.startswith(word):
                    return len(text_lower) - len(remainder), word

        # 앞 단어가 음성 인식으로 조금 뭉개진 경우에만 퍼지 매칭한다.
        first_token = re.split(r"[\s,!.?~]+", text_lower, maxsplit=1)[0]
        for word_type in ("primary", "english"):
            for word in WakeWordDetector.WAKE_WORDS[word_type]:
                ratio = SequenceMatcher(None, first_token, word).ratio()
                if ratio >= WakeWordDetector.FUZZY_THRESHOLD:
                    return 0, first_token

        return None, None

    @staticmethod
    def extract_command(text, wake_word_idx, wake_word):
        """Wake word 이후의 명령어 추출"""
        start_pos = wake_word_idx + len(wake_word)
        command = text[start_pos:].strip()

        # 한국어 조사/접속사 제거
        command = re.sub(
            r"^[\s,\.\/\-–—야아이는을여]+",
            "",
            command
        ).strip()

        return command

    @staticmethod
    def is_valid_command(command):
        """명령어가 유효한지 확인"""
        if len(command) < 2:
            return False
        if command in ["뭐", "뭐야", "뭐하냐", "뭐해"]:
            return False
        return True

    @classmethod
    def process(cls, text):
        """전체 wake word 감지 및 명령어 추출"""
        idx, wake_word = cls.find_wake_word(text)

        if wake_word is None:
            return None, None

        command = cls.extract_command(text, idx, wake_word)

        if not cls.is_valid_command(command):
            return wake_word, None

        return wake_word, command

# Claude CLI 세션 ID (대화 맥락 유지)
_session_id: str = ""
_session_lock = threading.Lock()
_claude_cache: dict[str, str] = {}
_tts_lock = threading.Lock()
_tts_active = threading.Event()

# ─────────────────────────────────────────────
# 시스템 프롬프트 로드
# ─────────────────────────────────────────────

def _load_system_prompt() -> str:
    base = (
        "당신은 자비스, AI 어시스턴트입니다. 간결하고 직접적으로 답변하세요. "
        "도구가 필요하면 <tool>이름</tool><params>{...}</params> 형식으로 호출하세요."
    )
    try:
        base = PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        pass
    # 한국어 전용 강제 접미사
    korean_suffix = (
        "\n\n[언어 강제] 반드시 한국어로만 답하세요. "
        "영어 단어나 문장을 섞지 마세요. 기술 용어도 한국어로 표현하세요."
    )
    return base + korean_suffix


# ─────────────────────────────────────────────
# TTS (Text-to-Speech) — edge-tts 사용
# ─────────────────────────────────────────────

async def _speak_async(text: str):
    """edge-tts로 텍스트를 음성으로 변환 후 재생"""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        audio_io = io.BytesIO(audio_data)
        data, samplerate = sf.read(audio_io)
        sd.play(data, samplerate)
        sd.wait()
    except Exception as e:
        if "UnicodeDecodeError" not in str(type(e).__name__):
            print(f"[TTS] ❌ 오류: {e}")


def speak_text(
    text: str,
    ui: JarvisUI | None = None,
    display_text: str | None = None,
):
    """동기 방식으로 TTS 재생 + 홀로그램 텍스트 표시"""
    if not text or not text.strip():
        return
    # 여러 응답이 겹쳐 재생되거나, TTS 중 마이크가 자기 목소리를 듣지 않게 한다.
    with _tts_lock:
        _tts_active.set()
        if ui:
            ui.set_state("SPEAKING")
            ui.write_log(f"자비스: {display_text or text}")
        try:
            # 채팅 모드에서도 답변 음성은 재생한다. 마이크만 별도로 정지된다.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_speak_async(text))
            finally:
                loop.close()
        except Exception as e:
            print(f"[TTS] ❌ {e}")
        finally:
            _tts_active.clear()
            if ui and not ui.muted:
                ui.set_state("LISTENING")


# ─────────────────────────────────────────────
# STT (Speech-to-Text) — SpeechRecognition 사용
# ─────────────────────────────────────────────

class _LevelMonitoringStream:
    """SpeechRecognition이 읽는 PCM에서 실시간 음량을 측정하는 스트림 래퍼."""

    def __init__(self, stream, callback, sample_width: int, cancel_check=None):
        self._stream = stream
        self._callback = callback
        self._sample_width = sample_width
        self._last_emit = 0.0
        self._cancel_check = cancel_check

    def read(self, size):
        if self._cancel_check and self._cancel_check():
            raise ChatModeActivated()
        data = self._stream.read(size)
        if self._cancel_check and self._cancel_check():
            raise ChatModeActivated()
        now = time.monotonic()
        if now - self._last_emit >= 0.03:
            self._last_emit = now
            self._callback(self._rms(data))
        return data

    def close(self):
        return self._stream.close()

    def _rms(self, data: bytes) -> float:
        if not data or self._sample_width != 2:
            return 0.0
        try:
            samples = array("h")
            samples.frombytes(data)
            if sys.byteorder == "big":
                samples.byteswap()
            if not samples:
                return 0.0
            return math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        except (ValueError, TypeError):
            return 0.0


class ChatModeActivated(Exception):
    """Raised to stop an active microphone read when chat mode opens."""


def listen_mic(ui: JarvisUI | None = None) -> str:
    """마이크 입력을 받아 텍스트로 변환 (한국어 최적화 + 음량 표시)"""
    global MIC_INDEX
    if ui and ui.chat_active:
        return ""
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 220
    recognizer.dynamic_energy_threshold = True
    # 문장 중간에 잠깐 쉬어도 녹음을 끝내지 않는다.
    recognizer.pause_threshold = 1.2
    recognizer.non_speaking_duration = 0.6
    recognizer.phrase_threshold = 0.25

    mic_kwargs = {"device_index": MIC_INDEX} if MIC_INDEX is not None else {}

    try:
        with sr.Microphone(**mic_kwargs) as source:
            if ui:
                ui.set_state("LISTENING")
                ui.set_mic_level(0.0)  # 음량 초기화
            print(f"[STT] 🎤 듣는 중... (마이크 인덱스={MIC_INDEX})")

            try:
                # 너무 짧은 보정은 키보드 소리 등을 목소리로 오인하기 쉽다.
                recognizer.adjust_for_ambient_noise(source, duration=0.35)
                recognizer.energy_threshold = max(180, min(recognizer.energy_threshold, 1200))
                print(f"[STT] 에너지 임계값: {int(recognizer.energy_threshold)} | 지금 말해보세요...")

                # recognizer.listen()이 실제로 읽는 동일 스트림을 감싸므로
                # 마이크 충돌 없이 발화 중 실시간 음량을 UI에 전달할 수 있다.
                if ui and source.stream is not None:
                    raw_stream = source.stream

                    def emit_level(rms):
                        baseline = max(120.0, float(recognizer.energy_threshold))
                        level = max(0.0, min(1.0, (rms - baseline * 0.35) / (baseline * 2.2)))
                        ui.set_mic_level(level)

                    source.stream = _LevelMonitoringStream(
                        raw_stream,
                        emit_level,
                        source.SAMPLE_WIDTH,
                        cancel_check=lambda: ui.chat_active,
                    )

                audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)

                print("[STT] 🎙️ 소리 감지됨, 인식 중...")

                if ui:
                    ui.set_mic_level(0.0)
                    ui.set_state("THINKING")

                # Google Speech Recognition - 한국어
                text = recognizer.recognize_google(audio, language="ko-KR")
                print(f"[STT] ✅ 인식됨: '{text}'")

                if ui:
                    ui.set_mic_level(0.0)  # 인식 완료 후 음량 리셋
                return text

            except ChatModeActivated:
                print("[STT] 채팅 모드 활성화 - 마이크 입력 중지")
                if ui:
                    ui.set_mic_level(0.0)
                return ""
            except sr.WaitTimeoutError:
                print(f"[STT] ⏱️ 입력 없음")
                if ui:
                    ui.set_mic_level(0.0)
                return ""
            except sr.UnknownValueError:
                print(f"[STT] 🔇 음성 감지되었으나 인식 불가")
                if ui:
                    ui.set_mic_level(0.0)
                return ""
            except Exception as e:
                print(f"[STT] ❌ 인식 오류: {e}", flush=True)
                if ui:
                    ui.set_mic_level(0.0)
                return ""
    except Exception as e:
        print(f"[STT] ❌ 마이크 오류: {e}", flush=True)
        # 마이크 오류 시 시스템 기본으로 재시도
        if MIC_INDEX is not None:
            print(f"[STT] ⚠️ 마이크 인덱스 {MIC_INDEX} 오류 - 시스템 기본 마이크 시도")
            MIC_INDEX = None
            return listen_mic(ui)  # 재귀 호출로 다시 시도
        return ""

def listen_mic_with_retry(ui=None, max_retries=2, retry_delays=[0.3, 0.5]):
    """STT with retry logic - 호환성 래퍼"""
    for attempt in range(max_retries):
        if ui and ui.chat_active:
            return "", STTStatus.TIMEOUT
        text = listen_mic(ui)
        if text:
            return text, STTStatus.SUCCESS
        if attempt < max_retries - 1:
            print(f"[STT] 재시도 {attempt+1}/{max_retries}...", flush=True)
            time.sleep(retry_delays[attempt])
    return "", STTStatus.TIMEOUT


# ─────────────────────────────────────────────
# Claude Code CLI 호출
# ─────────────────────────────────────────────

def _call_claude(
    user_message: str,
    system_prompt: str = "",
    recent_context: str = "",
) -> str:
    """claude -p 서브프로세스로 응답 생성"""
    global _session_id

    cache_key = re.sub(r"\s+", " ", user_message.strip().lower())
    if cache_key in _claude_cache:
        print("[Claude] 캐시 응답 사용")
        return _claude_cache[cache_key]

    with _session_lock:
        sid = _session_id

    # 첫 번째 호출에만 날짜와 메모리를 전달한다. 시스템 프롬프트는
    # --system-prompt로 넘겨 Claude Code의 큰 기본 프롬프트를 대체한다.
    if not sid and system_prompt:
        now = datetime.now().strftime("%Y년 %m월 %d일 %A %H:%M")
        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)

        full_message = (
            f"[현재 날짜/시간]: {now}\n"
        )
        if mem_str:
            full_message += f"\n{mem_str}\n"
        if recent_context:
            full_message += f"\n{recent_context}\n"
        full_message += f"\n[사용자 메시지]: {user_message}"
    else:
        full_message = user_message

    cmd = [
        "claude", "-p", full_message,
        "--output-format", "json",
        "--model", CLAUDE_MODEL,
        "--effort", CLAUDE_EFFORT,
        # 실시간 검색은 앱의 빠른 웹 도구가 담당한다. Claude Code의 내장
        # 도구와 브라우저/MCP 초기화를 끄면 일반 대화 시작 시간이 줄어든다.
        "--tools", "",
        "--permission-mode", "dontAsk",
        "--no-chrome",
        "--disable-slash-commands",
        "--prompt-suggestions", "false",
    ]
    if sid:
        cmd.extend(["--resume", sid])
    elif system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    print(
        f"[Claude] 📤 요청 중... "
        f"(모델: {CLAUDE_MODEL}, 세션: {sid[:8] if sid else '신규'})"
    )

    try:
        # UTF-8 강제 환경변수 설정 (Windows cp949 충돌 방지)
        import os as _os
        env = _os.environ.copy()
        env["PYTHONUTF8"]      = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,  # stdin 비활성화 (경고 메시지 제거)
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # stderr를 stdout으로 병합
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # 답변 생성이 오래 걸려도 중간에 프로세스를 종료하지 않는다.
        # 이 작업은 백그라운드 스레드에서 실행되므로 UI는 계속 움직인다.
        started_at = time.monotonic()
        raw_out, _ = proc.communicate()
        elapsed = time.monotonic() - started_at

        stdout = raw_out.strip()
        if not stdout:
            print("[Claude] ⚠️ 응답 없음", flush=True)
            return ""

        try:
            data = json.loads(stdout)
            response_text = data.get("result", "").strip()

            # 세션 ID 저장 (대화 맥락 유지)
            new_sid = data.get("session_id", "")
            if new_sid:
                with _session_lock:
                    _session_id = new_sid

            if response_text:
                _claude_cache[cache_key] = response_text
            print(f"[Claude] ✅ 응답 수신 ({elapsed:.1f}초, {len(response_text)}자)")
            return response_text

        except json.JSONDecodeError:
            # JSON이 아닌 경우 그냥 텍스트로 반환
            return stdout

    except FileNotFoundError:
        return (
            "claude 명령어를 찾을 수 없습니다. "
            "Claude Code가 설치되어 있는지 확인하세요: https://claude.ai/download"
        )
    except Exception as e:
        print(f"[Claude] ❌ 예외: {e}")
        traceback.print_exc()
        return f"오류 발생: {str(e)[:200]}"


# ─────────────────────────────────────────────
# 빠른 로컬 라우터 (Claude 호출 없음)
# ─────────────────────────────────────────────

def _fuzzy_match(text: str, keywords: list[str], threshold: float = 0.6) -> bool:
    """부분 매칭 + 오류 허용 (뭉개진 음성도 인식)"""
    from difflib import SequenceMatcher
    t = text.lower().strip()
    for kw in keywords:
        # 완전 일치 먼저 확인
        if kw in t:
            return True
        # 부분 유사도 확인 (80% 이상 유사)
        ratio = SequenceMatcher(None, t, kw).ratio()
        if ratio > 0.75:
            return True
    return False


def _fast_route(text: str) -> tuple[str | None, dict, str | None]:
    """
    Claude 없이 키워드로 바로 도구 라우팅.
    반환: (tool_name, params, direct_answer)
      - 뭉개진 음성도 유추해서 인식
      - direct_answer가 있으면 도구 없이 바로 말함
      - tool_name이 있으면 해당 도구 실행
      - 둘 다 None이면 Claude에게 위임
    """
    t   = text.lower().strip()
    now = datetime.now()

    # ── 초고속 기본 대화 ──
    # 짧은 인사와 상태 확인은 모델을 실행할 이유가 없다.
    compact = re.sub(r"[\s!?.,~]+", "", t)
    if compact in {
        "안녕", "안녕하세요", "하이", "반가워", "반가워요",
        "좋은아침", "좋은저녁",
    }:
        return None, {}, "안녕하세요. 무엇을 도와드릴까요?"
    if compact in {"고마워", "고맙다", "감사해", "감사합니다", "땡큐"}:
        return None, {}, "천만에요."
    if compact in {"잘가", "다음에봐", "바이"}:
        return None, {}, "네, 필요할 때 다시 불러주세요."
    if compact in {
        "잘있어", "작동해", "작동하니", "듣고있어", "듣고있니",
        "준비됐어", "준비됐니", "거기있어", "거기있니",
    }:
        return None, {}, "네, 정상 작동 중이며 듣고 있습니다."
    if compact in {"너누구야", "넌누구야", "이름이뭐야"}:
        return None, {}, "저는 경민님의 인공지능 비서 자비스입니다."

    # ── 계산 / 단위 변환 ──
    calc_text = t
    for source, target in {
        "더하기": "+", "플러스": "+", "빼기": "-", "마이너스": "-",
        "곱하기": "*", "곱한": "*", "나누기": "/", "나눈": "/",
    }.items():
        calc_text = calc_text.replace(source, target)
    expression = re.sub(r"[^0-9+\-*/().%^]", "", calc_text)
    if (
        expression
        and re.search(r"\d", expression)
        and re.search(r"[+\-*/%^]", expression)
        and any(word in t for word in ("계산", "얼마", "더하기", "빼기", "곱하기", "나누기"))
    ):
        return "calculate", {"expression": expression}, None

    unit_aliases = (
        "킬로미터|키로미터|km|미터|m|센티미터|cm|밀리미터|mm|마일|mi|"
        "킬로그램|키로그램|kg|그램|g|파운드|lb|리터|l|밀리리터|ml|섭씨|화씨"
    )
    unit_match = re.search(
        rf"(-?\d+(?:\.\d+)?)\s*({unit_aliases}).*?(?:는|은|을|를|에서|로)?\s*"
        rf"({unit_aliases})(?:로|으로|는|은)?.*?(?:바꿔|변환|얼마)",
        t,
    )
    if unit_match:
        return "unit_convert", {
            "value": float(unit_match.group(1)),
            "from": unit_match.group(2),
            "to": unit_match.group(3),
        }, None

    # ── 환율 ──
    if any(word in t for word in ("환율", "달러", "유로", "엔화", "위안", "파운드")):
        currencies = {
            "달러": "USD", "미국": "USD", "usd": "USD",
            "원": "KRW", "krw": "KRW",
            "유로": "EUR", "eur": "EUR",
            "엔": "JPY", "엔화": "JPY", "jpy": "JPY",
            "위안": "CNY", "cny": "CNY",
            "파운드": "GBP", "gbp": "GBP",
            "호주 달러": "AUD", "캐나다 달러": "CAD",
        }
        found = []
        for name, code in sorted(currencies.items(), key=lambda item: -len(item[0])):
            if name in t and code not in found:
                found.append(code)
        base = found[0] if found else "USD"
        quote = found[1] if len(found) > 1 else ("KRW" if base != "KRW" else "USD")
        amount_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:만|천)?", t)
        amount = float(amount_match.group(1)) if amount_match else 1.0
        if amount_match and "만" in t[amount_match.end():amount_match.end() + 2]:
            amount *= 10000
        elif amount_match and "천" in t[amount_match.end():amount_match.end() + 2]:
            amount *= 1000
        return "exchange_rate", {
            "base": base, "quote": quote, "amount": amount,
        }, None

    # ── 대기질 / 미세먼지 / 자외선 ──
    if any(word in t for word in ("미세먼지", "초미세먼지", "대기질", "공기질", "자외선")):
        cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "수원",
                  "청주", "제주", "강릉", "전주", "창원", "성남", "고양",
                  "천안", "세종", "구미", "포항", "경주", "평택", "화성", "용인"]
        loc = next((c for c in cities if c in t), "서울")
        return "air_quality", {"city": loc}, None

    # ── 공휴일 ──
    if any(word in t for word in ("공휴일", "빨간날", "쉬는 날", "쉬는날")):
        year_match = re.search(r"(20\d{2})\s*년?", t)
        return "public_holidays", {
            "year": int(year_match.group(1)) if year_match else now.year,
            "country": "KR",
            "mode": "all" if any(w in t for w in ("전체", "모두", "목록")) else "next",
        }, None

    # ── 실시간 지진 ──
    if any(word in t for word in ("지진", "진도", "규모 몇")):
        magnitude_match = re.search(r"(?:규모|매그니튜드)\s*(\d+(?:\.\d+)?)", t)
        return "recent_earthquakes", {
            "minimum_magnitude": (
                float(magnitude_match.group(1)) if magnitude_match else 4.5
            )
        }, None

    # ── 백과사전 빠른 조회 ──
    if any(word in t for word in ("위키백과", "백과사전", "위키에서")):
        query = t
        for word in ("위키백과에서", "백과사전에서", "위키에서", "검색해줘", "찾아줘", "알려줘"):
            query = query.replace(word, " ")
        return "encyclopedia", {"query": query.strip() or text}, None

    # ── 시간 ── (다양한 표현 지원: "몇시야", "지금 몇 시야", "시간이 어떻게" 등)
    time_keywords = ["몇시", "몇시야", "시간", "시각", "몇시간", "지금시", "현재시", "지금", "몇", "시야", "시간이", "지금 몇"]
    if _fuzzy_match(t, time_keywords, threshold=0.7):
        # "날씨"가 아닌지 확인 (날씨 질문이 아니어야 함)
        if "날씨" not in t and "기온" not in t and "온도" not in t:
            hour = now.hour
            minute = now.minute
            # 자연스러운 응답
            if hour == 0:
                time_str = f"자정 {minute}분"
            elif hour < 12:
                time_str = f"오전 {hour}시 {minute}분"
            elif hour == 12:
                time_str = f"정오 {minute}분"
            else:
                time_str = f"오후 {hour-12}시 {minute}분"
            return None, {}, f"현재 시각은 {time_str}입니다."

    # ── 날씨 ── (날짜보다 먼저 체크! "오늘 날씨" 구분하기 위해)
    if _fuzzy_match(t, ["날씨", "기온", "온도", "비와", "비가", "눈이", "기상", "날시"]):
        cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "수원",
                  "청주", "제주", "강릉", "전주", "창원", "성남", "고양",
                  "천안", "세종", "구미", "포항", "경주", "평택", "화성", "용인"]
        loc = next((c for c in cities if c in t), "")
        # 도시를 말하지 않으면 기본 지역(서울)의 실제 날씨를 조회한다.
        return "weather_report", {
            "city": loc or "서울",
            "time": text,
        }, None

    # 최신성/가격/구매 정보는 Claude의 기억에 맡기지 않고 웹 검색으로 보낸다.
    live_keywords = (
        "실시간", "최신", "뉴스", "검색", "웹에서", "인터넷",
        "주가", "코인 가격", "비트코인", "경기 결과", "스포츠 순위",
        "교통 상황", "가격 비교",
    )
    shopping_context = any(
        word in t for word in (
            "노트북", "컴퓨터", "휴대폰", "스마트폰", "태블릿",
            "이어폰", "헤드폰", "자동차", "제품",
        )
    ) and any(word in t for word in ("추천", "구매", "살까", "가격", "비교"))
    if any(word in t for word in live_keywords) or shopping_context:
        return "web_search", {"query": text, "max_results": 5}, None

    # ── 날짜/요일 ── (오늘, 내일, 모레, 다음주 등)
    if _fuzzy_match(t, ["날짜", "몇월", "며칠", "요일", "무슨요일", "내일", "모레", "다음", "어제"]):
        weekdays = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]

        # 내일, 모레 등 상대적 날짜 처리
        from datetime import timedelta
        target_date = now
        if "어제" in t:
            target_date = now - timedelta(days=1)
        elif "내일" in t or "내일은" in t:
            target_date = now + timedelta(days=1)
        elif "모레" in t:
            target_date = now + timedelta(days=2)
        elif "다음주" in t:
            target_date = now + timedelta(days=7)

        wd = weekdays[target_date.weekday()]
        label = "오늘은" if target_date == now else "그날은"
        return None, {}, f"{label} {target_date.strftime('%Y년 %m월 %d일')} {wd}입니다."

    # ── 유튜브 ── (유튜, 유튜브, 동영상 등)
    if _fuzzy_match(t, ["유튜브", "youtube", "유튜", "유튜ㅠ", "동영상"]):
        query = text
        for w in ["유튜브에서", "유튜브", "youtube", "틀어줘", "틀어", "재생해줘",
                  "재생해", "보여줘", "보여", "검색해줘", "검색해", "동영상"]:
            query = re.sub(w, "", query, flags=re.IGNORECASE).strip()
        return "youtube_video", {"action": "search", "query": query or text}, None

    # ── 앱 열기 ──
    open_triggers = ["열어줘", "열어", "실행해줘", "실행해", "켜줘", "켜", "시작", "열기"]
    if _fuzzy_match(t, open_triggers):
        app_name = text
        for w in open_triggers + ["줘", "주세요", "해줘", "해"]:
            app_name = app_name.replace(w, "").strip()
        if app_name:
            return "open_app", {"app_name": app_name}, None

    # ── 볼륨/밝기 설정 ──
    if _fuzzy_match(t, ["볼륨", "소리", "음량", "밝기", "밝게", "어둡게"]):
        return "computer_settings", {"task": text}, None

    # ── 알림/리마인더 ──
    if _fuzzy_match(t, ["알림", "리마인더", "알려줘", "분후", "시간후", "나중"]):
        return "reminder", {"task": text}, None

    # Claude에게 위임
    return None, {}, None


# ─────────────────────────────────────────────
# 도구 호출 파싱
# ─────────────────────────────────────────────

_TOOL_PATTERN  = re.compile(r'<tool>(.*?)</tool>',   re.DOTALL | re.IGNORECASE)
_PARAMS_PATTERN = re.compile(r'<params>(.*?)</params>', re.DOTALL | re.IGNORECASE)


def _parse_and_dispatch(response: str, ui=None, speak_fn=None) -> str | None:
    """Claude 응답에서 도구 추출 → 실행 → 결과 반환. 도구 없으면 None."""
    tool_name, params, clean = parse_tool_call(response)
    if not tool_name:
        return None
    result = execute_tool(tool_name, params or {}, ui=ui, speak_fn=speak_fn)
    return result or clean or None


def parse_tool_call(response: str) -> tuple[str | None, dict | None, str]:
    """응답 텍스트에서 도구 호출 추출"""
    tool_match   = _TOOL_PATTERN.search(response)
    params_match = _PARAMS_PATTERN.search(response)

    if not tool_match:
        return None, None, response

    tool_name = tool_match.group(1).strip()
    params: dict = {}

    if params_match:
        try:
            params = json.loads(params_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 도구 태그를 제거한 순수 텍스트 (사용자에게 말할 부분)
    clean = _TOOL_PATTERN.sub("", response)
    clean = _PARAMS_PATTERN.sub("", clean).strip()

    return tool_name, params, clean


# ─────────────────────────────────────────────
# 도구 실행
# ─────────────────────────────────────────────

def execute_tool(
    tool_name: str,
    params: dict,
    ui: JarvisUI | None = None,
    speak_fn=None
) -> str:
    """도구 이름에 따라 해당 액션 모듈 실행"""
    print(f"[도구] 🔧 {tool_name}  {params}")
    if ui:
        ui.set_state("THINKING")
        ui.write_log(f"[도구] {tool_name}")

    try:
        match tool_name:
            case "open_app":
                r = open_app(parameters=params, player=ui)
                return r or f"{params.get('app_name', '앱')}을(를) 열었습니다."

            case "weather_report":
                r = weather_action(parameters=params, player=ui)
                return r or "날씨 정보를 가져왔습니다."

            case "exchange_rate":
                return exchange_rate(params, player=ui)

            case "air_quality":
                return air_quality(params, player=ui)

            case "public_holidays":
                return public_holidays(params, player=ui)

            case "encyclopedia":
                return encyclopedia(params, player=ui)

            case "recent_earthquakes":
                return recent_earthquakes(params, player=ui)

            case "calculate":
                return calculate(params, player=ui)

            case "unit_convert":
                return unit_convert(params, player=ui)

            case "web_search":
                r = web_search_action(parameters=params, player=ui)
                return r or "검색이 완료되었습니다."

            case "send_message":
                r = send_message(parameters=params, player=ui)
                return r or "메시지를 전송했습니다."

            case "reminder":
                r = reminder(parameters=params, player=ui)
                return r or "알림이 설정되었습니다."

            case "youtube_video":
                r = youtube_video(parameters=params, player=ui)
                return r or "완료되었습니다."

            case "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": params, "player": ui, "speak": speak_fn},
                    daemon=True
                ).start()
                return "화면 분석을 시작합니다."

            case "computer_settings":
                r = computer_settings(parameters=params, player=ui)
                return r or "완료되었습니다."

            case "browser_control":
                r = browser_control(parameters=params, player=ui)
                return r or "완료되었습니다."

            case "file_controller":
                r = file_controller(parameters=params, player=ui)
                return r or "완료되었습니다."

            case "desktop_control":
                r = desktop_control(parameters=params, player=ui)
                return r or "완료되었습니다."

            case "code_helper":
                r = code_helper(parameters=params, player=ui, speak=speak_fn)
                return r or "완료되었습니다."

            case "dev_agent":
                r = dev_agent(parameters=params, player=ui, speak=speak_fn)
                return r or "완료되었습니다."

            case "agent_task":
                from .agent.task_queue import get_queue, TaskPriority
                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH
                }
                priority = priority_map.get(
                    params.get("priority", "normal").lower(), TaskPriority.NORMAL
                )
                task_id = get_queue().submit(
                    goal=params.get("goal", ""),
                    priority=priority,
                    speak=speak_fn
                )
                return f"작업이 시작되었습니다. (ID: {task_id})"

            case "computer_control":
                r = computer_control(parameters=params, player=ui)
                return r or "완료되었습니다."

            case "game_updater":
                r = game_updater(parameters=params, player=ui, speak=speak_fn)
                return r or "완료되었습니다."

            case "flight_finder":
                r = flight_finder(parameters=params, player=ui)
                return r or "완료되었습니다."

            case "file_processor":
                if not params.get("file_path") and ui and getattr(ui, "current_file", None):
                    params["file_path"] = ui.current_file
                r = file_processor(parameters=params, player=ui, speak=speak_fn)
                return r or "완료되었습니다."

            case "save_memory":
                category = params.get("category", "notes")
                key      = params.get("key", "")
                value    = params.get("value", "")
                if key and value:
                    update_memory({category: {key: {"value": value}}})
                    print(f"[메모리] 💾 저장: {category}/{key} = {value}")
                return "기억했습니다."

            case "shutdown_jarvis":
                if speak_fn:
                    speak_fn("안녕히 계세요.")
                import os, time
                time.sleep(1.5)
                os._exit(0)

            case _:
                return f"알 수 없는 도구: {tool_name}"

    except Exception as e:
        print(f"[도구] error: {tool_name} - {e}")
        traceback.print_exc()
        return f"오류: {str(e)[:150]}"


# ─────────────────────────────────────────────
# 메인 대화 루프
# ─────────────────────────────────────────────

class JarvisAssistant:
    def __init__(self, ui):
        self.ui            = ui
        self.session_id    = None
        self.system_prompt = _load_system_prompt()
        self._history: list[dict] = []
        self._interaction_busy = threading.Event()
        self._conversation_manager = ConversationManager()

    @staticmethod
    def _should_store_long_term(user_text: str) -> bool:
        markers = (
            "기억해", "내 이름은", "나는 ", "제가 ", "좋아해", "싫어해",
            "내 프로젝트", "내 목표", "내 계획", "학교는", "사는 곳", "생일은",
        )
        return any(marker in user_text for marker in markers)

    def _extract_long_term_memory(self, user_text: str, response: str):
        if not self._should_store_long_term(user_text):
            return
        memory_update = extract_memory(user_text, response)
        if memory_update:
            update_memory(memory_update)
            print("[메모리] 음성/채팅 공통 장기 기억 업데이트", flush=True)

    def _respond(
        self,
        user_text: str,
        response: str,
        response_type: str,
        source: str,
        spoken_text: str | None = None,
    ):
        if not response or not response.strip():
            return
        self._conversation_manager.add_conversation(
            user_text,
            response,
            response_type=response_type,
            source=source,
        )
        threading.Thread(
            target=self._extract_long_term_memory,
            args=(user_text, response),
            daemon=True,
        ).start()
        speak_text(
            spoken_text or response,
            self.ui,
            display_text=response if spoken_text else None,
        )

    def _process_input(self, user_text: str, source: str = "voice"):
        user_text = user_text.strip()
        if not user_text:
            return
        self.ui.write_log(f"나: {user_text}")
        self.ui.set_state("생각 중")

        if needs_verified_research(user_text):
            print("[라우터] verified_research", flush=True)
            self.ui.set_state("처리 중")
            researched = run_research_pipeline(user_text)
            if researched:
                self._respond(
                    user_text,
                    researched,
                    "research",
                    source,
                    spoken_text=research_text_for_speech(researched),
                )
            else:
                self._respond(
                    user_text,
                    "웹 조사를 완료하지 못했습니다. 잠시 후 다시 시도해주세요.",
                    "research_error",
                    source,
                )
            return

        # 빠른 로컬 처리 (_fast_route는 (tool_name, params, direct_answer) 튜플 반환)
        tool_name, params, direct_answer = _fast_route(user_text)
        route_name = tool_name or ("local_answer" if direct_answer else "claude")
        print(f"[라우터] {route_name}", flush=True)
        if direct_answer:
            # 로컬 답변: 동기 처리 (즉시 응답)
            self._respond(user_text, direct_answer, "local", source)
            return
        if tool_name:
            self.ui.set_state("처리 중")
            result = _parse_and_dispatch(
                f"<tool>{tool_name}</tool><params>{json.dumps(params, ensure_ascii=False)}</params>",
                self.ui,
                speak_fn=lambda t: speak_text(t, self.ui)  # 동기 처리
            )
            if result:
                self._respond(user_text, result, tool_name, source)
            return

        # 호출자는 이미 작업 스레드이므로 여기서 스레드를 한 번 더 만들지 않는다.
        # 그래야 응답과 TTS가 끝날 때까지 음성 루프를 정확히 멈출 수 있다.
        self.ui.set_state("처리 중")
        response = _call_claude(
            user_text,
            self.system_prompt,
            recent_context=self._conversation_manager.get_recent_context(6),
        )

        # 도구 호출 파싱
        tool_result = _parse_and_dispatch(
            response, self.ui, speak_fn=lambda t: speak_text(t, self.ui)
        )
        if tool_result is not None:
            final = tool_result
        else:
            final = response

        # 도구 태그 제거 후 발화
        clean = re.sub(r"<tool>.*?</tool>", "", final, flags=re.DOTALL)
        clean = re.sub(r"<params>.*?</params>", "", clean, flags=re.DOTALL).strip()
        if clean:
            self._respond(user_text, clean, "claude", source)

    def _process_input_guarded(self, user_text: str, source: str = "voice"):
        """한 번에 하나의 음성 명령만 처리하고 종료 후 다시 듣는다."""
        try:
            self._process_input(user_text, source=source)
        except Exception as e:
            print(f"[명령 처리] 오류: {e}", flush=True)
            traceback.print_exc()
        finally:
            self._interaction_busy.clear()
            if source == "chat":
                self.ui.set_chat_busy(False)
            if not self.ui.muted and not _tts_active.is_set():
                self.ui.set_state("LISTENING")

    def _start_voice_command(self, text: str):
        if self._interaction_busy.is_set():
            print("[자비스] 이전 명령 처리 중이라 새 입력을 잠시 보류합니다.", flush=True)
            return
        self._interaction_busy.set()
        threading.Thread(
            target=self._process_input_guarded,
            args=(text, "voice"),
            daemon=True,
        ).start()

    def submit_text_command(self, text: str):
        """채팅 입력도 음성 처리와 겹치지 않게 같은 잠금으로 실행한다."""
        if self._interaction_busy.is_set():
            self.ui.write_log("자비스: 이전 명령을 처리하고 있어요. 잠시 후 다시 보내주세요.")
            return
        self._interaction_busy.set()
        self._process_input_guarded(text, source="chat")

    def voice_loop(self):
        self.ui.wait_for_api_key()
        time.sleep(0.5)
        print("[자비스] 준비 완료.", flush=True)

        # 안내 음성이 끝난 뒤 듣기를 시작해 자기 목소리를 명령으로 오인하지 않는다.
        speak_text("헤이 자비스라고 불러주세요.", self.ui)

        while True:
            try:
                if self.ui.muted:
                    time.sleep(0.3)
                    continue
                if self.ui.chat_active:
                    time.sleep(0.05)
                    continue
                if _tts_active.is_set() or self._interaction_busy.is_set():
                    time.sleep(0.05)
                    continue

                # STT로 음성 인식 (재시도 로직 포함)
                text, stt_status = listen_mic_with_retry(self.ui, max_retries=2)

                if not text:
                    # 인식 실패 → 조용히 무시
                    continue

                print(f"[STT] 원문: '{text}'", flush=True)

                # Wake word 감지 및 명령어 추출
                wake_word, command = WakeWordDetector.process(text)

                if wake_word is None:
                    # Wake word 없음 → 다음 반복
                    continue

                if command:
                    # 웨이크워드 + 명령 한 문장
                    print(f"[자비스] 명령: '{command}'", flush=True)
                    self._start_voice_command(command)
                else:
                    # 웨이크워드만 감지 → 다음 발화 대기
                    print(f"[자비스] 웨이크워드 감지, 명령 대기...", flush=True)
                    next_text, _ = listen_mic_with_retry(self.ui, max_retries=1)
                    if next_text:
                        # 두 번째 문장에서 "자비스"를 다시 말해도 명령에는
                        # 호출어를 포함하지 않는다.
                        next_wake, next_command = WakeWordDetector.process(next_text)
                        if next_wake and next_command:
                            next_text = next_command
                        elif next_wake and not next_command:
                            continue
                        print(f"[자비스] 명령: '{next_text}'", flush=True)
                        self._start_voice_command(next_text)

            except Exception as e:
                print(f"[voice_loop] 오류: {e}", flush=True)
                traceback.print_exc()
                time.sleep(0.5)


def main():
    face_path = str(BASE_DIR / "core" / "face.png")
    ui = JarvisUI(face_path=face_path)
    assistant = JarvisAssistant(ui)
    ui.on_text_command = assistant.submit_text_command
    threading.Thread(target=assistant.voice_loop, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
