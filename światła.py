import argparse
import json
import socket
import sys
from typing import Dict, Any, Optional, Tuple

#!/usr/bin/env python3
# Plik: światła.py
# Prosty skrypt do wysyłania komend UDP sterujących światłami.


LIGHTS: Dict[str, Dict[str, Any]] = {
    "1": {"name": "Światło 1", "ip": "192.168.0.136", "port": 38899},
    "2": {"name": "Światło 2", "ip": "192.168.0.185", "port": 38899},
}

# Predefined colors for easy access
COLORS: Dict[str, Tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
    "yellow": (255, 255, 0),
    "purple": (255, 0, 255),
    "cyan": (0, 255, 255),
    "orange": (255, 165, 0),
    "pink": (255, 192, 203),
    "warm_white": (255, 147, 41),
}

def build_payload(state: Optional[bool] = None, brightness: Optional[int] = None, 
                 rgb: Optional[Tuple[int, int, int]] = None) -> dict:
    params: Dict[str, Any] = {}
    
    if state is not None:
        params["state"] = state
    
    if brightness is not None:
        if not (0 <= brightness <= 100):
            raise ValueError("Jasność (brightness) musi być 0-100")
        params["dimming"] = brightness
    
    if rgb is not None:
        r, g, b = rgb
        if not all(0 <= val <= 255 for val in [r, g, b]):
            raise ValueError("Wartości RGB muszą być 0-255")
        params["r"] = r
        params["g"] = g
        params["b"] = b
    
    return {
        "id": 1,
        "method": "setPilot",
        "params": params
    }

def send_command(light_id: str, payload: dict) -> bool:
    """Send UDP command to light"""
    try:
        light = LIGHTS[light_id]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        
        message = json.dumps(payload).encode('utf-8')
        sock.sendto(message, (light["ip"], light["port"]))
        sock.close()
        return True
    except Exception as e:
        print(f"Błąd wysyłania komendy: {e}")
        return False

def set_color(light_id: str, color_name: str, brightness: int = 100) -> bool:
    """Set light to predefined color"""
    if color_name not in COLORS:
        print(f"Dostępne kolory: {', '.join(COLORS.keys())}")
        return False
    
    rgb = COLORS[color_name]
    payload = build_payload(state=True, brightness=brightness, rgb=rgb)
    return send_command(light_id, payload)

def set_rgb(light_id: str, r: int, g: int, b: int, brightness: int = 100) -> bool:
    """Set light to custom RGB color"""
    payload = build_payload(state=True, brightness=brightness, rgb=(r, g, b))
    return send_command(light_id, payload)

def turn_on(light_id: str, brightness: int = 100) -> bool:
    """Turn light on with optional brightness"""
    payload = build_payload(state=True, brightness=brightness)
    return send_command(light_id, payload)

def turn_off(light_id: str) -> bool:
    """Turn light off"""
    payload = build_payload(state=False)
    return send_command(light_id, payload)

def list_lights():
    print("Dostępne światła:")
    for k, v in LIGHTS.items():
        print(f"  {k}: {v['name']} ({v['ip']}:{v['port']})")

def parse_args():
    p = argparse.ArgumentParser(description="Sterowanie światłami (UDP JSON).")
    sub = p.add_subparsers(dest="cmd")

    sub_list = sub.add_parser("list", help="Wypisz listę świateł")

    sub_on = sub.add_parser("on", help="Włącz światło")
    sub_on.add_argument("which", help="Numer światła lub all")
    sub_on.add_argument("-b", "--brightness", type=int, help="Jasność 0-100")

    sub_off = sub.add_parser("off", help="Wyłącz światło")
    sub_off.add_argument("which", help="Numer światła lub all")

    sub_raw = sub.add_parser("raw", help="Wyślij surowy JSON (id/method/params)")
    sub_raw.add_argument("which", help="Numer światła lub all")
    sub_raw.add_argument("json", help='JSON np. {"id":1,"method":"getPilot"}')

    p.add_argument("-n", "--dry-run", action="store_true", help="Pokaż co byłoby wysłane")
    p.add_argument("-v", "--verbose", action="store_true", help="Więcej informacji")

    return p.parse_args()

def main():
    args = parse_args()

    if args.cmd == "list" or args.cmd is None:
        list_lights()
        return

    targets = []
    if args.cmd in ("on", "off", "raw"):
        if args.which == "all":
            targets = list(LIGHTS.keys())
        else:
            if args.which not in LIGHTS:
                print("Nieznane światło:", args.which, file=sys.stderr)
                sys.exit(1)
            targets = [args.which]

    if args.cmd == "on":
        for t in targets:
            control_light(
                t,
                state=True,
                brightness=args.brightness,
                dry_run=args.dry_run,
                verbose=args.verbose
            )
    elif args.cmd == "off":
        for t in targets:
            control_light(
                t,
                state=False,
                brightness=None,
                dry_run=args.dry_run,
                verbose=args.verbose
            )
    elif args.cmd == "raw":
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError as e:
            print("Błędny JSON:", e, file=sys.stderr)
            sys.exit(1)
        for t in targets:
            light = LIGHTS[t]
            if args.dry_run or args.verbose:
                print(f"[{t}] {light['name']} -> {payload}")
            if not args.dry_run:
                send_udp(light["ip"], light["port"], payload)
    else:
        print("Nieznane polecenie", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()