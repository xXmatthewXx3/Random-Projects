import argparse
import colorsys
import json
import math
import random
import signal
import socket
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Set

WIZ_PORT = 38899

# ---------- Rate limiting / coalescing ----------

_MIN_INTERVAL = 0.15   # seconds between UDP sends per bulb (tunable via CLI)
_COLOR_EPS = 12        # minimal total RGB delta to consider "changed"
_DIM_EPS = 6           # minimal brightness change to send
_SEND_STATE: Dict[str, Dict[str, Any]] = {}  # ip -> {t,last,(r,g,b),dim,jitter}

def _ip_state(ip: str) -> Dict[str, Any]:
    st = _SEND_STATE.get(ip)
    if not st:
        st = {"t": 0.0, "last": (None, None, None), "dim": None, "jitter": random.uniform(0.0, 0.02)}
        _SEND_STATE[ip] = st
    return st

def set_rate_limits(min_interval: float, color_eps: int, dim_eps: int = 6):
    global _MIN_INTERVAL, _COLOR_EPS, _DIM_EPS
    _MIN_INTERVAL = max(0.08, float(min_interval))
    _COLOR_EPS = max(1, int(color_eps))
    _DIM_EPS = max(1, int(dim_eps))

def _color_distance(a: Tuple[int,int,int], b: Tuple[int,int,int]) -> int:
    return abs(a[0]-b[0]) + abs(a[1]-b[1]) + abs(a[2]-b[2])

# ---------- WiZ UDP primitives (with throttling) ----------

def _udp_send(ip: str, payload: Dict[str, Any], timeout: float = 0.6, expect_reply: bool = False) -> Optional[Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(data, (ip, WIZ_PORT))
        if expect_reply:
            resp, _ = sock.recvfrom(4096)
            return json.loads(resp.decode("utf-8"))
        return None
    except socket.timeout:
        return None
    finally:
        sock.close()

def wiz_get_pilot(ip: str) -> Optional[Dict[str, Any]]:
    return _udp_send(ip, {"method": "getPilot", "params": {}}, expect_reply=True)

def wiz_set_rgb(ip: str, r: int, g: int, b: int, brightness: int = 100, state: Optional[bool] = True, force: bool = False) -> None:
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    brightness = max(10, min(100, int(brightness)))
    st = _ip_state(ip)
    now = time.time()
    last_rgb = st["last"]
    last_dim = st["dim"]
    if last_rgb[0] is not None:
        if not force:
            if now - st["t"] < _MIN_INTERVAL:
                # too soon; drop if change is tiny
                if _color_distance((r,g,b), last_rgb) < _COLOR_EPS and abs(brightness - (last_dim or brightness)) < _DIM_EPS:
                    return
            else:
                # enough time passed, but still skip trivial deltas
                if _color_distance((r,g,b), last_rgb) < max(3, _COLOR_EPS//2) and abs(brightness - (last_dim or brightness)) < max(2, _DIM_EPS//2):
                    return
    params: Dict[str, Any] = {"r": r, "g": g, "b": b, "dimming": brightness}
    if state is not None:
        params["state"] = bool(state)
    _udp_send(ip, {"method": "setPilot", "params": params})
    st["t"], st["last"], st["dim"] = now + st["jitter"], (r,g,b), brightness  # stagger a bit

def wiz_set_state(ip: str, on: bool, force: bool = False) -> None:
    st = _ip_state(ip)
    now = time.time()
    if not force and now - st["t"] < _MIN_INTERVAL:
        return
    _udp_send(ip, {"method": "setPilot", "params": {"state": bool(on)}})
    st["t"] = now + st["jitter"]

def wiz_set_scene(ip: str, scene_id: int, speed: Optional[int] = None, brightness: Optional[int] = None) -> None:
    st = _ip_state(ip)
    now = time.time()
    if now - st["t"] < _MIN_INTERVAL:
        return
    params: Dict[str, Any] = {"sceneId": int(scene_id), "state": True}
    if speed is not None:
        params["speed"] = max(5, min(200, int(speed)))
    if brightness is not None:
        params["dimming"] = max(10, min(100, int(brightness)))
    _udp_send(ip, {"method": "setPilot", "params": params})
    st["t"] = now + st["jitter"]

# ---------- Discovery ----------

def discover_wiz(timeout: float = 1.0) -> List[str]:
    ips: Set[str] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    payload = json.dumps({"method": "getSystemConfig", "params": {}}).encode("utf-8")
    try:
        sock.sendto(payload, ("255.255.255.255", WIZ_PORT))
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp, addr = sock.recvfrom(4096)
                if addr and addr[0]:
                    ips.add(addr[0])
            except socket.timeout:
                break
    finally:
        sock.close()
    return sorted(ips)

# ---------- Utils ----------

def hsv_to_rgb_int(h: float, s: float, v: float) -> Tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255)

# fixed-FPS frame loop
def run_for(duration: float, fps: float, step):
    start = time.time()
    frame = 0
    dt = 1.0 / max(1.0, fps)
    next_t = start
    while time.time() - start < duration:
        step(frame, time.time() - start)
        frame += 1
        next_t += dt
        sleep = next_t - time.time()
        if sleep > 0:
            time.sleep(sleep)

# ---------- Patterns (slower, stable) ----------

def pattern_rainbow_cycle(ips: List[str], duration: float = 10.0, speed: float = 0.12, sat: float = 1.0, val: float = 1.0, fps: float = 8.0):
    if not ips: return
    n = len(ips)
    phase = random.random()
    def step(frame, t):
        tt = t * speed + phase
        bright = int(val * 100)
        for i, ip in enumerate(ips):
            h = (tt + i / max(1, n)) % 1.0
            r, g, b = hsv_to_rgb_int(h, sat, val)
            wiz_set_rgb(ip, r, g, b, brightness=bright)
    run_for(duration, fps, step)

def pattern_strobe(ips: List[str], duration: float = 8.0, bpm: int = 100, color: Tuple[int, int, int] = (255, 255, 255)):
    if not ips: return
    # Two-bank brightness toggle; avoid power toggles
    interval = 60.0 / max(1, bpm)  # one beat
    half = interval / 2.0
    r, g, b = color
    start = time.time()
    bank_a = [ip for i, ip in enumerate(ips) if i % 2 == 0]
    bank_b = [ip for i, ip in enumerate(ips) if i % 2 == 1]
    while time.time() - start < duration:
        # A bright, B dim
        for ip in bank_a:
            wiz_set_rgb(ip, r, g, b, brightness=100)
        for ip in bank_b:
            wiz_set_rgb(ip, r, g, b, brightness=15)
        time.sleep(half)
        # A dim, B bright
        for ip in bank_a:
            wiz_set_rgb(ip, r, g, b, brightness=15)
        for ip in bank_b:
            wiz_set_rgb(ip, r, g, b, brightness=100)
        time.sleep(half)

def pattern_sparkle(ips: List[str], duration: float = 10.0, base: Tuple[int, int, int] = (40, 40, 40), sparks_per_tick: int = 2, fps: float = 7.0):
    if not ips: return
    r0, g0, b0 = base
    def step(frame, t):
        for ip in ips:
            wiz_set_rgb(ip, r0, g0, b0, brightness=40)
        k = min(len(ips), max(1, sparks_per_tick))
        for ip in random.sample(ips, k):
            h = random.random()
            r, g, b = hsv_to_rgb_int(h, 1.0, 1.0)
            wiz_set_rgb(ip, r, g, b, brightness=100)
    run_for(duration, fps, step)

def pattern_pulse(ips: List[str], duration: float = 10.0, bpm: int = 90, hue: Optional[float] = None, sat: float = 1.0, fps: float = 10.0):
    if not ips: return
    base_h = random.random() if hue is None else hue % 1.0
    def step(frame, t):
        phase = (t * (bpm / 60.0)) % 1.0
        val = 0.25 + 0.75 * 0.5 * (1.0 + math.sin(2 * math.pi * phase))
        r, g, b = hsv_to_rgb_int(base_h, sat, val)
        bright = int(20 + 80 * val)
        for ip in ips:
            wiz_set_rgb(ip, r, g, b, brightness=bright)
    run_for(duration, fps, step)

def pattern_wave(ips: List[str], duration: float = 10.0, speed: float = 3.5, hue: Optional[float] = None, fps: float = 8.0):
    if not ips: return
    n = len(ips)
    base_h = random.random() if hue is None else hue % 1.0
    def step(frame, t):
        for i, ip in enumerate(ips):
            phase = (t * speed + i / max(1, n)) % 1.0
            val = 0.35 + 0.65 * 0.5 * (1.0 + math.cos(2 * math.pi * phase))
            r, g, b = hsv_to_rgb_int(base_h + 0.08 * i, 1.0, val)
            wiz_set_rgb(ip, r, g, b, brightness=int(20 + 80 * val))
    run_for(duration, fps, step)

# ---------- Powerful Disco (pattern mixer) ----------

def run_powerful_disco(ips: List[str], runtime: Optional[float] = None):
    if not ips:
        print("Brak świateł – podaj IP lub użyj --discover.", file=sys.stderr)
        return
    print(f"Start DISCO na {len(ips)} światłach: {', '.join(ips)}. Ctrl+C aby zakończyć.")
    start_time = time.time()
    try:
        while True:
            choice = random.choice(["rainbow", "strobe", "sparkle", "pulse", "wave"])
            seg = random.uniform(7.0, 12.0)
            if runtime is not None and time.time() - start_time + seg > runtime:
                seg = max(1.0, runtime - (time.time() - start_time))
            if choice == "rainbow":
                pattern_rainbow_cycle(ips, duration=seg, speed=random.uniform(0.09, 0.16), sat=random.uniform(0.85, 1.0), val=random.uniform(0.85, 1.0), fps=8.0)
            elif choice == "strobe":
                bpm = random.randint(90, 120)
                color = random.choice([(255, 255, 255), hsv_to_rgb_int(random.random(), 1.0, 1.0)])
                pattern_strobe(ips, duration=seg, bpm=bpm, color=color)
            elif choice == "sparkle":
                base = tuple(int(x) for x in hsv_to_rgb_int(random.random(), 1.0, 0.2))
                k = random.randint(1, max(1, len(ips)//3 or 1))
                pattern_sparkle(ips, duration=seg, base=base, sparks_per_tick=k, fps=7.0)
            elif choice == "pulse":
                bpm = random.randint(70, 110)
                hue = random.random()
                pattern_pulse(ips, duration=seg, bpm=bpm, hue=hue, fps=10.0)
            elif choice == "wave":
                speed = random.uniform(3.0, 5.0)
                hue = random.random()
                pattern_wave(ips, duration=seg, speed=speed, hue=hue, fps=8.0)
            if runtime is not None and time.time() - start_time >= runtime:
                break
    except KeyboardInterrupt:
        pass

# ---------- State snapshot/restore ----------

def snapshot_states(ips: List[str]) -> Dict[str, Dict[str, Any]]:
    states: Dict[str, Dict[str, Any]] = {}
    for ip in ips:
        st = wiz_get_pilot(ip)
        if st and "result" in st:
            states[ip] = st["result"]
    return states

def restore_states(states: Dict[str, Dict[str, Any]]):
    for ip, res in states.items():
        try:
            if not res.get("state", True):
                wiz_set_state(ip, False, force=True)
                continue
            if "r" in res and "g" in res and "b" in res:
                r, g, b = int(res.get("r", 255)), int(res.get("g", 255)), int(res.get("b", 255))
                dim = int(res.get("dimming", 100))
                wiz_set_rgb(ip, r, g, b, brightness=dim, state=True, force=True)
            elif "sceneId" in res:
                scene = int(res["sceneId"])
                dim = int(res.get("dimming", 100))
                speed = res.get("speed")
                wiz_set_scene(ip, scene, speed=speed, brightness=dim)
        except Exception:
            pass

# ---------- CLI ----------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Potężna dyskoteka dla świateł WiZ (UDP setPilot) z ograniczeniem tempa.")
    p.add_argument("--ips", type=str, help="Lista IP oddzielona przecinkami, np. 192.168.1.50,192.168.1.51")
    p.add_argument("--discover", action="store_true", help="Wyszukaj lampy przez broadcast")
    p.add_argument("--mode", type=str, default="disco", choices=["disco","rainbow","strobe","sparkle","pulse","wave"], help="Tryb działania")
    p.add_argument("--runtime", type=float, default=None, help="Czas działania w sekundach (domyślnie bez końca)")
    p.add_argument("--bpm", type=int, default=100, help="Dla strobe/pulse: uderzenia na minutę")
    p.add_argument("--speed", type=float, default=0.12, help="Dla rainbow/wave: prędkość")
    p.add_argument("--min-interval", type=float, default=0.15, help="Min. odstęp między komendami na lampę (s)")
    p.add_argument("--eps", type=int, default=12, help="Próg zmiany koloru (suma |ΔRGB|) do wysyłki")
    return p.parse_args()

def main():
    args = parse_args()
    set_rate_limits(args.min-interval if hasattr(args, "min-interval") else args.min_interval, args.eps)

    ips: List[str] = []
    if args.ips:
        ips = [x.strip() for x in args.ips.split(",") if x.strip()]
    if args.discover:
        found = discover_wiz(timeout=1.0)
        for ip in found:
            if ip not in ips:
                ips.append(ip)
    if not ips:
        print("Brak IP. Użyj --ips lub --discover.", file=sys.stderr)
        sys.exit(1)

    states = snapshot_states(ips)

    def on_exit(signum=None, frame=None):
        restore_states(states)
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    try:
        if args.mode == "disco":
            run_powerful_disco(ips, runtime=args.runtime)
        elif args.mode == "rainbow":
            pattern_rainbow_cycle(ips, duration=args.runtime or 30.0, speed=args.speed)
        elif args.mode == "strobe":
            pattern_strobe(ips, duration=args.runtime or 30.0, bpm=args.bpm)
        elif args.mode == "sparkle":
            pattern_sparkle(ips, duration=args.runtime or 30.0)
        elif args.mode == "pulse":
            pattern_pulse(ips, duration=args.runtime or 30.0, bpm=args.bpm)
        elif args.mode == "wave":
            pattern_wave(ips, duration=args.runtime or 30.0, speed=args.speed)
    finally:
        restore_states(states)

if __name__ == "__main__":
    main()