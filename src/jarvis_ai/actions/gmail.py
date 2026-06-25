"""Gmail API actions with desktop OAuth and verifiable results."""

from __future__ import annotations

import base64
import os
import re
import webbrowser
from email.message import EmailMessage
from pathlib import Path

from ..paths import CONFIG_DIR


SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]
CREDENTIALS_PATH = CONFIG_DIR / "google_credentials.json"
TOKEN_PATH = CONFIG_DIR / "google_token.json"


def _google_modules():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        return Request, Credentials, InstalledAppFlow, build
    except ImportError:
        return None


def _setup_message() -> str:
    return (
        "Gmail 실제 연결이 아직 설정되지 않았습니다. Google Cloud에서 Gmail API를 "
        "활성화하고 데스크톱 OAuth 클라이언트 JSON을 내려받아 "
        f"'{CREDENTIALS_PATH}' 이름으로 저장한 뒤 다시 명령해주세요. "
        "그다음 브라우저에서 Google 권한을 한 번 승인하면 됩니다."
    )


def _service():
    modules = _google_modules()
    if not modules:
        raise RuntimeError(
            "Google Gmail 라이브러리가 없습니다. "
            "google-api-python-client, google-auth-httplib2, "
            "google-auth-oauthlib을 설치해주세요."
        )
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(_setup_message())

    Request, Credentials, InstalledAppFlow, build = modules
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except (ValueError, OSError):
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SCOPES,
            )
            creds = flow.run_local_server(port=0, open_browser=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _header(headers: list[dict], name: str) -> str:
    target = name.lower()
    for item in headers:
        if str(item.get("name", "")).lower() == target:
            return str(item.get("value", "")).strip()
    return ""


def _decode_body(payload: dict) -> str:
    def walk(part: dict) -> list[str]:
        texts: list[str] = []
        mime = str(part.get("mimeType") or "")
        data = ((part.get("body") or {}).get("data") or "")
        if data and mime in {"text/plain", "text/html"}:
            try:
                decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                text = decoded.decode("utf-8", errors="replace")
                if mime == "text/html":
                    text = re.sub(r"<[^>]+>", " ", text)
                texts.append(re.sub(r"\s+", " ", text).strip())
            except (ValueError, TypeError):
                pass
        for child in part.get("parts") or []:
            texts.extend(walk(child))
        return texts

    return "\n".join(text for text in walk(payload) if text)[:5000]


def _list_threads(service, query: str, max_results: int) -> list[dict]:
    response = (
        service.users()
        .threads()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return response.get("threads") or []


def _search(service, query: str, max_results: int = 5) -> str:
    threads = _list_threads(service, query or "in:inbox", max_results)
    if not threads:
        return "조건에 맞는 Gmail 메일을 찾지 못했습니다."
    lines = []
    for thread in threads:
        data = (
            service.users()
            .threads()
            .get(
                userId="me",
                id=thread["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        message = (data.get("messages") or [{}])[-1]
        headers = (message.get("payload") or {}).get("headers") or []
        lines.append(
            f"- {_header(headers, 'Date')} | {_header(headers, 'From')} | "
            f"{_header(headers, 'Subject') or '(제목 없음)'}"
        )
    return f"Gmail 검색 결과 {len(lines)}개입니다.\n" + "\n".join(lines)


def _read_latest(service, query: str) -> str:
    threads = _list_threads(service, query or "in:inbox", 1)
    if not threads:
        return "조건에 맞는 Gmail 메일을 찾지 못했습니다."
    data = (
        service.users()
        .threads()
        .get(userId="me", id=threads[0]["id"], format="full")
        .execute()
    )
    message = (data.get("messages") or [{}])[-1]
    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    body = _decode_body(payload) or str(message.get("snippet") or "")
    return (
        f"보낸 사람: {_header(headers, 'From')}\n"
        f"제목: {_header(headers, 'Subject') or '(제목 없음)'}\n"
        f"날짜: {_header(headers, 'Date')}\n"
        f"내용: {body[:3500]}"
    )


def _create_message(to: str, subject: str, body: str) -> dict:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject or "자비스에서 보낸 메일"
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return {"raw": raw}


def _create_draft(service, to: str, subject: str, body: str) -> str:
    result = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": _create_message(to, subject, body)})
        .execute()
    )
    draft_id = result.get("id")
    if not draft_id:
        raise RuntimeError("Gmail이 초안 ID를 반환하지 않았습니다.")
    return f"Gmail 초안을 만들었습니다. 수신자: {to}, 초안 ID: {draft_id}"


def _send(service, to: str, subject: str, body: str) -> str:
    result = (
        service.users()
        .messages()
        .send(userId="me", body=_create_message(to, subject, body))
        .execute()
    )
    message_id = result.get("id")
    thread_id = result.get("threadId")
    if not message_id:
        raise RuntimeError("Gmail이 발송 성공 ID를 반환하지 않았습니다.")
    return (
        f"Gmail 발송이 확인되었습니다. 수신자: {to}, "
        f"메시지 ID: {message_id}, 스레드 ID: {thread_id or '없음'}"
    )


def gmail_action(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """Search/read Gmail or create/send a message with API proof IDs."""
    params = parameters or {}
    action = str(params.get("action") or "").lower().strip()
    if action == "setup":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        webbrowser.open("https://developers.google.com/workspace/gmail/api/quickstart/python")
        try:
            if os.name == "nt":
                os.startfile(str(CONFIG_DIR))
        except OSError:
            pass
        return (
            "Gmail 공식 OAuth 설정 안내와 자비스 config 폴더를 열었습니다. "
            "데스크톱 앱 자격 증명을 내려받아 google_credentials.json으로 저장한 뒤 "
            "Gmail 명령을 다시 실행해주세요."
        )
    if action == "setup_status":
        if not CREDENTIALS_PATH.exists():
            return _setup_message()
        if TOKEN_PATH.exists():
            return "Gmail OAuth 연결 파일이 준비되어 있습니다."
        return "Gmail OAuth 자격 증명은 준비됐으며 첫 실행 시 Google 로그인이 필요합니다."

    try:
        service = _service()
        if action == "search":
            return _search(
                service,
                str(params.get("query") or "in:inbox"),
                max(1, min(int(params.get("max_results", 5)), 10)),
            )
        if action == "read_latest":
            return _read_latest(service, str(params.get("query") or "in:inbox"))
        if action in {"draft", "send"}:
            to = str(params.get("to") or params.get("receiver") or "").strip()
            subject = str(params.get("subject") or "자비스에서 보낸 메일").strip()
            body = str(params.get("body") or params.get("message") or "").strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
                return "정확한 수신자 이메일 주소가 필요합니다."
            if not body:
                return "메일 본문이 비어 있어 실행하지 않았습니다."
            if action == "draft":
                return _create_draft(service, to, subject, body)
            return _send(service, to, subject, body)
        return f"지원하지 않는 Gmail 작업입니다: {action or '(없음)'}"
    except FileNotFoundError as exc:
        return str(exc)
    except Exception as exc:
        print(f"[Gmail] 오류: {type(exc).__name__}: {exc}")
        return f"Gmail 작업에 실패했습니다: {str(exc)[:220]}"
