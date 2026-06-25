from __future__ import annotations

import json
import html
import math
import os
import platform
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal, QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QKeySequence,
    QPainter, QPen, QPixmap, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)

from .paths import CONFIG_DIR, PACKAGE_DIR

BASE_DIR   = PACKAGE_DIR
API_FILE   = CONFIG_DIR / "api_keys.json"

_OS = platform.system()


class C:
    BG       = "#00060a"
    PANEL    = "#010d14"
    PANEL2   = "#010f18"
    BORDER   = "#0d3347"
    BORDER_B = "#1a5c7a"
    BORDER_A = "#0f4060"
    PRI      = "#00d4ff"
    PRI_DIM  = "#007a99"
    PRI_GHO  = "#001f2e"
    ACC      = "#ff6b00"
    ACC2     = "#ffcc00"
    GREEN    = "#00ff88"
    RED      = "#ff3355"
    MUTED_C  = "#ff3366"
    TEXT     = "#8ffcff"
    TEXT_DIM = "#3a8a9a"
    TEXT_MED = "#5ab8cc"
    WHITE    = "#d8f8ff"
    DARK     = "#000d14"
    BAR_BG   = "#011520"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ─── 시스템 메트릭 수집 ───────────────────────────────────────────────────────

class _SysMetrics:
    def __init__(self):
        self.cpu = self.mem = self.net = 0.0
        self.gpu = self.tmp = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        net = ((nc.bytes_sent - self._last_net.bytes_sent) +
               (nc.bytes_recv - self._last_net.bytes_recv)) / max(dt, 0.001) / (1024*1024)
        self._last_net = nc; self._last_net_t = now
        gpu = self._get_gpu()
        tmp = self._get_temp()
        with self._lock:
            self.cpu = cpu; self.mem = mem; self.net = net
            self.gpu = gpu; self.tmp = tmp

    def _get_gpu(self) -> float:
        try:
            r = subprocess.run(
                ["nvidia-smi","--query-gpu=utilization.gpu","--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals: return sum(vals)/len(vals)
        except Exception: pass
        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp","k10temp","cpu_thermal","acpitz"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
        except Exception: pass
        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell","-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    return float(r.stdout.strip().split("\n")[0]) / 10.0 - 273.15
            except Exception: pass
        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {"cpu": self.cpu, "mem": self.mem, "net": self.net,
                    "gpu": self.gpu, "tmp": self.tmp}


_metrics = _SysMetrics()


# ─── HUD 캔버스 (홀로그램 애니메이션) ────────────────────────────────────────

class HudCanvas(QWidget):
    def __init__(self, face_path: str = "", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted   = False
        self.speaking = False
        self.state   = "초기화 중"
        self.mic_level = 0.0
        self._mic_level_smoothed = 0.0
        self._last_mic_level_at = 0.0

        # ── 상태별 색상 팔레트 ──
        # (primary_hex, glow_r, glow_g, glow_b)
        self._PALETTES = {
            "듣는 중":   ("#ffffff", 255, 255, 255),  # 흰색 (기본)
            "말하는 중": ("#3399ff", 0,   100, 255),  # 파란색
            "생각 중":   ("#9900ff", 153,  0,  255),  # 보라색 (더 눈에 띄게)
            "처리 중":   ("#ff2244", 255,  20,  40),  # 빨간색
            "THINKING":  ("#9900ff", 153,  0,  255),  # 보라색
            "SPEAKING":  ("#3399ff", 0,   100, 255),
            "LISTENING": ("#ffffff", 255, 255, 255),
            "음소거":    ("#cc2266", 200,  10,  80),  # 자주/분홍
            "초기화 중": ("#aaaaaa", 170, 170, 170),  # 회색
        }
        self._cur_pal  = self._PALETTES["초기화 중"]
        self._tgt_pal  = self._cur_pal
        self._pal_r    = float(self._cur_pal[1])
        self._pal_g    = float(self._cur_pal[2])
        self._pal_b    = float(self._cur_pal[3])

        self._tick = 0
        self._scale = 1.0; self._tgt_scale = 1.0
        self._halo  = 55.0; self._tgt_halo  = 55.0
        self._last_t = time.time()
        self._scan  = 0.0;  self._scan2 = 180.0
        self._rings = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink = True; self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        if face_path: self._load_face(face_path)

        # 볼류메트릭 구형 파티클 (내부까지 꽉 찬 점구름)
        rng = random.Random(7)
        self._vol_pts: list[tuple[float, float, float, float]] = []  # x,y,z,edge
        while len(self._vol_pts) < 1600:
            x = rng.uniform(-1, 1)
            y = rng.uniform(-1, 1)
            z = rng.uniform(-1, 1)
            d2 = x*x + y*y + z*z
            if d2 <= 1.0:
                # edge: 표면에 가까울수록 1 (밝음), 중심은 0 (어두움)
                self._vol_pts.append((x, y, z, d2))
        self._vol_rot = 0.0   # Y축 회전각

        # 홀로그램 텍스트 (음성 대화 표시)
        self._hud_user   = ""
        self._hud_jarvis = ""
        self._usr_alpha  = 0.0
        self._jrv_alpha  = 0.0
        self._usr_hold   = 0
        self._jrv_hold   = 0

        tmr = QTimer(self); tmr.timeout.connect(self._step); tmr.start(16)

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz-2, sz-2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO(); img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        # Breathing pulse: 사인파 기반 규칙적 맥동 + 상태별 변조
        breath = math.sin(self._tick * 0.018) * 0.5 + 0.5   # 0~1
        if self.speaking:
            self._tgt_scale = 1.06 + breath * 0.14           # 1.06~1.20
            self._tgt_halo  = 160.0 + breath * 50.0
        elif self.muted:
            self._tgt_scale = 0.88 + breath * 0.06
            self._tgt_halo  = 18.0 + breath * 10.0
        elif self.state == "듣는 중":
            # 입력이 끊기면 빠르게 원래 크기로 돌아오고, 목소리에는 부드럽게 반응한다.
            if now - self._last_mic_level_at > 0.18:
                self.mic_level = 0.0
            smoothing = 0.48 if self.mic_level > self._mic_level_smoothed else 0.20
            self._mic_level_smoothed += (
                self.mic_level - self._mic_level_smoothed
            ) * smoothing
            voice = self._mic_level_smoothed
            # 실제 발화 음량이 중심 구체의 확대·수축에 직접 반영된다.
            voice_flutter = math.sin(self._tick * 0.22) * voice * 0.035
            self._tgt_scale = min(
                1.80,
                0.95 + breath * 0.05 + voice * 0.80 + voice_flutter,
            )
            self._tgt_halo = 70.0 + breath * 22.0 + voice * 205.0
        elif self.state in ("생각 중", "처리 중"):
            # 분석 중에는 크기 변화보다 정밀한 맥동과 궤도 회전을 강조한다.
            analysis_wave = math.sin(self._tick * 0.055) * 0.5 + 0.5
            self._tgt_scale = 0.98 + analysis_wave * 0.055
            self._tgt_halo = 105.0 + analysis_wave * 42.0
        else:
            self._tgt_scale = 0.96 + breath * 0.10           # 0.96~1.06
            self._tgt_halo  = 80.0 + breath * 30.0
        sp = 0.12 if self.speaking else 0.06
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp
        # 상태별 색상 팔레트 부드럽게 전환
        want = self._PALETTES.get(self.state, self._PALETTES["듣는 중"])
        tr, tg, tb = float(want[1]), float(want[2]), float(want[3])
        spd_c = 0.06
        self._pal_r += (tr - self._pal_r) * spd_c
        self._pal_g += (tg - self._pal_g) * spd_c
        self._pal_b += (tb - self._pal_b) * spd_c

        if self.speaking:
            speeds = [1.3, -0.9, 2.0]
        elif self.state in ("생각 중", "처리 중"):
            speeds = [2.5, -1.9, 3.3]
        elif self.state == "듣는 중" and self._mic_level_smoothed > 0.06:
            speeds = [1.0, -0.7, 1.55]
        else:
            speeds = [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360
        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360
        fw  = min(self.width(), self.height())
        lim = fw * 0.74; spd2 = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd2 for r in self._pulses if r + spd2 < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)
        if self.speaking and random.random() < 0.28:
            cx, cy = self.width()/2, self.height()/2
            ang = random.uniform(0, 2*math.pi); r_s = fw * 0.28
            self._particles.append([cx + math.cos(ang)*r_s, cy + math.sin(ang)*r_s,
                                     math.cos(ang)*random.uniform(0.9,2.4),
                                     math.sin(ang)*random.uniform(0.9,2.4)-0.4, 1.0])
        self._particles = [[p[0]+p[2],p[1]+p[3],p[2]*0.97,p[3]*0.97,p[4]-0.028]
                           for p in self._particles if p[4] > 0]
        # 볼류메트릭 구체 회전
        self._vol_rot = (self._vol_rot + (0.012 if self.speaking else 0.004)) % (2 * math.pi)
        # 홀로그램 텍스트 페이드
        if self._usr_hold > 0:
            self._usr_alpha = min(185, self._usr_alpha + 14); self._usr_hold -= 1
        else:
            self._usr_alpha = max(0, self._usr_alpha - 4)
        if self._jrv_hold > 0:
            self._jrv_alpha = min(235, self._jrv_alpha + 11); self._jrv_hold -= 1
        else:
            self._jrv_alpha = max(0, self._jrv_alpha - 3)
        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink; self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # 현재 상태 색
        r = max(0, min(255, int(self._pal_r)))
        g = max(0, min(255, int(self._pal_g)))
        b = max(0, min(255, int(self._pal_b)))
        halo = self._halo
        def pc(a=255): return QColor(r, g, b, max(0, min(255, int(a))))
        def pw(a=255): # 흰색 ~ 현재색 혼합
            wr = int(r + (255-r)*0.3); wg = int(g + (255-g)*0.3); wb = int(b + (255-b)*0.3)
            return QColor(wr, wg, wb, max(0, min(255, int(a))))

        # ── 볼류메트릭 구체 (항상 흰색·선명) ──
        sph_r = fw * 0.26 * self._scale
        cos_r = math.cos(self._vol_rot)
        sin_r = math.sin(self._vol_rot)

        rendered: list[tuple[float,float,float,float,float]] = []
        for x, y, z, d2 in self._vol_pts:
            rx = x * cos_r + z * sin_r
            rz = -x * sin_r + z * cos_r
            sx = cx + rx * sph_r
            sy = cy - y  * sph_r
            depth  = (rz + 1) * 0.5
            edge   = d2
            # 표면 집중 + 앞면 강조
            bright = edge ** 0.45 * 0.78 + depth * 0.22
            alpha  = max(0, min(255, int(halo * bright ** 0.42)))
            sz = 0.5 + bright * 2.8
            rendered.append((rz, sx, sy, sz, alpha))

        rendered.sort(key=lambda d: d[0])
        p.setPen(Qt.PenStyle.NoPen)
        for _, sx, sy, sz, alpha in rendered:
            # 답변 중에는 점 구체 자체가 밝은 파랑으로 전환된다.
            if self.speaking:
                point_color = QColor(80, 190, 255, alpha)
            else:
                point_color = QColor(255, 255, 255, alpha)
            p.setBrush(QBrush(point_color))
            p.drawEllipse(QPointF(sx, sy), sz, sz)

        # ── glow halo (구체 뒤 은은한 빛) ──
        from PyQt6.QtGui import QRadialGradient
        glow_r = sph_r * 1.35
        grad = QRadialGradient(cx, cy, glow_r)
        if self.speaking:
            grad.setColorAt(0.0, QColor(45, 165, 255, min(90, int(halo * 0.42))))
            grad.setColorAt(0.55, QColor(20, 100, 255, min(40, int(halo * 0.20))))
        else:
            grad.setColorAt(0.0, QColor(255, 255, 255, min(60, int(halo * 0.35))))
            grad.setColorAt(0.55, QColor(200, 220, 255, min(25, int(halo * 0.14))))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # ── 말할 때 파티클 폭발 효과 ──
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(pw(a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.0, 2.0)

        # ── 생각/처리 중: 교차하는 분석 궤도 ──
        if self.state in ("생각 중", "처리 중"):
            orbit_color = QColor(r, g, b, 150)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.save()
            p.translate(cx, cy)
            for i, angle in enumerate((self._scan, self._scan2, self._rings[2])):
                p.save()
                p.rotate(angle + i * 60)
                p.setPen(QPen(orbit_color, 1.2 if i < 2 else 0.8))
                orbit_w = sph_r * (2.45 + i * 0.20)
                orbit_h = sph_r * (0.72 + i * 0.16)
                p.drawEllipse(QRectF(-orbit_w / 2, -orbit_h / 2, orbit_w, orbit_h))
                marker_x = math.cos(self._tick * 0.045 + i * 2.1) * orbit_w / 2
                marker_y = math.sin(self._tick * 0.045 + i * 2.1) * orbit_h / 2
                p.setBrush(QBrush(QColor(230, 190, 255, 220)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(marker_x, marker_y), 2.6, 2.6)
                p.restore()
            p.restore()

        # ── 답변 중: 방사형 음성 스펙트럼 ──
        if self.speaking:
            p.setBrush(Qt.BrushStyle.NoBrush)
            bars = 40
            inner = sph_r * 1.17
            for i in range(bars):
                angle = (math.tau * i / bars) - math.pi / 2
                activity = (
                    math.sin(self._tick * 0.18 + i * 0.72) * 0.5 + 0.5
                )
                activity *= 0.55 + (
                    math.sin(self._tick * 0.07 + i * 1.31) * 0.5 + 0.5
                ) * 0.45
                length = 7.0 + activity * 22.0
                x1 = cx + math.cos(angle) * inner
                y1 = cy + math.sin(angle) * inner
                x2 = cx + math.cos(angle) * (inner + length)
                y2 = cy + math.sin(angle) * (inner + length)
                p.setPen(QPen(QColor(60, 165, 255, 105 + int(activity * 145)), 2.0))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 텍스트 오버레이 없음 (채팅 패널로 이동)

    def set_hud_user(self, text: str):
        self._hud_user  = text; self._usr_alpha = 0.0; self._usr_hold = 210

    def set_hud_jarvis(self, text: str):
        self._hud_jarvis = text; self._jrv_alpha = 0.0; self._jrv_hold = 270


# ─── 시스템 모니터 오버레이 (좌상단) ────────────────────────────────────────

class SysMonitorOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(170, 175)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._snap = {"cpu":0,"mem":0,"net":0,"gpu":-1,"tmp":-1}
        self._uptime = "--:--"; self._procs = "--"
        tmr = QTimer(self); tmr.timeout.connect(self._refresh); tmr.start(2000)
        self._refresh()

    def _refresh(self):
        s = _metrics.snapshot(); self._snap = s
        try:
            elapsed = time.time() - psutil.boot_time()
            self._uptime = f"{int(elapsed//3600):02d}:{int((elapsed%3600)//60):02d}"
        except: self._uptime = "--:--"
        try: self._procs = str(len(psutil.pids()))
        except: self._procs = "--"
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W,H = self.width(), self.height()
        # 배경
        p.setBrush(QBrush(qcol(C.PANEL, 220))); p.setPen(QPen(qcol(C.BORDER,160),0.8))
        p.drawRoundedRect(QRectF(0,0,W,H),6,6)
        # 헤더
        p.setFont(QFont("Courier New",7,QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI),1))
        p.drawText(QRectF(8,6,W-16,14),Qt.AlignmentFlag.AlignLeft,"◈ 시스템 모니터")
        p.setPen(QPen(qcol(C.BORDER,160),0.5))
        p.drawLine(QPointF(6,21),QPointF(W-6,21))

        snap = self._snap
        metrics = [
            ("CPU",   snap["cpu"],  C.PRI,  f"{snap['cpu']:.0f}%"),
            ("메모리", snap["mem"],  C.ACC2, f"{snap['mem']:.0f}%"),
            ("네트워크",min(100,snap["net"]*10), C.GREEN,
             f"{snap['net']*1024:.0f}KB/s" if snap["net"]<1 else f"{snap['net']:.1f}MB/s"),
            ("GPU",   max(0,snap["gpu"]) if snap["gpu"]>=0 else 0,
             C.ACC,  f"{snap['gpu']:.0f}%" if snap["gpu"]>=0 else "N/A"),
            ("온도",  min(100,(snap["tmp"]/100)*100) if snap["tmp"]>=0 else 0,
             "#ff6688", f"{snap['tmp']:.0f}°C" if snap["tmp"]>=0 else "N/A"),
        ]
        y = 28
        for label, pct, color, val_str in metrics:
            p.setFont(QFont("Courier New",7))
            p.setPen(QPen(qcol(C.TEXT_DIM),1))
            p.drawText(QRectF(8,y,80,13),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,label)
            p.setPen(QPen(qcol(color),1))
            p.drawText(QRectF(0,y,W-8,13),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,val_str)
            bar_y = y+14; bw=W-16
            p.setBrush(QBrush(qcol(C.BAR_BG))); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(8,bar_y,bw,3),1,1)
            fw=max(0,int(bw*pct/100))
            if fw>0:
                bar_col = qcol(C.RED) if pct>85 else qcol(C.ACC) if pct>65 else qcol(color)
                p.setBrush(QBrush(bar_col)); p.drawRoundedRect(QRectF(8,bar_y,fw,3),1,1)
            y += 29

        # 업타임 / 프로세스
        p.setFont(QFont("Courier New",7,QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.GREEN),1))
        p.drawText(QRectF(8,y,80,14),Qt.AlignmentFlag.AlignLeft,f"UP {self._uptime}")
        p.setPen(QPen(qcol(C.TEXT_MED),1))
        p.drawText(QRectF(0,y,W-8,14),Qt.AlignmentFlag.AlignRight,f"PROC {self._procs}")


# ─── 시계 오버레이 (우상단) ──────────────────────────────────────────────────

class ClockOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(170, 42)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        tmr = QTimer(self); tmr.timeout.connect(self.update); tmr.start(1000)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W,H = self.width(),self.height()
        p.setBrush(QBrush(qcol(C.PANEL,220))); p.setPen(QPen(qcol(C.BORDER,160),0.8))
        p.drawRoundedRect(QRectF(0,0,W,H),6,6)
        p.setFont(QFont("Courier New",15,QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI),1))
        p.drawText(QRectF(0,2,W,22),Qt.AlignmentFlag.AlignCenter,time.strftime("%H:%M:%S"))
        p.setFont(QFont("Courier New",7))
        p.setPen(QPen(qcol(C.TEXT_DIM),1))
        p.drawText(QRectF(0,22,W,16),Qt.AlignmentFlag.AlignCenter,time.strftime("%Y년 %m월 %d일"))




class SetupOverlay(QWidget):
    done = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0,6,10,245);
                border: 1px solid {C.BORDER_B}; border-radius:6px;
            }}
        """)
        detected = {"darwin":"mac","windows":"windows"}.get(_OS.lower(),"linux")
        self._sel_os = detected
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30,22,30,22); layout.setSpacing(8)

        def _lbl(txt,fs=9,bold=False,color=C.PRI,align=Qt.AlignmentFlag.AlignCenter):
            w=QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Courier New",fs,QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color:{color}; background:transparent;"); return w

        layout.addWidget(_lbl("◈  시스템 초기화",13,True))
        layout.addWidget(_lbl("자비스를 처음 실행하기 전에 설정해주세요.",9,color=C.PRI_DIM))
        layout.addSpacing(6)

        sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        claude_ok = self._check_claude()
        status_col = C.GREEN if claude_ok else C.RED
        status_txt = ("✅  Claude CLI 감지됨" if claude_ok
                      else "❌  Claude CLI 미설치 — npm install -g @anthropic-ai/claude-code")
        layout.addWidget(_lbl(status_txt,8,color=status_col,align=Qt.AlignmentFlag.AlignLeft))
        layout.addSpacing(8)

        sep2=QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{C.BORDER};"); layout.addWidget(sep2)

        layout.addWidget(_lbl("운영 체제",8,color=C.TEXT_DIM,align=Qt.AlignmentFlag.AlignLeft))
        det_name={"windows":"Windows","mac":"macOS","linux":"Linux"}[detected]
        layout.addWidget(_lbl(f"자동 감지됨: {det_name}",8,color=C.ACC2,align=Qt.AlignmentFlag.AlignLeft))

        os_row=QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str,QPushButton]={}
        for key,label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn=QPushButton(label); btn.setFont(QFont("Courier New",9,QFont.Weight.Bold))
            btn.setFixedHeight(32); btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _,k=key: self._sel(k))
            os_row.addWidget(btn); self._os_btns[key]=btn
        layout.addLayout(os_row); self._sel(detected); layout.addSpacing(12)

        init_btn=QPushButton("▸  시스템 초기화")
        init_btn.setFont(QFont("Courier New",10,QFont.Weight.Bold)); init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{C.PRI};
                border:1px solid {C.PRI_DIM}; border-radius:3px; }}
            QPushButton:hover {{ background:{C.PRI_GHO}; border:1px solid {C.PRI}; }}
        """)
        init_btn.clicked.connect(lambda: self.done.emit(self._sel_os))
        layout.addWidget(init_btn)

    def _check_claude(self):
        try:
            r=subprocess.run(["claude","--version"],capture_output=True,timeout=5)
            return r.returncode==0
        except: return False

    def _sel(self, key):
        self._sel_os=key
        pal={"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k,btn in self._os_btns.items():
            if k==key:
                fg,bg=pal[k]
                btn.setStyleSheet(f"""QPushButton {{ background:{fg}; color:{bg};
                    border:none; border-radius:3px; font-weight:bold; }}""")
            else:
                btn.setStyleSheet(f"""QPushButton {{ background:#000d12; color:{C.TEXT_DIM};
                    border:1px solid {C.BORDER}; border-radius:3px; }}
                    QPushButton:hover {{ color:{C.TEXT}; border:1px solid {C.BORDER_B}; }}""")


# ─── 메인 윈도우 ─────────────────────────────────────────────────────────────


# ─── 메인 윈도우 (음성 전용) ─────────────────────────────────────────────────

# ─── 미니 채팅 패널 ──────────────────────────────────────────────────────────

class MiniChatPanel(QWidget):
    """JARVIS HUD와 어울리는 채팅 패널."""
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 컨테이너 ──
        card = QWidget()
        card.setObjectName("chat_card")
        card.setStyleSheet(f"""
            QWidget#chat_card {{
                background: rgba(1, 13, 20, 246);
                border-radius: 18px;
                border: 1px solid {C.BORDER_B};
            }}
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # 헤더
        hdr = QWidget()
        hdr.setFixedHeight(58)
        hdr.setStyleSheet("background: transparent;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 0, 14, 0)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("JARVIS CHAT")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        title_box.addWidget(title)
        self._status = QLabel("채팅 중 · 마이크 일시 정지")
        self._status.setFont(QFont("Arial", 8))
        self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        title_box.addWidget(self._status)
        hdr_lay.addLayout(title_box)
        hdr_lay.addStretch()
        sub = QLabel("TEXT MODE")
        sub.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        sub.setStyleSheet(f"""
            color: {C.PRI};
            background: {C.PRI_GHO};
            border: 1px solid {C.PRI_DIM};
            border-radius: 8px;
            padding: 3px 7px;
        """)
        hdr_lay.addWidget(sub)
        card_lay.addWidget(hdr)

        # 구분선
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color: {C.BORDER};")
        card_lay.addWidget(div)

        # 대화 영역
        self._log = QTextBrowser()
        self._log.setReadOnly(True)
        self._log.setOpenExternalLinks(True)
        self._log.setFont(QFont("Malgun Gothic", 10))
        self._log.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                color: {C.WHITE};
                border: none;
                padding: 14px 12px;
            }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{
                background: {C.PRI_DIM};
                border-radius: 2px;
            }}
        """)
        self._log.setPlaceholderText("메시지를 입력하면 대화가 여기에 표시됩니다.")
        card_lay.addWidget(self._log, 1)

        # 입력 영역
        inp_area = QWidget()
        inp_area.setFixedHeight(62)
        inp_area.setStyleSheet("background: transparent;")
        inp_lay = QHBoxLayout(inp_area)
        inp_lay.setContentsMargins(12, 10, 12, 10)
        inp_lay.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("자비스에게 메시지 보내기")
        self._input.setFont(QFont("Apple SD Gothic Neo, Malgun Gothic, Arial", 12))
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.DARK};
                color: {C.WHITE};
                border: 1px solid {C.BORDER};
                border-radius: 19px;
                padding: 6px 16px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: {C.PRI_GHO};
            }}
        """)
        self._input.returnPressed.connect(self._send)
        inp_lay.addWidget(self._input)

        send_btn = QPushButton("↑")
        send_btn.setFixedSize(34, 34)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI};
                color: #001018;
                border: none;
                border-radius: 17px;
            }}
            QPushButton:hover {{ background: {C.WHITE}; }}
        """)
        send_btn.clicked.connect(self._send)
        inp_lay.addWidget(send_btn)
        card_lay.addWidget(inp_area)

        root.addWidget(card)

    def _send(self):
        txt = self._input.text().strip()
        if txt:
            self._input.clear()
            self.submitted.emit(txt)

    def focus(self): self._input.setFocus()

    @staticmethod
    def _message_html(text: str) -> str:
        safe = html.escape(text)
        safe = re.sub(
            r"(https?://[^\s<]+)",
            r'<a style="color:#00d4ff" href="\1">\1</a>',
            safe,
        )
        return safe.replace("\n", "<br>")

    def append_user(self, text: str):
        body = self._message_html(text)
        self._log.append(f"""
            <div style="margin:8px 0 8px 36px; padding:9px 12px;
                        background:#063447; color:#e8fbff;
                        border-radius:12px;">
                <div style="font-size:9px; color:#70dfff; margin-bottom:4px;">YOU</div>
                {body}
            </div>
        """)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def append_jarvis(self, text: str):
        body = self._message_html(text)
        self._log.append(f"""
            <div style="margin:8px 36px 8px 0; padding:10px 12px;
                        background:#071820; color:#d8f8ff;
                        border-left:3px solid #00d4ff; border-radius:10px;">
                <div style="font-size:9px; color:#00d4ff; margin-bottom:4px;">JARVIS</div>
                {body}
            </div>
        """)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def set_status(self, text: str, busy: bool = False):
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {C.ACC2 if busy else C.GREEN}; background: transparent;"
        )


# ─── 채팅 버튼 (우하단 원형) ─────────────────────────────────────────────────

class ChatBubbleBtn(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open = False
        self._refresh()

    def set_open(self, v: bool):
        self._open = v; self._refresh()

    def _refresh(self):
        if self._open:
            self.setStyleSheet("""
                QPushButton {
                    background: #fff;
                    border: none;
                    border-radius: 23px;
                    color: #111;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #eee; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #ffffff;
                    border: none;
                    border-radius: 23px;
                    color: #111;
                    font-size: 18px;
                }
                QPushButton:hover { background: #eee; }
            """)
        self.setText("✕" if self._open else "💬")


# ─── 메인 윈도우 ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    _state_sig    = pyqtSignal(str)
    _usr_sig      = pyqtSignal(str)
    _jrv_sig      = pyqtSignal(str)
    _chat_log_sig = pyqtSignal(tuple)   # ("user"|"jarvis", text)
    _mic_sig      = pyqtSignal(float)   # 마이크 레벨 (0.0~1.0)

    def __init__(self, face_path: str = ""):
        super().__init__()
        self.setWindowTitle("자비스 — MARK XXXIX")
        self.setMinimumSize(640, 480)
        self.resize(1100, 720)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move((screen.width() - 1100) // 2, (screen.height() - 720) // 2)

        self._muted      = False
        self._chat_open  = False
        self._chat_mode_event = threading.Event()
        self._overlay: SetupOverlay | None = None
        self.on_text_command = None

        # HUD
        self.hud = HudCanvas(face_path)
        self.setCentralWidget(self.hud)
        self.hud.setStyleSheet("background: black;")

        # 우하단 채팅 버튼
        self._chat_btn = ChatBubbleBtn(self.hud)
        self._chat_btn.setFixedSize(52, 52)
        self._chat_btn.clicked.connect(self._toggle_chat)

        # 채팅 패널 (대화 내역 포함)
        self._chat_panel = MiniChatPanel(self.hud)
        self._chat_panel.submitted.connect(self._on_chat_submit)
        self._chat_panel.hide()

        # 시그널
        self._state_sig.connect(self._apply_state)
        self._usr_sig.connect(lambda t: self.hud.set_hud_user(t))
        self._jrv_sig.connect(lambda t: self.hud.set_hud_jarvis(t))
        self._chat_log_sig.connect(self._append_chat_message)
        self._mic_sig.connect(self._on_mic_level)

        # 단축키
        QShortcut(QKeySequence("F4"),  self).activated.connect(self._toggle_mute)
        QShortcut(QKeySequence("F11"), self).activated.connect(self._toggle_fullscreen)
        QShortcut(QKeySequence("F1"),  self).activated.connect(self._toggle_chat)

        # 설정 확인 → 이미 설정 완료면 바로 준비, 아니면 셋업 오버레이
        self._ready = self._check_config()
        if not self._ready:
            QTimer.singleShot(200, self._show_setup)

        self._reposition()

    # ── 레이아웃 ──

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _reposition(self):
        W, H = self.width(), self.height()
        bsz = 52
        self._chat_btn.setGeometry(W - bsz - 14, H - bsz - 14, bsz, bsz)
        pw, ph = 340, min(520, H - 100)
        self._chat_panel.setGeometry(W - pw - 14, H - bsz - ph - 12, pw, ph)
        if self._overlay:
            ow, oh = 380, 280
            self._overlay.setGeometry((W - ow) // 2, (H - oh) // 2, ow, oh)

    def _toggle_chat(self):
        self._chat_open = not self._chat_open
        self._chat_btn.set_open(self._chat_open)
        if self._chat_open:
            self._chat_mode_event.set()
            self._chat_panel.set_status("채팅 중 · 마이크 일시 정지")
            self._chat_panel.show(); self._chat_panel.raise_()
            self._chat_panel.focus()
        else:
            self._chat_mode_event.clear()
            self._chat_panel.hide()

    def _append_chat_message(self, pair: tuple):
        role, text = pair
        if role == "user":
            self._chat_panel.append_user(text)
        else:
            self._chat_panel.append_jarvis(text)

    def _on_chat_submit(self, text: str):
        self._chat_panel.append_user(text)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    def _on_mic_level(self, level: float):
        """애니메이션 루프가 사용할 최신 마이크 레벨을 저장한다."""
        self.hud.mic_level = max(0.0, min(float(level), 1.0))
        self.hud._last_mic_level_at = time.time()

    # ── 토글 ──

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._apply_state("음소거" if self._muted else "듣는 중")

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    # ── 설정 ──

    def _check_config(self) -> bool:
        try:
            data = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(data.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        self._overlay = SetupOverlay(self)
        self._overlay.done.connect(self._on_setup_done)
        W, H = self.width(), self.height()
        ow, oh = 380, 280
        self._overlay.setGeometry((W - ow) // 2, (H - oh) // 2, ow, oh)
        self._overlay.show(); self._overlay.raise_()

    def _on_setup_done(self, os_name: str):
        CONFIG_DIR.mkdir(exist_ok=True)
        API_FILE.write_text(json.dumps({"os_system": os_name}, indent=4), encoding="utf-8")
        self._ready = True
        if self._overlay: self._overlay.hide(); self._overlay = None
        self._apply_state("듣는 중")

    # ── 상태 ──

    def _apply_state(self, state: str):
        state_map = {
            "LISTENING": "듣는 중", "THINKING": "생각 중",
            "PROCESSING": "처리 중", "SPEAKING": "말하는 중", "MUTED": "음소거",
        }
        state = state_map.get(state, state)
        self.hud.state = state
        self.hud.speaking = state in ("말하는 중", "SPEAKING")
        if self._chat_open:
            status = {
                "생각 중": "답변을 생각하는 중…",
                "처리 중": "요청을 처리하는 중…",
                "말하는 중": "답변 완료",
            }.get(state, "채팅 중 · 마이크 일시 정지")
            self._chat_panel.set_status(
                status, busy=state in ("생각 중", "처리 중")
            )


# ─── 공개 API ────────────────────────────────────────────────────────────────

class JarvisUI:
    """main.py가 사용하는 공개 인터페이스"""

    def __init__(self, face_path: str = ""):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path=face_path)
        self._win.show()

    @property
    def root(self): return self
    def mainloop(self): self._app.exec()

    @property
    def muted(self) -> bool: return self._win._muted
    @property
    def chat_active(self) -> bool: return self._win._chat_mode_event.is_set()
    @property
    def speaking(self) -> bool: return self._win.hud.speaking
    @property
    def state(self) -> str: return self._win.hud.state
    @property
    def current_file(self) -> str | None: return None

    @property
    def on_text_command(self): return self._win.on_text_command
    @on_text_command.setter
    def on_text_command(self, cb): self._win.on_text_command = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        if text.startswith("나: "):
            self._win._usr_sig.emit(text[3:120])
        elif text.startswith("자비스: "):
            full_text = text[5:]
            self._win._jrv_sig.emit(full_text[:220])
            self._win._chat_log_sig.emit(("jarvis", full_text))

    def wait_for_api_key(self):
        while not self._win._ready: time.sleep(0.1)

    def start_speaking(self): self._win._state_sig.emit("SPEAKING")
    def stop_speaking(self):
        if not self._win._muted: self._win._state_sig.emit("LISTENING")

    def set_mic_level(self, level: float):
        """마이크 실시간 레벨 전달 (0.0~1.0)"""
        self._win._mic_sig.emit(float(level))
