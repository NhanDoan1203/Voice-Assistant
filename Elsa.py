"""
Elsa — Voice assistant powered by Gemini
"""

import os
import sys
import re
import json
import random
import webbrowser
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import speech_recognition as sr
import sounddevice as sd
from scipy.io.wavfile import write as wav_write
import numpy as np
import playsound
from gtts import gTTS
import wikipedia
import yfinance as yf
import pyautogui

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


# ── Text-to-speech ────────────────────────────────────────────────────────────

SPEECH_RATE = 230
_tts_engine = None


def _speak_local(text: str) -> bool:
    global _tts_engine
    if pyttsx3 is None:
        return False

    try:
        if _tts_engine is None:
            _tts_engine = pyttsx3.init()
            _tts_engine.setProperty("rate", SPEECH_RATE)
        _tts_engine.say(str(text))
        _tts_engine.runAndWait()
        return True
    except Exception as e:
        print(f"  [local audio error: {e}]")
        return False


def speak(text: str):
    print(f"Elsa: {text}")
    if _speak_local(text):
        return

    try:
        tts = gTTS(text=str(text), lang='en')
        tmp = f"_elsa_tts_{random.randint(1, 9_999_999)}.mp3"
        tts.save(tmp)
        playsound.playsound(tmp)
        os.remove(tmp)
    except Exception as e:
        print(f"  [audio error: {e}]")


# ── Speech-to-text ────────────────────────────────────────────────────────────

_recognizer = sr.Recognizer()

def _record_and_transcribe(duration: float = 6, tmp: str = "_elsa_mic.wav") -> str:
    fs = 16_000
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    wav_write(tmp, fs, audio)
    text = ""
    try:
        with sr.AudioFile(tmp) as src:
            data = _recognizer.record(src)
        text = _recognizer.recognize_google(data)
    except sr.UnknownValueError:
        text = ""
    except sr.RequestError:
        speak("Speech recognition is unavailable right now.")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return text.lower()


def listen(prompt: str = "") -> str:
    if prompt:
        speak(prompt)
    print("Elsa: (listening...)")
    text = _record_and_transcribe()
    if not text:
        speak("I didn't catch that, could you say it again?")
    print(f"You: {text}")
    return text


def _detect_clap(duration: float = 0.35, threshold: int = 12000) -> bool:
    fs = 16_000
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    return int(np.max(np.abs(audio))) >= threshold


def _wake_command(text: str) -> str | None:
    wake_phrases = ("hey elsa", "hi elsa", "hello elsa", "elsa", "wake up")
    for phrase in wake_phrases:
        if phrase in text:
            return text.split(phrase, 1)[1].strip(" ,.!?")
    return None


def wait_for_wake() -> str:
    print("Elsa: (standby - say 'hey Elsa', 'wake up', or clap)")
    while True:
        try:
            if _detect_clap():
                print("Elsa: (clap detected)")
                return ""
        except Exception as e:
            print(f"  [clap detection error: {e}]")

        text = _record_and_transcribe(duration=3, tmp="_elsa_wake.wav")
        if not text:
            continue

        print(f"Heard: {text}")
        command = _wake_command(text)
        if command is not None:
            return command


# ── Volume control ────────────────────────────────────────────────────────────

def set_volume(level: int):
    level = max(0, min(100, int(level)))
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetSpeakers()
        devices.EndpointVolume.SetMasterVolumeLevelScalar(level / 100.0, None)
    except Exception:
        from ctypes import windll
        vol = int(level * 0xFFFF / 100)
        windll.winmm.waveOutSetVolume(0, vol | (vol << 16))


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_search_web(query: str, site: str = "google") -> str:
    q = query.replace(" ", "+")
    urls = {
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "maps":    f"https://www.google.com/maps/search/{q}",
        "google":  f"https://www.google.com/search?q={q}",
    }
    webbrowser.get().open(urls.get(site, urls["google"]))
    return f"Opened {site} for: {query}"


def tool_get_stock(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is None:
            return {"error": f"Price unavailable for {symbol}"}
        return {
            "name":     info.get("shortName", symbol),
            "symbol":   symbol.upper(),
            "price":    round(price, 2),
            "currency": info.get("currency", "USD"),
        }
    except Exception as e:
        return {"error": str(e)}


def tool_take_screenshot() -> str:
    os.makedirs("D:/screenshot", exist_ok=True)
    path = "D:/screenshot/screen.png"
    pyautogui.screenshot().save(path)
    return f"Screenshot saved to {path}"


def tool_set_volume(level: int) -> str:
    set_volume(level)
    return f"Volume set to {level}%"


def tool_create_note(content: str) -> str:
    filename = str(datetime.now()).replace(":", "-") + "-note.txt"
    with open(filename, "w") as f:
        f.write(content)
    subprocess.Popen(["notepad.exe", filename])
    return f"Note saved to {filename}"


def tool_record_audio(seconds: int) -> str:
    fs = 44_100
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=2)
    sd.wait()
    wav_write("Myrecording.wav", fs, audio)
    return f"Recorded {seconds}s to Myrecording.wav"


def tool_coin_flip() -> str:
    return random.choice(["heads", "tails"])


def tool_rock_paper_scissors(player_move: str) -> dict:
    moves = ["rock", "paper", "scissors"]
    computer = random.choice(moves)
    player = player_move.lower().strip()
    if player not in moves:
        return {"error": f"'{player}' is not a valid move"}
    wins_against = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    if player == computer:
        outcome = "draw"
    elif wins_against[player] == computer:
        outcome = "player wins"
    else:
        outcome = "computer wins"
    return {"player": player, "computer": computer, "outcome": outcome}


def tool_get_wikipedia(topic: str) -> dict:
    try:
        summary = wikipedia.summary(topic, sentences=2)
        webbrowser.get().open(
            "https://en.wikipedia.org/wiki/" + topic.replace(" ", "_")
        )
        return {"summary": summary}
    except wikipedia.exceptions.DisambiguationError as e:
        return {"error": f"Ambiguous topic. Options: {', '.join(e.options[:4])}"}
    except wikipedia.exceptions.PageError:
        return {"error": f"No Wikipedia page found for '{topic}'"}
    except Exception as e:
        return {"error": str(e)}


def tool_shutdown(action: str) -> str:
    if action == "restart":
        subprocess.Popen(["shutdown", "-r", "-t", "5"])
        return "Restarting in 5 seconds"
    else:
        subprocess.Popen(["shutdown", "-s", "-t", "5"])
        return "Shutting down in 5 seconds"


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Open a browser to search Google, YouTube, or Google Maps. "
                "Use for web searches, weather, news, location lookups, and anything "
                "that benefits from a live search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "site":  {
                        "type": "string",
                        "enum": ["google", "youtube", "maps"],
                        "description": "Which site to use (default: google)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": (
                "Get the current price of a stock or cryptocurrency. "
                "Accepts any valid Yahoo Finance ticker symbol (AAPL, TSLA, BTC-USD, ETH-USD, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Ticker symbol, e.g. AAPL, MSFT, BTC-USD",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture the current screen and save it as an image file.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set the system speaker volume to a specific percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Volume level from 0 (mute) to 100 (max)",
                    }
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "Save a note or reminder to a text file and open it in Notepad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The text content of the note"}
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_audio",
            "description": "Record audio from the microphone for a specified number of seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "How many seconds to record (max 300)",
                    }
                },
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "coin_flip",
            "description": "Flip a coin and return heads or tails.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rock_paper_scissors",
            "description": (
                "Play a round of rock-paper-scissors against the computer. "
                "If the player's move is unknown, ask for it first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "player_move": {
                        "type": "string",
                        "description": "The player's choice: rock, paper, or scissors",
                    }
                },
                "required": ["player_move"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wikipedia",
            "description": (
                "Look up a topic on Wikipedia and open the page in the browser. "
                "Good for definitions, facts, and explanations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic to look up"}
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown_computer",
            "description": "Shut down or restart the computer. Always confirm with the user before calling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["shutdown", "restart"],
                        "description": "Whether to shut down or restart",
                    }
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exit_elsa",
            "description": "Exit and close the Elsa assistant when the user says goodbye or asks to quit.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_FN = {
    "search_web":          lambda i: tool_search_web(i["query"], i.get("site", "google")),
    "get_stock_price":     lambda i: tool_get_stock(i["symbol"]),
    "take_screenshot":     lambda i: tool_take_screenshot(),
    "set_volume":          lambda i: tool_set_volume(int(i["level"])),
    "create_note":         lambda i: tool_create_note(i["content"]),
    "record_audio":        lambda i: tool_record_audio(min(int(i["seconds"]), 300)),
    "coin_flip":           lambda i: tool_coin_flip(),
    "rock_paper_scissors": lambda i: tool_rock_paper_scissors(i["player_move"]),
    "get_wikipedia":       lambda i: tool_get_wikipedia(i["topic"]),
    "shutdown_computer":   lambda i: tool_shutdown(i["action"]),
    "exit_elsa":           lambda _: "__exit__",
}


# ── Gemini engine ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""\
You are Elsa, a smart, warm, and witty AI voice assistant running on the user's PC.
Today is {datetime.now().strftime('%A, %B %d, %Y')}.

Rules for your responses:
- Your replies are spoken aloud via text-to-speech, so write in natural spoken language.
- Be concise: 1 to 3 sentences is ideal. Only go longer when the user genuinely needs detail.
- Never use markdown, bullet points, headers, or special characters — they sound awful when spoken.
- Be conversational, friendly, and occasionally playful. You have a personality.
- Answer factual questions directly from your knowledge when no tool is needed.
- Use tools when the user wants a real action (search, stock price, screenshot, etc.).
- Remember context across the conversation and refer back to earlier topics naturally.
- If you are unsure what the user wants, ask a short clarifying question.
- For rock-paper-scissors: if the user has not said their move yet, ask for it before calling the tool.\
"""

_conversation: list[dict] = []
_gemini_api_key: str | None = None
GEMINI_MODEL = "gemini-2.5-flash"


def _load_gemini_api_key() -> str | None:
    """Load the Gemini API key from the environment or a local .env file."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return api_key.strip().strip('"').strip("'")

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return None

    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            if key.strip() in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
                return value.strip().strip('"').strip("'")

    return None


def _run_tool(name: str, tool_input: dict) -> str:
    """Execute a tool, handling voice-prompt cases inline."""
    if name == "rock_paper_scissors" and not tool_input.get("player_move"):
        move = listen("What's your move — rock, paper, or scissors?")
        tool_input["player_move"] = move

    if name == "record_audio" and "seconds" not in tool_input:
        dur_str = listen("How many seconds would you like to record?")
        nums = re.findall(r"\d+", dur_str)
        tool_input["seconds"] = int(nums[0]) if nums else 5

    fn = TOOL_FN.get(name)
    if fn is None:
        return f"Unknown tool: {name}"

    result = fn(tool_input)
    return json.dumps(result) if isinstance(result, dict) else str(result)


def _gemini_tool_declarations() -> list[dict]:
    """Convert Elsa's tool list into Gemini function declarations."""
    declarations = []
    for tool in TOOLS:
        fn = tool.get("function", tool)
        declarations.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return declarations


def _gemini_generate_content(contents: list[dict]) -> dict:
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "tools": [{"functionDeclarations": _gemini_tool_declarations()}],
        "generationConfig": {"maxOutputTokens": 512},
    }
    query = urllib.parse.urlencode({"key": _gemini_api_key})
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent?{query}"
    )
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            error_body = json.loads(e.read().decode("utf-8"))
            message = error_body.get("error", {}).get("message", str(e))
        except Exception:
            message = str(e)

        if e.code in {400, 403}:
            raise RuntimeError(
                "Gemini rejected this API key or request. Please check that the key is correct "
                "and the Gemini API is enabled for your Google project. "
                f"Details: {message}"
            ) from e
        if e.code == 429:
            raise RuntimeError(
                "Gemini is rate limiting this key or it has no available quota. "
                f"Details: {message}"
            ) from e
        raise RuntimeError(f"Gemini returned an error: {message}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            "I could not reach Gemini. Please check your internet connection and try again."
        ) from e


def _gemini_parts(response: dict) -> list[dict]:
    candidates = response.get("candidates") or []
    if not candidates:
        return []
    return candidates[0].get("content", {}).get("parts", []) or []


def respond_to(user_text: str) -> str | None:
    """Send a message to Gemini, handle any tool calls, return the spoken reply."""
    global _conversation

    _conversation.append({"role": "user", "parts": [{"text": user_text}]})

    while True:
        try:
            response = _gemini_generate_content(_conversation)
        except RuntimeError as e:
            return str(e)

        parts = _gemini_parts(response)
        function_calls = [part["functionCall"] for part in parts if "functionCall" in part]

        # No tool calls — final text reply
        if not function_calls:
            reply = "".join(part.get("text", "") for part in parts).strip()
            if reply:
                _conversation.append({"role": "model", "parts": [{"text": reply}]})
            if len(_conversation) > 30:
                _conversation = _conversation[-30:]
            return reply or None

        # Store the assistant message (with tool_calls) in history
        _conversation.append({"role": "model", "parts": parts})

        # Execute each tool and append results
        for function_call in function_calls:
            name = function_call.get("name", "")
            args = function_call.get("args", {}) or {}

            print(f"  [tool: {name} {args}]")

            if name == "exit_elsa":
                speak("It was great talking with you. Goodbye!")
                sys.exit(0)

            result_str = _run_tool(name, args)

            _conversation.append({
                "role": "function",
                "parts": [{
                    "functionResponse": {
                        "name": name,
                        "response": {"result": result_str},
                    }
                }],
            })

        # Loop so Gemini can formulate its reply now that it has the tool results


# ── Startup ───────────────────────────────────────────────────────────────────

def _greeting() -> str:
    h = datetime.now().hour
    if h < 12:  return "Good morning"
    if h < 17:  return "Good afternoon"
    if h < 21:  return "Good evening"
    return "Good night"


def main():
    global _gemini_api_key

    api_key = _load_gemini_api_key()
    if not api_key:
        print(
            "\nERROR: GEMINI_API_KEY environment variable is not set.\n"
            "Set it in PowerShell for this terminal:\n"
            "  $env:GEMINI_API_KEY = 'YOUR_GEMINI_API_KEY'\n\n"
            "Or create D:\\Code\\Py\\.env with:\n"
            "  GEMINI_API_KEY=YOUR_GEMINI_API_KEY\n\n"
            "Then re-run Elsa.\n"
        )
        sys.exit(1)

    _gemini_api_key = api_key

    speak(
        f"{_greeting()}! I'm Elsa, your AI assistant. "
        "Say hey Elsa, say wake up, or clap when you need me."
    )

    while True:
        user_input = wait_for_wake()
        if not user_input:
            user_input = listen("I'm listening.")
        if not user_input:
            continue

        reply = respond_to(user_input)
        if reply:
            speak(reply)


if __name__ == "__main__":
    main()
