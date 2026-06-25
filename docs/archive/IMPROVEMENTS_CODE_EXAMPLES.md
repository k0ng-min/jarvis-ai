# JARVIS AI 개선 코드 예제 모음

이 문서는 다양한 JARVIS 프로젝트에서 발견한 우수 구현 패턴과 즉시 적용 가능한 코드 스니펫을 정리했습니다.

---

## 1️⃣ STT (음성 인식) 개선

### 패턴 1: 재시도 로직과 Exponential Backoff (필수)

**현재 main.py의 문제:**
```python
# ❌ 문제: 실패 시 그냥 empty string 반환 → 다음 반복으로 넘어감
text = recognizer.recognize_google(audio, language="ko-KR")
```

**개선된 구현 (적용하세요):**
```python
import time
from enum import Enum

class STTStatus(Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    UNRECOGNIZED = "unrecognized"
    MICROPHONE_ERROR = "mic_error"
    NETWORK_ERROR = "network_error"

def listen_mic_with_retry(
    ui=None,
    max_retries=2,
    retry_delays=[0.3, 0.5],
    timeout=6,
    phrase_time_limit=10
):
    """
    STT with intelligent retry logic
    
    Args:
        ui: UI instance for state updates
        max_retries: 최대 시도 횟수
        retry_delays: 각 재시도 전 대기 시간 (초)
        timeout: 입력 대기 시간 (초)
        phrase_time_limit: 최대 음성 길이 (초)
    
    Returns:
        (text, status) 튜플
    """
    global MIC_INDEX
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 200
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.5
    
    mic_kwargs = {"device_index": MIC_INDEX} if MIC_INDEX is not None else {}
    
    for attempt in range(max_retries):
        try:
            with sr.Microphone(**mic_kwargs) as source:
                if ui:
                    ui.set_state("LISTENING")
                
                print(f"[STT] 🎤 시도 {attempt+1}/{max_retries}", flush=True)
                
                # 배경음 적응 (짧은 시간으로 스킵 가능)
                recognizer.adjust_for_ambient_noise(source, duration=0.1)
                
                # 음성 수집
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit
                )
                
                # 상태 변경
                if ui:
                    ui.set_state("PROCESSING")
                
                # Google Speech-to-Text
                text = recognizer.recognize_google(audio, language="ko-KR")
                
                if text:
                    print(f"[STT] ✅ 인식: '{text}'", flush=True)
                    return text, STTStatus.SUCCESS
        
        except sr.WaitTimeoutError:
            print(f"[STT] ⏱️ 입력 타임아웃 ({attempt+1}/{max_retries})", flush=True)
            
            if attempt < max_retries - 1:
                wait_time = retry_delays[attempt]
                print(f"[STT] ⏳ {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                if ui:
                    ui.set_state("LISTENING")
            else:
                return "", STTStatus.TIMEOUT
        
        except sr.UnknownValueError:
            print(f"[STT] 🔇 음성 인식 불가 ({attempt+1}/{max_retries})", flush=True)
            
            if attempt < max_retries - 1:
                wait_time = retry_delays[attempt]
                print(f"[STT] 재시도...")
                time.sleep(wait_time)
                if ui:
                    ui.set_state("LISTENING")
            else:
                return "", STTStatus.UNRECOGNIZED
        
        except sr.RequestError as e:
            print(f"[STT] 🌐 네트워크 오류: {e}", flush=True)
            
            if "timed out" in str(e).lower():
                # 네트워크 타임아웃 → 재시도 가능
                if attempt < max_retries - 1:
                    time.sleep(1.0)
                    continue
            
            return "", STTStatus.NETWORK_ERROR
        
        except Exception as e:
            if "Input device" in str(e) or "No such device" in str(e):
                print(f"[STT] 🎤 마이크 오류: {e}", flush=True)
                
                # 마이크 오류 → fallback to system default
                if MIC_INDEX is not None:
                    print(f"[STT] 시스템 기본 마이크로 재시도...")
                    MIC_INDEX = None
                    mic_kwargs = {}
                    continue
                
                return "", STTStatus.MICROPHONE_ERROR
            else:
                print(f"[STT] ❌ 예상치 못한 오류: {e}", flush=True)
                return "", STTStatus.NETWORK_ERROR
    
    print(f"[STT] 모든 재시도 실패", flush=True)
    return "", STTStatus.TIMEOUT

# 사용 예제:
# text, status = listen_mic_with_retry(ui)
# if status == STTStatus.SUCCESS:
#     process_command(text)
# elif status == STTStatus.TIMEOUT:
#     speak_text("음성을 감지하지 못했습니다. 다시 시도해주세요.", ui)
```

---

### 패턴 2: 배경음(노이즈) 기반 동적 타임아웃

**출처:** isair/jarvis 에서 영감

```python
def adjust_threshold_for_environment(recognizer, source, target_snr=10):
    """
    배경음 수준에 따라 에너지 임계값 동적 조정
    
    SNR (Signal-to-Noise Ratio): 신호 대 노이즈 비
    - SNR > 15: 조용한 환경 (사무실)
    - SNR 10-15: 중간 (집)
    - SNR < 10: 시끄러운 환경 (카페)
    """
    print("[STT] 🔊 환경 분석 중...", flush=True)
    
    # 배경음 프로필링
    recognizer.adjust_for_ambient_noise(source, duration=0.3)
    ambient_energy = recognizer.energy_threshold
    
    # SNR 추정
    if ambient_energy < 100:
        snr = 20  # 매우 조용함
        timeout_factor = 1.0
        print("[STT] 🤫 매우 조용한 환경 감지", flush=True)
    elif ambient_energy < 250:
        snr = 15
        timeout_factor = 1.0
        print("[STT] 🏠 보통 환경 감지", flush=True)
    elif ambient_energy < 500:
        snr = 10
        timeout_factor = 1.2
        print("[STT] 🔊 시끄러운 환경 감지 - 타임아웃 증가", flush=True)
    else:
        snr = 5
        timeout_factor = 1.5
        print("[STT] 🎸 매우 시끄러운 환경 감지 - 타임아웃 대폭 증가", flush=True)
    
    return {
        "energy_threshold": recognizer.energy_threshold,
        "snr": snr,
        "timeout": 6 * timeout_factor,
        "pause_threshold": 0.5 + (0.5 * (1 - timeout_factor))
    }
```

---

## 2️⃣ Wake Word 감지 개선

### 패턴 1: Robust Wake Word Extraction (필수)

**현재 main.py의 문제:**
```python
# ❌ 복잡한 정규식 → 오류 가능
parts = re.split(
    r"(?:헤이\s*)?(?:자비스|jarvis|...)",
    text, maxsplit=1, flags=re.IGNORECASE
)
command = parts[-1].strip()
```

**개선된 구현:**
```python
class WakeWordDetector:
    """Wake word 감지 및 명령어 추출"""
    
    WAKE_WORDS = {
        "primary": ["자비스", "자비", "재비스", "재비"],
        "english": ["jarvis", "javis", "javice"],
        "prefix": ["헤이", "안녕", "어이", "이봐", "어"],
    }
    
    FUZZY_THRESHOLD = 0.75  # 75% 이상 유사도
    
    @staticmethod
    def find_wake_word(text):
        """
        텍스트에서 wake word 찾기
        
        Returns:
            (start_idx, wake_word) or (None, None)
        """
        text_lower = text.lower()
        
        # 1. 정확한 매칭 (빠름)
        for word_type, words in WakeWordDetector.WAKE_WORDS.items():
            for word in words:
                if word in text_lower:
                    idx = text_lower.find(word)
                    return idx, word
        
        # 2. 퍼지 매칭 (뭉개진 음성 허용)
        from difflib import SequenceMatcher
        for word_type, words in WakeWordDetector.WAKE_WORDS.items():
            for word in words:
                ratio = SequenceMatcher(None, text_lower, word).ratio()
                if ratio >= WakeWordDetector.FUZZY_THRESHOLD:
                    idx = text_lower.find(word)
                    return idx, word
        
        return None, None
    
    @staticmethod
    def extract_command(text, wake_word_idx, wake_word):
        """
        Wake word 이후의 명령어 추출
        
        Examples:
            "자비스 시간이 뭐야" → "시간이 뭐야"
            "자비스야 날씨 봐줘" → "날씨 봐줘"
            "자비스, 유튜브 틀어줘" → "유튜브 틀어줘"
        """
        # Wake word 뒤의 텍스트
        start_pos = wake_word_idx + len(wake_word)
        command = text[start_pos:].strip()
        
        # 한국어 조사/접속사 제거
        # 패턴: 공백, 쉼표, 마침표, 조사(야, 아, 이, 여, 는, 을, 을)
        command = re.sub(
            r"^[\s,\.\/\-–—야아이는을여]+",
            "",
            command
        ).strip()
        
        return command
    
    @staticmethod
    def is_valid_command(command):
        """명령어가 유효한지 확인"""
        # 너무 짧거나 "뭐", "뭐야" 같은 불완전한 명령 제외
        if len(command) < 2:
            return False
        
        if command in ["뭐", "뭐야", "뭐하냐", "뭐해"]:
            return False
        
        return True
    
    @classmethod
    def process(cls, text):
        """
        전체 wake word 감지 및 명령어 추출
        
        Returns:
            (wake_word, command) or (None, None)
        """
        idx, wake_word = cls.find_wake_word(text)
        
        if wake_word is None:
            return None, None
        
        command = cls.extract_command(text, idx, wake_word)
        
        if not cls.is_valid_command(command):
            # 명령어가 없으면 다음 발화 대기
            return wake_word, None
        
        return wake_word, command

# 사용:
# wake_word, command = WakeWordDetector.process("자비스 날씨 봐줘")
# # wake_word = "자비스", command = "날씨 봐줘"
```

### 패턴 2: LLM 기반 Intent Classification (선택사항, 고급)

**출처:** isair/jarvis

```python
async def classify_intent_with_llm(text):
    """
    LLM을 사용한 wake word 감지 (더 정확)
    
    Pros:
    - 복잡한 문장에서도 작동
    - Echo detection 가능 (자신의 음성 재생 감지)
    - 자연스러운 문장 처리
    
    Cons:
    - LLM 호출 오버헤드 (1-2초)
    - 네트워크 필요
    
    Best Practice: 빠른 매칭 먼저 → 불명확한 경우만 LLM 호출
    """
    
    # 단계 1: 빠른 키워드 매칭 (우선)
    if WakeWordDetector.find_wake_word(text)[0] is not None:
        return "summoned", None
    
    # 단계 2: 불명확한 경우만 LLM 호출
    prompt = f"""사용자 발화: "{text}"

이 발화에서 사용자가 AI 어시스턴트('자비스')를 부르려는 의도가 있나요?

응답 형식:
{{"intent": "summon|echo|command|other", "confidence": 0.0-1.0}}

- summon: "자비스야, ...", "자비스 ...", "jarvis ..." (어시스턴트 호출)
- echo: 자신이 방금 말한 문장이 들려온 것 (무시해야 함)
- command: 직접 명령 ("시간 알려줘", "날씨 봐줘") - 자비스 호출 없음
- other: 기타
"""
    
    response = await _call_claude_async(prompt)
    try:
        data = json.loads(response)
        return data.get("intent"), data.get("confidence")
    except:
        return "other", 0.0

# 사용:
# intent, confidence = await classify_intent_with_llm("사비스 뭐해")
# if intent == "summon" and confidence > 0.7:
#     process_as_wake_word()
```

---

## 3️⃣ TTS (음성 합성) 개선

### 패턴 1: Fallback Chain with Retry (현재 구현 개선)

**현재 main.py:**
```python
# ✅ 이미 좋은 구현, 약간만 개선
async def _speak_async(text: str):
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        # ...
```

**개선된 구현:**
```python
import asyncio
from enum import Enum
import time

class TTSStatus(Enum):
    SUCCESS = "success"
    EDGE_TTS_FAILED = "edge_tts_failed"
    PYTTSX3_FALLBACK = "pyttsx3_fallback"
    ALL_FAILED = "all_failed"

async def speak_with_fallback(
    text: str,
    ui=None,
    primary_voice="ko-KR-SunHiNeural",
    fallback_voice="ko-KR-InJoonNeural"
):
    """
    다층 폴백 체인을 사용한 TTS
    
    1단계: Edge-TTS (원하는 목소리)
    2단계: Edge-TTS (대체 목소리)
    3단계: pyttsx3 (빠른 폴백)
    """
    
    if not text or not text.strip():
        return TTSStatus.SUCCESS
    
    # 1단계: Primary Edge-TTS
    try:
        print(f"[TTS] 1단계: Edge-TTS ({primary_voice})", flush=True)
        if ui:
            ui.set_state("SPEAKING")
        
        import edge_tts
        communicate = edge_tts.Communicate(text, primary_voice)
        audio_data = b""
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        if audio_data:
            audio_io = io.BytesIO(audio_data)
            data, samplerate = sf.read(audio_io)
            sd.play(data, samplerate)
            sd.wait()
            print("[TTS] ✅ Edge-TTS 성공", flush=True)
            return TTSStatus.SUCCESS
    
    except Exception as e:
        print(f"[TTS] ⚠️ 1단계 실패: {e}", flush=True)
    
    # 2단계: Fallback Edge-TTS voice
    if fallback_voice != primary_voice:
        try:
            print(f"[TTS] 2단계: Edge-TTS ({fallback_voice})", flush=True)
            
            import edge_tts
            communicate = edge_tts.Communicate(text, fallback_voice)
            audio_data = b""
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            if audio_data:
                audio_io = io.BytesIO(audio_data)
                data, samplerate = sf.read(audio_io)
                sd.play(data, samplerate)
                sd.wait()
                print(f"[TTS] ✅ 폴백 음성으로 재생 ({fallback_voice})", flush=True)
                return TTSStatus.EDGE_TTS_FAILED
        
        except Exception as e:
            print(f"[TTS] ⚠️ 2단계 실패: {e}", flush=True)
    
    # 3단계: pyttsx3 (빠른 폴백, 로컬)
    try:
        print("[TTS] 3단계: pyttsx3 폴백", flush=True)
        
        import pyttsx3
        engine = pyttsx3.init()
        
        # 한국어 지원 여부 확인
        voices = engine.getProperty('voices')
        korean_voice = next(
            (v.id for v in voices if 'korean' in v.name.lower()),
            None
        )
        
        if korean_voice:
            engine.setProperty('voice', korean_voice)
        
        # 속도/볼륨 조정
        engine.setProperty('rate', 150)  # 말하기 속도
        engine.setProperty('volume', 0.9)
        
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        
        print("[TTS] ✅ pyttsx3로 재생 완료", flush=True)
        return TTSStatus.PYTTSX3_FALLBACK
    
    except Exception as e:
        print(f"[TTS] ❌ pyttsx3 실패: {e}", flush=True)
    
    # 모든 폴백 실패
    print("[TTS] ❌ 모든 TTS 시도 실패", flush=True)
    return TTSStatus.ALL_FAILED

def speak_text_improved(text: str, ui=None):
    """동기 래퍼 (기존 호환성)"""
    if not text or not text.strip():
        return
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            status = loop.run_until_complete(speak_with_fallback(text, ui))
        finally:
            loop.close()
        
        return status
    except Exception as e:
        print(f"[TTS] ❌ 동기 호출 오류: {e}", flush=True)
```

### 패턴 2: TTS 비동기 큐잉 (성능 개선)

```python
class AsyncTTSQueue:
    """
    여러 TTS 요청을 순차적으로 처리하는 큐
    
    이점:
    - TTS 중첩 재생 방지
    - 응답 순서 보장
    - 성능 향상
    """
    
    def __init__(self, ui=None):
        self.queue = asyncio.Queue()
        self.ui = ui
        self.worker_task = None
        self.active = False
    
    async def enqueue(self, text):
        """음성 텍스트를 큐에 추가"""
        if not text or not text.strip():
            return
        
        await self.queue.put(text)
        
        # 처음 요청이면 워커 시작
        if not self.active:
            asyncio.create_task(self._process_queue())
    
    async def _process_queue(self):
        """백그라운드에서 큐의 항목들을 순차 처리"""
        self.active = True
        
        try:
            while True:
                # 타임아웃 있이 대기 (3초)
                try:
                    text = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=3.0
                    )
                except asyncio.TimeoutError:
                    break
                
                # TTS 실행
                await speak_with_fallback(text, self.ui)
                self.queue.task_done()
        
        finally:
            self.active = False
    
    async def wait_until_empty(self):
        """모든 큐 항목이 처리될 때까지 대기"""
        await self.queue.join()

# 전역 TTS 큐
_tts_queue = None

async def init_tts_queue(ui=None):
    """TTS 큐 초기화"""
    global _tts_queue
    _tts_queue = AsyncTTSQueue(ui)

async def speak_queued(text):
    """큐를 통해 음성 재생"""
    global _tts_queue
    if _tts_queue:
        await _tts_queue.enqueue(text)
    else:
        # 큐 미초기화 시 직접 재생
        await speak_with_fallback(text)

# 사용:
# main() 에서:
# asyncio.run(init_tts_queue(ui))
# 이후:
# asyncio.run(speak_queued("안녕하세요"))
```

---

## 4️⃣ 타임아웃 및 오류 처리

### 패턴 1: 동적 타임아웃 설정

```python
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class TimeoutConfig:
    """타임아웃 설정 관리"""
    
    # STT (음성 입력)
    stt_input_timeout: float = 6.0      # 입력 대기
    stt_phrase_timeout: float = 10.0    # 최대 음성 길이
    stt_max_retries: int = 2
    
    # TTS (음성 출력)
    tts_timeout: float = 30.0           # Edge-TTS API 호출
    tts_max_retries: int = 2
    
    # Claude API
    claude_timeout: float = 15.0        # 응답 대기 (단축됨)
    claude_max_retries: int = 1
    
    # 도구 실행
    tool_timeout: float = 60.0
    tool_max_retries: int = 2
    
    # 환경별 프로필
    _presets: Dict[str, Dict] = field(default_factory=lambda: {
        "quiet": {
            "stt_input_timeout": 5.0,
            "stt_max_retries": 1,
        },
        "normal": {
            "stt_input_timeout": 6.0,
            "stt_max_retries": 2,
        },
        "noisy": {
            "stt_input_timeout": 8.0,
            "stt_max_retries": 3,
        },
        "fast": {
            "claude_timeout": 10.0,
            "tts_timeout": 20.0,
        },
        "slow": {
            "claude_timeout": 30.0,
            "tts_timeout": 60.0,
        }
    })
    
    def apply_preset(self, preset_name: str):
        """미리 정의된 프로필 적용"""
        if preset_name not in self._presets:
            print(f"[설정] ⚠️ 알 수 없는 프로필: {preset_name}")
            return
        
        preset = self._presets[preset_name]
        for key, value in preset.items():
            if hasattr(self, key):
                setattr(self, key, value)
                print(f"[설정] {key} = {value}")
    
    def to_dict(self):
        """딕셔너리로 변환 (JSON 저장용)"""
        return {
            "stt_input_timeout": self.stt_input_timeout,
            "stt_phrase_timeout": self.stt_phrase_timeout,
            "stt_max_retries": self.stt_max_retries,
            "tts_timeout": self.tts_timeout,
            "tts_max_retries": self.tts_max_retries,
            "claude_timeout": self.claude_timeout,
            "claude_max_retries": self.claude_max_retries,
            "tool_timeout": self.tool_timeout,
            "tool_max_retries": self.tool_max_retries,
        }

# 사용:
config = TimeoutConfig()
config.apply_preset("noisy")  # 시끄러운 환경에 맞춘 설정
```

### 패턴 2: 구조화된 오류 복구

```python
from enum import Enum
from typing import Callable, Any

class ErrorRecoveryStrategy(Enum):
    """오류 복구 전략"""
    RETRY = "retry"              # 다시 시도
    SKIP = "skip"                # 건너뛰기
    FALLBACK = "fallback"        # 대체 방법 사용
    ABORT = "abort"              # 중단
    REPLAN = "replan"            # 계획 변경

def handle_error_with_strategy(
    error: Exception,
    operation_name: str,
    context: Dict[str, Any],
    recovery_handlers: Dict[ErrorRecoveryStrategy, Callable]
) -> Tuple[ErrorRecoveryStrategy, Any]:
    """
    오류를 분석하고 복구 전략을 결정
    
    Args:
        error: 발생한 예외
        operation_name: 작업 이름 (예: "listen_mic", "call_claude")
        context: 컨텍스트 정보 (예: {"attempt": 2, "max_retries": 3})
        recovery_handlers: 각 전략별 처리 함수
    
    Returns:
        (strategy, result) 튜플
    """
    
    attempt = context.get("attempt", 1)
    max_retries = context.get("max_retries", 2)
    
    # 1단계: 오류 타입별 분류
    if isinstance(error, TimeoutError):
        if attempt < max_retries:
            strategy = ErrorRecoveryStrategy.RETRY
        else:
            strategy = ErrorRecoveryStrategy.ABORT
    
    elif isinstance(error, ConnectionError):
        strategy = ErrorRecoveryStrategy.FALLBACK
    
    elif isinstance(error, ValueError):
        strategy = ErrorRecoveryStrategy.SKIP
    
    else:
        strategy = ErrorRecoveryStrategy.REPLAN
    
    # 2단계: 복구 핸들러 실행
    if strategy in recovery_handlers:
        handler = recovery_handlers[strategy]
        result = handler(error, operation_name, context)
        return strategy, result
    
    return strategy, None

# 사용 예제:
def retry_handler(error, op, ctx):
    print(f"[오류] {op} 재시도 ({ctx['attempt']}/{ctx['max_retries']})")
    time.sleep(0.5 * ctx['attempt'])  # Exponential backoff

def fallback_handler(error, op, ctx):
    print(f"[오류] {op} 폴백 사용")
    return "fallback_result"

handlers = {
    ErrorRecoveryStrategy.RETRY: retry_handler,
    ErrorRecoveryStrategy.FALLBACK: fallback_handler,
}

# 호출:
try:
    result = risky_operation()
except Exception as e:
    strategy, recovery_result = handle_error_with_strategy(
        error=e,
        operation_name="listen_mic",
        context={"attempt": 1, "max_retries": 2},
        recovery_handlers=handlers
    )
```

---

## 5️⃣ 마이크 관리 개선

### 패턴: 안전한 마이크 인덱스 관리

```python
class MicrophoneManager:
    """마이크 인덱스를 안전하게 관리"""
    
    def __init__(self, prefer_usb=True):
        self.index = None
        self.fallback_used = False
        self.error_count = 0
        self.max_errors = 3
        self.prefer_usb = prefer_usb
        
        # 초기 감지
        self.detect()
    
    def detect(self):
        """최고 품질의 마이크 자동 감지"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            
            # 우선순위
            candidates = []
            
            for i, device in enumerate(devices):
                # 입력 장치만 필터링
                if device['max_input_channels'] == 0:
                    continue
                if device['max_output_channels'] > 0:  # 입출력 겸용 제외
                    continue
                
                name_lower = device['name'].lower()
                
                # USB 마이크 우선
                if self.prefer_usb and 'usb' in name_lower:
                    candidates.append((i, 100, device['name']))
                # 마이크 포함
                elif 'microphone' in name_lower or 'mic' in name_lower:
                    candidates.append((i, 90, device['name']))
                # 입력 장치
                elif 'input' in name_lower:
                    candidates.append((i, 80, device['name']))
                # 기타
                else:
                    candidates.append((i, 50, device['name']))
            
            if candidates:
                # 우선순위 정렬
                candidates.sort(key=lambda x: x[1], reverse=True)
                self.index = candidates[0][0]
                print(f"[마이크] ✅ 감지: {candidates[0][2]} (인덱스: {self.index})")
            else:
                print("[마이크] ⚠️ 입력 장치 없음 - 시스템 기본값 사용")
                self.index = None
        
        except Exception as e:
            print(f"[마이크] ❌ 감지 실패: {e}")
            self.index = None
    
    def get_kwargs(self):
        """음성 인식기용 kwargs 반환"""
        if self.index is None:
            return {}
        return {"device_index": self.index}
    
    def mark_error(self):
        """마이크 오류 기록 - 안전한 폴백"""
        self.error_count += 1
        
        if self.error_count >= self.max_errors:
            print(f"[마이크] ⚠️ {self.max_errors}회 오류 - 기본값으로 리셋")
            self.index = None
            self.fallback_used = True
            self.error_count = 0
            return True
        
        return False
    
    def reset(self):
        """마이크 설정 초기화"""
        self.index = None
        self.fallback_used = False
        self.error_count = 0
        self.detect()

# 전역 마이크 관리자
_mic_manager = None

def init_microphone():
    global _mic_manager
    _mic_manager = MicrophoneManager()

def get_microphone_manager():
    global _mic_manager
    if _mic_manager is None:
        init_microphone()
    return _mic_manager

# 사용:
# init_microphone()
# mic = get_microphone_manager()
# kwargs = mic.get_kwargs()
# try:
#     result = recognize(kwargs)
# except MicError:
#     mic.mark_error()
```

---

## 📝 요약: 각 패턴별 영향도

| 패턴 | 적용 난이도 | 성능 향상 | 안정성 향상 | 우선순위 |
|------|-----------|---------|-----------|---------|
| STT 재시도 | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 🔴 HIGH |
| Wake word 추출 | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | 🔴 HIGH |
| TTS Fallback 개선 | ⭐ | ⭐ | ⭐⭐⭐ | 🟡 MED |
| TTS 비동기 큐잉 | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | 🟡 MED |
| 동적 타임아웃 | ⭐⭐ | ⭐ | ⭐⭐ | 🟡 MED |
| 마이크 관리 | ⭐⭐⭐ | - | ⭐⭐⭐ | 🔴 HIGH |
| LLM Intent 분류 | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 🟢 LOW |

---

**다음 단계:** 위 패턴들을 main.py에 통합하고 테스트하세요!
