"""The game for Video Studio's runner: savegames, the autorun file, starting and ending the game,
its log, the START screens, typing keys, the window size. (Screenshot Studio's runner, for video.)"""
import datetime, glob, os, re, shutil, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

from vs_common import DOCS, STUDIO, MOD_NAME, LOG_TAG, REPO

APP_ID = "2300320"
PROCESS = "FarmingSimulator2025Game.exe"
WORK = os.path.join(STUDIO, "autorun")       # backups, kept savegames, log copies


# ---------------------------------------------------------------- savegames and the mod
# farm names that must never be seen in a video (menus, monitors): renamed for the run only
BLOCKED_FARM_NAMES = {"big koch farms"}
NEUTRAL_FARM_NAMES = ["Green Valley Farm", "Riverside Acres", "Hilltop Grain Co.", "Meadow Brook Farm", "Oak Lane Farm"]


def farm_renames(save_path):
    """vsFarmName steps for the farms of a savegame whose names must not show."""
    path = os.path.join(save_path, "farms.xml")
    if not os.path.isfile(path):
        return []
    text = open(path, encoding="utf-8", errors="replace").read()
    steps = []
    # every farm: they are real players' farms on a server save, and some names must never show at all
    for i, (fid, name) in enumerate(re.findall(r'<farm farmId="(\d+)" name="([^"]*)"', text)):
        steps.append(f"vsFarmName {fid} {NEUTRAL_FARM_NAMES[i % len(NEUTRAL_FARM_NAMES)]}")
    return steps


def savegames(docs=DOCS):
    out = []
    for path in glob.glob(os.path.join(docs, "savegame*")):
        m = re.fullmatch(r"savegame(\d+)", os.path.basename(path))
        xml = os.path.join(path, "careerSavegame.xml")
        if not m or not os.path.isfile(xml):
            continue
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError:
            continue

        def text(key):
            el = root.find(key)
            return el.text if el is not None and el.text else ""
        mods = {el.get("modName") for el in root.iter("mod")}
        out.append({"index": int(m.group(1)), "name": text("settings/savegameName"), "map": text("settings/mapTitle"),
                    "date": text("settings/saveDateFormatted"), "hasMod": MOD_NAME in mods, "mods": mods, "path": path})
    return sorted(out, key=lambda s: s["index"])


def mod_version(modDesc_text):
    m = re.search(r"<version>\s*([^<\s]+)\s*</version>", modDesc_text)
    return m.group(1) if m else None


def installed_version(docs=DOCS, name=MOD_NAME):
    z = os.path.join(docs, "mods", name + ".zip")
    if not os.path.isfile(z):
        return None
    with zipfile.ZipFile(z) as zf:
        return mod_version(zf.read("modDesc.xml").decode("utf-8", "replace"))


def repo_version(repo=REPO):
    with open(os.path.join(repo, "modDesc.xml"), encoding="utf-8") as f:
        return mod_version(f.read())


# ---------------------------------------------------------------- autorun file
def write_autorun(steps, save, studio=STUDIO, now=None):
    os.makedirs(studio, exist_ok=True)
    root = ET.Element("autorun", savegame=str(save), created=(now or datetime.datetime.now()).strftime("%Y%m%d_%H%M%S"))
    for s in steps:
        ET.SubElement(root, "step").text = s
    ET.indent(root)
    path = os.path.join(studio, "autorun.xml")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def remove_autorun(studio=STUDIO):
    path = os.path.join(studio, "autorun.xml")
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


# ---------------------------------------------------------------- savegame backup
def with_mods(career_xml, names, docs=DOCS):
    """Switch mods on in a careerSavegame.xml for this run only (the savegame backup puts the list back).
    Each must be a zip in the mods folder. Returns the names added."""
    if not names:
        return []
    with open(career_xml, encoding="utf-8") as f:
        text = f.read()
    have = set(re.findall(r'<mod\s+modName="([^"]+)"', text))
    lines = []
    for name in names:
        z = os.path.join(docs, "mods", name + ".zip")
        if name in have or not os.path.isfile(z):
            continue
        with zipfile.ZipFile(z) as zf:
            desc = zf.read("modDesc.xml").decode("utf-8", "replace")
        version = mod_version(desc) or "1.0.0.0"
        m = re.search(r"<title>\s*<en>\s*(?:<!\[CDATA\[)?([^<\]]+)", desc)
        title = (m.group(1).strip() if m else name).replace('"', "'").replace("&", "&amp;")
        lines.append(f'    <mod modName="{name}" title="{title}" version="{version}" required="false" fileHash=""/>')
    if not lines:
        return []
    last = list(re.finditer(r'[ \t]*<mod\s+modName="[^"]+"[^>]*/>[ \t]*\r?\n', text))[-1]
    nl = "\r\n" if "\r\n" in last.group(0) else "\n"
    text = text[:last.end()] + nl.join(lines) + nl + text[last.end():]
    with open(career_xml, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return [re.search(r'modName="([^"]+)"', l).group(1) for l in lines]


def snapshot(folder):
    out = {}
    for top, _, files in os.walk(folder):
        for f in files:
            p = os.path.join(top, f)
            st = os.stat(p)
            out[os.path.relpath(p, folder)] = (st.st_size, st.st_mtime_ns)
    return out


def backup(folder, work=WORK, stamp=None):
    os.makedirs(work, exist_ok=True)
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(work, f"backup_{os.path.basename(folder)}_{stamp}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for top, _, files in os.walk(folder):
            for f in files:
                p = os.path.join(top, f)
                zf.write(p, os.path.relpath(p, folder))
    return path, snapshot(folder)


def prune_backups(work=WORK, keep=3):
    """Only the newest `keep` savegame backups stay (each is a whole savegame)."""
    zips = sorted(glob.glob(os.path.join(work, "backup_*.zip")), key=os.path.getmtime)
    for z in zips[:-keep] if keep else zips:
        os.remove(z)


def restore_if_changed(folder, backup_zip, before, work=WORK, stamp=None):
    if snapshot(folder) == before:
        return None
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    kept = os.path.join(work, f"{os.path.basename(folder)}_changed_{stamp}")
    shutil.move(folder, kept)
    with zipfile.ZipFile(backup_zip) as zf:
        zf.extractall(folder)
    return kept


# ---------------------------------------------------------------- the window size (game.xml)
DISPLAY_KEYS = ("width", "height", "fullscreenMode")


def read_display(game_xml):
    with open(game_xml, encoding="utf-8") as f:
        text = f.read()
    block = re.search(r"<display>([\s\S]*?)</display>", text)
    out = {}
    for k in DISPLAY_KEYS:
        m = re.search(rf"<{k}>\s*([^<]*?)\s*</{k}>", block.group(1)) if block else None
        out[k] = m.group(1) if m else None
    return out


def write_display(game_xml, values):
    """Sets width/height/fullscreenMode inside <display> of game.xml (only those)."""
    with open(game_xml, encoding="utf-8") as f:
        text = f.read()
    block = re.search(r"<display>([\s\S]*?)</display>", text)
    if not block:
        return False
    inner = block.group(1)
    for k, v in values.items():
        if v is not None:
            inner = re.sub(rf"(<{k}>)[^<]*(</{k}>)", rf"\g<1>{v}\g<2>", inner, count=1)
    new = text[:block.start(1)] + inner + text[block.end(1):]
    if new != text:
        with open(game_xml, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    return True


# ---------------------------------------------------------------- the log
class LogWatch:
    """Fed with new log text; keeps what matters for the run."""
    def __init__(self, tag=LOG_TAG):
        self.tag = tag
        self.started = self.done = self.refused = self.quitting = False
        self.loaded = self.entered = self.autostart = False
        self.last_line_at = None
        self.step = None
        self.keys = []
        self.clips = []          # "Clip 3 orbit (...)" lines as they start
        self.clip_done = 0
        self.errors = 0
        self.lines = []
        self._buf = ""
        self._near = 0

    def feed(self, text, now=None):
        self._buf += text
        *lines, self._buf = self._buf.split("\n")
        if lines:
            self.last_line_at = now if now is not None else time.time()
        out = []
        word = self.tag.strip("[]")
        for raw in lines:
            line = raw.rstrip("\r")
            if f"{self.tag} Loaded" in line:
                self.loaded = True
            elif "Auto start local savegame" in line:
                self.autostart = True
            elif "Entered Gameplay" in line:
                self.entered = True
            ours = word in line
            error = re.search(r"\b(Error|LUA call stack)\b", line) is not None
            if error:
                self.errors += 1
            if ours or (error and self._near > 0) or (self._near > 0 and line.startswith(("  ", "\t"))):
                out.append(line)
            self._near = 6 if ours or (error and self._near > 0) else max(0, self._near - 1)
            step = re.search(r"autorun: step (\d+/\d+ .*?) -> ", line)
            if step:
                self.step = step.group(1)
                keys = re.match(r"\d+/\d+ vsKeys (.+)$", step.group(1))
                if keys:
                    self.keys.append(keys.group(1).strip())
            k = re.search(r"\[VideoStudio\] keys: (.+)$", line)
            if k:
                self.keys.append(k.group(1).strip())
            m = re.search(r"Clip (\d+) (\w+) \(", line)
            if m and ours:
                self.clips.append((int(m.group(1)), m.group(2)))
            if ours and re.search(r"Clip \d+ done", line):
                self.clip_done += 1
            if "autorun: started" in line:
                self.started = True
            elif "autorun: done" in line:
                self.done = True
            elif "autorun: quitting" in line:
                self.quitting = True
            elif "autorun:" in line and "not run" in line:
                self.refused = True
        self.lines += out
        return out


def follow_log(path, since, watch, should_stop, poll=0.3, echo=print):
    pos = 0
    while not should_stop():
        if os.path.isfile(path) and os.path.getmtime(path) >= since:
            with open(path, encoding="utf-8", errors="replace") as f:
                f.seek(0, os.SEEK_END)
                if f.tell() < pos:
                    pos = 0
                f.seek(pos)
                text = f.read()
                pos = f.tell()
            for line in watch.feed(text):
                echo("  game| " + line)
        time.sleep(poll)


# ---------------------------------------------------------------- the game process and window
def game_pids():
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {PROCESS}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    pids = set()
    for row in out.splitlines():
        cells = [c.strip().strip('"') for c in row.split(",")]
        if len(cells) > 1 and cells[0].lower() == PROCESS.lower() and cells[1].isdigit():
            pids.add(int(cells[1]))
    return pids


def game_running():
    return bool(game_pids())


def user32():
    try:
        import ctypes
        return ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        return None


def game_window():
    """The game's main window handle and its client size, or (None, None)."""
    u = user32()
    if u is None:
        return None, None
    import ctypes
    from ctypes import wintypes
    pids, windows = game_pids(), []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and u.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            u.GetClientRect(hwnd, ctypes.byref(rect))
            windows.append((rect.right * rect.bottom, hwnd, (rect.right, rect.bottom)))
        return True
    u.EnumWindows(each, 0)
    if not windows:
        return None, None
    _, hwnd, size = max(windows)
    return hwnd, size


def focus_game():
    u = user32()
    hwnd, _ = game_window()
    if u is None or hwnd is None:
        return None
    u.ShowWindow(hwnd, 9)
    u.keybd_event(0x12, 0, 0, 0)
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    return hwnd if u.GetForegroundWindow() == hwnd else None


KEY_NAMES = {"enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
             "backspace": 0x08, "delete": 0x2E, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
             "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "backslash": 0xDC,
             "ctrl": 0x11, "alt": 0x12, "shift": 0x10, **{f"f{i}": 0x6F + i for i in range(1, 13)},
             "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3, "lalt": 0xA4, "ralt": 0xA5,
             **{f"num{i}": 0x60 + i for i in range(10)}}
EXTENDED = {0x2E, 0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0xA3, 0xA5}
MOUSE_WORD = re.compile(r"^(click|rclick|mclick|move|wheel)@(\d+)[,x](\d+)$")     # x: inside keys= (where "," splits words)
HOLD_WORD = re.compile(r"^hold@([a-z0-9+]+):(\d+(?:\.\d+)?)$")     # hold@q:8 = Q held down 8 s


def parse_keys(spec):
    out = []
    for word in spec.split():
        low = word.lower()
        m, h = MOUSE_WORD.match(low), HOLD_WORD.match(low)
        r = re.match(r"^([a-z0-9+]+)\*(\d+)$", low)       # down*20 = Down pressed 20 times, quickly
        if r and not m and not h:
            out.append(("repeat", (r.group(1).split("+"), int(r.group(2)))))
        elif h:
            out.append(("hold", (h.group(1).split("+"), float(h.group(2)))))
        elif m:
            out.append(("mouse", (m.group(1), int(m.group(2)), int(m.group(3)))))
        elif low == "pause":
            out.append(("pause", 1.0))
        elif "+" in low and len(low) > 1:
            out.append(("chord", low.split("+")))
        elif low in KEY_NAMES:
            out.append(("chord", [low]))
        else:
            out.append(("text", word))
    return out


def send_keys(actions):
    hwnd = focus_game()
    if hwnd is None:
        return False
    u = user32()

    def mouse(kind, x, y):
        import ctypes
        from ctypes import wintypes
        rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        u.GetClientRect(hwnd, ctypes.byref(rect))
        u.ClientToScreen(hwnd, ctypes.byref(origin))
        w, h = max(rect.right, 1), max(rect.bottom, 1)
        sx, sy = origin.x + round(x * w / 1920), origin.y + round(y * h / 1080)
        u.SetCursorPos(sx - 12, sy - 12)
        time.sleep(0.15)
        for i in range(1, 4):
            u.SetCursorPos(sx - 12 + 4 * i, sy - 12 + 4 * i)
            time.sleep(0.15)
        time.sleep(0.5)
        if kind == "wheel":
            for _ in range(5):
                u.mouse_event(0x0800, 0, 0, -120 & 0xFFFFFFFF, 0)
                time.sleep(0.25)
        elif kind != "move":
            down, up = {"click": (0x0002, 0x0004), "rclick": (0x0008, 0x0010), "mclick": (0x0020, 0x0040)}[kind]
            u.mouse_event(down, 0, 0, 0, 0)
            time.sleep(0.12)
            u.mouse_event(up, 0, 0, 0, 0)
        time.sleep(1.5)

    def vk_of(name):
        if name in KEY_NAMES:
            return KEY_NAMES[name], 0
        r = u.VkKeyScanW(ord(name[0]))
        return r & 0xFF, (r >> 8) & 0xFF

    def press(vks, up=False):
        for vk in (reversed(vks) if up else vks):
            u.keybd_event(vk, u.MapVirtualKeyW(vk, 0), (2 if up else 0) | (1 if vk in EXTENDED else 0), 0)
            time.sleep(0.05)

    def tap(vks):
        for vk in vks:
            u.keybd_event(vk, u.MapVirtualKeyW(vk, 0), 1 if vk in EXTENDED else 0, 0)
            time.sleep(0.05)
        time.sleep(0.08)
        for vk in reversed(vks):
            u.keybd_event(vk, u.MapVirtualKeyW(vk, 0), 2 | (1 if vk in EXTENDED else 0), 0)
            time.sleep(0.05)
        time.sleep(0.1)

    for kind, value in actions:
        if kind == "pause":
            time.sleep(value)
        elif kind == "mouse":
            mouse(*value)
        elif kind == "repeat":
            vks = [vk_of(n)[0] for n in value[0]]
            for _ in range(value[1]):
                tap(vks)
                time.sleep(0.12)
            time.sleep(0.5)
        elif kind == "hold":
            vks = [vk_of(n)[0] for n in value[0]]
            press(vks)
            time.sleep(value[1])
            press(vks, up=True)
            time.sleep(0.5)
        elif kind == "chord":
            tap([vk_of(n)[0] for n in value])
            time.sleep(1.0)
        else:
            for ch in value:
                vk, state = vk_of(ch)
                tap(([0x10] if state & 1 else []) + [vk])
    return True


class StartPresser:
    """Presses Enter on the two screens that wait for it (mod updates, START after loading)."""
    QUIET, EVERY, MAX = 12, 10, 8

    def __init__(self, enabled=True, press=None, echo=print):
        self.enabled, self.presses, self.last = enabled, 0, None
        self.press = press or (lambda: send_keys([("chord", ["enter"])]))
        self.echo = echo

    def due(self, watch, now):
        return (self.enabled and (watch.autostart or watch.loaded) and not watch.entered and not watch.started
                and watch.last_line_at is not None and now - watch.last_line_at >= self.QUIET
                and (self.last is None or now - self.last >= self.EVERY) and self.presses < self.MAX)

    def tick(self, watch, now=None):
        now = now if now is not None else time.time()
        if self.due(watch, now):
            self.last, self.presses = now, self.presses + 1
            ok = self.press()
            self.echo("Pressing START (Enter) in the game window" if ok
                      else "! Couldn't bring the game window to the front: press START yourself")
        return False


class KeyTyper:
    def __init__(self, send=None, echo=print):
        self.send, self.echo = send or (lambda spec: send_keys(parse_keys(spec))), echo

    def tick(self, watch):
        while watch.keys:
            spec = watch.keys.pop(0)
            ok = self.send(spec)
            self.echo(f"Typing into the game: {spec}" if ok else f"! Couldn't bring the game window to the front to type: {spec}")
        return False


def steam_exe():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            exe = winreg.QueryValueEx(k, "SteamExe")[0]
            if os.path.isfile(exe):
                return exe
    except OSError:
        pass
    exe = r"C:\Program Files (x86)\Steam\steam.exe"
    return exe if os.path.isfile(exe) else None


def steam_waiting(since, app=APP_ID, stuck=15):
    """What Steam waits for before it starts the game (a cloud conflict dialog, an update), or None:
    from Steam's content_log.txt, lines since `since` (epoch)."""
    exe = steam_exe()
    tail = ""
    for name in ("console_log.txt", "content_log.txt"):
        log = os.path.join(os.path.dirname(exe), "logs", name) if exe else None
        if not log or not os.path.isfile(log):
            continue
        try:
            with open(log, encoding="utf-8", errors="replace") as f:
                f.seek(max(0, os.path.getsize(log) - 300000))
                tail += f.read() + "\n"
        except OSError:
            pass
    # every launch passes "waiting for user response to CreatingProcess" and goes on in the same second:
    # only a launch whose latest state is still "waiting", for a while, is stuck on a dialog
    latest = {}
    for line in tail.splitlines():
        m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", line)
        a = re.search(r"ActionID (\d+)\] : LaunchApp", line)
        if not m or not a or f"AppID {app}" not in line:
            continue
        t = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
        if t >= since - 2:
            latest[a.group(1)] = (t, line)
    for t, line in latest.values():
        if "waiting for user response" in line and time.time() - t >= stuck:
            return line.split("LaunchApp", 1)[-1].strip()
    return None


def start_game(save):
    steam = steam_exe()
    if steam is None:
        sys.exit("Steam not found")
    subprocess.Popen([steam, "-applaunch", APP_ID, "-autoStartSavegameId", str(save), "-skipStartVideos"])


def end_game():
    subprocess.run(["taskkill", "/IM", PROCESS, "/F"], capture_output=True)


CRASH_DUMPS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CrashDumps")


def crash_logged(since):
    ms = int((time.time() - since) * 1000) + 5000
    q = f"*[System[Provider[@Name='Application Error'] and TimeCreated[timediff(@SystemTime) <= {ms}]]]"
    try:
        out = subprocess.run(["wevtutil", "qe", "Application", f"/q:{q}", "/f:text", "/rd:true", "/c:20"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for block in out.split("Event[")[1:]:
        if PROCESS.lower() in block.lower():
            m = re.search(r"Exception code:\s*(0x[0-9a-fA-F]+)", block)
            return m.group(1) if m else "?"
    return None


def wait_for(cond, seconds, poll=1.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(poll)
    return cond()
