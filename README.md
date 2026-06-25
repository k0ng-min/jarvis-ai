# JARVIS AI

한국어 음성 명령과 Claude CLI를 결합한 데스크톱 AI 어시스턴트입니다.

## 주요 기능

- 한국어 음성 인식과 호출어 감지
- 마이크 음량에 반응하는 PyQt6 홀로그램 UI
- Claude Haiku 기반 설명, 추론, 복잡한 대화
- 인물·사건 질문은 Claude 기본 웹 검색으로 여러 출처를 조사하고 자체 검수
- Open-Meteo 실시간 날씨·대기질 조회
- 실시간 환율, 공휴일, 지진, 웹 검색
- 계산과 단위 변환
- 앱 실행, 컴퓨터 설정, 파일 및 브라우저 제어
- Gmail 실제 검색·읽기·초안·발송 및 로그인 유지 웹앱 제어
- 유튜브 영상 검색·재생·자막 기반 내용 분석
- PDF, DOCX, XLSX, CSV, PPTX 문서 읽기·요약·질의
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
python scripts/bootstrap.py
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

패키지 설치 후에는 아래 방식도 사용할 수 있습니다.

```bash
jarvis-ai
python -m jarvis_ai
```

실행 후 다음처럼 말할 수 있습니다.

- `자비스 안녕`
- `자비스 3일 뒤 서울 날씨 알려줘`
- `자비스 서울 미세먼지 어때`
- `자비스 100달러는 원으로 얼마야`
- `자비스 최근 주요 지진 알려줘`
- `자비스 지메일 안 읽은 메일 찾아줘`
- `자비스 지메일로 user@example.com에게 테스트 메일 보내줘`
- `자비스 구글 지도에서 서울역 찾아줘`
- `자비스 이 유튜브 영상 분석해줘 https://youtube.com/watch?v=...`
- `자비스 PDF 파일 요약해줘`
- `자비스 하늘이 파란 이유를 설명해줘`

## 테스트

```bash
python -m compileall -q src tests main.py
python scripts/run_test.py tests/integration/test_realtime_tools.py
python scripts/run_test.py tests/integration/test_claude_quality.py
```

`test_claude_quality.py`는 실제 Claude API 사용량이 발생할 수 있습니다.

## 프로젝트 구조

```text
src/jarvis_ai/     제품 코드
tests/integration/ 자동·통합 테스트
tests/manual/      마이크·UI 수동 테스트
scripts/           진단 및 개발 스크립트
docs/archive/      과거 분석 자료
config/            로컬 설정
memory/            로컬 장기 기억
```

## 설정 및 개인정보

최초 실행 시 `config/api_keys.json`과 `memory/long_term.json`이 로컬에 생성됩니다. 이 파일들은 개인 설정과 기억을 포함할 수 있어 Git에서 제외됩니다.

설정 형식은 [config/api_keys.example.json](config/api_keys.example.json)을 참고하세요.

### Gmail 연결

1. Google Cloud에서 Gmail API를 활성화합니다.
2. OAuth 동의 화면을 설정합니다.
3. OAuth 클라이언트 유형을 `데스크톱 앱`으로 생성합니다.
4. 내려받은 JSON을 `config/google_credentials.json`으로 저장합니다.
5. 자비스에서 Gmail 명령을 실행하고 열린 Google 로그인 화면에서 한 번 승인합니다.

승인 토큰은 `config/google_token.json`에, 웹앱 로그인 상태는
`config/browser_profile/`에 로컬 저장되며 모두 Git에서 제외됩니다.

Gmail 발송 성공은 Google API가 메시지 ID를 반환한 경우에만 확정합니다.
일반 웹앱 화면 자동화는 서비스 API 영수증이 없으면 성공을 단정하지 않습니다.

## 실시간 데이터 제공처

- [Open-Meteo](https://open-meteo.com/) — 날씨·대기질
- [Frankfurter](https://frankfurter.dev/) — 환율
- [Nager.Date](https://date.nager.at/) — 공휴일
- [USGS](https://earthquake.usgs.gov/) — 지진
- [MediaWiki API](https://www.mediawiki.org/wiki/API:REST_API) — 백과사전

## 주의

컴퓨터 제어 기능은 사용자 PC에서 실제 동작을 수행합니다. 신뢰할 수 있는 환경에서 사용하고, 중요한 명령은 실행 결과를 직접 확인하세요.

## 개발 브랜치 절차

기능 변경은 `main`에 직접 커밋하지 않습니다.

```bash
git switch main
git pull
git switch -c feature/기능명
# 구현 및 테스트
git push -u origin feature/기능명
```

테스트가 통과하고 실제 동작을 확인한 뒤에만 `main`으로 병합합니다.
