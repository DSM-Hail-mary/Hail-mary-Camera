"""
metrics.py — Jetson 실제 기기 지표 수집

실제 값 소스:
  - temperature : /sys/class/thermal/thermal_zone*/temp  (실측, °C)
  - power       : jtop(jetson-stats, 정확) 또는 sysfs INA3221(근사), W
  - fps         : camera.py 캡처 통계의 구간 델타 (실측)
  - frame_drop  : camera.py 드롭 카운터의 구간 델타 (실측)
  - gps         : gps.py 수신 상태 (1/0)

MetricsCollector.snapshot() 이 한 번에 실제 지표 스냅샷을 반환한다.
Jetson이 아닌 환경에서는 온도/전력이 None을 반환한다(예외 없음).
"""
import glob
import os
import time
from typing import Optional


def _read_int(path) -> Optional[int]:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def read_temp_c() -> Optional[float]:
    """thermal_zone*/temp 중 최고값(°C). 실패 시 None."""
    temps = []
    for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        v = _read_int(p)
        if v is not None:
            temps.append(v / 1000.0)
    return round(max(temps), 1) if temps else None


def read_power_w(jtop=None) -> Optional[float]:
    """총 소비전력(W).
    1) jtop 인스턴스가 있으면 그 총전력을 사용(정확).
    2) 없으면 sysfs INA3221 전력 모니터의 VDD_IN 레일을 읽음(근사).
    3) 둘 다 실패하면 None.
    """
    # 1) jetson-stats(jtop)
    if jtop is not None:
        try:
            return round(jtop.power["tot"]["power"] / 1000.0, 2)   # mW → W
        except Exception:
            pass
    # 2) sysfs INA3221 (VDD_IN 총전력 레일)
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        for lbl in glob.glob(os.path.join(hwmon, "in*_label")):
            try:
                name = open(lbl).read().strip().upper()
            except Exception:
                continue
            if "VDD_IN" in name or name == "IN":       # 총입력 레일 우선
                idx = os.path.basename(lbl)[2:-6]       # in{idx}_label
                mv = _read_int(os.path.join(hwmon, f"in{idx}_input"))
                ma = _read_int(os.path.join(hwmon, f"curr{idx}_input"))
                if mv and ma:
                    return round(mv * ma / 1e6, 2)      # mV*mA = µW → W
    return None


class MetricsCollector:
    """카메라/GPS/jtop를 묶어 실제 지표 스냅샷을 만든다.

    fps/drops는 이전 snapshot 이후의 구간 델타로 계산하므로,
    주기적으로 snapshot()을 호출하는 쪽(pipeline)에서 사용한다.
    """
    def __init__(self, camera=None, gps=None, jtop=None):
        self.camera = camera
        self.gps = gps
        self.jtop = jtop
        self._last_t: Optional[float] = None
        self._last_cap = 0
        self._last_drop = 0

    def snapshot(self) -> dict:
        now = time.time()
        temp = read_temp_c()
        power = read_power_w(self.jtop)

        fps: Optional[float] = None
        drops = 0
        if self.camera is not None:
            cap = self.camera.stats.captured
            drp = self.camera.stats.dropped
            if self._last_t is not None and now > self._last_t:
                dt = now - self._last_t
                fps = round((cap - self._last_cap) / dt, 1)
                drops = drp - self._last_drop
            self._last_cap = cap
            self._last_drop = drp
        self._last_t = now

        gps = 0
        if self.gps is not None:
            gps = 1 if self.gps.read().get("has_fix") else 0

        return {"temp": temp, "power": power, "fps": fps, "drops": drops, "gps": gps}


if __name__ == "__main__":
    print("temp(°C):", read_temp_c())
    print("power(W):", read_power_w())       # jtop 없으면 sysfs 시도 → 없으면 None
    print("snapshot(no hw):", MetricsCollector().snapshot())
