from typing import Dict, Any, Optional, Tuple
import socket
import json
import curses
import time


LIGHTS: Dict[str, Dict[str, Any]] = {
    "1": {"name": "Światło 1", "ip": "192.168.0.136", "port": 38899, "state": False, "brightness": 100, "color": "white"},
    "2": {"name": "Światło 2", "ip": "192.168.0.185", "port": 38899, "state": False, "brightness": 100, "color": "white"},
}


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

def rgb_to_color_name(r: int, g: int, b: int) -> str:

    min_distance = float('inf')
    closest_color = "white"
    
    for name, (cr, cg, cb) in COLORS.items():
        distance = ((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2) ** 0.5
        if distance < min_distance:
            min_distance = distance
            closest_color = name
    
    return closest_color

def get_light_status(light_id: str) -> Optional[Dict[str, Any]]:
    try:
        light = LIGHTS[light_id]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        
        # Send getPilot command
        command = {"method": "getPilot", "params": {}}
        message = json.dumps(command).encode('utf-8')
        sock.sendto(message, (light["ip"], light["port"]))
        
        # Receive response
        response, addr = sock.recvfrom(1024)
        sock.close()
        
        data = json.loads(response.decode('utf-8'))
        
        if 'result' in data:
            result = data['result']
            
            # Parse the response
            status = {
                'state': result.get('state', False),
                'brightness': result.get('dimming', 100),
                'r': result.get('r', 255),
                'g': result.get('g', 255), 
                'b': result.get('b', 255),
                'online': True
            }
            
            # Determine color name from RGB
            status['color'] = rgb_to_color_name(status['r'], status['g'], status['b'])
            
            return status
        
        return None
        
    except Exception as e:
        return {'online': False, 'error': str(e)}

def refresh_all_lights_status():
    for light_id in LIGHTS.keys():
        status = get_light_status(light_id)
        if status and status.get('online', False):
            LIGHTS[light_id].update(status)
        elif status:
            LIGHTS[light_id]['online'] = False
            LIGHTS[light_id]['error'] = status.get('error', 'Unknown error')

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
    try:
        light = LIGHTS[light_id]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        
        message = json.dumps(payload).encode('utf-8')
        sock.sendto(message, (light["ip"], light["port"]))
        sock.close()
        return True
    except Exception as e:
        return False

def set_color(light_id: str, color_name: str, brightness: int = 100) -> bool:
    if color_name not in COLORS:
        return False
    
    rgb = COLORS[color_name]
    payload = build_payload(state=True, brightness=brightness, rgb=rgb)
    success = send_command(light_id, payload)
    if success:
        LIGHTS[light_id]["state"] = True
        LIGHTS[light_id]["brightness"] = brightness
        LIGHTS[light_id]["color"] = color_name
        LIGHTS[light_id]["r"], LIGHTS[light_id]["g"], LIGHTS[light_id]["b"] = rgb
    return success

def turn_on(light_id: str, brightness: int = 100) -> bool:
    color = LIGHTS[light_id]["color"]
    rgb = COLORS.get(color, COLORS["white"])
    payload = build_payload(state=True, brightness=brightness, rgb=rgb)
    success = send_command(light_id, payload)
    if success:
        LIGHTS[light_id]["state"] = True
        LIGHTS[light_id]["brightness"] = brightness
    return success

def turn_off(light_id: str) -> bool:
    payload = build_payload(state=False)
    success = send_command(light_id, payload)
    if success:
        LIGHTS[light_id]["state"] = False
    return success

class LightControlApp:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_light = 0
        self.menu_mode = "main"  # "main", "color", "brightness"
        self.color_selection = 0
        self.brightness_value = 100
        self.status_message = ""
        self.color_list = list(COLORS.keys())
        self.last_refresh = 0
        
        # Colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # ON
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)    # OFF
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Selected
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)   # Header
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Offline

    def draw_header(self):
        self.stdscr.addstr(0, 0, "=== STEROWANIE ŚWIATŁAMI ===", curses.color_pair(4) | curses.A_BOLD)
        self.stdscr.addstr(1, 0, "Użyj strzałek, ENTER, ESC, R-odśwież, Q-wyjście")

    def draw_lights_status(self):
        y_start = 3
        for i, (light_id, light) in enumerate(LIGHTS.items()):
            y = y_start + i * 4
            
            # Highlight current selection
            attr = curses.color_pair(3) | curses.A_REVERSE if i == self.current_light else curses.A_NORMAL
            
            # Light name
            self.stdscr.addstr(y, 0, f"{light['name']}:", attr)
            
            # Online/Offline status
            if light.get('online', True):
                # Status
                if light["state"]:
                    status_color = curses.color_pair(1)
                    status_text = "ON"
                else:
                    status_color = curses.color_pair(2)
                    status_text = "OFF"
                
                self.stdscr.addstr(y, 15, status_text, status_color | curses.A_BOLD)
                
                # Brightness and color (if on)
                if light["state"]:
                    self.stdscr.addstr(y + 1, 2, f"Jasność: {light['brightness']}%")
                    self.stdscr.addstr(y + 1, 20, f"Kolor: {light['color']}")
                    
                    # Show RGB values if available
                    if all(key in light for key in ['r', 'g', 'b']):
                        self.stdscr.addstr(y + 2, 2, f"RGB: ({light['r']}, {light['g']}, {light['b']})")
            else:
                self.stdscr.addstr(y, 15, "OFFLINE", curses.color_pair(5) | curses.A_BOLD)
                if 'error' in light:
                    error_msg = light['error'][:30] + "..." if len(light['error']) > 30 else light['error']
                    self.stdscr.addstr(y + 1, 2, f"Error: {error_msg}")

    def draw_menu_options(self):
        height, width = self.stdscr.getmaxyx()
        y_start = height - 10
        
        if self.menu_mode == "main":
            options = [
                "SPACE - Włącz/Wyłącz",
                "C - Zmień kolor",
                "B - Zmień jasność",
                "R - Odśwież status",
                "A - Wszystkie ON",
                "S - Wszystkie OFF"
            ]
        elif self.menu_mode == "color":
            current_color = self.color_list[self.color_selection]
            rgb = COLORS[current_color]
            options = [
                f"Wybierz kolor: {current_color}",
                f"RGB: {rgb}",
                "Użyj ← → do zmiany",
                "ENTER - Zastosuj",
                "ESC - Anuluj"
            ]
        elif self.menu_mode == "brightness":
            options = [
                f"Jasność: {self.brightness_value}%",
                "Użyj ← → do zmiany",
                "ENTER - Zastosuj", 
                "ESC - Anuluj"
            ]
        
        for i, option in enumerate(options):
            self.stdscr.addstr(y_start + i, 0, option)

    def draw_status_message(self):
        if self.status_message:
            height, width = self.stdscr.getmaxyx()
            self.stdscr.addstr(height - 2, 0, self.status_message, curses.color_pair(1))

    def set_status(self, message: str):
        self.status_message = message

    def handle_main_menu(self, key):
        if key == curses.KEY_UP and self.current_light > 0:
            self.current_light -= 1
        elif key == curses.KEY_DOWN and self.current_light < len(LIGHTS) - 1:
            self.current_light += 1
        elif key == ord(' '):  # Space to toggle
            light_id = list(LIGHTS.keys())[self.current_light]
            light = LIGHTS[light_id]
            if light["state"]:
                if turn_off(light_id):
                    self.set_status(f"Wyłączono {light['name']}")
                else:
                    self.set_status(f"Błąd wyłączania {light['name']}")
            else:
                if turn_on(light_id, light["brightness"]):
                    self.set_status(f"Włączono {light['name']}")
                else:
                    self.set_status(f"Błąd włączania {light['name']}")
        elif key == ord('r') or key == ord('R'):
            self.set_status("Odświeżanie statusu...")
            self.stdscr.refresh()
            refresh_all_lights_status()
            self.set_status("Status odświeżony")
        elif key == ord('c') or key == ord('C'):
            self.menu_mode = "color"
            light_id = list(LIGHTS.keys())[self.current_light]
            current_color = LIGHTS[light_id]["color"]
            self.color_selection = self.color_list.index(current_color) if current_color in self.color_list else 0
        elif key == ord('b') or key == ord('B'):
            self.menu_mode = "brightness"
            light_id = list(LIGHTS.keys())[self.current_light]
            self.brightness_value = LIGHTS[light_id]["brightness"]
        elif key == ord('a') or key == ord('A'):
            # Turn all lights on
            success_count = 0
            for light_id in LIGHTS.keys():
                if turn_on(light_id, LIGHTS[light_id]["brightness"]):
                    success_count += 1
            self.set_status(f"Włączono {success_count}/{len(LIGHTS)} świateł")
        elif key == ord('s') or key == ord('S'):
            # Turn all lights off
            success_count = 0
            for light_id in LIGHTS.keys():
                if turn_off(light_id):
                    success_count += 1
            self.set_status(f"Wyłączono {success_count}/{len(LIGHTS)} świateł")

    def handle_color_menu(self, key):
        if key == curses.KEY_LEFT and self.color_selection > 0:
            self.color_selection -= 1
        elif key == curses.KEY_RIGHT and self.color_selection < len(self.color_list) - 1:
            self.color_selection += 1
        elif key == ord('\n') or key == ord('\r'):  # Enter
            light_id = list(LIGHTS.keys())[self.current_light]
            color_name = self.color_list[self.color_selection]
            brightness = LIGHTS[light_id]["brightness"]
            if set_color(light_id, color_name, brightness):
                self.set_status(f"Ustawiono kolor {color_name}")
            else:
                self.set_status(f"Błąd ustawiania koloru")
            self.menu_mode = "main"
        elif key == 27:  # ESC
            self.menu_mode = "main"

    def handle_brightness_menu(self, key):
        if key == curses.KEY_LEFT and self.brightness_value > 0:
            self.brightness_value = max(0, self.brightness_value - 5)
        elif key == curses.KEY_RIGHT and self.brightness_value < 100:
            self.brightness_value = min(100, self.brightness_value + 5)
        elif key == ord('\n') or key == ord('\r'):  # Enter
            light_id = list(LIGHTS.keys())[self.current_light]
            if LIGHTS[light_id]["state"]:
                color_name = LIGHTS[light_id]["color"]
                if set_color(light_id, color_name, self.brightness_value):
                    self.set_status(f"Ustawiono jasność {self.brightness_value}%")
                else:
                    self.set_status(f"Błąd ustawiania jasności")
            else:
                LIGHTS[light_id]["brightness"] = self.brightness_value
                self.set_status(f"Zapisano jasność {self.brightness_value}%")
            self.menu_mode = "main"
        elif key == 27:  # ESC
            self.menu_mode = "main"

    def run(self):
        self.set_status("Ładowanie statusu świateł...")
        self.stdscr.refresh()
        refresh_all_lights_status()
        
        while True:
            self.stdscr.clear()
            
            current_time = time.time()
            if current_time - self.last_refresh > 30:
                refresh_all_lights_status()
                self.last_refresh = current_time
            
            self.draw_header()
            self.draw_lights_status()
            self.draw_menu_options()
            self.draw_status_message()
            
            self.stdscr.refresh()

            key = self.stdscr.getch()

            if self.status_message:
                time.sleep(0.1) 
                self.status_message = ""
            
            if key == ord('q') or key == ord('Q'):
                break
            
            if self.menu_mode == "main":
                self.handle_main_menu(key)
            elif self.menu_mode == "color":
                self.handle_color_menu(key)
            elif self.menu_mode == "brightness":
                self.handle_brightness_menu(key)

def main_app(stdscr):
    curses.curs_set(0)  # Hide cursor
    app = LightControlApp(stdscr)
    app.run()

if __name__ == "__main__":
    curses.wrapper(main_app)