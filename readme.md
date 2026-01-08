# My Python Projects

A repository containing a collection of my smaller projects, scripts, and experiments. It includes tools for IoT control, working with text user interfaces (TUI), API integrations, and AI handling.

## Project List

### 🏠 IoT and Smart Home (WiZ Lights)
Projects related to controlling WiZ lighting via the UDP protocol.

*   **`disco.py`** – The most advanced script in this collection. Features a bulb detection system (`discover`) and various lighting effect modes (party, strobe, rainbow).
*   **`światła2.py`** – Terminal control panel (TUI) based on the `curses` library. Allows convenient color and brightness adjustment using keyboard arrows.
*   **`alarm.py`** – Home alarm simulation. Saves the current light state, triggers intense red flashes, and restores the original settings upon completion.
*   **`światła.py`** – Simple CLI (Command Line Interface) for quickly switching specific lamps on/off from the console.

> **Important:** Some scripts (like `światła.py`) have hardcoded local device IP addresses. You must adjust them in the code before use.

### 📰 Media and Info
*   **`RSS.py`** – Console news reader. Fetches headlines from RSS feeds (e.g., RMF24) and uses `BeautifulSoup` to retrieve full article content without leaving the terminal.

### 📡 Communication and API
*   **`sms.py`** – SMS gateway client (`szybkisms.pl`). Used for sending messages (including Flash types) and checking costs/balance directly from the command line.
*   **`chat.py`** – Experiment with the OpenAI API (GPT-4o-mini). An interesting feature is the "human typing" simulation – the bot doesn't output text immediately but pauses and makes typos to make the conversation look natural.

---

## How to run?

### 1. Environment Setup
Install required libraries (list generated from my environment):
```bash
pip install -r requirements.txt
```

### 2. Ustawienie pliku .env
For `sms.py` and `chat.py` GATEWAY_API_BEARER and OPENAI_API_KEY are required respectively.