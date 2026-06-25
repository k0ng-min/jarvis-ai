"""
마이크에서 직접 음성을 녹음하고 인식
"""

import speech_recognition as sr
import soundfile as sf
import numpy as np
from scipy.io import wavfile
import time

print("="*70)
print("🎤 마이크 직접 테스트")
print("="*70)

# 설정
MIC_INDEX = 26  # 블루투스 이어폰
DURATION = 5  # 5초 녹음

print(f"\n📌 마이크 설정: 인덱스 {MIC_INDEX}")
print(f"⏱️ 녹음 시간: {DURATION}초")
print("\n준비되셨으면 엔터를 누르세요...")
input()

# 마이크에서 녹음
print("\n🔴 녹음 중...", end="", flush=True)
recognizer = sr.Recognizer()
recognizer.energy_threshold = 100
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.5

try:
    with sr.Microphone(device_index=MIC_INDEX) as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print(" 배경음 적응 완료")

        # 원(음량 표시)
        for i in range(DURATION):
            print(f"  {i+1}초 / {DURATION}초", end="\r", flush=True)
            time.sleep(1)

        print(f"\n🎙️ 음성 수신 중...")
        audio = recognizer.listen(source, timeout=DURATION+2, phrase_time_limit=DURATION+1)
        print("✅ 녹음 완료")

except Exception as e:
    print(f"\n❌ 마이크 오류: {e}")
    exit(1)

# 녹음 파일 저장
print("\n[저장] 녹음 파일 저장 중...")
try:
    audio_data = np.frombuffer(audio.get_wav_data(), dtype=np.int16)
    sample_rate = audio.sample_rate
    wavfile.write("mic_test_recording.wav", sample_rate, audio_data)
    print("✅ 저장 완료: mic_test_recording.wav")
except Exception as e:
    print(f"❌ 저장 실패: {e}")
    exit(1)

# STT 인식
print("\n[STT] Speech-to-Text 인식 중...")
try:
    print("🔍 Google Speech API 호출...", end="", flush=True)
    text = recognizer.recognize_google(audio, language="ko-KR")
    print(" ✅")
    print(f"📢 인식 결과: '{text}'")

except sr.UnknownValueError:
    print(" ❌ 음성 인식 불가")
    text = None
except sr.RequestError as e:
    print(f" ❌ API 오류: {e}")
    text = None
except Exception as e:
    print(f" ❌ 오류: {e}")
    text = None

# Wake word 감지
if text:
    print("\n[Wake Word] 감지 중...")
    from main import WakeWordDetector
    wake_word, command = WakeWordDetector.process(text)

    if wake_word:
        print(f"✅ Wake word 감지: '{wake_word}'")
        if command:
            print(f"📋 명령어: '{command}'")
        else:
            print("⚠️ 명령어 없음")
    else:
        print("❌ Wake word 감지 실패")

print("\n" + "="*70)
print("✅ 테스트 완료")
print("="*70)
