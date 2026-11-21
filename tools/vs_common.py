"""Shared bits of the Video Studio tools: folders, ffmpeg, the brand (fonts, colors, intro/outro)."""
import json, os, re, shutil, subprocess, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
MOD_NAME = "FS25_VideoStudio"
LOG_TAG = "[VideoStudio]"


def documents():
    """Documents/My Games/FarmingSimulator2025 (OneDrive's Documents first, where Windows moves it)."""
    home = os.path.expanduser("~")
    for base in (os.path.join(home, "OneDrive", "Documents"), os.path.join(home, "Documents")):
        p = os.path.join(base, "My Games", "FarmingSimulator2025")
        if os.path.isdir(p):
            return p
    return os.path.join(home, "Documents", "My Games", "FarmingSimulator2025")


DOCS = os.environ.get("FS25_DOCS") or documents()
STUDIO = os.path.join(DOCS, "modSettings", MOD_NAME)       # the mod's folder: clip lists, autorun
# recordings, clips, finished videos: big files, so not in Documents or Videos (OneDrive often syncs those)
VIDEOS = os.environ.get("VS_VIDEOS") or os.path.join(os.path.expanduser("~"), "FS25 Video Studio")

WIDTH, HEIGHT, FPS = 1600, 900, 60


# ---------------------------------------------------------------- ffmpeg
def ffmpeg_exe(name="ffmpeg"):
    exe = shutil.which(name)
    if exe:
        return exe
    # winget's Gyan build isn't always on PATH in a fresh shell
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    if os.path.isdir(base):
        for top, _, files in os.walk(base):
            if name + ".exe" in files:
                return os.path.join(top, name + ".exe")
    sys.exit(f"{name} not found: install it (winget install Gyan.FFmpeg) and open a new terminal")


BELOW_NORMAL = 0x00004000      # Windows priority class: the game (and the player) come first


def game_is_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq FarmingSimulator2025Game.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "farmingsimulator2025game.exe" in out.lower()


def ffmpeg(args, quiet=True, check=True, **kw):
    """ffmpeg at low priority; while the game runs, with half the processor threads, so editing never
    makes the game stutter or the computer overheat while someone plays."""
    threads = []
    if game_is_running() and "-threads" not in args:
        threads = ["-threads", str(max(2, (os.cpu_count() or 4) // 2))]
    cmd = [ffmpeg_exe(), "-hide_banner", "-y"] + (["-loglevel", "error"] if quiet else []) + threads + list(args)
    if os.name == "nt":
        kw.setdefault("creationflags", BELOW_NORMAL)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if check and r.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + " ".join(cmd)[:2000] + "\n" + (r.stderr or "")[-3000:])
    return r


def probe(path):
    """{duration, width, height, fps, audio, start} of a media file."""
    r = subprocess.run([ffmpeg_exe("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe {path}: {r.stderr.strip()}")
    j = json.loads(r.stdout)
    out = {"duration": float(j.get("format", {}).get("duration") or 0), "audio": False, "start": float(j.get("format", {}).get("start_time") or 0)}
    for s in j.get("streams", []):
        if s.get("codec_type") == "video" and "width" not in out:
            out["width"], out["height"] = s.get("width"), s.get("height")
            num, _, den = (s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1").partition("/")
            out["fps"] = float(num) / float(den or 1) if float(den or 1) else 0
            out["vcodec"] = s.get("codec_name")
        elif s.get("codec_type") == "audio":
            out["audio"] = True
            out["acodec"] = s.get("codec_name")
    return out


def video_encoder(kind="x264"):
    """Encoder arguments for finished videos. x264 'slow' for the final (best quality per bit), nvenc
    for drafts (fast)."""
    if kind == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", "18", "-b:v", "16M",
                "-maxrate", "24M", "-bufsize", "48M", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-x264-params", "keyint=120:min-keyint=60"]


# ---------------------------------------------------------------- brand
BRANDS = os.path.join(REPO, "presets")


def find_upwards(rel, start=REPO, levels=4):
    """A path like '_brand/font/Outfit.ttf' next to the repo or a few folders up (DTM-Mods keeps the
    brand kit beside the mod repos)."""
    d = start
    for _ in range(levels):
        p = os.path.join(d, rel)
        if os.path.exists(p):
            return p
        d = os.path.dirname(d)
    return None


SYSTEM_FONTS = [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def load_brand(name_or_path="auto"):
    """The brand: colors, font, intro/outro, logo. 'auto' = DTM when its kit is found, else neutral.
    A brand file is JSON (presets/brand_*.json); paths in it are found next to it, next to the repo,
    or a few folders up."""
    if name_or_path in (None, "", "auto"):
        name_or_path = "dtm" if find_upwards(os.path.join("_brand", "font", "Outfit.ttf")) else "neutral"
    path = name_or_path
    if not os.path.isfile(path):
        path = os.path.join(BRANDS, f"brand_{name_or_path}.json")
    with open(path, encoding="utf-8") as f:
        b = json.load(f)
    base = os.path.dirname(os.path.abspath(path))

    def resolve(p):
        if not p:
            return None
        for cand in (p, os.path.join(base, p)):
            if os.path.exists(cand):
                return os.path.abspath(cand)
        return find_upwards(p)
    for key in ("font", "intro", "outro", "logo", "watermark", "thumbnail_overlay", "outro_still"):
        b[key] = resolve(b.get(key))
    if not b.get("font"):
        b["font"] = next((f for f in SYSTEM_FONTS if os.path.isfile(f)), None)
    b["name_or_path"] = name_or_path
    return b


def hex_rgb(h, alpha=None):
    h = h.lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return rgb + (alpha,) if alpha is not None else rgb


# ---------------------------------------------------------------- mod repos
def find_repo(name_or_path, root=None):
    """A mod repo by path or by folder name (with a modDesc.xml) under C:/Programming/fs2025."""
    if name_or_path and os.path.isfile(os.path.join(name_or_path, "modDesc.xml")):
        return os.path.abspath(name_or_path)
    root = root or os.path.dirname(os.path.dirname(REPO))
    for top, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith((".", "node_modules", "dist", "__"))]
        if os.path.basename(top).lower() == str(name_or_path).lower() and "modDesc.xml" in files:
            return top
        if top.count(os.sep) - root.count(os.sep) > 3:
            dirs[:] = []
    return None


def mod_info(repo):
    """{title, version, author, description, name} from a repo's modDesc.xml (English)."""
    import xml.etree.ElementTree as ET
    path = os.path.join(repo, "modDesc.xml")
    root = ET.parse(path).getroot()

    def text(key):
        el = root.find(key + "/en")
        if el is None:
            el = root.find(key)
        return (el.text or "").strip() if el is not None and el.text else ""
    desc = text("description")
    # the first paragraph, without ModHub's "Category: ..." lines
    lines = [l.strip() for l in desc.splitlines()]
    para = []
    for l in lines:
        if re.match(r"^(Category|Price|Power|Required power|Max\. speed|Working width|Working speed|Capacity|Monthly upkeep|Description|Hotkeys|GitHub):", l):
            continue
        if not l and para:
            break
        if l:
            para.append(l)
    return {"title": text("title"), "version": (root.findtext("version") or "").strip(),
            "author": (root.findtext("author") or "").strip(), "description": " ".join(para),
            "name": os.path.basename(os.path.abspath(repo))}


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "video"
