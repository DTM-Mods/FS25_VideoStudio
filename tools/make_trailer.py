"""A trailer from the best moments of many mods' videos (a channel trailer, a "new this month"):

    python make_trailer.py <spec.json> [--draft] [--sheet]

The spec names the shots: the mod, the clip (its file name without .mov, as in that mod's clips folder), from
which second and how long, optionally speed, zoom [x, y, w], label (default: the mod's video title from
videos/<mod>.json), title (the trailer's title over it), end_card (the closing shot). Each clip comes from the
mod's newest run folder (<VIDEOS>/<stamp>_<mod>/clips). Every shot carries the mod's name in the corner.
--sheet only makes a contact sheet of the chosen moments (start, middle, end of each), to check them first.
Out: <VIDEOS>/trailers/<name>/ (the video, thumbnail, description).
"""
import argparse, glob, json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vs_edit  # noqa: E402
from vs_common import VIDEOS, WIDTH, HEIGHT, FPS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def clip_file(mod, clip):
    for d in sorted(glob.glob(os.path.join(VIDEOS, f"*_{mod}")), reverse=True):
        hits = glob.glob(os.path.join(d, "clips", clip + ".*"))
        if hits:
            return hits[0]
    raise SystemExit(f"No clip {clip} of {mod} in {VIDEOS}")


def label_of(mod):
    p = os.path.join(ROOT, "videos", mod + ".json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("title") or mod.replace("FS25_", "")
    return mod.replace("FS25_", "")


def storyboard(spec):
    sections = []
    for i, s in enumerate(spec["shots"]):
        src = clip_file(s["mod"], s["clip"])
        dur = vs_edit.probe(src)["duration"]
        seconds = float(s.get("seconds", 3.5))
        start = float(s.get("from", 0.25))
        sec = {"clip": src, "trim": [start, max(0.0, dur - start - seconds)], "seconds": seconds,
               "speed": float(s.get("speed", 1.0))}
        label = s.get("label", label_of(s["mod"]))
        if label:
            sec["chip"] = {"label": label, "prefix": ""}
        for k in ("zoom", "title", "end_card", "caption"):
            if k in s:
                sec[k] = s[k]
        if i and s.get("cut"):
            sec["transition"] = "cut"
        sections.append(sec)
    th = spec.get("thumbnail", {})
    shot = sections[int(th.get("shot", 0))]
    return {
        "title": spec["title"], "kicker": spec.get("kicker", ""), "line": spec.get("line", ""),
        "mod": "", "version": "", "description": spec.get("description", ""), "url": "https://dtmmods.com",
        "style": "showcase", "brand": spec.get("brand", "auto"), "grade": "natural", "bars": 0,
        "transition": "fade", "tdur": float(spec.get("tdur", 0.4)), "size": [WIDTH, HEIGHT], "fps": FPS,
        "hook": None, "intro": True, "outro": True, "outro_seconds": spec.get("outro_seconds", 8), "watermark": True,
        "music": "generated", "music_seed": spec.get("music_seed", 1), "music_volume": 1.0, "game_audio": 0,
        "end_card": spec.get("end_card"),
        "thumbnail": {"clip": shot["clip"], "at": 0.5, "text": th.get("text", spec["title"]), "accent": th.get("accent", "")},
        "sections": sections, "clip_dir": "",
    }


def sheet(sb, out):
    """start / middle / end of every shot, one row each."""
    from PIL import Image
    rows = []
    for s in sb["sections"]:
        t0 = s["trim"][0]
        row = []
        for f in (0.05, 0.5, 0.95):
            p = out + f".tmp.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0 + s['seconds'] * f:.2f}", "-i", s["clip"],
                            "-frames:v", "1", "-vf", "scale=320:-1", p], check=True)
            row.append(Image.open(p).copy())
        rows.append(row)
    img = Image.new("RGB", (960, 180 * len(rows)))
    for r, row in enumerate(rows):
        for c, im in enumerate(row):
            img.paste(im, (320 * c, 180 * r))
    img.save(out)
    os.remove(out + ".tmp.png")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--sheet", action="store_true", help="only a contact sheet of the chosen moments")
    a = ap.parse_args()
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    out_dir = os.path.join(VIDEOS, "trailers", re.sub(r"[^A-Za-z0-9_-]+", "_", spec.get("name", "trailer")))
    os.makedirs(out_dir, exist_ok=True)
    sb = storyboard(spec)
    with open(os.path.join(out_dir, "storyboard.json"), "w", encoding="utf-8") as f:
        json.dump(sb, f, indent=2)
    if a.sheet:
        print(sheet(sb, os.path.join(out_dir, "moments.jpg")))
        return 0
    r = vs_edit.render(sb, out_dir, draft=a.draft, teaser=False)
    print(f"Trailer: {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
