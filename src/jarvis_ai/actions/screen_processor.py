# actions/screen_processor.py — 자비스 화면/카메라 분석 (Claude CLI 기반)

import base64
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import mss
    import mss.tools
    _MSS_OK = True
except ImportError:
    _MSS_OK = False

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

try:
    import PIL.Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

IMG_MAX_W = 1280
IMG_MAX_H = 720
JPEG_Q    = 70


def _to_jpeg(img_bytes: bytes) -> bytes:
    if not _PIL_OK:
        return img_bytes
    img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_Q)
    return buf.getvalue()


def _capture_screenshot() -> bytes:
    if not _MSS_OK:
        raise RuntimeError("mss 모듈이 설치되지 않았습니다: pip install mss")
    with mss.mss() as sct:
        shot      = sct.grab(sct.monitors[1])
        png_bytes = mss.tools.to_png(shot.rgb, shot.size)
    return _to_jpeg(png_bytes)


def _capture_camera() -> bytes:
    if not _CV2_OK:
        raise RuntimeError("opencv-python이 설치되지 않았습니다: pip install opencv-python")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("카메라를 열 수 없습니다.")
    for _ in range(5):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise RuntimeError("카메라 프레임을 캡처할 수 없습니다.")
    if _PIL_OK:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_Q)
        return buf.getvalue()
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
    return buf.tobytes()


def _analyze_with_claude(image_bytes: bytes, user_text: str) -> str:
    """이미지를 임시 파일로 저장 후 Claude CLI로 분석"""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        prompt = (
            f"이 이미지를 분석해주세요. {user_text}\n"
            f"2~3문장으로 간결하게 한국어로 답변하세요."
        )
        # Claude CLI는 --image 플래그 또는 파일 경로를 지원합니다
        cmd = ["claude", "-p", prompt, "--output-format", "json"]

        # 이미지 파일 경로를 프롬프트에 포함
        prompt_with_img = f"[이미지 파일: {tmp_path}]\n\n{prompt}"
        cmd[2] = prompt_with_img

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, encoding="utf-8"
        )

        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
        else:
            print(f"[Screen] Claude 오류: {result.stderr[:200]}")
            return "화면을 분석하는 중 오류가 발생했습니다."

    except Exception as e:
        print(f"[Screen] ❌ 분석 실패: {e}")
        return f"분석 오류: {str(e)[:100]}"
    finally:
        try:
            import os
            os.unlink(tmp_path)
        except Exception:
            pass


def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> bool:
    user_text = (parameters or {}).get("text", "").strip()
    if not user_text:
        user_text = "화면에 무엇이 있나요?"

    angle = (parameters or {}).get("angle", "screen").lower().strip()
    print(f"[Screen] angle={angle!r}  text={user_text!r}")

    try:
        if angle == "camera":
            image_bytes = _capture_camera()
            print("[Screen] 📷 카메라 캡처 완료")
        else:
            image_bytes = _capture_screenshot()
            print("[Screen] 🖥️ 스크린샷 캡처 완료")
    except Exception as e:
        print(f"[Screen] ❌ 캡처 실패: {e}")
        if speak:
            speak(f"캡처에 실패했습니다: {str(e)[:80]}")
        return False

    print(f"[Screen] 📦 {len(image_bytes)} 바이트 → Claude 분석 중")

    def _run_analysis():
        result = _analyze_with_claude(image_bytes, user_text)
        print(f"[Screen] 💬 분석 결과: {result[:100]}")
        if player:
            player.write_log(f"자비스: {result[:120]}")
        if speak:
            speak(result)

    threading.Thread(target=_run_analysis, daemon=True).start()
    return True
