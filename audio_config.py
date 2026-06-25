"""
다양한 오디오 입출력 장치 지원
- USB 마이크
- 3.5mm 마이크
- Bluetooth 마이크
- 기본 마이크
- 다양한 스피커
"""

import sounddevice as sd
import speech_recognition as sr

def list_audio_devices():
    """모든 오디오 장치 목록"""
    print("\n" + "="*60)
    print("🎤 이용 가능한 오디오 입출력 장치")
    print("="*60)

    devices = sd.query_devices()

    print("\n【 입력 장치 (마이크) 】")
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            mark = "👁️" if device['name'] == sd.default.device[0] else "  "
            print(f"  {mark} [{i}] {device['name']}")
            print(f"      채널: {device['max_input_channels']}개")

    print("\n【 출력 장치 (스피커) 】")
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:
            mark = "👁️" if device['name'] == sd.default.device[1] else "  "
            print(f"  {mark} [{i}] {device['name']}")
            print(f"      채널: {device['max_output_channels']}개")

    print("\n💡 자비스에서 사용할 장치를 선택하려면:")
    print("  main.py에서 MIC_INDEX와 SPEAKER_INDEX를 설정하세요\n")

def auto_detect_best_devices():
    """최고의 오디오 장치 자동 감지"""
    devices = sd.query_devices()

    best_mic = None
    best_speaker = None

    # 마이크 선택 우선순위: USB > Bluetooth > 기본
    priority_keywords = ["usb", "stereo", "bluetooth", "realtek", "high definition"]

    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            name_lower = device['name'].lower()
            for keyword in priority_keywords:
                if keyword in name_lower:
                    best_mic = i
                    break

    # 스피커 선택
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:
            name_lower = device['name'].lower()
            if "speakers" in name_lower or "line out" in name_lower:
                best_speaker = i
                break

    return best_mic, best_speaker

def test_audio():
    """오디오 입출력 테스트"""
    print("\n" + "="*60)
    print("🎵 오디오 장치 테스트")
    print("="*60)

    try:
        # 마이크 테스트
        print("\n🎤 마이크 테스트 (3초 녹음)...")
        rec = sr.Recognizer()
        with sr.Microphone() as source:
            print("   말해보세요...")
            audio = rec.listen(source, timeout=3)
            print("   ✅ 마이크 OK\n")
    except Exception as e:
        print(f"   ❌ 마이크 오류: {e}\n")

    try:
        # 스피커 테스트
        print("🔊 스피커 테스트 (소리 재생)...")
        import numpy as np

        # 1초 1000Hz 신호음
        sr = 44100
        duration = 1
        t = np.linspace(0, duration, sr * duration)
        signal = np.sin(2 * np.pi * 1000 * t) * 0.1

        sd.play(signal, sr)
        sd.wait()
        print("   ✅ 스피커 OK\n")
    except Exception as e:
        print(f"   ❌ 스피커 오류: {e}\n")

if __name__ == "__main__":
    print("\n자비스 오디오 설정 도우미\n")

    # 1. 장치 목록 표시
    list_audio_devices()

    # 2. 최고의 장치 자동 감지
    best_mic, best_speaker = auto_detect_best_devices()
    if best_mic is not None or best_speaker is not None:
        print(f"\n💡 추천 설정:")
        if best_mic is not None:
            print(f"   MIC_INDEX = {best_mic}")
        if best_speaker is not None:
            print(f"   SPEAKER_INDEX = {best_speaker}")

    # 3. 오디오 테스트
    input("\n엔터를 누르면 오디오 테스트를 시작합니다...")
    test_audio()

    print("✅ 설정이 완료되었습니다!")
