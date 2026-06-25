# JARVIS AI

한국어 음성 명령과 Claude CLI를 결합한 데스크톱 AI 어시스턴트입니다.

## 주요 기능

- 한국어 음성 인식과 호출어 감지
- 마이크 음량에 반응하는 PyQt6 홀로그램 UI
- Claude Haiku 기반 설명, 추론, 복잡한 대화
- Open-Meteo 실시간 날씨·대기질 조회
- 실시간 환율, 공휴일, 지진, 웹 검색
- 계산과 단위 변환
- 앱 실행, 컴퓨터 설정, 파일 및 브라우저 제어
- Edge TTS 한국어 음성 답변

단순한 명령은 로컬 또는 전용 도구로 빠르게 처리하고, 설명과 추론이 필요한 질문만 Claude에 전달합니다.

## 요구 사항

- Python 3.10 이상
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- Windows 권장
- 마이크 및 인터넷 연결

## 설치

```bash
git clone https://github.com/k0ng-min/jarvis-ai.git
cd jarvis-ai
python setup.py
```

Claude CLI를 설치하고 로그인합니다.

```bash
npm install -g @anthropic-ai/claude-code
claude
```

## 실행

```bash
python main.py
```

실행 후 다음처럼 말할 수 있습니다.

- `자비스 안녕`
- `자비스 3일 뒤 서울 날씨 알려줘`
- `자비스 서울 미세먼지 어때`
- `자비스 100달러는 원으로 얼마야`
- `자비스 최근 주요 지진 알려줘`
- `자비스 하늘이 파란 이유를 설명해줘`

## 테스트

```bash
python -m py_compile main.py ui.py
python test_realtime_tools.py
python test_claude_quality.py
```

`test_claude_quality.py`는 실제 Claude API 사용량이 발생할 수 있습니다.

## 설정 및 개인정보

최초 실행 시 `config/api_keys.json`과 `memory/long_term.json`이 로컬에 생성됩니다. 이 파일들은 개인 설정과 기억을 포함할 수 있어 Git에서 제외됩니다.

설정 형식은 [config/api_keys.example.json](config/api_keys.example.json)을 참고하세요.

## 실시간 데이터 제공처

- [Open-Meteo](https://open-meteo.com/) — 날씨·대기질
- [Frankfurter](https://frankfurter.dev/) — 환율
- [Nager.Date](https://date.nager.at/) — 공휴일
- [USGS](https://earthquake.usgs.gov/) — 지진
- [MediaWiki API](https://www.mediawiki.org/wiki/API:REST_API) — 백과사전

## 주의

컴퓨터 제어 기능은 사용자 PC에서 실제 동작을 수행합니다. 신뢰할 수 있는 환경에서 사용하고, 중요한 명령은 실행 결과를 직접 확인하세요.

