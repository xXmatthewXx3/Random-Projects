import os, re, time
from rich.console import Console
from openai import OpenAI
from dotenv import load_dotenv

console = Console()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Accept [pause], [pause=600ms], [pause=0.6s], and [wait=...], case-insensitive
PAUSE_TAG = re.compile(r"\[\s*(?:pause|wait)(?:\s*=\s*(\d+(?:\.\d+)?)\s*(ms|s)?)?\s*\]", re.IGNORECASE)

SYSTEM_PROMPT = (
    "You are a concise assistant. Pace your replies like natural human speech (~140 wpm). "
    "Insert [pause=120ms] at short clause boundaries (commas/;/:/). "
    "Insert [pause=380ms] at sentence endings (.?!). "
    "Occasionally use a longer [pause=600ms] before key points or topic shifts. "
    "Use pauses sparingly; only where they aid rhythm and clarity. "
    "When including code, do NOT put pause tags inside code blocks—only in surrounding prose. "
    "Keep answers short."
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

TAG_RE = re.compile(r"^\[\s*(?:pause|wait)(?:\s*=\s*(\d+(?:\.\d+)?)\s*(ms|s)?)?\s*\]$", re.IGNORECASE)
_tag_buf = "" 

def _emit(text: str, style: str = "cyan", ch_delay: float = 0.02):
    for ch in text:
        console.print(ch, end="", style=style, highlight=False, markup=False, soft_wrap=False)
        console.file.flush()
        extra = 0.0
        if ch in ".!?": extra = 0.35
        elif ch in ",;:": extra = 0.12
        elif ch == "\n": extra = 0.25
        time.sleep(ch_delay + extra)

def _sleep_for_tag(match) -> None:
    num = match.group(1)
    unit = (match.group(2) or "").lower() if num else ""
    if num:
        val = float(num)
        dur_sec = val / 1000.0 if unit.startswith("ms") or unit == "" else val
    else:
        dur_sec = 0.5
    time.sleep(dur_sec)

def _process_pending(text: str, final: bool = False) -> None:
    global _tag_buf
    plain = []

    def flush_plain():
        if plain:
            _emit("".join(plain))
            plain.clear()

    for ch in text:
        if _tag_buf:
            _tag_buf += ch
            if ch == "]":
                m = TAG_RE.match(_tag_buf)
                if m:
                    flush_plain()
                    _sleep_for_tag(m)
                else:
                    flush_plain()
                    _emit(_tag_buf)
                _tag_buf = ""
        else:
            if ch == "[":
                _tag_buf = "["
            else:
                plain.append(ch)

    flush_plain()

    if final and _tag_buf:
        _emit(_tag_buf)
        _tag_buf = ""

def stream_assistant(messages, style="cyan", ch_delay=0.02) -> str:
    full = []
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        stream=True,
    )
    console.print("\nAssistant:", style="magenta")
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue
        full.append(delta)
        _process_pending(delta, final=False)
    _process_pending("", final=True)
    console.print()  # newline
    return "".join(full)

def main():
    if not os.getenv("OPENAI_API_KEY"):
        console.print("Set OPENAI_API_KEY in your environment.", style="red")
        return
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    console.print("Simple Chat. Ctrl+C to exit.", style="green")
    try:
        while True:
            user = input("\nYou: ").strip()
            if not user: 
                continue
            messages.append({"role": "user", "content": user})
            assistant = stream_assistant(messages)
            messages.append({"role": "assistant", "content": assistant})
    except (KeyboardInterrupt, EOFError):
        console.print("\nBye.", style="yellow")

if __name__ == "__main__":
    main()