import socket
import json
import time
import signal
import sys
from typing import Dict, Any, Optional, Tuple

LIGHTS: Dict[str, Dict[str, Any]] = {
    "1": {"name": "Światło 1", "ip": "192.168.0.136", "port": 38899},
    "2": {"name": "Światło 2", "ip": "192.168.0.185", "port": 38899},
}

original_states: Dict[str, Dict[str, Any]] = {}

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
        print(f"Błąd wysyłania komendy do {light_id}: {e}")
        return False

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
            
            return status
        
        return None
        
    except Exception as e:
        print(f"Błąd pobierania statusu {light_id}: {e}")
        return None

def save_current_states():
    print("🔍 Sprawdzanie aktualnego stanu świateł...")
    
    for light_id, light_info in LIGHTS.items():
        print(f"   Pobieranie stanu: {light_info['name']}")
        status = get_light_status(light_id)
        
        if status:
            original_states[light_id] = status
            state_text = "ON" if status['state'] else "OFF"
            if status['state']:
                print(f"   ✅ {light_info['name']}: {state_text}, Jasność: {status['brightness']}%, RGB: ({status['r']}, {status['g']}, {status['b']})")
            else:
                print(f"   ✅ {light_info['name']}: {state_text}")
        else:
            # Default fallback state
            original_states[light_id] = {
                'state': False,
                'brightness': 100,
                'r': 255,
                'g': 255,
                'b': 255
            }
            print(f"   ⚠️  {light_info['name']}: Nie można pobrać stanu, używam domyślnego (OFF)")

def restore_original_states():
    print("\n🔄 Przywracanie oryginalnego stanu świateł...")
    
    for light_id, original_state in original_states.items():
        light_info = LIGHTS[light_id]
        print(f"   Przywracanie: {light_info['name']}")
        
        if original_state['state']:
            payload = {
                "id": 1,
                "method": "setPilot",
                "params": {
                    "state": True,
                    "dimming": original_state['brightness'],
                    "r": original_state['r'],
                    "g": original_state['g'],
                    "b": original_state['b']
                }
            }
        else:
            # Light was off
            payload = {
                "id": 1,
                "method": "setPilot",
                "params": {"state": False}
            }
        
        if send_command(light_id, payload):
            state_text = "ON" if original_state['state'] else "OFF"
            print(f"   ✅ {light_info['name']}: {state_text}")
        else:
            print(f"   ❌ {light_info['name']}: Błąd przywracania")

def set_alarm_mode():
    alarm_payload = {
        "id": 1,
        "method": "setPilot",
        "params": {
            "state": True,
            "dimming": 100,
            "r": 255,
            "g": 0,
            "b": 0
        }
    }
    
    for light_id, light_info in LIGHTS.items():
        send_command(light_id, alarm_payload)

def turn_off_all():
    off_payload = {
        "id": 1,
        "method": "setPilot",
        "params": {"state": False}
    }
    
    for light_id in LIGHTS.keys():
        send_command(light_id, off_payload)

def signal_handler(sig, frame):
    print("\n\n🛑 ZATRZYMYWANIE ALARMU...")
    restore_original_states()
    print("\n✅ Alarm zatrzymany. Światła przywrócone do oryginalnego stanu.")
    sys.exit(0)

def print_alarm_banner():
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                          🚨 ALARM 🚨                          ║
║                                                              ║
║                    SYSTEM ALARMOWY AKTYWNY                   ║
║                                                              ║
║              Naciśnij Ctrl+C aby zatrzymać alarm             ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)

def run_alarm():
    print_alarm_banner()
    
    flash_count = 0
    start_time = time.time()
    
    try:
        while True:
            # Flash on (red)
            print(f"🔴 ALARM AKTYWNY - Błysk #{flash_count + 1} - Czas: {int(time.time() - start_time)}s", end='\r')
            set_alarm_mode()
            time.sleep(0.5)
            
            # Flash off
            print(f"⚫ ALARM AKTYWNY - Błysk #{flash_count + 1} - Czas: {int(time.time() - start_time)}s", end='\r')
            turn_off_all()
            time.sleep(0.5)
            
            flash_count += 1
            
    except KeyboardInterrupt:
        signal_handler(None, None)

def main():
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚨 SYSTEM ALARMOWY 🚨")
    print("=" * 50)
    
    # Save current states before starting alarm
    save_current_states()
    
    print("\n⚠️  URUCHAMIANIE ALARMU ZA 3 SEKUNDY...")
    for i in range(3, 0, -1):
        print(f"   {i}...")
        time.sleep(1)
    
    # Start alarm
    run_alarm()

if __name__ == "__main__":
    main()