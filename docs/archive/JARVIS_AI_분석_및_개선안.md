# JARVIS AI 프로젝트 분석 및 개선안

## 📊 연구 대상 프로젝트 (상위 10개)

| 순위 | 프로젝트명 | 별 | 주요 특징 |
|------|----------|-----|----------|
| 1 | J.A.R.V.I.S (GauravSingh9356) | 1.2k | Python 개인 어시스턴트, OCR/뉴스/음악 |
| 2 | Jarvis Desktop Voice Assistant | 781 | 음성 인식 + TTS, 시스템 명령 |
| 3 | jarvis-ai-assistant | 570 | Mac 음성 AI, TypeScript/Native |
| 4 | JARVIS-ChatGPT | 453 | ChatGPT + OpenAI Whisper + TTS |
| 5 | J.A.R.V.I.S (BolisettySujith) | 363 | pyttsx3 + SpeechRecognition |
| 6 | OpenJarvis | 82.7% Python | 다중 에이전트, Rust 성능 최적화 |
| 7 | Jarvis (isair) | 556 | 100% 프라이빗 로컬 AI, Whisper |
| 8 | JARVIS-1 (CraftJarvis) | - | 멀티모달 에이전트 (Minecraft) |

**한국 프로젝트:**
- **gyeongseon-k/jarvis-ai** - 한국어 전용, Faster-Whisper + Edge-TTS, 퀴즈 감지 로직

---

## 🔍 분석된 핵심 구현 패턴

### 1️⃣ 음성 인식 (Speech-to-Text)

#### 라이브러리 선택:
| 라이브러리 | 장점 | 단점 | 사용 프로젝트 |
|-----------|------|------|-------------|
| **Google Speech-to-Text** | 높은 정확도, 한국어 지원 | API 비용, 네트워크 필요 | JARVIS (메인) |
| **OpenAI Whisper** | 오프라인, 다국어, 정확도 우수 | CPU/메모리 소비 | isair/jarvis, JARVIS-ChatGPT |
| **Faster-Whisper** | Whisper보다 빠름 (ONNX) | 설정 복잡 | gyeongseon-k/jarvis-ai |
| **PicoVoice/Porcupine** | 로컬 wake word 감지 | API 키 필요, 제한적 | JARVIS-ChatGPT (옵션) |
| **Deepgram** | 빠른 전사, 저비용 | 외부 API | jarvis-ai-assistant |

#### 한국어 최적화 전략 (gyeongseon-k/jarvis-ai):
```python
# Faster-Whisper로 RMS 기반 음성 활동 감지 (VAD)
# - 고정 타임아웃 대신 자동 종료
# - 침묵 감지하면 자동으로 녹음 종료
# - 뭉개진 음성 처리: "자비스" → "사비스", "자빗스" 등 허용
```

#### 타임아웃 패턴:
```python
# 권장 설정:
recognizer.timeout = 6  # 마이크 입력 대기 (초)
recognizer.phrase_time_limit = 10  # 최대 음성 길이
recognizer.pause_threshold = 0.5  # 침묵 감지 임계값
recognizer.energy_threshold = 200  # 배경음 필터 (동적 조정)
```

---

### 2️⃣ 텍스트-음성 변환 (Text-to-Speech)

#### 라이브러리 비교:
| 라이브러리 | 언어 지원 | 성능 | 오프라인 | 품질 |
|-----------|----------|------|---------|------|
| **Edge-TTS** | 다국어 (한국어 우수) | 빠름 | ✗ | 매우 우수 |
| **pyttsx3** | 제한적 | 느림 | ✓ | 저품질 |
| **Tacotron** | 커스터마이징 | 중간 | ✓ | 우수 |
| **IBM Watson TTS** | 다국어 | 빠름 | ✗ | 우수 |

#### Edge-TTS 사용 전략 (gyeongseon-k + main.py):
```python
# 자동 언어 감지 + 최적 음성 선택
TTS_VOICE_KO = "ko-KR-SunHiNeural"  # 여성
TTS_VOICE_EN = "en-GB-RyanNeural"    # 남성

# 응답 텍스트 언어 감지 → 자동 음성 전환
# 음성 속도 조정: +20% 가속화 (자연스러운 응답 속도)
# pygame.mixer + pyttsx3 폴백 체인
```

#### Fallback 전략 (JARVIS-ChatGPT):
```
1차: Tacotron (JARVIS 캐릭터 음성)
  ↓
2차: IBM Watson TTS (국제 언어)
  ↓
3차: pyttsx3 (빠른 폴백)
```

---

### 3️⃣ Wake Word 감지 ("헤이 자비스")

#### 패턴별 구현:

**방식 A: Fuzzy Matching (빠른 반응)**
```python
# main.py 현재 구현
WAKE = ["자비스", "jarvis", "자비", "재비스", "재비", "javis", "javice"]
# - 뭉개진 음성 허용 (STT 오류 대응)
# - SequenceMatcher로 80% 유사도 확인
# - 부분 매칭 + 전체 매칭 이중 확인
```

**방식 B: 음절별 Fuzzy Matching (정밀함)**
```python
# gyeongseon-k/jarvis-ai
# "자비스" 인식 + "사비스", "자빗스" 허용
# "자비를 구하다" 같은 false positive 필터링
# 음절 위치별 문자 화이트리스트 적용
```

**방식 C: LLM 기반 Intent 분류 (정확함)**
```python
# isair/jarvis
# Whisper 결과 → LLM Intent Judge (gemma4:e2b)
# - Echo detection (자신의 음성 재생 감지)
# - Stop command 구분
# - 문장 내 어디서든 "Jarvis" 인식 가능
```

#### 마이크 감지 & 오류 처리 (main.py 현재):
```python
def _auto_detect_mic_index():
    """최고 품질 마이크 자동 감지"""
    priority_keywords = ["usb", "microphone", "input", "mic", "audio input"]
    
    # 1단계: 우선 키워드가 있는 입력 장치 찾기
    # 2단계: 첫 번째 입력 장치 찾기 (입력만, 출력 제외)
    # 3단계: 감지 실패 → None (시스템 기본)
    
    # 마이크 오류 시 fallback (재귀 호출)
    if MIC_INDEX is not None:
        MIC_INDEX = None
        return listen_mic(ui)  # 재시도
```

---

### 4️⃣ 타임아웃 처리 및 사용자 피드백

#### 계층별 타임아웃 (isair/jarvis):
```
1. Cold Startup: 60초 (Ollama 로딩)
2. Web Search: 20초 (외부 API 차단)
3. Tool Operation: 300초 idle timeout
4. Voice Recognition: 6초 (입력 대기) / 10초 (최대 길이)
5. Claude 응답: 15초 (원본 30초 → 단축)
```

#### UI 상태 피드백 (main.py):
```python
# 상태 변화: LISTENING → THINKING → SPEAKING
# 각 상태 전환 시 UI에 명확한 시각적 신호 제공
ui.set_state("LISTENING")   # 🎤 듣는 중
ui.set_state("THINKING")    # 💭 생각 중
ui.set_state("SPEAKING")    # 🗣️ 말하는 중
```

#### 종료 조건 (JARVIS-ChatGPT):
```
- 사용자 stop 키워드 ("감사합니다", "고마워")
- 30초 이상 침묵
- 단문 응답 감지
```

---

### 5️⃣ 에러 복구 메커니즘

#### 에러 분류 전략 (gyeongseon-k/jarvis-ai):
```python
# API 오류 구분
- API 키 누락/만료 → 사용자 친화적 메시지
- 쿼타 초과 → "이달의 검색 한도가 다했습니다"
- 네트워크 오류 → 자동 재시도
- 기타 예외 → 로깅 + 폴백
```

#### 지능형 오류 복구 (error_handler.py):
```python
def analyze_error(step, error, attempt=1, max_attempts=2):
    """Claude를 사용한 오류 분석 및 결정"""
    
    decision = "retry|skip|replan|abort"
    # RETRY: 일시적 오류 (네트워크, 타임아웃)
    # SKIP: 비필수 단계
    # REPLAN: 접근 방식 변경 (대체 도구 사용)
    # ABORT: 근본적 실패 (중단)
```

#### 재시도 로직 (권장):
```python
# Exponential backoff
retry_delays = [0.5, 1, 2, 4]  # 초 단위
for attempt, delay in enumerate(retry_delays):
    try:
        result = api_call()
        return result
    except TemporaryError:
        if attempt < len(retry_delays) - 1:
            time.sleep(delay)
        else:
            return fallback_result()
```

---

## 🎯 우리 main.py 현재 상태 분석

### ✅ 이미 구현된 우수 사항:
1. **자동 마이크 감지** - 입력 장치만 필터링, 우선순위 기반 선택
2. **Wake word Fuzzy Matching** - 뭉개진 음성 처리 (80% 유사도)
3. **빠른 로컬 라우터** - Claude 호출 없이 시간/날씨/앱 열기 등 즉시 처리
4. **멀티 폴백 TTS** - Edge-TTS + pyttsx3 체인
5. **에러 분류** - API 키 오류/네트워크 오류 구분
6. **세션 관리** - Claude 세션 ID 유지로 대화 맥락 보존
7. **한국어 강제** - 시스템 프롬프트에 한국어 전용 접미사

### ⚠️ 미흡한 부분:
1. STT 재시도 로직 미흡 (단순 empty string 반환)
2. Wake word 후 명령어 추출 정규식 복잡도 높음
3. 타임아웃 에러 처리 단순 (15초로 단축했지만 조정 여지 부족)
4. 마이크 인덱스 글로벌 변수 (재귀 호출 위험)
5. TTS 동기 처리 → 느린 응답

---

## 💡 개선안 (우선순위별)

### 🔴 HIGH PRIORITY (즉시 적용 필요)

#### 1. STT 재시도 로직 강화
**문제:** 음성 인식 실패 시 그냥 empty string 반환 → 빈 명령 무시
**해결:**
```python
def listen_mic_with_retry(ui, max_retries=2, backoff_delays=[0.3, 0.5]):
    """재시도 로직이 있는 STT"""
    for attempt in range(max_retries):
        try:
            text = _listen_once(ui)  # 기존 로직
            if text:  # 성공
                return text
        except sr.WaitTimeoutError:
            if attempt < max_retries - 1:
                print(f"[STT] ⏱️ 타임아웃 - {backoff_delays[attempt]}초 후 재시도")
                time.sleep(backoff_delays[attempt])
                ui.set_state("LISTENING")  # 상태 초기화
        except sr.UnknownValueError:
            if attempt < max_retries - 1:
                print(f"[STT] 🔇 인식 불가 - {backoff_delays[attempt]}초 후 재시도")
                time.sleep(backoff_delays[attempt])
    
    if ui:
        ui.set_state("IDLE")
    return ""
```

#### 2. Wake Word 후 명령어 추출 개선
**문제:** 정규식 `r"(?:헤이\s*)?(?:자비스|jarvis|...)"` 복잡 + 오류 가능성
**해결:**
```python
WAKE_PATTERNS = {
    "main": ["자비스", "자비", "재비스", "재비"],
    "english": ["jarvis", "javis", "javice"],
    "prefix": ["헤이", "안녕", "어이"]
}

def extract_command_from_wake(text):
    """Wake word 제거 후 명령어 추출"""
    for pattern in WAKE_PATTERNS["main"] + WAKE_PATTERNS["english"]:
        if pattern in text.lower():
            idx = text.lower().find(pattern)
            # Wake word 뒤의 텍스트 (접속사 제거)
            cmd = text[idx + len(pattern):].strip()
            # 앞 공백, 조사 제거: "야 뭐야", ", 뭐야" 등
            cmd = re.sub(r"^[\s,\.야아이는이여]+", "", cmd).strip()
            return cmd
    return ""
```

#### 3. 타임아웃 조정 가능한 구조
**문제:** Timeout 값들이 하드코딩 → 조정 어려움
**해결:**
```python
# config.py (새 파일)
VOICE_CONFIG = {
    "STT": {
        "timeout": 6,              # 입력 대기
        "phrase_time_limit": 10,   # 최대 음성 길이
        "pause_threshold": 0.5,    # 침묵 감지
        "energy_threshold": 200,   # 배경음 필터
        "retry_max": 2,
        "retry_delays": [0.3, 0.5],
    },
    "TTS": {
        "speed_rate": 1.2,         # 음성 속도 (1.2배 = 20% 빠름)
        "language_detect": True,
    },
    "WAKE_WORD": {
        "fuzzy_threshold": 0.75,   # 유사도 임계값 (75%+)
        "retry_on_fail": True,
    },
    "CLAUDE": {
        "timeout": 15,             # 응답 대기
        "retry_on_timeout": True,
    }
}
```

#### 4. 마이크 인덱스 전역 변수 제거
**문제:** `MIC_INDEX`를 전역으로 변경 → 재귀 호출 위험
**해결:**
```python
class AudioManager:
    def __init__(self):
        self.mic_index = None
        self.retry_count = 0
        self.max_mic_retries = 2
    
    def reset_mic(self):
        """마이크 오류 시 기본값으로 리셋"""
        if self.retry_count < self.max_mic_retries:
            self.mic_index = None
            self.retry_count += 1
            return True
        return False
```

---

### 🟡 MEDIUM PRIORITY (다음 주 내 개선)

#### 5. TTS 비동기 처리 + 큐잉
**문제:** 동기 TTS 처리 → 느린 응답, 여러 메시지 겹침
**해결:**
```python
class TTSQueue:
    def __init__(self, ui):
        self.queue = asyncio.Queue()
        self.ui = ui
        self.worker_task = None
    
    async def enqueue(self, text):
        """음성 재생 큐에 추가"""
        await self.queue.put(text)
    
    async def process_queue(self):
        """백그라운드에서 순차 재생"""
        while True:
            text = await self.queue.get()
            await _speak_async(text)
            self.queue.task_done()
```

#### 6. Wake Word 감지에 LLM Intent 분류 추가
**문제:** 단순 문자열 매칭 → False Positive 가능
**해결:**
```python
async def detect_wake_word_smart(text):
    """
    1단계: 빠른 키워드 매칭 (Fuzzy)
    2단계: LLM으로 Intent 확인
    """
    # 먼저 빠른 매칭
    if any(w in text.lower() for w in ["자비스", "jarvis"]):
        # LLM으로 최종 확인 (선택사항)
        prompt = f"이 문장에서 사용자가 'Jarvis'를 호출한 의도가 있나? '{text}'"
        intent = await check_intent_with_llm(prompt)  # 비동기
        if intent == "summon":
            return True
    return False
```

#### 7. 상세한 로깅 + 디버그 모드
**문제:** 오류 원인 파악 어려움
**해결:**
```python
import logging

logger = logging.getLogger("jarvis")
handler = logging.FileHandler("jarvis_debug.log")
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# 사용
logger.debug(f"[STT] 마이크 감지: {device['name']}")
logger.error(f"[TTS] 오류: {e}", exc_info=True)
```

---

### 🟢 LOW PRIORITY (향후 개선)

#### 8. Echo Detection (자신의 음성 재생 감지)
**구현:**
```python
def detect_echo(audio_chunk):
    """방금 재생한 TTS 음성이 다시 들어오는지 감지"""
    # MFCC (Mel-Frequency Cepstral Coefficients) 비교
    # 라이브러리: librosa, python_speech_features
    pass
```

#### 9. Context-Aware 응답 길이 조정
**구현:**
```python
# 문맥에 따라 TTS 속도/길이 조정
if len(response) > 500:
    tts_speed_rate = 1.3  # 긴 응답은 더 빠르게
elif len(response) < 50:
    tts_speed_rate = 1.0  # 짧은 응답은 자연스럽게
```

#### 10. Multi-language 자동 감지
**구현:**
```python
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0

def detect_language(text):
    """응답 텍스트의 언어 자동 감지"""
    try:
        lang = detect(text)
        return lang  # 'ko', 'en', 'ja', etc.
    except:
        return 'ko'  # 기본값 한국어
```

---

## 📈 적용 전후 비교

### Before:
- STT 실패 → 침묵 → 다음 iteration
- Wake word 추출 오류 → 명령 손실
- TTS 동기 처리 → 느린 응답 (3-5초 추가)
- 마이크 오류 → 무한 재귀 위험
- 타임아웃 조정 불가 → 환경별 적응 불가

### After:
- STT 재시도 → 성공률 향상 (estimated +15-20%)
- 안정적 Wake word 추출 → 명령 손실 감소
- TTS 비동기 + 큐잉 → 응답 시간 단축 (1-2초)
- 안전한 마이크 fallback → 무한 루프 방지
- 동적 타임아웃 → 환경별 최적화

---

## 🔧 즉시 적용 가능한 코드 스니펫

### Snippet 1: STT 재시도 함수
```python
def listen_mic_robust(ui=None, max_retries=2):
    """재시도 로직이 있는 음성 인식"""
    global MIC_INDEX
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 200
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.5
    
    retry_delays = [0.3, 0.5]
    mic_kwargs = {"device_index": MIC_INDEX} if MIC_INDEX is not None else {}
    
    for attempt in range(max_retries):
        try:
            with sr.Microphone(**mic_kwargs) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.1)
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=10)
                text = recognizer.recognize_google(audio, language="ko-KR")
                print(f"[STT] ✅ ({attempt+1}/{max_retries}) '{text}'")
                return text
        except sr.WaitTimeoutError:
            if attempt < max_retries - 1:
                print(f"[STT] ⏱️ 타임아웃 - {retry_delays[attempt]:.1f}초 후 재시도")
                time.sleep(retry_delays[attempt])
                if ui:
                    ui.set_state("LISTENING")
        except sr.UnknownValueError:
            if attempt < max_retries - 1:
                print(f"[STT] 🔇 인식 불가 - {retry_delays[attempt]:.1f}초 후 재시도")
                time.sleep(retry_delays[attempt])
        except Exception as e:
            if MIC_INDEX is not None and "Input device" in str(e):
                print(f"[STT] 마이크 오류 - 기본값으로 재시도")
                MIC_INDEX = None
                return listen_mic_robust(ui, max_retries - attempt - 1)
            return ""
    
    return ""
```

### Snippet 2: 안전한 마이크 인덱스 관리
```python
class MicrophoneManager:
    def __init__(self):
        self.index = _auto_detect_mic_index()
        self.fallback_used = False
    
    def get_kwargs(self):
        """마이크 kwargs 반환"""
        return {"device_index": self.index} if self.index is not None else {}
    
    def mark_error(self):
        """마이크 오류 기록 - 한 번만"""
        if not self.fallback_used:
            self.index = None
            self.fallback_used = True
            return True
        return False  # 이미 폴백 사용 → 더 이상 변경 없음

# 사용
mic_mgr = MicrophoneManager()
kwargs = mic_mgr.get_kwargs()
if error and mic_mgr.mark_error():
    # 한 번만 기본 마이크로 시도
    pass
```

### Snippet 3: Wake Word 안정적 추출
```python
def extract_command_after_wake(text):
    """Wake word 제거 후 명령어 추출 - 개선된 버전"""
    wake_words = {
        "main": ["자비스", "자비", "재비스", "재비"],
        "english": ["jarvis", "javis", "javice"],
    }
    
    text_lower = text.lower()
    
    # 모든 wake word 후보 찾기
    matches = []
    for word_type, words in wake_words.items():
        for word in words:
            if word in text_lower:
                matches.append((text_lower.find(word), len(word), word))
    
    if not matches:
        return ""
    
    # 가장 처음 나타나는 wake word 선택
    idx, word_len, word = min(matches, key=lambda x: x[0])
    
    # Wake word 뒤 텍스트 추출
    command = text[idx + word_len:].strip()
    
    # 한국어 조사 제거: "야 뭐야", ", 뭐야", "아 뭐야" 등
    command = re.sub(r"^[\s,\.\/\-–—야아이는이여]+", "", command).strip()
    
    return command
```

### Snippet 4: 동적 타임아웃 설정
```python
class VoiceConfig:
    """동적으로 조정 가능한 음성 설정"""
    def __init__(self):
        self.stt_timeout = 6
        self.stt_phrase_limit = 10
        self.claude_timeout = 15
        self.tts_speed = 1.2
        self.max_retries = 2
    
    def adjust_for_environment(self, noise_level: float):
        """배경 노이즈 수준에 따라 조정"""
        if noise_level > 0.8:  # 높은 노이즈
            self.stt_timeout = 8
            self.max_retries = 3
            print("[설정] 🔊 높은 배경음 감지 - 타임아웃 증가")
        elif noise_level < 0.2:  # 낮은 노이즈
            self.stt_timeout = 5
            self.max_retries = 1
            print("[설정] 🤫 조용한 환경 - 타임아웃 감소")
    
    def to_dict(self):
        return {
            "stt_timeout": self.stt_timeout,
            "stt_phrase_limit": self.stt_phrase_limit,
            "claude_timeout": self.claude_timeout,
            "tts_speed": self.tts_speed,
            "max_retries": self.max_retries,
        }

# 사용
config = VoiceConfig()
config.adjust_for_environment(noise_level=0.6)
```

---

## 📋 적용 체크리스트

### Phase 1: 안정성 (1주일)
- [ ] STT 재시도 로직 추가 (Snippet 1)
- [ ] 마이크 인덱스 관리 개선 (Snippet 2)
- [ ] Wake word 추출 개선 (Snippet 3)
- [ ] 테스트: 10회 연속 음성 인식 성공률 측정

### Phase 2: 설정화 (2주일)
- [ ] 동적 타임아웃 설정 (Snippet 4)
- [ ] config.py 생성 및 모듈화
- [ ] 로깅 시스템 구축
- [ ] 테스트: 다양한 환경에서 동작 확인

### Phase 3: 성능 최적화 (3주일)
- [ ] TTS 비동기 + 큐잉 구현
- [ ] Wake word LLM Intent 분류 추가 (선택사항)
- [ ] Echo detection 구현 (선택사항)
- [ ] 성능 프로파일링 및 병목 제거

---

## 🎓 참고한 우수 사례

| 기능 | 출처 | 특징 |
|------|------|------|
| 한국어 최적화 | gyeongseon-k/jarvis-ai | Fuzzy matching + RMS-VAD |
| TTS Fallback | JARVIS-ChatGPT | 3단계 폴백 체인 |
| Intent Classification | isair/jarvis | LLM 기반 wake word |
| Error Handling | error_handler.py (우리) | 4가지 결정 (retry/skip/replan/abort) |
| 타임아웃 계층 | isair/jarvis | 6단계 타임아웃 전략 |

---

## 🚀 다음 단계

1. **Snippet 1-4를 main.py에 통합** (이번 주)
2. **테스트 스크립트 작성** - 각 함수별 단위 테스트
3. **CI/CD 파이프라인 구축** - 자동 테스트 + 성능 측정
4. **사용자 피드백 수집** - 실제 환경에서 에러율 측정
5. **문서화** - 각 설정값의 의미와 조정 방법 기록

---

## 📚 참고 자료

### GitHub 프로젝트:
- https://github.com/gyeongseon-k/jarvis-ai (한국어 최적화)
- https://github.com/isair/jarvis (프라이빗 로컬 AI)
- https://github.com/gia-guar/JARVIS-ChatGPT (Fallback 패턴)

### 라이브러리 문서:
- SpeechRecognition: https://github.com/Uberi/speech_recognition
- Edge-TTS: https://github.com/rany2/edge-tts
- Faster-Whisper: https://github.com/SYSTRAN/faster-whisper

---

**작성일:** 2026-06-25 | **분석 대상:** 10개 JARVIS AI 프로젝트 | **추천 우선순위:** HIGH → MEDIUM → LOW
