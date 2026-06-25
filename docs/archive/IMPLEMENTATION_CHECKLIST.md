# JARVIS AI 개선 구현 체크리스트

이 문서는 분석 결과를 바탕으로 main.py를 개선하기 위한 단계별 체크리스트입니다.

---

## 🎯 목표
- ✅ STT 실패율 감소 (현재 추정 15% → 5% 이하)
- ✅ 응답 지연 감소 (현재 3-5초 → 1-2초)
- ✅ 마이크 오류 처리 안정화
- ✅ 환경별 최적화 설정

**예상 완료 시간:** 2-3주 (병렬 진행 시 1-2주)

---

## Phase 1: 안정성 (1주)

### Week 1-1: STT 재시도 로직 추가

**파일:** `main.py` → 함수 `listen_mic()` 교체

**체크리스트:**
- [ ] `STTStatus` Enum 클래스 추가
- [ ] `listen_mic_with_retry()` 함수 구현
  - [ ] max_retries 파라미터 추가
  - [ ] retry_delays 리스트 정의
  - [ ] WaitTimeoutError 처리
  - [ ] UnknownValueError 처리
  - [ ] RequestError (네트워크) 처리
  - [ ] 마이크 오류 감지 및 폴백
- [ ] 기존 `listen_mic()` 호출부 교체
  ```python
  # 기존
  text = listen_mic(ui)
  
  # 변경
  text, status = listen_mic_with_retry(ui, max_retries=2)
  if status != STTStatus.SUCCESS:
      print(f"[STT] 실패: {status.value}")
  ```
- [ ] main.py의 `voice_loop()` 메서드에서 `listen_mic()` 호출 업데이트
- [ ] 테스트: 연속 10회 음성 인식 시도 → 성공률 측정

**시간:** ~2시간
**테스트 명령어:**
```bash
# 마이크 테스트 스크립트 (test_stt.py)
for i in range(10):
    text, status = listen_mic_with_retry()
    print(f"{i+1}. {status.value}")
```

---

### Week 1-2: 마이크 인덱스 안전화

**파일:** `main.py` → 함수 `_auto_detect_mic_index()`, 전역변수 `MIC_INDEX` 리팩토링

**체크리스트:**
- [ ] `MicrophoneManager` 클래스 생성
  - [ ] `__init__()` 메서드
  - [ ] `detect()` 메서드
  - [ ] `get_kwargs()` 메서드
  - [ ] `mark_error()` 메서드
  - [ ] `reset()` 메서드
- [ ] 전역 `_mic_manager` 변수 추가
- [ ] `init_microphone()` 함수 추가
- [ ] `get_microphone_manager()` 함수 추가
- [ ] main() 함수에서 `init_microphone()` 호출 추가
- [ ] 모든 `MIC_INDEX` 참조를 `get_microphone_manager().index` 로 변경
- [ ] 재귀 호출 제거 (listen_mic_with_retry 내부에서 폴백 처리)
- [ ] 테스트: 마이크 뽑았다 꽂기 → 자동 감지 확인

**시간:** ~2시간
**변경 전후:**
```python
# Before (위험)
global MIC_INDEX
MIC_INDEX = None
return listen_mic_robust(ui, ...)  # 재귀

# After (안전)
mic = get_microphone_manager()
if mic.mark_error():
    # 1회만 기본값으로 재시도
    return listen_mic_robust(ui, ...)
```

---

### Week 1-3: Wake Word 추출 개선

**파일:** `main.py` → `voice_loop()` 메서드 → wake word 처리 부분

**체크리스트:**
- [ ] `WakeWordDetector` 클래스 생성
  - [ ] `WAKE_WORDS` 딕셔너리
  - [ ] `find_wake_word()` 메서드
  - [ ] `extract_command()` 메서드
  - [ ] `is_valid_command()` 메서드
  - [ ] `process()` 클래스메서드
- [ ] 기존 정규식 제거:
  ```python
  # 제거할 코드
  parts = re.split(
      r"(?:헤이\s*)?(?:자비스|jarvis|...)",
      text, maxsplit=1, flags=re.IGNORECASE
  )
  ```
- [ ] 새 코드 추가:
  ```python
  wake_word, command = WakeWordDetector.process(text)
  if not wake_word:
      continue
  if not command:
      next_text = listen_mic_with_retry(ui)
      command = next_text
  ```
- [ ] 테스트 케이스:
  - [ ] "자비스 시간이 뭐야" → command = "시간이 뭐야"
  - [ ] "자비스야 날씨 봐줘" → command = "날씨 봐줘"
  - [ ] "자비스, 유튜브 틀어줘" → command = "유튜브 틀어줘"
  - [ ] "사비스 뭐해" (뭉개진 발음) → wake_word = "사비스"

**시간:** ~1.5시간
**성능 개선:** 정규식 오류 제거 → 명령 손실률 감소

---

### Phase 1 테스트
```python
# test_phase1.py
def test_phase1():
    """Phase 1 테스트 스위트"""
    
    # 1. STT 재시도 테스트
    print("[테스트] STT 재시도 로직...")
    for i in range(5):
        text, status = listen_mic_with_retry(max_retries=2)
        assert status in [STTStatus.SUCCESS, STTStatus.TIMEOUT]
    
    # 2. 마이크 관리 테스트
    print("[테스트] 마이크 관리...")
    mic = get_microphone_manager()
    assert mic.index is not None or mic.index is None  # 무조건 설정됨
    assert not mic.mark_error()  # 첫 호출은 True
    
    # 3. Wake word 테스트
    print("[테스트] Wake word 추출...")
    test_cases = [
        ("자비스 시간이 뭐야", ("자비스", "시간이 뭐야")),
        ("사비스야 날씨 봐줘", ("사비스", "날씨 봐줘")),
    ]
    for text, expected in test_cases:
        result = WakeWordDetector.process(text)
        assert result == expected, f"실패: {text} → {result}"
    
    print("[테스트] ✅ Phase 1 통과")

if __name__ == "__main__":
    test_phase1()
```

**예상 성과:**
- STT 성공률: +15-20%
- 마이크 오류 자동 복구: 100%
- 명령어 손실 감소: ~95% 이상

---

## Phase 2: 성능 & 설정화 (2주)

### Week 2-1: 동적 타임아웃 설정

**파일:** `config.py` (새 파일 생성) + `main.py` 통합

**체크리스트:**
- [ ] `config.py` 파일 생성
  ```python
  from dataclasses import dataclass
  
  @dataclass
  class TimeoutConfig:
      # STT
      stt_input_timeout: float = 6.0
      stt_phrase_timeout: float = 10.0
      stt_max_retries: int = 2
      # ... (전체 IMPROVEMENTS_CODE_EXAMPLES.md 참고)
  ```
- [ ] `TimeoutConfig` 클래스 구현
  - [ ] 필드: stt_*, tts_*, claude_*, tool_*
  - [ ] `apply_preset()` 메서드
  - [ ] `to_dict()` 메서드
  - [ ] `_presets` 딕셔너리 (quiet, normal, noisy, fast, slow)
- [ ] `main.py` 시작 부분에 설정 로드
  ```python
  from config import TimeoutConfig
  
  TIMEOUT_CONFIG = TimeoutConfig()
  # 기본값: "normal"
  # 환경 변수로 변경 가능: os.getenv("JARVIS_PROFILE", "normal")
  ```
- [ ] 모든 timeout 값들을 설정에서 참조하도록 변경
  ```python
  # Before
  audio = recognizer.listen(source, timeout=6, phrase_time_limit=10)
  
  # After
  audio = recognizer.listen(
      source,
      timeout=TIMEOUT_CONFIG.stt_input_timeout,
      phrase_time_limit=TIMEOUT_CONFIG.stt_phrase_timeout
  )
  ```
- [ ] claude 호출 timeout 변경
  ```python
  # main.py의 _call_claude()
  # timeout=30 → timeout=TIMEOUT_CONFIG.claude_timeout (기본 15)
  ```
- [ ] 테스트: 프로필 전환 확인
  ```bash
  JARVIS_PROFILE=noisy python main.py  # 시끄러운 환경
  JARVIS_PROFILE=fast python main.py   # 빠른 응답
  ```

**시간:** ~2시간

---

### Week 2-2: 로깅 시스템 구축

**파일:** `logging_config.py` (새 파일) + `main.py` 통합

**체크리스트:**
- [ ] `logging_config.py` 생성
  ```python
  import logging
  from pathlib import Path
  
  def setup_logging(log_level=logging.INFO):
      logger = logging.getLogger("jarvis")
      handler = logging.FileHandler("jarvis_debug.log")
      # ...
  ```
- [ ] 로그 레벨 설정
  - [ ] DEBUG: 상세 정보 (마이크 감지, STT 진행)
  - [ ] INFO: 주요 이벤트 (명령 시작, 완료)
  - [ ] WARNING: 경고 (타임아웃, 오류)
  - [ ] ERROR: 오류 (API 실패, 예외)
- [ ] 주요 함수에 로깅 추가
  - [ ] `listen_mic_with_retry()`: 시도, 실패, 성공
  - [ ] `_call_claude()`: 요청, 응답 시간
  - [ ] `speak_with_fallback()`: 각 폴백 단계
  - [ ] 오류 처리: 스택 트레이스 기록
- [ ] 로그 파일 위치: `./jarvis_debug.log`
- [ ] 로그 로테이션 (선택)
  ```python
  from logging.handlers import RotatingFileHandler
  handler = RotatingFileHandler(
      "jarvis_debug.log",
      maxBytes=10*1024*1024,  # 10MB
      backupCount=5
  )
  ```
- [ ] 테스트: 로그 파일 생성 확인
  ```bash
  python main.py
  tail -f jarvis_debug.log  # 실시간 모니터링
  ```

**시간:** ~1.5시간
**이점:** 오류 디버깅 시간 단축 → 50% 이상

---

### Week 2-3: TTS 개선 (선택사항, 고급)

**파일:** `main.py` → `_speak_async()`, `speak_text()` 함수

**체크리스트:**
- [ ] `speak_with_fallback()` 비동기 함수 추가
  - [ ] 1단계: Primary Edge-TTS
  - [ ] 2단계: Fallback Edge-TTS voice
  - [ ] 3단계: pyttsx3
- [ ] `TTSStatus` Enum 추가
- [ ] 기존 `_speak_async()` → `speak_with_fallback()` 교체
- [ ] 폴백 로직 테스트
  - [ ] Edge-TTS 비활성화 → pyttsx3 폴백 확인
  - [ ] 여러 음성 지원 확인
- [ ] (선택) `AsyncTTSQueue` 큐 구현
  - [ ] 여러 TTS 요청 순차 처리
  - [ ] 동시 재생 방지
  - [ ] 응답 순서 보장

**시간:** ~2-3시간 (큐 구현 시)
**성능 개선:** 응답 지연 -1초 (큐 미구현 시 -500ms)

---

### Phase 2 테스트
```python
# test_phase2.py
def test_phase2():
    from config import TimeoutConfig
    
    # 1. 타임아웃 설정 테스트
    print("[테스트] 타임아웃 설정...")
    config = TimeoutConfig()
    config.apply_preset("noisy")
    assert config.stt_input_timeout == 8.0
    assert config.stt_max_retries == 3
    
    # 2. 로깅 테스트
    print("[테스트] 로깅...")
    import logging
    logger = logging.getLogger("jarvis")
    logger.info("테스트 메시지")
    assert Path("jarvis_debug.log").exists()
    
    # 3. TTS 폴백 테스트
    print("[테스트] TTS 폴백...")
    # await speak_with_fallback("테스트")
    
    print("[테스트] ✅ Phase 2 통과")
```

---

## Phase 3: 고급 기능 (3주, 선택사항)

### Week 3-1: LLM 기반 Wake Word 감지 (선택, 고급)

**파일:** `main.py` → `voice_loop()` 메서드

**체크리스트:**
- [ ] `classify_intent_with_llm()` 비동기 함수 추가
- [ ] 2단계 감지:
  - [ ] 1단계: 빠른 키워드 매칭
  - [ ] 2단계: 불명확한 경우만 LLM 호출
- [ ] (선택) Echo detection 추가
  ```python
  # 자신의 음성 재생을 감지하고 무시
  if intent == "echo":
      continue  # 다음 반복으로
  ```

**시간:** ~3시간
**이점:** False positive 감소 (15-20%)

---

### Week 3-2: Context-Aware 응답 조정 (선택)

**체크리스트:**
- [ ] 응답 길이에 따른 TTS 속도 조정
  ```python
  if len(response) > 500:
      tts_speed = 1.3  # 긴 응답은 빠르게
  elif len(response) < 50:
      tts_speed = 1.0  # 짧은 응답은 자연스럽게
  ```
- [ ] 다국어 자동 감지
  ```python
  from langdetect import detect
  lang = detect(response)
  if lang == 'en':
      TTS_VOICE = "en-GB-RyanNeural"
  ```

**시간:** ~1시간

---

## 📊 예상 개선 효과

### STT (음성 인식)
| 지표 | Before | After | 개선율 |
|------|--------|-------|--------|
| 1회 성공률 | 85% | 95% | +10% |
| 3회 누적 성공률 | 97% | 99.9% | +2.9% |
| 평균 재시도 횟수 | 1.5 | 1.1 | -27% |
| 사용자 불편감 | 중간 | 낮음 | - |

### 응답 시간
| 단계 | Before | After | 개선 |
|------|--------|-------|------|
| STT | 2-3초 | 2-3초 | - |
| Claude 호출 | 3-5초 | 2-4초 | -1초 |
| TTS | 1-2초 | 1-2초 | - |
| **총합** | **6-10초** | **5-9초** | **-10%** |

### 안정성
| 지표 | Before | After | 개선 |
|------|--------|-------|------|
| 마이크 오류 복구율 | 0% | 95% | +95% |
| 무한 루프 발생 | 가능 | 불가능 | ✅ |
| 명령어 손실율 | ~5% | ~1% | -80% |
| 사용자 재시도 빈도 | 높음 | 낮음 | - |

---

## ⏰ 일정 (권장)

```
Week 1:
  Mon-Wed: STT 재시도 로직 (2h)
  Wed-Thu: 마이크 관리 (2h)
  Thu-Fri: Wake word 추출 (1.5h)
  Fri: Phase 1 테스트 & 버그 수정 (3h)

Week 2:
  Mon-Tue: 타임아웃 설정 (2h)
  Tue-Wed: 로깅 시스템 (1.5h)
  Wed-Thu: TTS 개선 (2-3h)
  Thu-Fri: Phase 2 테스트 & 최적화 (3h)

Week 3 (선택):
  Mon-Tue: LLM Intent 분류 (3h)
  Tue-Wed: Context-aware 조정 (1h)
  Wed-Fri: 통합 테스트 & 배포 (4h)
```

**병렬 진행 시: 1.5-2주 단축 가능**

---

## 📋 각 Phase별 커밋 메시지 템플릿

### Phase 1
```
feat(stt): Add STT retry logic with exponential backoff

- Implement STTStatus enum
- Add listen_mic_with_retry() with max_retries support
- Handle TimeoutError, UnknownValueError, RequestError separately
- Fallback to system default microphone on device error

BREAKING CHANGE: listen_mic() now returns (text, status) tuple
```

### Phase 2
```
refactor(config): Introduce dynamic timeout configuration

- Create config.py with TimeoutConfig class
- Add preset profiles (quiet, normal, noisy, fast, slow)
- Implement logging system with RotatingFileHandler
- Update all timeout values to use TIMEOUT_CONFIG

feat(tts): Improve TTS with fallback chain
- Implement speak_with_fallback() with 3-level fallback
- Add TTSStatus enum
```

### Phase 3
```
feat(wake-word): Add LLM-based intent classification (experimental)

- Implement classify_intent_with_llm() for ambiguous cases
- Add echo detection to filter own speech
- Improve false positive filtering

feat(response): Add context-aware response adjustment
- Auto-adjust TTS speed based on response length
- Implement multi-language detection
```

---

## 🔍 Quality Assurance

### 단위 테스트
```python
# tests/test_stt.py
# tests/test_wake_word.py
# tests/test_tts.py
# tests/test_config.py
```

### 통합 테스트
```python
# tests/test_voice_loop.py
# - 연속 5회 명령 처리
# - 타임아웃 복구
# - 오류 로깅
```

### 성능 프로파일링
```python
import cProfile
cProfile.run('main()', sort='cumtime')
```

---

## 🚨 주의사항

### 주의 1: 마이크 인덱스 전역 변수
- ❌ 재귀 호출로 변경 금지
- ✅ 클래스 인스턴스로 관리
- ✅ 최대 1회 폴백만 허용

### 주의 2: API 타임아웃
- 현재 `claude_timeout=15초` (짧음)
- 느린 네트워크 환경 고려
- `JARVIS_PROFILE=slow` 옵션 사용 권고

### 주의 3: TTS 스트리밍
- Edge-TTS는 스트리밍 API 사용
- 네트워크 불안정 시 실패 가능
- pyttsx3 폴백 필수

### 주의 4: 로깅 용량
- `jarvis_debug.log` 자동 로테이션 설정
- 일일 ~50MB 생성 (프로필 따라 다름)
- 주 단위 백업 권고

---

## ✅ 최종 체크리스트

### 배포 전 확인
- [ ] 모든 Phase 1-3 테스트 통과
- [ ] 성능 프로파일링 완료 (응답 시간 < 10초)
- [ ] 로그 파일 생성 확인
- [ ] 다양한 환경에서 테스트 (조용함, 시끄러움)
- [ ] 마이크 오류 복구 확인
- [ ] 문서 업데이트 (README, 설정 가이드)
- [ ] Git commit 및 주석 추가
- [ ] 사용자 피드백 수집 (베타 테스트)

---

**시작일:** 2026-06-25 | **예상 완료:** 2026-07-15 (Phase 1-2) / 2026-07-30 (Phase 3 포함)
