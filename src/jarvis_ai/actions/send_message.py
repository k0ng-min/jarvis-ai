# actions/send_message.py — 자비스 메시지 전송

import time
import pyautogui
import webbrowser
from urllib.parse import quote_plus

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08


def _open_app(app_name: str) -> bool:
    try:
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(2.0)
        return True
    except Exception as e:
        print(f"[SendMessage] {app_name} 열기 실패: {e}")
        return False


def _send_whatsapp(receiver: str, message: str) -> str:
    try:
        if not _open_app("WhatsApp"):
            return "WhatsApp을 열 수 없습니다."
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)
        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"{receiver}에게 WhatsApp 메시지를 보냈습니다."
    except Exception as e:
        return f"WhatsApp 오류: {e}"


def _send_telegram(receiver: str, message: str) -> str:
    try:
        if not _open_app("Telegram"):
            return "Telegram을 열 수 없습니다."
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)
        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"{receiver}에게 Telegram 메시지를 보냈습니다."
    except Exception as e:
        return f"Telegram 오류: {e}"


def _send_instagram(receiver: str, message: str) -> str:
    try:
        webbrowser.open("https://www.instagram.com/direct/new/")
        time.sleep(3.5)
        pyautogui.write(receiver, interval=0.05)
        time.sleep(1.5)
        pyautogui.press("down")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)
        for _ in range(3):
            pyautogui.press("tab")
            time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(1.5)
        pyautogui.write(message, interval=0.04)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"{receiver}에게 Instagram DM을 보냈습니다."
    except Exception as e:
        return f"Instagram 오류: {e}"


def _send_generic(platform: str, receiver: str, message: str) -> str:
    try:
        if not _open_app(platform):
            return f"{platform}을(를) 열 수 없습니다."
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)
        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"{receiver}에게 {platform} 메시지를 보냈습니다."
    except Exception as e:
        return f"{platform} 오류: {e}"


def send_message(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params       = parameters or {}
    receiver     = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform     = params.get("platform", "whatsapp").strip().lower()

    if not receiver:
        return "메시지를 보낼 상대방을 알려주세요."
    if not message_text:
        return "어떤 메시지를 보낼지 알려주세요."

    print(f"[SendMessage] 📨 {platform} → {receiver}: {message_text[:40]}")
    if player:
        player.write_log(f"[메시지] {receiver}에게 전송 중...")

    if "whatsapp" in platform or "wp" in platform:
        return _send_whatsapp(receiver, message_text)
    elif "telegram" in platform or "tg" in platform:
        return _send_telegram(receiver, message_text)
    elif "instagram" in platform or "ig" in platform or "insta" in platform:
        return _send_instagram(receiver, message_text)
    else:
        return _send_generic(platform, receiver, message_text)
