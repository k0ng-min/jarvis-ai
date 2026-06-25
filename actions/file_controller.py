# actions/file_controller.py — 자비스 파일/폴더 관리

import shutil
from pathlib import Path
from datetime import datetime

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False


def _resolve_path(raw: str) -> Path:
    shortcuts = {
        "desktop":   Path.home() / "Desktop",
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "pictures":  Path.home() / "Pictures",
        "music":     Path.home() / "Music",
        "videos":    Path.home() / "Videos",
        "home":      Path.home(),
        "바탕화면":  Path.home() / "Desktop",
        "다운로드":  Path.home() / "Downloads",
        "문서":      Path.home() / "Documents",
    }
    lower = raw.strip().lower()
    if lower in shortcuts:
        return shortcuts[lower]
    return Path(raw).expanduser()


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def list_files(path: str = "desktop") -> str:
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"경로를 찾을 수 없습니다: {target}"
        if not target.is_dir():
            return f"폴더가 아닙니다: {target}"
        items = []
        for item in sorted(target.iterdir()):
            if item.name.startswith("."): continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                items.append(f"📄 {item.name} ({_format_size(item.stat().st_size)})")
        if not items:
            return f"빈 폴더입니다: {target}"
        return f"{target.name}/ ({len(items)}개):\n" + "\n".join(items)
    except PermissionError:
        return f"권한이 없습니다: {path}"
    except Exception as e:
        return f"목록 오류: {e}"


def create_file(path: str, content: str = "") -> str:
    try:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"파일 생성: {target.name}"
    except Exception as e:
        return f"파일 생성 실패: {e}"


def create_folder(path: str) -> str:
    try:
        target = Path(path).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        return f"폴더 생성: {target}"
    except Exception as e:
        return f"폴더 생성 실패: {e}"


def delete_file(path: str) -> str:
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return f"찾을 수 없습니다: {path}"
        if _SEND2TRASH:
            send2trash.send2trash(str(target))
            return f"휴지통으로 이동: {target.name}"
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return f"삭제됨: {target.name}"
    except Exception as e:
        return f"삭제 실패: {e}"


def move_file(source: str, destination: str) -> str:
    try:
        src = Path(source).expanduser()
        dst = _resolve_path(destination)
        if not src.exists():
            return f"소스를 찾을 수 없습니다: {source}"
        if dst.is_dir():
            dst = dst / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"이동 완료: {src.name} → {dst.parent.name}/"
    except Exception as e:
        return f"이동 실패: {e}"


def copy_file(source: str, destination: str) -> str:
    try:
        src = Path(source).expanduser()
        dst = _resolve_path(destination)
        if not src.exists():
            return f"소스를 찾을 수 없습니다: {source}"
        if dst.is_dir():
            dst = dst / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        return f"복사 완료: {src.name} → {dst.parent.name}/"
    except Exception as e:
        return f"복사 실패: {e}"


def rename_file(path: str, new_name: str) -> str:
    try:
        target   = Path(path).expanduser()
        new_path = target.parent / new_name
        if not target.exists():
            return f"찾을 수 없습니다: {path}"
        if new_path.exists():
            return f"'{new_name}' 이름의 파일이 이미 존재합니다."
        target.rename(new_path)
        return f"이름 변경: {target.name} → {new_name}"
    except Exception as e:
        return f"이름 변경 실패: {e}"


def read_file(path: str, max_chars: int = 3000) -> str:
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return f"파일을 찾을 수 없습니다: {path}"
        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (총 {len(content)}자 중 일부)"
        return content
    except Exception as e:
        return f"읽기 실패: {e}"


def write_file(path: str, content: str, append: bool = False) -> str:
    try:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        return f"{'추가' if append else '작성'} 완료: {target.name}"
    except Exception as e:
        return f"쓰기 실패: {e}"


def find_files(name: str = "", extension: str = "", path: str = "home", max_results: int = 20) -> str:
    try:
        search_path = _resolve_path(path)
        if not search_path.exists():
            return f"검색 경로를 찾을 수 없습니다: {path}"
        results = []
        pattern = f"*{extension}" if extension else "*"
        for item in search_path.rglob(pattern):
            if item.is_file():
                if name and name.lower() not in item.name.lower(): continue
                results.append(f"📄 {item.name} ({_format_size(item.stat().st_size)}) — {item.parent}")
                if len(results) >= max_results: break
        if not results:
            return f"'{name or extension}'을(를) 찾지 못했습니다."
        return f"{len(results)}개 발견:\n" + "\n".join(results)
    except Exception as e:
        return f"검색 오류: {e}"


def get_largest_files(path: str = "home", count: int = 10) -> str:
    try:
        search_path = _resolve_path(path)
        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try: files.append((item.stat().st_size, item))
                except: pass
        files.sort(reverse=True)
        top = files[:count]
        if not top:
            return "파일을 찾지 못했습니다."
        lines = [f"가장 큰 파일 {len(top)}개:\n"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}")
        return "\n".join(lines)
    except Exception as e:
        return f"오류: {e}"


def get_disk_usage(path: str = "home") -> str:
    try:
        target = _resolve_path(path)
        usage  = shutil.disk_usage(target)
        pct    = usage.used / usage.total * 100
        return (
            f"디스크 사용량 ({target}):\n"
            f"  전체: {_format_size(usage.total)}\n"
            f"  사용: {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  여유: {_format_size(usage.free)}"
        )
    except Exception as e:
        return f"디스크 정보 오류: {e}"


def get_file_info(path: str) -> str:
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return f"찾을 수 없습니다: {path}"
        stat = target.stat()
        return (
            f"이름: {target.name}\n"
            f"종류: {'폴더' if target.is_dir() else '파일'}\n"
            f"크기: {_format_size(stat.st_size)}\n"
            f"위치: {target.parent}\n"
            f"생성: {datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M')}\n"
            f"수정: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')}"
        )
    except Exception as e:
        return f"파일 정보 오류: {e}"


def file_controller(parameters: dict, response=None, player=None, session_memory=None) -> str:
    action  = (parameters or {}).get("action", "").lower().strip()
    path    = (parameters or {}).get("path", "desktop")
    name    = (parameters or {}).get("name", "")
    content = (parameters or {}).get("content", "")

    def full_path():
        base = _resolve_path(path)
        return str(base / name) if name else str(base)

    result = "알 수 없는 액션입니다."
    try:
        match action:
            case "list":           result = list_files(path)
            case "create_file":    result = create_file(full_path(), content)
            case "create_folder":  result = create_folder(full_path())
            case "delete":         result = delete_file(full_path())
            case "move":           result = move_file(full_path(), parameters.get("destination", ""))
            case "copy":           result = copy_file(full_path(), parameters.get("destination", ""))
            case "rename":         result = rename_file(full_path(), parameters.get("new_name", ""))
            case "read":           result = read_file(full_path())
            case "write":          result = write_file(full_path(), content, parameters.get("append", False))
            case "find":           result = find_files(name, parameters.get("extension", ""), path)
            case "largest":        result = get_largest_files(path, parameters.get("count", 10))
            case "disk_usage":     result = get_disk_usage(path)
            case "info":           result = get_file_info(full_path())
            case _:                result = f"알 수 없는 액션: '{action}'"
    except Exception as e:
        result = f"파일 관리 오류: {e}"

    if player:
        player.write_log(f"[파일] {result[:60]}")
    return result
