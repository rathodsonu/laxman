import speech_recognition as sr
import pyttsx3
import os
import threading
import time
import pygame
import re
import webbrowser
import requests
import subprocess
from urllib.parse import quote_plus
from flask import Flask, render_template 


# =================== CONFIGURATION ===================

app = Flask(__name__)

SYSTEM32_TASKKILL = r"C:\Windows\System32\taskkill.exe"

pygame.mixer.init()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------- Quick Links ----------------
QUICK_LINKS = {
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "github": "https://github.com"
}

# ---------------- Local Apps Paths ----------------
APPS_PATHS = {
    "whatsapp": r"C:\Users\YourUserName\AppData\Local\WhatsApp\WhatsApp.exe",  # बदलो
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe"
}

# ---------------- Helpers ----------------
assistant_running = True

def play_tone(filename):
    try:
        path = os.path.join(BASE_DIR, "sounds", filename)
        if os.path.exists(path):
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
    except Exception as e:
        print("Sound error:", e)

def speak(text):
    play_tone("google_start.mp3")
    print("Assistant:", text)
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        voices = engine.getProperty("voices")
        engine.setProperty("voice", voices[1].id if len(voices) > 1 else voices[0].id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print("Speech error:", e)
    play_tone("google_end.mp3")

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Calibrating for background noise...")
        r.adjust_for_ambient_noise(source, duration=1)
        r.energy_threshold = 400
        print("Listening...")
        try:
            audio = r.listen(source, phrase_time_limit=6)
            query = r.recognize_google(audio, language="en-IN")
            print("You said:", query)
            return query.lower().strip()
        except sr.UnknownValueError:
            speak("Sorry, I couldn't understand.")
            return ""
        except sr.RequestError:
            speak("Internet connection issue.")
            return ""

# ---------------- Keyword Normalization ----------------
def normalize(text: str) -> str:
    replacements = {
        "khol": "open", "kholo": "open", "khole": "open", " kholo": " open",
        "band karo": "close", "band": "close",
        "chalu": "open", "chalu karo": "open",
        "dhoond": "search", "dhundo": "search", "search karo": "search",
        "map": "maps", "naksha": "maps",
        "gana": "song", "gaana": "song", "music": "song",
        "chaloo": "open", "chrome kholo": "open chrome",
    }
    t = " " + text + " "
    for k, v in replacements.items():
        t = t.replace(f" {k} ", f" {v} ")
    return " ".join(t.split())

def is_math_expr(s: str) -> bool:
    return bool(re.fullmatch(r"[0-9\.\+\-\*/\(\) ]+", s.replace(" ", "")))

def ensure_url(s: str) -> str:
    s = s.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if "." in s and " " not in s:
        return "https://" + s
    return s

# ---------------- YouTube Direct Play ----------------
def play_song_on_youtube(song_name):
    try:
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(song_name)}"
        html = requests.get(search_url).text
        video_ids = re.findall(r"watch\?v=(\S{11})", html)
        if video_ids:
            first_video_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
            webbrowser.open(first_video_url)
            return True
    except Exception as e:
        print("Error playing song:", e)
    return False

# ---------------- Action Executors ----------------
def open_website(url_or_query: str):
    url_or_query = url_or_query.strip()
    if url_or_query in QUICK_LINKS:
        webbrowser.open(QUICK_LINKS[url_or_query])
        return True
    if "." in url_or_query and " " not in url_or_query:
        webbrowser.open(ensure_url(url_or_query))
        return True
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(url_or_query)}")
    return True

def open_file_or_here(target: str):
    path = target.strip().strip('"').strip("'")
    if os.path.isabs(path) and os.path.exists(path):
        os.startfile(path)
        return True
    else:
        candidate = os.path.join(BASE_DIR, path)
        if os.path.exists(candidate):
            os.startfile(candidate)
            return True
    return False

def open_app(app_name: str):
    app_name = app_name.lower().strip()
    if app_name in APPS_PATHS:
        try:
            os.startfile(APPS_PATHS[app_name])
            speak(f"Opening {app_name}")
        except Exception as e:
            speak(f"Error opening {app_name}: {e}")
    elif app_name.endswith(".exe") and os.path.exists(app_name):
        try:
            os.startfile(app_name)
            speak(f"Opening {app_name}")
        except Exception as e:
            speak(f"Error opening {app_name}: {e}")
    else:
        speak(f"I don't know how to open {app_name}, searching online.")
        open_website(app_name)

def close_app(app_name: str):
    app_name = app_name.lower().strip()
    exe_name = None

    # Check if it's a known local app
    if app_name in APPS_PATHS:
        exe_name = os.path.basename(APPS_PATHS[app_name])
    elif app_name.endswith(".exe"):
        exe_name = app_name

    # Close normal apps
    if exe_name:
        try:
            subprocess.run([SYSTEM32_TASKKILL, "/F", "/IM", exe_name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            speak(f"Closed {app_name}")
            return
        except Exception as e:
            speak(f"Error closing {app_name}: {e}")
            return

    # Handle browsers and web apps (Edge version)
    browser_processes = {
        "edge": "msedge.exe",
        "youtube": "msedge.exe",
        "google": "msedge.exe",
        "gmail": "msedge.exe",
        "facebook": "msedge.exe",
        "instagram": "msedge.exe",
        "maps": "msedge.exe",
        "whatsapp": "msedge.exe",
        "github": "msedge.exe"
    }

    if app_name in browser_processes:
        try:
            subprocess.run([SYSTEM32_TASKKILL, "/F", "/IM", browser_processes[app_name]],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            speak(f"Closed {app_name}")
            return
        except Exception as e:
            speak(f"Error closing {app_name}: {e}")
            return

    speak(f"I don't know how to close {app_name}")



# ---------------- Command Processor ----------------
def process_command(command: str):
    global assistant_running
    if not command:
        return True

    t = normalize(command)

    if any(k in t for k in ["exit", "quit", "stop assistant", "goodbye"]):
        speak("Goodbye!")
        assistant_running = False
        return False

    if t.startswith("close ") or t.startswith("stop "):
        app_name = t.replace("close ", "").replace("stop ", "").strip()
        close_app(app_name)
        return True

    if is_math_expr(t.replace(" ", "")):
        try:
            result = eval(t)
            speak(f"The answer is {result}")
        except Exception:
            speak("Sorry, I couldn't calculate that.")
        return True

    if t.startswith("open "):
        rest = t[5:].strip()
        if rest in APPS_PATHS or rest.endswith(".exe"):
            open_app(rest)
            return True
        if rest in QUICK_LINKS or "." in rest:
            open_website(rest)
            return True
        if open_file_or_here(rest):
            speak(f"Opening file {rest}")
            return True
        speak(f"Searching for {rest}")
        open_website(rest)
        return True

    if t.startswith("search ") or t.startswith("google "):
        q = t.split(" ", 1)[1] if " " in t else ""
        if q:
            speak(f"Searching for {q}")
            open_website(q)
            return True

    if "youtube" in t or t.startswith("play "):
        q = t.replace("youtube", "").replace("play", "").strip()
        if not q:
            q = "trending music"
        speak(f"Playing on YouTube: {q}")
        if not play_song_on_youtube(q):
            webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(q)}")
        return True

    if "maps" in t or t.startswith("navigate ") or "directions" in t:
        place = t.replace("navigate", "").replace("directions", "").replace("maps", "").strip()
        if not place:
            place = "nearby places"
        speak(f"Opening maps for {place}")
        webbrowser.open(f"https://www.google.com/maps/search/{quote_plus(place)}")
        return True

    if "wikipedia" in t:
        topic = t.replace("wikipedia", "").strip()
        if not topic:
            topic = "Main Page"
        speak(f"Opening Wikipedia for {topic}")
        webbrowser.open(f"https://en.wikipedia.org/w/index.php?search={quote_plus(topic)}")
        return True

    speak(f"Searching for {command}")
    open_website(command)
    return True

# ---------------- Main Loop ----------------
def main():
    global assistant_running
    assistant_running = True
    speak("Say 'hello ravan' to start.")

    while assistant_running:
        wake = listen()
        if "hello ravan" in wake:
            speak("Hi! How can I help you?")
            break
        time.sleep(0.3)

    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=1)
        while assistant_running:
            print("Listening for commands...")
            try:
                audio = r.listen(source, phrase_time_limit=7)
                cmd = r.recognize_google(audio, language="en-IN")
                print("You said:", cmd)
                if not process_command(cmd.lower()):
                    break
            except sr.UnknownValueError:
                speak("Sorry, I didn't catch that.")
            except sr.RequestError:
                speak("Internet problem.")
            time.sleep(0.6)

# ---------------- FLASK Routes ----------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/start-assistant")
def start_assistant():
    threading.Thread(target=main).start()
    return 'Voice assistant started! Say "hello ravan".'

# ---------------- Run ----------------
if __name__ == "__main__":
    app.run(debug=True)
