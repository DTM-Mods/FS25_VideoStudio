"""Makes the finished video from cut clips.

A storyboard (storyboard.json beside the clips, made by `auto_storyboard` and free to edit) says what
goes where: the hook, the brand intro, a title over the first clip, the clips with their captions and
transitions, the colors with a chip per color, an end card with the download link, the brand outro,
the music. render() turns it into:

    <slug>_1600x900.mp4     the video (H.264 High, 60 fps, AAC 320k, -14 LUFS, +faststart)
    thumbnail.jpg           1280x720 (YouTube's size)
    description.txt         title ideas, description with chapters, tags
    teaser.mp4, teaser.gif  a short loop for the README and the website
    shorts.mp4              1080x1920 for YouTube Shorts (with --shorts)
    _work/                  the pieces (deleted with --clean)
"""
import json, math, os, re, shutil, subprocess, textwrap

from vs_common import (ffmpeg, probe, load_brand, hex_rgb, mod_info, find_repo, slug, video_encoder,
                       DOCS, WIDTH, HEIGHT, FPS)

# ---------------------------------------------------------------- looks
GRADES = {
    "none": "",
    "natural": "eq=contrast=1.03:saturation=1.07,unsharp=5:5:0.3:5:5:0",
    "warm": "colorbalance=rs=0.03:gs=0.01:bs=-0.03:rm=0.02:bm=-0.02,eq=contrast=1.04:saturation=1.08,unsharp=5:5:0.3:5:5:0",
    "vivid": "eq=contrast=1.07:saturation=1.18:gamma=0.98,unsharp=5:5:0.45:5:5:0",
    "film": "curves=master='0/0.035 0.25/0.23 0.5/0.5 0.75/0.78 1/0.965',eq=saturation=0.96,"
            "colorbalance=rs=0.02:bs=0.035:rh=0.025:bh=-0.02,vignette=angle=PI/5,unsharp=5:5:0.25:5:5:0",
}
STYLES = {
    # transition between sections, its length, the look, letterbox (picture aspect; 0 = none), hook clip first
    "showcase": {"transition": "fade", "tdur": 0.6, "grade": "natural", "bars": 0, "hook": True},
    "cinematic": {"transition": "fade", "tdur": 0.9, "grade": "film", "bars": 2.0, "hook": True},
    "clean": {"transition": "fade", "tdur": 0.5, "grade": "natural", "bars": 0, "hook": False},
    "punchy": {"transition": "smoothleft", "tdur": 0.35, "grade": "vivid", "bars": 0, "hook": True},
}
WORK_SHOTS = {"follow", "side", "lead", "flypast"}


# ---------------------------------------------------------------- graphics (Pillow)
def font(brand, size, weight=400):
    from PIL import ImageFont
    f = ImageFont.truetype(brand["font"], size) if brand.get("font") else ImageFont.load_default()
    try:
        f.set_variation_by_axes([weight])      # Outfit is a variable font (100..900)
    except (OSError, AttributeError, ValueError):
        pass
    return f


def text_width(draw, text, f, spacing=0):
    if not spacing:
        return draw.textlength(text, font=f)
    return sum(draw.textlength(c, font=f) for c in text) + spacing * max(0, len(text) - 1)


def draw_spaced(draw, xy, text, f, fill, spacing=0):
    x, y = xy
    if not spacing:
        draw.text((x, y), text, font=f, fill=fill)
        return
    for c in text:
        draw.text((x, y), c, font=f, fill=fill)
        x += draw.textlength(c, font=f) + spacing


def fit_font(brand, draw, text, max_w, size, weight, min_size=28):
    while size > min_size:
        f = font(brand, size, weight)
        if text_width(draw, text, f) <= max_w:
            return f
        size -= 2
    return font(brand, min_size, weight)


def shadowed(layer, radius=6, alpha=150, offset=(0, 3)):
    """The layer with a soft dark shadow under it (legible over any picture)."""
    from PIL import Image, ImageFilter
    a = layer.split()[-1]
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: v * alpha // 255).filter(ImageFilter.GaussianBlur(radius)))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(sh, offset)
    out.alpha_composite(layer)
    return out


def wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def title_layers(brand, out_dir, title, kicker, line, W=WIDTH, H=HEIGHT):
    """Three full-frame PNGs for the title: a dark scrim, the title block, the line under it."""
    from PIL import Image, ImageDraw
    c = brand["colors"]
    s = W / 1600
    # scrim: dark from the bottom left
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = scrim.load()
    dark = hex_rgb(c["dark"])
    for y in range(H):
        for x in range(0, W, 4):
            v = max(0.0, (y / H - 0.35) / 0.65) ** 1.4 * (1 - 0.45 * x / W)
            a = int(215 * min(1.0, v))
            for k in range(4):
                if x + k < W:
                    px[x + k, y] = dark + (a,)
    block = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    x0 = int(96 * s)
    tf = fit_font(brand, d, title, int(1250 * s), int(96 * s), 800)
    kf = font(brand, int(24 * s), 600)
    asc, desc = tf.getmetrics()
    ty = int(H - 200 * s) - asc
    if kicker:
        draw_spaced(d, (x0 + 3, ty - int(40 * s)), kicker.upper(), kf, hex_rgb(c["accent"]), spacing=int(5 * s))
    d.text((x0, ty), title, font=tf, fill=hex_rgb(c["light"]))
    bar_y = ty + asc + desc + int(14 * s)
    d.rounded_rectangle((x0 + 3, bar_y, x0 + 3 + int(132 * s), bar_y + int(7 * s)), radius=int(3 * s), fill=hex_rgb(c["accent"]))
    sub = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if line:
        ds = ImageDraw.Draw(sub)
        lf = font(brand, int(28 * s), 450)
        ds.text((x0 + 3, bar_y + int(26 * s)), line, font=lf, fill=hex_rgb(c["light"]) + (235,))
    paths = []
    for name, im in (("scrim", scrim), ("title", shadowed(block, 8, 170)), ("line", shadowed(sub, 6, 160))):
        p = os.path.join(out_dir, f"title_{name}.png")
        im.save(p)
        paths.append(p)
    return paths


def lower_third(brand, path, heading, text="", W=WIDTH, H=HEIGHT, align="left"):
    """A panel with a gold bar: heading and a line or two. Full-frame PNG."""
    from PIL import Image, ImageDraw
    c = brand["colors"]
    s = W / 1600
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    hf = font(brand, int(36 * s), 750)
    bf = font(brand, int(23 * s), 420)
    pad_x, pad_y, bar = int(30 * s), int(20 * s), int(7 * s)
    max_text = int(640 * s)
    lines = wrap(d, text, bf, max_text) if text else []
    hw = d.textlength(heading, font=hf)
    tw = max([d.textlength(l, font=bf) for l in lines] + [0])
    w = int(max(hw, tw) + 2 * pad_x + bar)
    ha, hd = hf.getmetrics()
    ba, bd = bf.getmetrics()
    lh = ba + bd + int(4 * s)
    h = int(pad_y * 2 + ha + hd + (int(8 * s) + lh * len(lines) if lines else 0))
    x = int(64 * s) if align == "left" else (W - w) // 2
    y = H - int(84 * s) - h
    d.rounded_rectangle((x, y, x + w, y + h), radius=int(12 * s), fill=hex_rgb(c["dark"]) + (228,))
    d.rounded_rectangle((x, y, x + bar + int(6 * s), y + h), radius=int(12 * s), fill=hex_rgb(c["accent"]))
    d.rectangle((x + bar, y, x + bar + int(6 * s), y + h), fill=hex_rgb(c["dark"]) + (228,))
    d.text((x + bar + pad_x, y + pad_y), heading, font=hf, fill=hex_rgb(c["light"]))
    for i, l in enumerate(lines):
        d.text((x + bar + pad_x, y + pad_y + ha + hd + int(8 * s) + i * lh), l, font=bf, fill=hex_rgb(c["light"]) + (215,))
    shadowed(im, 10, 120, (0, 4)).save(path)
    return path


def chip(brand, path, label, prefix="", W=WIDTH, H=HEIGHT):
    """A small pill bottom right: "3/12  BLUE"."""
    from PIL import Image, ImageDraw
    c = brand["colors"]
    s = W / 1600
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(brand, int(27 * s), 650)
    pf = font(brand, int(22 * s), 500)
    sp = int(3 * s)
    lw = text_width(d, label.upper(), f, sp)
    pw = text_width(d, prefix, pf, sp) + int(14 * s) if prefix else 0
    h = int(56 * s)
    w = int(lw + pw + 2 * int(24 * s))
    x, y = W - int(64 * s) - w, H - int(84 * s) - h
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=hex_rgb(c["dark"]) + (220,))
    asc, desc = f.getmetrics()
    ty = y + (h - asc - desc) // 2 + int(1 * s)
    if prefix:
        pa, pd_ = pf.getmetrics()
        draw_spaced(d, (x + int(24 * s), y + (h - pa - pd_) // 2 + int(2 * s)), prefix, pf, hex_rgb(c["accent"]), sp)
    draw_spaced(d, (x + int(24 * s) + pw, ty), label.upper(), f, hex_rgb(c["light"]), sp)
    shadowed(im, 8, 110, (0, 3)).save(path)
    return path


def keycaps(brand, path, keys, label="", W=WIDTH, H=HEIGHT):
    """The keys being pressed, top right: keycaps with "+" between, a label under them ("Opens the menu")."""
    from PIL import Image, ImageDraw
    c = brand["colors"]
    s = W / 1600
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(brand, int(30 * s), 700)
    pf = font(brand, int(28 * s), 600)
    lf = font(brand, int(21 * s), 500)
    kh, pad, gap = int(58 * s), int(20 * s), int(14 * s)
    widths = [max(kh, int(d.textlength(k, font=f) + 2 * pad)) for k in keys]
    plus = d.textlength("+", font=pf)
    total = sum(widths) + (len(keys) - 1) * (2 * gap + plus)
    lw = d.textlength(label, font=lf) if label else 0
    box_w = int(max(total, lw) + 2 * int(22 * s))
    box_h = int(kh + 2 * int(18 * s) + (int(34 * s) if label else 0))
    x0, y0 = W - int(56 * s) - box_w, int(56 * s)
    d.rounded_rectangle((x0, y0, x0 + box_w, y0 + box_h), radius=int(14 * s), fill=hex_rgb(c["dark"]) + (215,))
    x = x0 + (box_w - total) / 2
    y = y0 + int(18 * s)
    asc, desc = f.getmetrics()
    for i, (k, w) in enumerate(zip(keys, widths)):
        # a keycap: a darker base under a lighter top, so it reads as a key
        d.rounded_rectangle((x, y + int(5 * s), x + w, y + kh), radius=int(10 * s), fill=(190, 184, 168))
        d.rounded_rectangle((x, y, x + w, y + kh - int(6 * s)), radius=int(10 * s), fill=hex_rgb(c["light"]))
        d.text((x + (w - d.textlength(k, font=f)) / 2, y + (kh - int(6 * s) - asc - desc) / 2), k, font=f, fill=hex_rgb(c["dark"]))
        x += w
        if i < len(keys) - 1:
            pa, pd_ = pf.getmetrics()
            d.text((x + gap, y + (kh - pa - pd_) / 2), "+", font=pf, fill=hex_rgb(c["accent"]))
            x += 2 * gap + plus
    if label:
        d.text((x0 + (box_w - lw) / 2, y + kh + int(10 * s)), label, font=lf, fill=hex_rgb(c["light"]) + (230,))
    shadowed(im, 10, 120, (0, 4)).save(path)
    return path


def end_card(brand, path, heading, url, W=WIDTH, H=HEIGHT):
    """Centered: "Free download" and the link, over a dark band."""
    from PIL import Image, ImageDraw
    c = brand["colors"]
    s = W / 1600
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    band_h = int(200 * s)
    y0 = H - band_h - int(70 * s)
    px = im.load()
    dark = hex_rgb(c["dark"])
    for y in range(y0 - int(60 * s), H):
        a = int(200 * min(1.0, max(0.0, (y - (y0 - 60 * s)) / (60 * s))))
        for x in range(W):
            px[x, y] = dark + (a,)
    hf = font(brand, int(30 * s), 600)
    uf = fit_font(brand, d, url, int(1300 * s), int(62 * s), 800)
    sp = int(6 * s)
    hw = text_width(d, heading.upper(), hf, sp)
    draw_spaced(d, ((W - hw) / 2, y0 + int(20 * s)), heading.upper(), hf, hex_rgb(c["accent"]), sp)
    uw = d.textlength(url, font=uf)
    d.text(((W - uw) / 2, y0 + int(70 * s)), url, font=uf, fill=hex_rgb(c["light"]))
    im.save(path)
    return path


def thumbnail(brand, frame_path, out, text, accent=None):
    """YouTube thumbnail, 1280x720: the frame a little punchier, the brand overlay, the words."""
    from PIL import Image, ImageDraw, ImageEnhance
    c = brand["colors"]
    im = Image.open(frame_path).convert("RGB").resize((1280, 720), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    im = ImageEnhance.Color(im).enhance(1.12)
    im = im.convert("RGBA")
    if brand.get("thumbnail_overlay"):
        ov = Image.open(brand["thumbnail_overlay"]).convert("RGBA").resize((1280, 720))
        im.alpha_composite(ov)
    else:
        grad = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
        gp = grad.load()
        for y in range(380, 720):
            a = int(230 * ((y - 380) / 340) ** 1.3)
            for x in range(1280):
                gp[x, y] = hex_rgb(c["dark"]) + (a,)
        im.alpha_composite(grad)
    d = ImageDraw.Draw(im)
    words = text.upper().split()
    acc = (accent or "").upper().split()
    f = fit_font(brand, d, " ".join(words), 1180, 104, 850, 48)
    asc, desc = f.getmetrics()
    x, y = 48, 690 - asc - desc + 12
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for i, w in enumerate(words):
        color = hex_rgb(c["accent"]) if (w in acc or (not acc and i == len(words) - 1)) else hex_rgb(c["light"])
        ld.text((x, y), w, font=f, fill=color)
        x += ld.textlength(w + " ", font=f)
    im.alpha_composite(shadowed(layer, 10, 200, (0, 4)))
    im.convert("RGB").save(out, quality=92)
    return out


# ---------------------------------------------------------------- the storyboard
def _mod_from_mods_folder(mod):
    import zipfile
    z = os.path.join(DOCS, "mods", mod + ".zip")
    if not os.path.isfile(z):
        return None
    import tempfile
    with zipfile.ZipFile(z) as zf, tempfile.TemporaryDirectory() as t:
        with open(os.path.join(t, "modDesc.xml"), "wb") as f:
            f.write(zf.read("modDesc.xml"))
        info = mod_info(t)
    info["name"] = mod
    return info


def auto_storyboard(clip_dir, repo=None, style="showcase", brand="auto", title=None, music="generated", **over):
    """A storyboard for the clips in clip_dir (clips.json), with the mod's name and version."""
    with open(os.path.join(clip_dir, "clips.json"), encoding="utf-8") as f:
        clips = json.load(f)["clips"]
    if not clips:
        raise SystemExit("No clips in " + clip_dir)
    st = STYLES[style]
    mods = [c.get("mod") for c in clips if c.get("mod") and c.get("mod") != "basegame"]
    mod = max(set(mods), key=mods.count) if mods else None
    info = None
    r = find_repo(repo) if repo else (find_repo(mod) if mod else None)
    if r:
        info = mod_info(r)
    elif mod:
        info = _mod_from_mods_folder(mod)
    info = info or {"title": clips[0].get("what") or "Farming Simulator 25", "version": "", "name": mod or ""}
    b = load_brand(brand)
    url = b.get("mod_url", "").format(slug=slug(re.sub(r"^FS25_", "", info.get("name") or info["title"]))) if b.get("mod_url") else ""

    def sec(c, **kw):
        d = {"clip": c["file"], "trim": [0.25, 0.25], "speed": 1.0}
        d.update(kw)
        return d
    main = [c for c in clips if c["shot"] not in WORK_SHOTS and c["shot"] not in ("colors", "ui", "pov")]
    # the closing shot (under the download link): the drone, else the longest of the main clips
    closing = next((c for c in main if c["shot"] == "drone"), None) or (max(main, key=lambda c: c["seconds"]) if len(main) > 2 else None)
    if closing is not None:
        main = [c for c in main if c is not closing]
    colors = [c for c in clips if c["shot"] == "colors"]
    work = [c for c in clips if c["shot"] in WORK_SHOTS]
    other = [c for c in clips if c["shot"] in ("ui", "pov")]
    sections = []
    for i, c in enumerate(main):
        s = sec(c)
        if i == 0:
            s["title"] = True
            s["chapter"] = "Overview"
        sections.append(s)
    for i, c in enumerate(colors):
        s = sec(c, trim=[0, 0], transition="cut" if i else None,
                chip={"label": c.get("color", ""), "prefix": f"{c.get('colorIndex', i + 1)}/{c.get('colorCount', len(colors))}"})
        if i == 0:
            s["caption"] = {"heading": f"{c.get('colorCount', len(colors))} colors",
                            "text": "Every shop color; what's hitched to it changes too."}
            s["chapter"] = "Colors"
            s["transition"] = None
        sections.append(s)
    for i, c in enumerate(work):
        s = sec(c, trim=[0.4, 0.3])
        if i == 0:
            s["chapter"] = "At work"
        sections.append(s)
    for i, c in enumerate(other):
        s = sec(c, trim=[0.3, 0.3])
        if i == 0:
            s["chapter"] = "In the game"
        sections.append(s)
    if closing is not None:
        sections.append(sec(closing, end_card=True))
    elif sections:
        sections[-1]["end_card"] = True
    # the hook: the middle of the widest shot (orbit, drone), before the intro
    hook = None
    for shot in ("orbit", "drone", "crane", "arc"):
        c = next((x for x in clips if x["shot"] == shot), None)
        if c:
            mid = c["seconds"] / 2
            hook = {"clip": c["file"], "start": max(0.0, mid - 2.0), "seconds": min(4.0, c["seconds"])}
            break
    thumb_clip = next((x for x in clips if x["shot"] in ("pushin", "arc", "front", "orbit")), clips[0])
    sb = {
        "title": title or info["title"],
        "kicker": "Farming Simulator 25 mod",
        "line": " · ".join(p for p in ((f"Version {info['version']}" if info.get("version") else ""),
                                        (f"by {b['byline']}" if b.get("byline") else "")) if p),
        "mod": info.get("name") or mod or "",
        "version": info.get("version", ""),
        "description": info.get("description", ""),
        "url": url,
        "style": style, "brand": brand, "grade": st["grade"], "bars": st["bars"],
        "transition": st["transition"], "tdur": st["tdur"],
        "size": [WIDTH, HEIGHT], "fps": FPS,
        "hook": hook if st["hook"] else None,
        "intro": bool(b.get("intro")), "outro": bool(b.get("outro")),
        "watermark": bool(b.get("watermark")),
        "music": music, "music_seed": 1, "music_volume": 1.0, "game_audio": 0.45,
        "end_card": {"heading": "Free download", "url": url.replace("https://", "")} if url else None,
        "thumbnail": {"clip": thumb_clip["file"], "at": 0.85, "text": f"{title or info['title']}", "accent": ""},
        "sections": sections,
        "clip_dir": os.path.abspath(clip_dir),
    }
    sb.update(over)
    return sb


# ---------------------------------------------------------------- rendering
def _bars_filter(aspect, W, H):
    if not aspect:
        return ""
    bh = max(0, int(round((H - W / float(aspect)) / 2)))
    return f",drawbox=x=0:y=0:w={W}:h={bh}:color=black:t=fill,drawbox=x=0:y={H - bh}:w={W}:h={bh}:color=black:t=fill" if bh else ""


def _ease_in(start, dur):
    return f"pow(1-clip((t-{start:.3f})/{dur:.3f},0,1),3)"


class Renderer:
    def __init__(self, sb, out_dir, draft=False, echo=print):
        self.sb, self.out_dir, self.draft, self.echo = sb, out_dir, draft, echo
        self.brand = load_brand(sb.get("brand", "auto"))
        self.W, self.H = sb.get("size", [WIDTH, HEIGHT])
        self.fps = sb.get("fps", FPS)
        self.work = os.path.join(out_dir, "_work")
        os.makedirs(self.work, exist_ok=True)
        self.clip_dir = sb.get("clip_dir", "")
        self.grade = GRADES.get(sb.get("grade", "natural"), sb.get("grade", ""))

    def clip_path(self, name):
        return name if os.path.isabs(name) else os.path.join(self.clip_dir, name)

    def seg_args(self):
        if self.draft:
            return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p"]
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p"]

    def look(self):
        return ("," + self.grade if self.grade else "") + _bars_filter(self.sb.get("bars"), self.W, self.H)

    # one piece of the video: a clip (trimmed, speed, look, overlays) with its sound, or silence
    def segment(self, name, src, start, seconds, speed=1.0, overlays=(), look=True, game_audio=None):
        out = os.path.join(self.work, name + ".mkv")
        info = probe(src)
        dur = seconds / speed
        args = ["-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", src]
        W, H, fps = self.W, self.H, self.fps
        chain = [f"[0:v]setpts=(PTS-STARTPTS)/{speed},fps={fps},scale={W}:{H}:flags=lanczos:force_original_aspect_ratio=decrease,"
                 f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p" + (self.look() if look else "") + "[b0]"]
        last = "b0"
        for k, ov in enumerate(overlays, start=1):
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", ov["png"]]
            a, b = ov["in"], ov["out"]
            fi, fo = ov.get("fade_in", 0.45), ov.get("fade_out", 0.4)
            chain.append(f"[{k}:v]format=rgba,fade=t=in:st={a:.3f}:d={fi:.3f}:alpha=1,"
                         f"fade=t=out:st={max(a + fi, b - fo):.3f}:d={fo:.3f}:alpha=1[o{k}]")
            sx, sy = ov.get("slide", (0, 0))
            x = f"{-sx}*{_ease_in(a, fi * 1.4)}" if sx else "0"
            y = f"{sy}*{_ease_in(a, fi * 1.4)}" if sy else "0"
            chain.append(f"[{last}][o{k}]overlay=x='{x}':y='{y}':eval=frame:enable='between(t,{a:.3f},{b:.3f})'[b{k}]")
            last = f"b{k}"
        chain.append(f"[{last}]format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v]")
        level = self.sb.get("game_audio", 0.45) if game_audio is None else game_audio
        if info.get("audio") and level > 0:
            tempo = f",atempo={speed}" if abs(speed - 1) > 1e-3 else ""
            chain.append(f"[0:a]asetpts=PTS-STARTPTS{tempo},aresample=48000,aformat=channel_layouts=stereo,"
                         f"volume={level},apad,atrim=0:{dur:.3f}[a]")
        else:
            args += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            chain.append(f"[{len(overlays) + 1}:a]atrim=0:{dur:.3f}[a]")
        args += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", "[a]", "-r", str(fps)] + self.seg_args()
        args += ["-c:a", "pcm_s16le", "-t", f"{dur:.3f}", out]
        ffmpeg(args)
        return {"path": out, "seconds": probe(out)["duration"] or dur, "name": name}

    def brand_clip(self, name, src):
        out = os.path.join(self.work, name + ".mkv")
        W, H, fps = self.W, self.H, self.fps
        dur = probe(src)["duration"]
        ffmpeg(["-i", src, "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
                "-filter_complex", f"[0:v]fps={fps},scale={W}:{H}:flags=lanczos:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,settb=AVTB[v]",
                "-map", "[v]", "-map", "1:a"] + self.seg_args() + ["-c:a", "pcm_s16le", "-t", f"{dur:.3f}", out])
        return {"path": out, "seconds": dur, "name": name}

    def overlays_for(self, i, s, seconds):
        """The PNG overlays of section i and their times (in the section's own time)."""
        ovs = []
        sb, W, H = self.sb, self.W, self.H
        cap = s.get("caption")
        title_out = 0.0
        if s.get("title"):
            scrim, title, line = title_layers(self.brand, self.work, sb["title"], sb.get("kicker", ""), sb.get("line", ""), W, H)
            # with a caption on the same clip (a how-to's first step) the title goes sooner and the caption after it
            end = min(seconds - 0.2, 3.2 if cap else 5.6)
            title_out = end + 0.3
            ovs += [{"png": scrim, "in": 0.2, "out": end + 0.3, "fade_in": 0.8, "fade_out": 0.7},
                    {"png": title, "in": 0.5, "out": end, "fade_in": 0.55, "fade_out": 0.5, "slide": (0, -36)},
                    {"png": line, "in": 0.95, "out": end, "fade_in": 0.5, "fade_out": 0.5, "slide": (0, -24)}]
        if cap:
            heading = cap.get("heading", "")
            if cap.get("step") is not None:
                heading = f"{cap['step']}.  {heading}"
            p = lower_third(self.brand, os.path.join(self.work, f"cap_{i:02d}.png"), heading, cap.get("text", ""), W, H)
            a = max(float(cap.get("at", 0.7)), title_out + 0.25 if title_out else 0.0)
            b = min(seconds - 0.25, a + float(cap.get("seconds", 4.2)))
            ovs.append({"png": p, "in": a, "out": b, "fade_in": 0.4, "fade_out": 0.35, "slide": (44, 0)})
        # keys pressed in this step: {"keys": ["Right Shift", "1"], "label": "Showcase", "at": 0.5, "seconds": 3}
        for k, kp in enumerate(s.get("keys") or []):
            p = keycaps(self.brand, os.path.join(self.work, f"keys_{i:02d}_{k}.png"), kp["keys"], kp.get("label", ""), W, H)
            a = float(kp.get("at", 0.4))
            b = min(seconds - 0.1, a + float(kp.get("seconds", 3.2)))
            ovs.append({"png": p, "in": a, "out": b, "fade_in": 0.25, "fade_out": 0.3, "slide": (0, -16)})
        # a numbered step for how-to videos: {"step": 2, "heading": "...", "text": "..."} as the caption
        ch = s.get("chip")
        if ch and ch.get("label"):
            p = chip(self.brand, os.path.join(self.work, f"chip_{i:02d}.png"), ch["label"], ch.get("prefix", ""), W, H)
            ovs.append({"png": p, "in": 0.12, "out": seconds - 0.05, "fade_in": 0.25, "fade_out": 0.15})
        if s.get("end_card") and sb.get("end_card"):
            ec = sb["end_card"]
            p = end_card(self.brand, os.path.join(self.work, "endcard.png"), ec.get("heading", ""), ec.get("url", ""), W, H)
            a = max(0.3, seconds - 4.5)
            ovs.append({"png": p, "in": a, "out": seconds, "fade_in": 0.6, "fade_out": 0.01, "slide": (0, -20)})
        return ovs

    def build_segments(self):
        sb = self.sb
        segs, trans = [], []        # trans[i]: (kind, seconds) between segs[i] and segs[i+1]
        default = (sb.get("transition", "fade"), float(sb.get("tdur", 0.6)))
        if sb.get("hook"):
            h = sb["hook"]
            self.echo("  hook")
            segs.append(self.segment("00_hook", self.clip_path(h["clip"]), h.get("start", 0), h.get("seconds", 4)))
            segs[-1]["kind"] = "hook"
        if sb.get("intro") and self.brand.get("intro"):
            if segs:
                trans.append(("fadeblack", 0.6))
            self.echo("  intro")
            segs.append(self.brand_clip("01_intro", self.brand["intro"]))
            segs[-1]["kind"] = "intro"
        sections = sb["sections"]
        for i, s in enumerate(sections):
            src = self.clip_path(s["clip"])
            info = probe(src)
            t0, t1 = s.get("trim", [0.25, 0.25])
            seconds = max(0.5, info["duration"] - t0 - t1)
            if s.get("seconds"):
                seconds = min(seconds, float(s["seconds"]))
            speed = float(s.get("speed", 1.0))
            ovs = self.overlays_for(i, s, seconds / speed)
            self.echo(f"  {i + 1:2d}/{len(sections)} {s['clip']}" + (f"  [{s['caption']['heading']}]" if s.get("caption") else ""))
            seg = self.segment(f"{i + 2:02d}_s{i:02d}", src, t0, seconds, speed, ovs)
            seg.update(kind="section", index=i, chapter=s.get("chapter"))
            if segs:
                t = s.get("transition") or None
                if s.get("transition") == "cut":
                    trans.append(("cut", 0))
                elif segs[-1]["kind"] == "intro":
                    trans.append(("fadeblack", 0.6))
                else:
                    trans.append((t or default[0], float(s.get("tdur", default[1]))))
            segs.append(seg)
        if sb.get("outro") and self.brand.get("outro"):
            trans.append(("fadeblack", 0.8))
            self.echo("  outro")
            segs.append(self.brand_clip("99_outro", self.brand["outro"]))
            segs[-1]["kind"] = "outro"
        return segs, trans

    def join(self, segs, trans):
        """All segments into one (video and sound), transitions between; returns its path and the
        start of each segment in the joined timeline."""
        out = os.path.join(self.work, "joined.mkv")
        args, chain = [], []
        for i, s in enumerate(segs):
            args += ["-i", s["path"]]
            # one timebase for everything (mkv reads back in ms, concat gives µs: xfade wants them equal)
            chain.append(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[n{i}v]")
            chain.append(f"[{i}:a]asetpts=PTS-STARTPTS[n{i}a]")
        cur_v, cur_a, length = "n0v", "n0a", segs[0]["seconds"]
        starts = [0.0]
        for i in range(1, len(segs)):
            kind, td = trans[i - 1]
            td = min(td, segs[i]["seconds"] / 2, segs[i - 1]["seconds"] / 2)
            nv, na = f"jv{i}", f"ja{i}"
            if kind == "cut" or td <= 0:
                chain.append(f"[{cur_v}][{cur_a}][n{i}v][n{i}a]concat=n=2:v=1:a=1[{nv}][{na}]")
                starts.append(length)
                length += segs[i]["seconds"]
            else:
                chain.append(f"[{cur_v}][n{i}v]xfade=transition={kind}:duration={td:.3f}:offset={length - td:.3f}[{nv}]")
                chain.append(f"[{cur_a}][n{i}a]acrossfade=d={td:.3f}:c1=tri:c2=tri[{na}]")
                starts.append(length - td)
                length += segs[i]["seconds"] - td
            cur_v, cur_a = nv, na
        args += ["-filter_complex", ";".join(chain), "-map", f"[{cur_v}]", "-map", f"[{cur_a}]"]
        args += ["-r", str(self.fps)] + self.seg_args() + ["-c:a", "pcm_s16le", out]
        ffmpeg(args)
        return out, starts, length

    def music(self, seconds):
        m = self.sb.get("music", "generated")
        out = os.path.join(self.work, "music.wav")
        if not m or m == "none":
            return None
        if m == "generated":
            import vs_music
            vs_music.write(out, seconds + 0.5, seed=int(self.sb.get("music_seed", 1)),
                           key=self.sb.get("music_key", "D"), bpm=float(self.sb.get("music_bpm", 92)))
            return out
        src = m if os.path.isabs(m) else os.path.join(self.clip_dir, m)
        if not os.path.isfile(src):
            src = m
        fade = min(4.0, seconds / 5)
        ffmpeg(["-stream_loop", "-1", "-i", src, "-t", f"{seconds:.3f}",
                "-af", f"aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=1.2,afade=t=out:st={seconds - fade:.3f}:d={fade:.3f}",
                "-c:a", "pcm_s16le", out])
        return out

    def mix(self, joined, music, seconds):
        """Game sound + music, then loudness to YouTube's -14 LUFS (two passes, linear)."""
        mixed = os.path.join(self.work, "mixed.wav")
        mv = float(self.sb.get("music_volume", 1.0))
        if music:
            ffmpeg(["-i", joined, "-i", music, "-filter_complex",
                    f"[0:a]aresample=48000[g];[1:a]volume={mv}[m];[g][m]amix=inputs=2:normalize=0:duration=first[a]",
                    "-map", "[a]", "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", mixed])
        else:
            ffmpeg(["-i", joined, "-map", "0:a", "-c:a", "pcm_s16le", mixed])
        target = "I=-14:TP=-1.5:LRA=11"
        r = ffmpeg(["-i", mixed, "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"], quiet=False)
        m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr)
        final = os.path.join(self.work, "final.wav")
        if m:
            j = json.loads(m.group(0))
            if float(j["input_i"]) < -60:       # silence: nothing to measure
                shutil.copy(mixed, final)
                return final
            af = (f"loudnorm={target}:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
                  f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,aresample=48000")
        else:
            af = f"loudnorm={target},aresample=48000"
        ffmpeg(["-i", mixed, "-af", af, "-c:a", "pcm_s16le", final])
        return final

    def final(self, joined, audio, out, wm_window):
        args = ["-i", joined, "-i", audio]
        wm = self.brand.get("watermark") if self.sb.get("watermark") else None
        size = int(self.W * 0.045)
        if wm and wm_window:
            a, b = wm_window
            args += ["-loop", "1", "-framerate", str(self.fps), "-i", wm]
            fc = (f"[2:v]scale={size}:{size},format=rgba,colorchannelmixer=aa=0.55[wm];"
                  f"[0:v][wm]overlay=x=W-w-{int(self.W * 0.03)}:y=H-h-{int(self.H * 0.04)}:enable='between(t,{a:.3f},{b:.3f})':shortest=1,format=yuv420p[v]")
            args += ["-filter_complex", fc, "-map", "[v]"]
        else:
            args += ["-map", "0:v"]
        enc = video_encoder("nvenc" if self.draft else "x264")
        args += ["-map", "1:a", "-r", str(self.fps)] + enc + ["-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                                                              "-movflags", "+faststart", "-metadata", f"title={self.sb['title']}", "-shortest", out]
        ffmpeg(args)
        return out


def chapters_of(segs, starts, sb, total):
    """YouTube chapters: from 00:00, at least 3, each at least 10 s; None when that can't be done."""
    marks = [(0.0, "Intro")]
    for s, t in zip(segs, starts):
        if s.get("chapter"):
            marks.append((t, s["chapter"]))
    outro = next((t for s, t in zip(segs, starts) if s["kind"] == "outro"), None)
    if outro is not None:
        marks.append((outro, "More mods"))
    # merge chapters shorter than 10 s into the one before
    merged = []
    for i, (t, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else total
        if merged and (t - merged[-1][0] < 10):
            continue
        if end - t < 10 and merged:
            continue
        merged.append((t, name))
    if len(merged) < 3:
        return None
    return [(f"{int(t // 60):02d}:{int(t % 60):02d}", name) for t, name in merged]


def description(sb, brand, chapters, music_credit):
    links = brand.get("links", {})
    lines = []
    if sb.get("description"):
        lines += [textwrap.fill(sb["description"], 400), ""]
    if sb.get("url"):
        lines.append(f"Download (free): {sb['url']}")
    if sb.get("version"):
        lines.append(f"Version in this video: {sb['version']}")
    lines.append("")
    if chapters:
        lines.append("Chapters")
        lines += [f"{t} {name}" for t, name in chapters]
        lines.append("")
    for k, v in links.items():
        lines.append(f"{k}: {v}")
    if music_credit:
        lines += ["", f"Music: {music_credit}"]
    if brand.get("hashtags"):
        lines += ["", brand["hashtags"]]
    title = sb["title"]
    head = [f"TITLE IDEAS", f"  {title} | {sb.get('kicker', 'FS25 mod')}" + (f" | {brand['name']}" if brand.get("name") else ""),
            f"  {title} {sb.get('version', '')}: showcase | FS25".replace("  ", " "), "",
            "TAGS", "  " + ", ".join(brand.get("tags", []) + [title]), "", "DESCRIPTION", ""]
    return "\n".join(head + lines) + "\n"


def render(sb, out_dir, draft=False, shorts=False, teaser=True, clean=False, echo=print):
    os.makedirs(out_dir, exist_ok=True)
    r = Renderer(sb, out_dir, draft=draft, echo=echo)
    with open(os.path.join(out_dir, "storyboard.json"), "w", encoding="utf-8") as f:
        json.dump(sb, f, indent=2)
    echo(f"Making '{sb['title']}' ({sb.get('style')}, {r.W}x{r.H} at {r.fps} fps{', draft' if draft else ''}):")
    segs, trans = r.build_segments()
    echo("  joining")
    joined, starts, total = r.join(segs, trans)
    echo(f"  sound: {sb.get('music')} music, game sound at {sb.get('game_audio')}")
    music = r.music(total)
    audio = r.mix(joined, music, total)
    main = [(s, t) for s, t in zip(segs, starts) if s["kind"] == "section"]
    wm_window = (main[0][1] + 6.0, main[-1][1] + main[-1][0]["seconds"]) if main else None
    name = slug(sb["title"]) + f"_{r.W}x{r.H}.mp4"
    out = os.path.join(out_dir, name)
    echo("  encoding " + name)
    r.final(joined, audio, out, wm_window)
    result = {"video": out, "seconds": total}
    # thumbnail
    th = sb.get("thumbnail") or {}
    if th.get("clip"):
        src = r.clip_path(th["clip"])
        frame = os.path.join(r.work, "thumb_frame.png")
        at = probe(src)["duration"] * float(th.get("at", 0.8))
        ffmpeg(["-ss", f"{at:.3f}", "-i", src, "-frames:v", "1", "-vf", f"scale={r.W}:{r.H}:flags=lanczos" + ("," + r.grade if r.grade else ""), frame])
        result["thumbnail"] = thumbnail(r.brand, frame, os.path.join(out_dir, "thumbnail.jpg"), th.get("text") or sb["title"], th.get("accent"))
    # description with chapters
    chapters = chapters_of(segs, starts, sb, total)
    credit = "made with DTM Video Studio's own music generator (free to use)" if sb.get("music") == "generated" else sb.get("music_credit", "")
    with open(os.path.join(out_dir, "description.txt"), "w", encoding="utf-8") as f:
        f.write(description(sb, r.brand, chapters, credit))
    result["chapters"] = chapters
    # teaser: 8 s from the first section after the title, as a loop for READMEs and the website
    if teaser and main:
        s, t = main[1] if len(main) > 1 else main[0]
        start = t + min(1.0, s["seconds"] / 4)
        tlen = min(8.0, s["seconds"] - 1.0)
        tz = os.path.join(out_dir, "teaser.mp4")
        ffmpeg(["-ss", f"{start:.3f}", "-t", f"{tlen:.3f}", "-i", out, "-an",
                "-vf", "fade=t=in:d=0.4,fade=t=out:st=%.3f:d=0.5" % (tlen - 0.5),
                "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", tz])
        gif = os.path.join(out_dir, "teaser.gif")
        ffmpeg(["-ss", f"{start:.3f}", "-t", f"{min(6.0, tlen):.3f}", "-i", out, "-filter_complex",
                "fps=15,scale=640:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a",
                gif])
        result["teaser"] = tz
    if shorts and main:
        result["shorts"] = make_shorts(r, out, main, os.path.join(out_dir, "shorts.mp4"))
    if clean:
        shutil.rmtree(r.work, ignore_errors=True)
    return result


def make_shorts(r, video, main, out, seconds=45):
    """1080x1920: the video in the middle over a blurred, zoomed copy of itself, the title above."""
    from PIL import Image, ImageDraw
    start = main[0][1]
    length = min(seconds, sum(s["seconds"] for s, _ in main) - 1)
    png = os.path.join(r.work, "shorts_title.png")
    im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = r.brand["colors"]
    tf = fit_font(r.brand, d, r.sb["title"], 960, 84, 800, 40)
    lines = wrap(d, r.sb["title"], tf, 960)
    y = 330
    for l in lines[:3]:
        w = d.textlength(l, font=tf)
        d.text(((1080 - w) / 2, y), l, font=tf, fill=hex_rgb(c["light"]))
        y += tf.getmetrics()[0] + 18
    kf = font(r.brand, 30, 600)
    k = (r.sb.get("kicker") or "").upper()
    kw = text_width(d, k, kf, 5)
    draw_spaced(d, ((1080 - kw) / 2, 270), k, kf, hex_rgb(c["accent"]), 5)
    if r.sb.get("url"):
        uf = fit_font(r.brand, d, r.sb["url"].replace("https://", ""), 980, 40, 600, 24)
        u = r.sb["url"].replace("https://", "")
        d.text(((1080 - d.textlength(u, font=uf)) / 2, 1560), u, font=uf, fill=hex_rgb(c["light"]))
    shadowed(im, 10, 190).save(png)
    fc = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,"
          "eq=brightness=-0.12:saturation=1.1[bg];[b]scale=1080:-2:flags=lanczos[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2[c];[c][1:v]overlay=0:0,format=yuv420p[v]")
    ffmpeg(["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", video, "-loop", "1", "-framerate", str(r.fps), "-i", png,
            "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-shortest", "-af", f"afade=t=out:st={length - 1.5:.3f}:d=1.5"]
           + video_encoder("x264") + ["-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", out])
    return out


# ---------------------------------------------------------------- checks
def check(path, expect=(WIDTH, HEIGHT), fps=FPS):
    """Problems a viewer would notice or YouTube would mind: size, frame rate, loudness, black or frozen
    stretches. Returns [(level, text)]; level '!' is wrong, '?' worth a look."""
    info = probe(path)
    out = []
    if (info.get("width"), info.get("height")) != tuple(expect):
        out.append(("!", f"size {info.get('width')}x{info.get('height')}, wanted {expect[0]}x{expect[1]}"))
    if abs((info.get("fps") or 0) - fps) > 0.5:
        out.append(("!", f"{info.get('fps'):.2f} fps, wanted {fps}"))
    if not info.get("audio"):
        out.append(("?", "no sound"))
    r = ffmpeg(["-i", path, "-vf", "blackdetect=d=0.6:pix_th=0.06,freezedetect=n=0.002:d=2.5", "-af", "ebur128=peak=true",
                "-f", "null", "-"], quiet=False)
    err = r.stderr
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    if lufs:
        i = float(lufs[-1])
        if abs(i + 14) > 1.5:
            out.append(("?", f"loudness {i:.1f} LUFS (YouTube plays at -14)"))
        out.append(("ok", f"loudness {i:.1f} LUFS, true peak {peak[-1] if peak else '?'} dBFS"))
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", err):
        a, b, d = map(float, m.groups())
        out.append(("?", f"black from {a:.1f} to {b:.1f} s ({d:.1f} s)"))
    starts = re.findall(r"freeze_start: ([\d.]+)", err)
    durs = re.findall(r"freeze_duration: ([\d.]+)", err)
    for a, d in zip(starts, durs):
        out.append(("?", f"frozen picture from {float(a):.1f} s for {float(d):.1f} s"))
    out.insert(0, ("ok", f"{info.get('width')}x{info.get('height')}, {info.get('fps', 0):.0f} fps, {info['duration']:.1f} s, "
                         f"{os.path.getsize(path) / 1e6:.0f} MB"))
    return out
