"""Draws icon_videoStudio.png (256x256) in the style of the DTM tool icons: green tile, straw rim, gold
viewfinder corners, the DTM pin bottom right, and a cream movie camera with two gold film reels.

    python tools/make_icon.py
"""
import os
from PIL import Image, ImageDraw

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 8                       # drawn 8x as big, then scaled down (smooth edges)
N = 256 * S
RIM, TILE, STRIPE = (126, 141, 93), (37, 90, 67), (32, 79, 59)
GOLD, CREAM, NIGHT, FIELD = (216, 163, 65), (244, 241, 232), (20, 51, 38), (46, 107, 79)


def p(*v):
    return [x * S for x in v]


im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle(p(0, 0, 255, 255), radius=44 * S, fill=RIM)
d.rounded_rectangle(p(5, 5, 250, 250), radius=40 * S, fill=TILE)
# faint field stripes, bottom left
stripes = Image.new("RGBA", (N, N), (0, 0, 0, 0))
sd = ImageDraw.Draw(stripes)
for k in range(3):
    o = k * 26
    sd.polygon(p(5, 168 + o, 120 + o, 250, 132 + o, 250, 5, 180 + o), fill=STRIPE + (255,))
mask = Image.new("L", (N, N), 0)
ImageDraw.Draw(mask).rounded_rectangle(p(5, 5, 250, 250), radius=40 * S, fill=255)
im.paste(stripes, (0, 0), Image.composite(stripes.split()[-1], Image.new("L", (N, N), 0), mask))
# viewfinder corners
w = 7
for x, y, dx, dy in ((38, 38, 1, 1), (217, 38, -1, 1)):
    d.rectangle(p(min(x, x + dx * 22), y, max(x, x + dx * 22), y + w), fill=GOLD)
    d.rectangle(p(x if dx > 0 else x - w, y, (x + w) if dx > 0 else x, y + 22), fill=GOLD)
# film reels
for cx in (92, 150):
    d.ellipse(p(cx - 30, 52, cx + 30, 112), fill=GOLD)
    d.ellipse(p(cx - 21, 61, cx + 21, 103), fill=NIGHT)
    d.ellipse(p(cx - 8, 74, cx + 8, 90), fill=GOLD)
    for ax, ay in ((0, -14), (12, 7), (-12, 7)):
        d.ellipse(p(cx + ax - 5, 82 + ay - 5, cx + ax + 5, 82 + ay + 5), fill=GOLD)
# camera body and lens hood
d.rounded_rectangle(p(46, 110, 182, 196), radius=14 * S, fill=CREAM)
d.polygon(p(182, 138, 222, 116, 222, 190, 182, 168), fill=CREAM)
d.rounded_rectangle(p(60, 124, 92, 136), radius=6 * S, fill=GOLD)
# the recording light
d.ellipse(p(150, 122, 168, 140), fill=(196, 64, 52))
# lens window on the body: a little field picture
d.rounded_rectangle(p(62, 148, 166, 184), radius=8 * S, fill=FIELD)
d.rectangle(p(62, 166, 166, 172), fill=(58, 128, 92))
d.ellipse(p(118, 152, 132, 166), fill=GOLD)
# the DTM pin, bottom right
d.ellipse(p(204, 204, 238, 238), fill=GOLD)
d.ellipse(p(210, 210, 232, 232), fill=CREAM)
out = os.path.join(REPO, "icon_videoStudio.png")
im.resize((256, 256), Image.LANCZOS).save(out)
print(out)
