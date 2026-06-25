"""자비스 설정 모듈"""
import platform

def get_os() -> str:
    return platform.system()

def is_windows() -> bool:
    return platform.system() == "Windows"

def is_mac() -> bool:
    return platform.system() == "Darwin"

def is_linux() -> bool:
    return platform.system() == "Linux"
