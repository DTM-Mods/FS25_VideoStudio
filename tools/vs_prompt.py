"""The step window: what you do now, on screen while the runner films (python vs_prompt.py <file>).

A small window beside the game window (on top of it if the screen has no room). The recorder only grabs
the game window (Windows Graphics Capture), so this window is never in the video. It never takes the
focus and clicks go through it, so the game keeps the keyboard and mouse.

The runner (fs25_video.py run / mod / batch) writes what to show into <VIDEOS>/prompt.json; the window
reads it a few times a second and closes when the runner says so or is gone.

A plan can have steps you do by hand during one clip: "hand" in the plan, and hand=1 on that clip's step:
    "steps": ["vsEnter", "vsShot ui dur=90 hand=1"],
    "hand": [{"at": 0, "do": "Press F1", "why": "The help box opens"},
             {"at": 18, "do": "Press ESC, then the gear icon"}, ...]
"at" is seconds into the clip; each one shows with a countdown to the next.
"""
import json, os, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vs_common import VIDEOS  # noqa: E402

PROMPT_FILE = os.path.join(VIDEOS, "prompt.json")
LEAD_S = 2.0        # the clip's log line comes before its START card and the settle: the footage starts later
HAND_WORD = "hand="


def hand_of(step):
    """'3/9 vsShot ui dur=90 hand=FS25_F1Toggle' -> 'FS25_F1Toggle' (or None)."""
    for w in (step or "").split():
        if w.startswith(HAND_WORD):
            return w[len(HAND_WORD):]
    return None


def step_seconds(step):
    """About how long a step takes, for the progress bar: its clips and its waits."""
    w = step.split()
    if not w:
        return 1
    opts = dict(x.split("=", 1) for x in w if "=" in x)
    try:
        dur = float(opts.get("dur", 0))
    except ValueError:
        dur = 0
    if w[0] == "vsShowcase":
        return {"quick": 50, "building": 80, "work": 60}.get(w[1] if len(w) > 1 else "", 95)
    if w[0] == "vsShot":
        shot = w[1] if len(w) > 1 else ""
        return 70 if shot == "colors" and not dur else (dur or 9) + 3
    if w[0] == "wait":
        try:
            return float(w[1])
        except (IndexError, ValueError):
            return 1
    return {"vsLight": 4, "vsMove": 6, "vsEnter": 2, "vsPower": 4, "quit": 1}.get(w[0], 1.5)


class Progress:
    """The whole set: which mod is being filmed and about how far along, from the autorun steps."""
    def __init__(self, steps, titles=None, clock=time.time, cues=None):
        self.steps, self.clock = list(steps or []), clock
        def hand_seconds(s):          # a clip filmed by hand: as long as its steps
            c = (cues or {}).get(hand_of(s) or "")
            return c[-1].get("at", 0) + c[-1].get("len", 10) + LEAD_S + 4 if c else step_seconds(s)
        self.weights = [hand_seconds(s) for s in self.steps]
        self.total = sum(self.weights) or 1
        self.mod_at, mods, cur = [], [], None
        for s in self.steps:
            w = s.split()
            if w[:1] == ["vsFolder"] and len(w) > 1:
                cur = w[1]
                if cur not in mods:
                    mods.append(cur)
            self.mod_at.append(cur)
        self.mods, self.titles = mods, titles or {}
        self.index, self.since = None, None

    def at(self, step):
        """The bar for the autorun's 'N/M ...' step line: {frac, label, left}."""
        if not self.steps:
            return None
        now = self.clock()
        try:
            n = int((step or "0/0").split("/", 1)[0]) - 1
        except ValueError:
            n = -1
        if n != self.index:
            self.index, self.since = n, now
        if n < 0:
            return {"frac": 0.0, "label": "Starting", "left": self.total}
        n = min(n, len(self.steps) - 1)
        done = sum(self.weights[:n]) + min(now - self.since, self.weights[n])
        frac = max(0.0, min(1.0, done / self.total))
        mod = self.mod_at[n]
        label = ""
        if mod and len(self.mods) > 1:
            label = f"Mod {self.mods.index(mod) + 1} of {len(self.mods)}: {self.titles.get(mod, mod)}"
        elif mod:
            label = self.titles.get(mod, mod)
        return {"frac": round(frac, 3), "label": label, "left": round(self.total - done)}


SAYS = {   # what a step does, in plain words, for the step window
    "vsFarmName": "Renaming the farms for the video (only for this session)",
    "vsSpawn": "Loading the machine from the shop (not saved)",
    "vsEnter": "Getting in (or next to) the machine",
    "vsTarget": "Picking what to film",
    "vsFolder": "Starting the next mod",
    "vsLight": "Setting the light and the time of day",
    "vsMove": "Moving the machine to open ground the camera can go round",
    "vsShowcase": "Filming the camera moves round it (about a minute and a half)",
    "vsPower": "Starting the engine",
    "vsWork": "Unfolding and switching on",
    "vsDrive": "Driving",
    "vsMenu": "Closing any menu left open",
    "vsTab": "Opening a tab",
    "wait": "Waiting for things to settle",
    "quit": "Closing the game",
}
SHOTS = {"colors": "Filming every color", "orbit": "Filming a slow circle round it", "ui": "Filming the screen"}


def step_says(step):
    """'11/36 vsShowcase' -> 'Filming the camera moves round it ...'."""
    cmd = (step or "").partition(" ")[2].split()
    if not cmd:
        return ""
    if cmd[0] == "vsShot":
        return SHOTS.get(cmd[1] if len(cmd) > 1 else "", "Filming a camera move")
    if cmd[0] == "vsMove" and len(cmd) > 1 and cmd[1] == "back":
        return "Putting the machine back where it was"
    if cmd[0] == "vsLight" and len(cmd) > 1 and cmd[1] == "off":
        return "Putting the time of day back"
    return SAYS.get(cmd[0], "")


def step_text(step):
    """'5/12 vsShot orbit dur=8' -> 'step 5 of 12 (vsShot orbit)'."""
    if not step:
        return ""
    num, _, cmd = step.partition(" ")
    a, _, b = num.partition("/")
    words = [w for w in cmd.split() if "=" not in w][:3]
    return f"Step {a} of {b}" + (f": {' '.join(words)}" if words else "")


PAUSE_KEYS = (0xA1, 0x38)      # Right Shift + 8: pause / go on (the step starts over)
NEXT_KEYS = (0xA1, 0x39)       # Right Shift + 9: done, next step
STOP_KEYS = "rshift+0"         # Video Studio's stop: ends the clip filmed by hand after the last step
KEY_HELP = 'When you\'ve done it, say "next" (or "go", "done") or press Right Shift + 9.'
WORDS = {"next": "next", "next step": "next", "ready": "next", "done": "next", "go": "next",
         "pause": "pause", "wait": "pause", "go on": "resume", "continue": "resume"}
HERE = os.path.dirname(os.path.abspath(__file__))
LISTENER = os.path.join(HERE, "vs_listen.ps1")
SPEAKER = os.path.join(HERE, "vs_speak.ps1")
DEAF_AFTER_S = 0.8             # the voice control ignores this long after the spoken step ends (echo)


def key_down(vk):
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except (OSError, AttributeError):
        return False


def powershell(script, stdin=False):
    import subprocess
    return subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
                            stdin=subprocess.PIPE if stdin else None, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class Keys:
    """Right Shift + 8 / 9 read straight from the keyboard, so they work in every game menu too."""
    def __init__(self, read=key_down, poll=0.03):
        self.read, self.poll = read, poll
        self.events, self.down = [], {}
        self.lock = threading.Lock()
        self.stopped = threading.Event()

    def check(self):
        for name, (a, b) in (("pause", PAUSE_KEYS), ("next", NEXT_KEYS)):
            d = self.read(a) and self.read(b)
            if d and not self.down.get(name):
                self.push(name)
            self.down[name] = d

    def start(self):
        def loop():
            while not self.stopped.wait(self.poll):
                self.check()
        threading.Thread(target=loop, daemon=True).start()
        return self

    def take(self):
        with self.lock:
            ev, self.events = self.events, []
        return ev

    def push(self, event):
        with self.lock:
            self.events.append(event)

    def stop(self):
        self.stopped.set()


class Voice:
    """Says each step out loud (vs_speak.ps1) and listens for your answer (vs_listen.ps1): Windows' own offline
    speech, a few words only. It doesn't listen while it speaks, so its own words don't count as yours. The
    microphone is never in the video; the speakers are (the game sound), so plans filmed by hand leave the game
    sound out (game_audio 0)."""
    def __init__(self, keys, echo=print, clock=time.time):
        self.keys, self.echo, self.clock = keys, echo, clock
        self.listener = self.speaker = None
        self.deaf_until = 0.0
        self.speaking = False
        self.heard = None

    def feed(self, line):
        """A line from the listener: 'next|0.91'. The event it makes, or None."""
        word, _, _ = line.strip().partition("|")
        ev = WORDS.get(word.strip().lower())
        if ev is None or self.speaking or self.clock() < self.deaf_until:
            return None
        self.keys.push(ev)
        self.heard = (word.strip(), self.clock())
        return ev

    def said(self):
        self.speaking = False
        self.deaf_until = self.clock() + DEAF_AFTER_S

    def say(self, text):
        if self.speaker is None or self.speaker.poll() is not None:
            return
        self.speaking = True
        try:
            self.speaker.stdin.write(text.replace("\n", " ") + "\n")
            self.speaker.stdin.flush()
        except OSError:
            self.speaking = False

    def start(self):
        try:
            self.speaker = powershell(SPEAKER, stdin=True)
            self.listener = powershell(LISTENER)
        except OSError as e:
            self.echo(f"! No voice ({e}): the keys still work")
            return self

        def read_speaker():
            for line in self.speaker.stdout:
                if line.strip() == "said":
                    self.said()

        def read_listener():
            for line in self.listener.stdout:
                if line.strip() == "listening":
                    self.echo("Voice on: it says each step and waits for next, go or done")
                else:
                    self.feed(line)
        threading.Thread(target=read_speaker, daemon=True).start()
        threading.Thread(target=read_listener, daemon=True).start()
        return self

    def stop(self):
        for p in (self.listener, self.speaker):
            if p is not None and p.poll() is None:
                p.kill()


class Director:
    """Tells you on screen (and out loud) what is going on and what to do. say() for a plain state, tick(watch)
    while the steps run: hands off, or your steps by hand. Each step waits for you: say "next" (go, done) or
    press Right Shift + 9; "pause" / Right Shift + 8 pauses (the step starts over when you go on, so the pause
    isn't in the video). After the last step it ends the clip (Video Studio's stop). times: {mod: when each step
    really started, seconds into the clip} for the cuts."""
    def __init__(self, cues=None, path=PROMPT_FILE, window=True, clock=time.time, steps=None, titles=None, keys=None,
                 voice=True):
        self.progress = Progress(steps, titles, clock, cues) if steps else None
        self.titles = titles or {}
        self.bar = None
        self.cues = {k: sorted(v, key=lambda c: c.get("at", 0)) for k, v in (cues or {}).items()}
        self.path, self.window, self.clock = path, window, clock
        self.keys = keys
        self.voice = voice
        self.proc = None
        self.hand = None          # the hand clip running: {mod, cues, t0, i, start, paused, stopped}
        self.times = {}
        self.seen_clips = 0
        self.last = None
        self.lock = threading.Lock()

    def start(self):
        self.say("wait", "Getting ready", "Nothing to do yet.")
        if self.keys is None and self.cues:
            self.keys = Keys().start()
            self.voice = Voice(self.keys).start() if self.voice is True else self.voice
        if self.window and self.proc is None:
            import subprocess
            exe = sys.executable
            w = os.path.join(os.path.dirname(exe), "pythonw.exe")
            try:
                self.proc = subprocess.Popen([w if os.path.isfile(w) else exe, os.path.abspath(__file__), self.path,
                                              str(os.getpid())])
            except OSError as e:
                print(f"! The step window didn't open: {e}")

    def speak(self, text):
        if isinstance(self.voice, Voice) or hasattr(self.voice, "say"):
            self.voice.say(text)

    def write(self, data):
        data = dict(data, pid=os.getpid(), bar=self.bar)
        with self.lock:
            if data == self.last:
                return
            self.last = data
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)

    def say(self, state, title, detail="", until=None, coming=None):
        """state: wait (hands off), you (your turn), ready (your turn soon), pause, done."""
        self.write({"state": state, "title": title, "detail": detail, "until": until, "next": coming})

    def title_of(self, mod):
        return self.titles.get(mod) or self.titles.get(mod.replace(" ", "_")) or mod.replace("FS25_", "")

    def _go(self, h, now, watch):
        """The next step (said out loud), or the end of the clip after the last one."""
        h["i"] += 1
        h["paused"] = False
        cues = h["cues"]
        if h["i"] < len(cues):
            h["start"] = now
            self.times[h["mod"]].append(round(now - h["t0"], 2))
            c = cues[h["i"]]
            first = f"Your turn: {self.title_of(h['mod'])}. " if h["i"] == 0 else ""
            self.speak(f"{first}{c.get('say') or c['do']}.")
        elif not h["stopped"]:
            h["stopped"] = now
            watch.keys.append(STOP_KEYS)
            self.speak("Thanks. Hands off now.")

    def tick(self, watch):
        now = self.clock()
        if self.progress is not None:
            self.bar = self.progress.at(watch.step)
        events = self.keys.take() if self.keys is not None else []
        mod = hand_of(watch.step)
        if len(watch.clips) > self.seen_clips:
            self.seen_clips = len(watch.clips)
            if mod and self.cues.get(mod):
                self.hand = {"mod": mod, "cues": self.cues[mod], "t0": now + LEAD_S, "i": -1, "start": None,
                             "paused": False, "stopped": None}
                self.times[mod] = []
            else:
                self.hand = None
        if self.hand is not None and mod is None:
            self.hand = None            # the hand clip is over: the next step started
        h = self.hand
        if h is not None:
            cues = h["cues"]
            if now < h["t0"]:
                self.say("ready", "Get ready: your turn", f"First: {cues[0]['do']}", until=h["t0"])
                return False
            if h["i"] < 0:
                self._go(h, now, watch)
            for ev in events:
                if h["i"] >= len(cues):
                    break
                if ev == "next":
                    self._go(h, now, watch)
                elif ev == "pause" or (ev == "resume" and h["paused"]):
                    h["paused"] = not h["paused"]
                    if h["paused"]:
                        self.speak("Paused. Say go on when you're back.")
                    else:                        # go on: the step starts over, the pause stays out of the video
                        h["start"] = now
                        self.times[h["mod"]][h["i"]] = round(now - h["t0"], 2)
                        self.speak(f"{cues[h['i']].get('say') or cues[h['i']]['do']}.")
            i = h["i"]
            if i >= len(cues):
                if h["stopped"] and now - h["stopped"] > 6 and not h.get("again"):
                    h["again"] = True
                    watch.keys.append(STOP_KEYS)      # once more, in case a menu swallowed it
                self.say("wait", "This part is done", "Hands off: the clip ends and the next one starts.")
                return False
            c = cues[i]
            after = cues[i + 1] if i + 1 < len(cues) else None
            if h["paused"]:
                self.say("pause", "Paused", 'Say "go on" or press Right Shift + 8: this step starts over, '
                         "so the pause isn't in the video.", coming=c["do"])
            else:
                why = (c.get("why", "") + "\n" if c.get("why") else "") + KEY_HELP
                self.say("you", c["do"], why, coming=after["do"] if after else "That's the last one")
        elif mod and self.cues.get(mod):
            self.say("ready", "Get ready: your turn", f"First: {self.cues[mod][0]['do']}")
        elif watch.step:
            self.say("wait", step_says(watch.step) or "Filming: hands off",
                     f"Hands off the keyboard and mouse, please.\n{step_text(watch.step)}")
        return False

    def close(self, title="Done", detail="The computer is yours."):
        if self.keys is not None:
            self.keys.stop()
        if hasattr(self.voice, "stop"):
            self.voice.stop()
        if self.bar is not None:
            self.bar = dict(self.bar, frac=1.0, left=0)
        self.say("done", title, detail)
        self.write({"state": "exit", "after": 8})


# ---------------------------------------------------------------- the window
COLORS = {"wait": ("#2b2f36", "#9aa3ad", "HANDS OFF"), "ready": ("#4a3a10", "#ffcc33", "GET READY"),
          "you": ("#0f3d1f", "#3ddc84", "YOUR TURN"), "done": ("#1d2a3a", "#6fb7ff", "DONE"),
          "pause": ("#3a1f3d", "#d68cff", "PAUSED"),
          "exit": ("#1d2a3a", "#6fb7ff", "DONE")}


def pid_alive(pid):
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259                        # STILL_ACTIVE
    except (OSError, AttributeError, ValueError):
        return True


def game_rect():
    """The game window's client area on screen (x, y, w, h), or None."""
    try:
        import ctypes
        from ctypes import wintypes
        import vs_game
        hwnd, _ = vs_game.game_window()
        if hwnd is None:
            return None
        u = ctypes.windll.user32
        r, o = wintypes.RECT(), wintypes.POINT()
        u.GetClientRect(hwnd, ctypes.byref(r))
        u.ClientToScreen(hwnd, ctypes.byref(o))
        return o.x, o.y, r.right, r.bottom
    except Exception:
        return None


def place(win_w, win_h, game, screen_w, screen_h, gap=16):
    """Where the window goes: right of the game, else left, else below, else on top of the game's corner."""
    if game is None:
        return screen_w - win_w - gap, gap
    x, y, w, h = game
    top = max(0, min(y, screen_h - win_h))
    if x + w + gap + win_w <= screen_w:
        return x + w + gap, top
    if x - gap - win_w >= 0:
        return x - gap - win_w, top
    if y + h + gap + win_h <= screen_h:
        return x, y + h + gap
    return x + w - win_w - gap, y + gap


def window(path, parent=None):
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        pass
    import tkinter as tk
    W, H = 640, 390
    root = tk.Tk()
    root.title("Video Studio: what to do")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.94)
    frame = tk.Frame(root, bd=0, highlightthickness=4)
    frame.pack(fill="both", expand=True)
    tag = tk.Label(frame, font=("Segoe UI", 14, "bold"), anchor="w")
    title = tk.Label(frame, font=("Segoe UI", 26, "bold"), anchor="w", justify="left", wraplength=W - 40)
    detail = tk.Label(frame, font=("Segoe UI", 15), anchor="w", justify="left", wraplength=W - 40)
    clock = tk.Label(frame, font=("Segoe UI", 20, "bold"), anchor="w")
    coming = tk.Label(frame, font=("Segoe UI", 13), anchor="w", justify="left", wraplength=W - 40)
    for w_ in (tag, title, detail, clock, coming):
        w_.pack(fill="x", padx=18, pady=(8, 0))
    barbox = tk.Frame(frame, bd=0)
    barbox.pack(side="bottom", fill="x", padx=18, pady=(0, 14))
    barlabel = tk.Label(barbox, font=("Segoe UI", 12), anchor="w")
    barlabel.pack(fill="x")
    canvas = tk.Canvas(barbox, height=14, highlightthickness=0, bd=0)
    canvas.pack(fill="x", pady=(4, 0))
    try:      # never take the focus, clicks go through to the game, not in the taskbar
        import ctypes
        u = ctypes.windll.user32
        root.update_idletasks()
        hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
        ex = u.GetWindowLongW(hwnd, -20)
        u.SetWindowLongW(hwnd, -20, ex | 0x08000000 | 0x00000080 | 0x00000020 | 0x00080000)
    except (OSError, AttributeError):
        pass
    state = {"data": None, "mtime": None, "exit_at": None, "placed_at": 0}

    def refresh():
        now = time.time()
        try:
            m = os.path.getmtime(path)
            if m != state["mtime"]:
                with open(path, encoding="utf-8") as f:
                    state["data"], state["mtime"] = json.load(f), m
        except (OSError, ValueError):
            pass
        d = state["data"] or {"state": "wait", "title": "Getting ready"}
        if d.get("state") == "exit" and state["exit_at"] is None:
            state["exit_at"] = now + float(d.get("after", 8))
        if (state["exit_at"] and now >= state["exit_at"]) or (parent and not pid_alive(parent)):
            root.destroy()
            return
        if now - state["placed_at"] > 2:
            state["placed_at"] = now
            x, y = place(W, H, game_rect(), root.winfo_screenwidth(), root.winfo_screenheight())
            root.geometry(f"{W}x{H}+{x}+{y}")
        bg, fg, word = COLORS.get(d.get("state"), COLORS["wait"])
        for w_ in (frame, tag, title, detail, clock, coming, barbox, barlabel):
            w_.configure(bg=bg)
        bar = d.get("bar")
        canvas.delete("all")
        if bar:
            cw = max(canvas.winfo_width(), 10)
            canvas.configure(bg="#14171c")
            canvas.create_rectangle(0, 0, int(cw * bar.get("frac", 0)), 14, fill=fg, width=0)
            left = bar.get("left") or 0
            eta = "" if left <= 0 else (f", about {round(left / 60)} min left" if left >= 90 else ", under 2 min left")
            barlabel.configure(text=f"{bar.get('label') or 'Filming'}: {round(100 * bar.get('frac', 0))} %{eta}", fg="#cfcfcf")
        else:
            canvas.configure(bg=bg)
            barlabel.configure(text="")
        frame.configure(highlightbackground=fg)
        tag.configure(text=word, fg=fg)
        if d.get("state") == "exit":
            title.configure(text="Done", fg="white")
            detail.configure(text="The computer is yours.", fg="#dddddd")
        else:
            title.configure(text=d.get("title", ""), fg="white")
            detail.configure(text=d.get("detail", ""), fg="#dddddd")
        until = d.get("until")
        clock.configure(text=f"{max(0, int(until - now + 0.99))} s" if until else "", fg=fg)
        coming.configure(text=f"Next: {d['next']}" if d.get("next") else "", fg="#bbbbbb")
        root.after(200, refresh)

    refresh()
    root.mainloop()


if __name__ == "__main__":
    window(sys.argv[1] if len(sys.argv) > 1 else PROMPT_FILE, sys.argv[2] if len(sys.argv) > 2 else None)
