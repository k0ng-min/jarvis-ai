"""main.py 임포트 진단"""
import sys

steps = [
    ("asyncio, threading, time", "import asyncio, threading, time, json, subprocess, re, sys, io, traceback"),
    ("speech_recognition", "import speech_recognition as sr"),
    ("sounddevice/soundfile", "import sounddevice as sd; import soundfile as sf"),
    ("ui", "from ui import JarvisUI"),
    ("memory", "from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt"),
    ("file_processor", "from actions.file_processor import file_processor"),
    ("flight_finder", "from actions.flight_finder import flight_finder"),
    ("open_app", "from actions.open_app import open_app"),
    ("weather_report", "from actions.weather_report import weather_action"),
    ("send_message", "from actions.send_message import send_message"),
    ("reminder", "from actions.reminder import reminder"),
    ("computer_settings", "from actions.computer_settings import computer_settings"),
    ("screen_processor", "from actions.screen_processor import screen_process"),
    ("youtube_video", "from actions.youtube_video import youtube_video"),
    ("desktop", "from actions.desktop import desktop_control"),
    ("browser_control", "from actions.browser_control import browser_control"),
    ("file_controller", "from actions.file_controller import file_controller"),
    ("code_helper", "from actions.code_helper import code_helper"),
    ("dev_agent", "from actions.dev_agent import dev_agent"),
    ("web_search", "from actions.web_search import web_search as web_search_action"),
    ("computer_control", "from actions.computer_control import computer_control"),
    ("game_updater", "from actions.game_updater import game_updater"),
]

for name, stmt in steps:
    try:
        exec(stmt)
        print(f"  ✅ {name}")
    except Exception as e:
        print(f"  ❌ {name}: {e}")

print("\n모든 임포트 완료. 이제 TTS 테스트...")
import asyncio, io, sounddevice as sd, soundfile as sf

async def _tts():
    import edge_tts
    c = edge_tts.Communicate("헤이 자비스라고 불러주세요.", "ko-KR-SunHiNeural")
    buf = b""
    async for chunk in c.stream():
        if chunk["type"] == "audio":
            buf += chunk["data"]
    data, sr_ = sf.read(io.BytesIO(buf))
    sd.play(data, sr_); sd.wait()

print("TTS 재생 중...")
try:
    asyncio.run(_tts())
    print("✅ TTS 정상")
except Exception as e:
    print(f"❌ TTS 실패: {e}")
