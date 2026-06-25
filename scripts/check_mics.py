"""
마이크 진단 스크립트
실행: python check_mics.py
"""
import sys, time

print("=" * 55)
print("  자비스 마이크 진단")
print("=" * 55)

# ── 1. pyaudio 확인 ──
print("\n[1] PyAudio 확인...")
try:
    import pyaudio
    print("  ✅ PyAudio 설치됨")
except ImportError:
    print("  ❌ PyAudio 없음 → pip install pyaudio")
    sys.exit(1)

# ── 2. 마이크 목록 ──
print("\n[2] 마이크 목록:")
import speech_recognition as sr
mics = sr.Microphone.list_microphone_names()
for i, name in enumerate(mics):
    tag = "  ◀ 현재 설정" if i == 2 else ""
    print(f"  [{i:2d}] {name}{tag}")

# ── 3. 마이크 실제 접근 테스트 ──
print("\n[3] 마이크 접근 테스트 (인덱스 2 — acro-probuds)...")
try:
    with sr.Microphone(device_index=2) as src:
        print("  ✅ 마이크 열기 성공")
except Exception as e:
    print(f"  ❌ 마이크 열기 실패: {e}")
    print("     → Windows 설정 > 개인 정보 보호 > 마이크 허용 확인 필요")
    sys.exit(1)

# ── 4. 실제 소리 감지 테스트 ──
print("\n[4] 소리 감지 테스트 (3초 동안 말해보세요)...")
recognizer = sr.Recognizer()
recognizer.energy_threshold = 200
recognizer.dynamic_energy_threshold = True
try:
    with sr.Microphone(device_index=2) as src:
        recognizer.adjust_for_ambient_noise(src, duration=0.5)
        print(f"  주변 소음 에너지: {int(recognizer.energy_threshold)}")
        print("  👂 3초 안에 말해보세요...")
        audio = recognizer.listen(src, timeout=4, phrase_time_limit=3)
        print("  ✅ 소리 감지됨!")
        try:
            text = recognizer.recognize_google(audio, language="ko-KR")
            print(f"  ✅ 인식 결과: '{text}'")
        except sr.UnknownValueError:
            print("  ⚠️  소리는 잡혔지만 텍스트 인식 실패 (노이즈이거나 너무 조용)")
except sr.WaitTimeoutError:
    print("  ❌ 소리 감지 안 됨 (마이크에 소리 입력 없음)")
    print("     → 블루투스 이어폰이 마이크 모드인지 확인")
    print("     → Windows 설정에서 기본 입력 장치가 acro-probuds인지 확인")
except Exception as e:
    print(f"  ❌ 오류: {e}")

print("\n[5] TTS 테스트...")
try:
    import asyncio, io, sounddevice as sd, soundfile as sf, edge_tts
    async def _tts():
        c = edge_tts.Communicate("마이크 테스트 완료입니다.", "ko-KR-SunHiNeural")
        buf = b""
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                buf += chunk["data"]
        data, sr_ = sf.read(io.BytesIO(buf))
        sd.play(data, sr_); sd.wait()
    asyncio.run(_tts())
    print("  ✅ TTS 정상 — 소리가 들렸으면 스피커/이어폰 출력도 정상")
except Exception as e:
    print(f"  ❌ TTS 오류: {e}")

print("\n진단 완료.")
