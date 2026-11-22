"""Finds the clips in a recording and cuts them out.

The mod covers the screen with a START card (magenta) while the camera gets into place and an END card
(cyan) when the move is over; both carry the clip number as 8 black/white cells along the bottom
quarter (most significant bit left). The recording is read once, very small (32x18), frame by frame
at 60 fps; a clip is every frame after its START card and before its END card, less a couple of frames
at each end (a card can bleed into the frame next to it: TAA, frame generation, scaling).

The clips' details (shot, subject, light, color) come from the mod's _clips_<time>.xml, matched by
clip number in order.
"""
import glob, json, os, re, subprocess
import xml.etree.ElementTree as ET

from vs_common import ffmpeg, ffmpeg_exe, probe, STUDIO, WIDTH, HEIGHT, FPS

SW, SH = 32, 18          # the size frames are read at


def classify(rgb, w=SW, h=SH):
    """('start'|'end'|None, code) of one small RGB frame (bytes, w*h*3)."""
    def px(x, y):
        i = (y * w + x) * 3
        return rgb[i], rgb[i + 1], rgb[i + 2]
    # most of the top must be the card's color: with the HUD on, the game draws its notifications and
    # hints over the card, so a few pixels may be anything
    top = [px(x, y) for y in range(1, int(h * 0.7)) for x in range(w)]
    n = len(top)
    magenta = sum(1 for p in top if p[0] > 170 and p[1] < 90 and p[2] > 170)
    cyan = sum(1 for p in top if p[0] < 90 and p[1] > 170 and p[2] > 170)
    if magenta >= 0.8 * n:
        kind = "start"
    elif cyan >= 0.8 * n:
        kind = "end"
    else:
        return None, None
    cell = w // 8
    bits = []
    for k in range(8):
        vals = [px(x, y) for y in range(int(h * 0.8), h - 1) for x in range(k * cell + 1, (k + 1) * cell - 1)]
        lums = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in vals]
        light = sum(1 for v in lums if v >= 185)
        dark = sum(1 for v in lums if v <= 70)
        if light >= 0.75 * len(lums):
            bits.append(1)
        elif dark >= 0.75 * len(lums):
            bits.append(0)
        else:
            return None, None          # a cell half way: a blended frame, not a card
    code = int("".join(map(str, bits)), 2)
    return (kind, code) if code > 0 else (None, None)


def read_frames(video, fps=FPS):
    """Yields (index, kind, code) for every frame at `fps` (the same frames the cut uses)."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", video,
           "-vf", f"fps={fps},scale={SW}:{SH}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = SW * SH * 3
    i = 0
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            kind, code = classify(buf)
            yield i, kind, code
            i += 1
    finally:
        p.stdout.close()
        p.wait()


def runs(frames):
    """Runs of equal cards: [(kind, code, first, last)]; frames without a card are left out."""
    out, cur = [], None
    for i, kind, code in frames:
        if cur is not None and cur[0] == kind and cur[1] == code and cur[3] == i - 1:
            cur[3] = i
            continue
        if cur is not None:
            out.append(tuple(cur))
        cur = [kind, code, i, i] if kind else None
    if cur is not None:
        out.append(tuple(cur))
    return out


def find_clips(card_runs, trim=2, min_frames=12):
    """[(code, first, last)] frames of each clip: after its START card, before its END card. A START
    with no END of the same number (the game ended) is left out."""
    out = []
    for i, (kind, code, first, last) in enumerate(card_runs):
        if kind != "start":
            continue
        for k2, c2, f2, l2 in card_runs[i + 1:]:
            if k2 == "start" and c2 != code:
                break
            if k2 == "end" and c2 == code:
                a, b = last + 1 + trim, f2 - 1 - trim
                if b - a + 1 >= min_frames:
                    out.append((code, a, b))
                break
    return out


# ---------------------------------------------------------------- the mod's clip lists
def read_manifests(since=0, studio=STUDIO, until=None):
    """Every clip from the _clips_*.xml written between `since` and `until` (epoch), oldest first."""
    clips = []
    for path in sorted(glob.glob(os.path.join(studio, "*", "_clips_*.xml")), key=os.path.getmtime):
        if os.path.getmtime(path) < since or (until is not None and os.path.getmtime(path) > until):
            continue
        root = ET.parse(path).getroot()
        for el in root.findall("clip"):
            c = dict(el.attrib)
            for k in ("duration", "hour", "fov"):
                if k in c:
                    c[k] = float(c[k])
            for k in ("n", "code", "colorIndex", "colorCount", "blocked"):
                if k in c:
                    c[k] = int(c[k])
            c["hud"] = c.get("hud") == "true"
            c["run"] = {"mod": root.get("mod"), "what": root.get("what"), "map": root.get("map"),
                        "version": root.get("version"), "list": path}
            clips.append(c)
    return clips


def match(found, manifest):
    """Pairs found clips (code, first, last) with manifest entries by code, in order."""
    out, used = [], set()
    for code, a, b in found:
        entry = None
        for j, m in enumerate(manifest):
            if j not in used and m.get("code") == code:
                entry = m
                used.add(j)
                break
        out.append((code, a, b, entry))
    return out


# ---------------------------------------------------------------- cutting
def cut(rec_dir, out_dir=None, since=None, trim=2, size=(WIDTH, HEIGHT), fps=FPS, echo=print, quality=14):
    """Cuts every clip of rec_dir/master.mkv into out_dir/NN_<shot>.mp4 with clips.json. Returns the list."""
    with open(os.path.join(rec_dir, "recording.json"), encoding="utf-8") as f:
        meta = json.load(f)
    video = os.path.join(rec_dir, meta.get("video", "master.mkv"))
    out_dir = out_dir or os.path.join(rec_dir, "clips")
    os.makedirs(out_dir, exist_ok=True)
    echo("Looking for the clips' cards in the recording ...")
    card_runs = runs(read_frames(video, fps))
    found = find_clips(card_runs, trim=trim)
    manifest = read_manifests(since if since is not None else (meta.get("started", 0) - 5),
                              until=meta["stopped"] + 30 if meta.get("stopped") else None)
    pairs = match(found, manifest)
    echo(f"{len(card_runs)} card(s), {len(found)} clip(s); {len(manifest)} in the clip lists")
    if not pairs:
        return []

    info = probe(video)
    w, h = info.get("width") or size[0], info.get("height") or size[1]
    # 16:9 from the middle (a window that isn't quite), then to the size
    cw, ch = (w, round(w * 9 / 16)) if w * 9 <= h * 16 else (round(h * 16 / 9), h)
    cw, ch = cw - cw % 2, ch - ch % 2
    geom = f"crop={cw}:{ch}:{(w - cw) // 2}:{(h - ch) // 2},scale={size[0]}:{size[1]}:flags=lanczos,setsar=1"
    audio = meta.get("audio") and os.path.isfile(os.path.join(rec_dir, meta["audio"]))
    offset = (meta["video_start"] - meta["audio_start"]) if audio and "video_start" in meta else 0.0

    names, parts, maps = [], [], []
    n = len(pairs)
    vs = "".join(f"[v{i}]" for i in range(n))
    parts.append(f"[0:v]fps={fps},split={n}{vs}" if n > 1 else f"[0:v]fps={fps}[v0]")
    if audio:
        a_s = "".join(f"[a{i}]" for i in range(n))
        # padded with silence: the sound file can end a few seconds before the picture (its recorder stops
        # first), and a clip whose sound range lies past its end would get no sound at all and fail
        parts.append(f"[1:a]apad,asplit={n}{a_s}" if n > 1 else "[1:a]apad[a0]")
    out_list = []
    for i, (code, a, b, entry) in enumerate(pairs):
        shot = (entry or {}).get("shot", "clip")
        color = (entry or {}).get("color")
        name = f"{i + 1:02d}_{shot}" + (f"_{re.sub(r'[^A-Za-z0-9]+', '', color)[:20]}" if color else "") + ".mp4"
        names.append(name)
        parts.append(f"[v{i}]trim=start_frame={a}:end_frame={b + 1},setpts=PTS-STARTPTS,{geom},format=yuv420p[o{i}]")
        maps.append(["-map", f"[o{i}]"])
        if audio:
            t0, t1 = offset + a / fps, offset + (b + 1) / fps
            parts.append(f"[a{i}]atrim=start={max(0, t0):.4f}:end={max(0, t1):.4f},asetpts=PTS-STARTPTS[s{i}]")
            maps[-1] += ["-map", f"[s{i}]"]
        rec = dict(entry or {"shot": "clip", "code": code})
        rec.update(file=name, frames=b - a + 1, seconds=(b - a + 1) / fps, first_frame=a, last_frame=b)
        out_list.append(rec)
    args = ["-i", video] + (["-i", os.path.join(rec_dir, meta["audio"])] if audio else [])
    args += ["-filter_complex", ";".join(parts)]
    for i, name in enumerate(names):
        args += maps[i] + ["-c:v", "libx264", "-preset", "fast", "-crf", str(quality), "-pix_fmt", "yuv420p", "-r", str(fps)]
        if audio:
            args += ["-c:a", "pcm_s16le"]
        args += [os.path.join(out_dir, name.replace(".mp4", ".mov") if audio else name)]
    if audio:
        for rec in out_list:
            rec["file"] = rec["file"].replace(".mp4", ".mov")
    echo(f"Cutting {n} clip(s) to {size[0]}x{size[1]} ...")
    ffmpeg(args)
    with open(os.path.join(out_dir, "clips.json"), "w", encoding="utf-8") as f:
        json.dump({"recording": os.path.abspath(rec_dir), "fps": fps, "size": list(size), "audio": bool(audio),
                   "clips": out_list}, f, indent=2)
    for rec in out_list:
        extra = f", {rec['color']}" if rec.get("color") else ""
        echo(f"  {rec['file']:28s} {rec['seconds']:5.1f} s  {rec.get('what', '')}{extra}")
    return out_list


def contact_sheet(clip_dir, out=None, per_row=3, thumb=(320, 180)):
    """One row per clip: its first, middle and last frame, numbered. For a look at what was filmed."""
    from PIL import Image, ImageDraw, ImageFont
    with open(os.path.join(clip_dir, "clips.json"), encoding="utf-8") as f:
        clips = json.load(f)["clips"]
    if not clips:
        return None
    pad, label_h = 8, 26
    W = per_row * thumb[0] + (per_row + 1) * pad
    H = len(clips) * (thumb[1] + label_h + pad) + pad
    sheet = Image.new("RGB", (W, H), (24, 28, 32))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    tmp = os.path.join(clip_dir, "_sheet_tmp.png")
    for r, c in enumerate(clips):
        y = pad + r * (thumb[1] + label_h + pad)
        d.text((pad, y + 3), f"{r + 1:2d}. {c['file']}  {c['seconds']:.1f} s  {c.get('what', '')}  {c.get('light', '')}"
               + (f"  {c['color']}" if c.get("color") else ""), fill=(235, 235, 230), font=font)
        for k, frac in enumerate((0.03, 0.5, 0.97)):
            t = max(0.0, c["seconds"] * frac - 0.02)
            ffmpeg(["-ss", f"{t:.3f}", "-i", os.path.join(clip_dir, c["file"]), "-frames:v", "1",
                    "-vf", f"scale={thumb[0]}:{thumb[1]}", tmp])
            sheet.paste(Image.open(tmp).convert("RGB"), (pad + k * (thumb[0] + pad), y + label_h))
    if os.path.isfile(tmp):
        os.remove(tmp)
    out = out or os.path.join(clip_dir, "_sheet.jpg")
    sheet.save(out, quality=88)
    return out
