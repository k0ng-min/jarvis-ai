"""
자비스 메모리 매니저
장기 기억 저장/로드/업데이트 — Claude Code CLI 기반
"""

import json
import re
import subprocess
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200


def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {}
    }


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()

    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[메모리] ⚠️ 로드 오류: {e}")
            return _empty_memory()


def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    serialized = json.dumps(memory, ensure_ascii=False)
    if len(serialized) <= MEMORY_MAX_CHARS:
        return memory

    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))

    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[메모리] 🗑️  정리됨: {cat}/{key}")

    return memory


def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return

    memory = _trim_to_limit(memory)

    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue

        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            if isinstance(value, dict) and "value" in value:
                new_val = _truncate_value(str(value["value"]))
            else:
                new_val = _truncate_value(str(value))

            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True

    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[메모리] 💾 저장됨: {list(memory_update.keys())}")
    return memory


def _call_claude_for_memory(prompt: str, system: str, max_tokens: int = 10) -> str:
    """Claude Code CLI를 사용해 메모리 관련 판단"""
    full_prompt = f"[시스템]: {system}\n\n{prompt}"
    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8"
        )
        if result.returncode != 0:
            return ""
        data = json.loads(result.stdout.strip())
        return data.get("result", "").strip()
    except Exception as e:
        print(f"[메모리] ⚠️ Claude 호출 실패: {e}")
        return ""


def should_extract_memory(user_text: str, jarvis_text: str, api_key: str = "") -> bool:
    """대화에서 기억할 내용이 있는지 확인"""
    try:
        combined = f"사용자: {user_text[:300]}\n자비스: {jarvis_text[:500]}"

        result = _call_claude_for_memory(
            f"다음 대화에 기억할 개인 정보가 있나요?\n"
            f"(이름, 나이, 도시, 직업, 취미, 선호도, 관계, 프로젝트, 계획 등)\n\n"
            f"대화:\n{combined}\n\n"
            f"YES 또는 NO로만 답하세요.",
            system="메모리 관련성 확인. YES 또는 NO만 답하세요.",
            max_tokens=5
        )
        return "YES" in result.upper()

    except Exception as e:
        print(f"[메모리] ⚠️ 판단 실패: {e}")
        return False


def extract_memory(user_text: str, jarvis_text: str, api_key: str = "") -> dict:
    """대화에서 기억할 정보 추출"""
    try:
        combined = f"사용자: {user_text[:600]}\n자비스: {jarvis_text[:300]}"

        raw = _call_claude_for_memory(
            f"다음 대화에서 기억할 개인 정보를 추출하세요.\n"
            f"유효한 JSON만 반환하세요. 없으면 {{}} 반환.\n\n"
            f"카테고리:\n"
            f"  identity      → 이름, 나이, 생일, 도시, 직업, 학교, 국적\n"
            f"  preferences   → 좋아하는 것들 (음식, 색깔, 음악, 영화, 게임, 스포츠 등)\n"
            f"  projects      → 진행 중인 프로젝트, 목표, 아이디어\n"
            f"  relationships → 주변 사람들 (친구, 가족, 파트너, 동료)\n"
            f"  wishes        → 미래 계획, 사고 싶은 것, 여행 계획\n"
            f"  notes         → 기타 기억할 내용 (습관, 일정 등)\n\n"
            f"형식:\n"
            f'{{\"identity\":{{\"name\":{{\"value\":\"경민\"}}}},\n'
            f' \"preferences\":{{\"favorite_food\":{{\"value\":\"pizza\"}}}}}}\n\n'
            f"대화:\n{combined}\n\nJSON:",
            system="유효한 JSON만 반환. 마크다운, 추가 설명 없음.",
            max_tokens=1024
        )

        clean = raw.strip()
        clean = re.sub(r"```(?:json)?", "", clean).strip().rstrip("`").strip()

        if not clean or clean == "{}":
            return {}

        return json.loads(clean)

    except json.JSONDecodeError:
        return {}
    except Exception as e:
        if "429" not in str(e):
            print(f"[메모리] ⚠️ 추출 실패: {e}")
        return {}


def format_memory_for_prompt(memory: dict | None) -> str:
    """메모리를 프롬프트 텍스트로 변환"""
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("선호도:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("진행 중인 프로젝트/목표:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("주변 사람들:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("소원/계획/바람:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("기타 메모:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[사용자에 대해 알고 있는 정보 — 자연스럽게 활용하되, 목록처럼 읽지 마세요]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"


def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"기억했습니다: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"잊었습니다: {category}/{key}"
    return f"찾을 수 없습니다: {category}/{key}"


forget_memory = forget
