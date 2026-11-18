#!/usr/bin/env python3
"""news-image-20261117 -- The World In One Picture, Tuesday 17 November 2026.

A newspaper front page drawn entirely by this program: its own PNG
encoder, its own pixel canvas, its own single-stroke vector font and
flat shape illustrations for eight stories of the day.  Standard
library only, fully deterministic (no time, no randomness, no files
read), so two runs write identical bytes.
"""
import math
import os
import struct
import zlib

# ---------------------------------------------------------------- canvas

SS = 2                      # supersample factor (render 2048, ship 1024)
W = 1024 * SS
H = 1024 * SS

PAPER = (247, 242, 231)
INK = (22, 22, 24)
RED = (179, 32, 42)
BLUEGREY = (84, 102, 122)
SKY = (203, 220, 232)
WATER = (126, 164, 190)
SAND = (226, 205, 158)
GREEN = (96, 138, 92)
GOLD = (214, 164, 52)
WHITE = (255, 255, 255)
LIGHT = (238, 231, 214)
MIDGREY = (150, 148, 140)


class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(bg) * (w * h)

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = c[0]
            self.px[i + 1] = c[1]
            self.px[i + 2] = c[2]

    def rect(self, x, y, w, h, c):
        x0 = max(0, int(x)); y0 = max(0, int(y))
        x1 = min(self.w, int(x + w)); y1 = min(self.h, int(y + h))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(c) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def disc(self, cx, cy, r, c):
        r = abs(r)
        x0 = int(cx - r - 1); x1 = int(cx + r + 1)
        y0 = int(cy - r - 1); y1 = int(cy + r + 1)
        r2 = r * r
        for yy in range(y0, y1 + 1):
            dy = yy - cy
            for xx in range(x0, x1 + 1):
                dx = xx - cx
                if dx * dx + dy * dy <= r2:
                    self.set(xx, yy, c)

    def ring(self, cx, cy, r, thick, c):
        ro = r + thick / 2.0
        ri = max(0.0, r - thick / 2.0)
        x0 = int(cx - ro - 1); x1 = int(cx + ro + 1)
        y0 = int(cy - ro - 1); y1 = int(cy + ro + 1)
        for yy in range(y0, y1 + 1):
            dy = yy - cy
            for xx in range(x0, x1 + 1):
                dx = xx - cx
                d = math.sqrt(dx * dx + dy * dy)
                if ri <= d <= ro:
                    self.set(xx, yy, c)

    def line(self, x0, y0, x1, y1, thick, c):
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        r = thick / 2.0
        for i in range(steps + 1):
            t = i / steps if steps else 0
            self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, c)

    def polyline(self, pts, thick, c, close=False):
        seq = list(pts)
        if close and len(seq) > 2:
            seq.append(seq[0])
        for a, b in zip(seq, seq[1:]):
            self.line(a[0], a[1], b[0], b[1], thick, c)

    def polygon(self, pts, c):
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys))); y1 = min(self.h - 1, int(max(ys)))
        n = len(pts)
        for yy in range(y0, y1 + 1):
            yc = yy + 0.5
            xs = []
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if (ay <= yc < by) or (by <= yc < ay):
                    xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.rect(xs[i], yy, xs[i + 1] - xs[i], 1, c)

    def triangle(self, a, b, cpt, c):
        self.polygon([a, b, cpt], c)

    def arc(self, cx, cy, r, a0, a1, thick, c):
        steps = max(8, int(abs(a1 - a0) * r / 4))
        prev = None
        for i in range(steps + 1):
            t = a0 + (a1 - a0) * i / steps
            p = (cx + r * math.cos(t), cy + r * math.sin(t))
            if prev is not None:
                self.line(prev[0], prev[1], p[0], p[1], thick, c)
            prev = p


def downscale(cv):
    """Box-average the 2x canvas down to 1024x1024 RGB bytes."""
    out = bytearray(1024 * 1024 * 3)
    w = cv.w
    px = cv.px
    for y in range(1024):
        sy = y * SS
        for x in range(1024):
            sx = x * SS
            i00 = ((sy * w) + sx) * 3
            i01 = i00 + 3
            i10 = i00 + w * 3
            i11 = i10 + 3
            o = (y * 1024 + x) * 3
            for k in range(3):
                out[o + k] = (px[i00 + k] + px[i01 + k] +
                              px[i10 + k] + px[i11 + k] + 2) // 4
    return bytes(out)


def write_png(path, rgb, w, h):
    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body +
                struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
           chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


# ---------------------------------------------------------------- font
# Single-stroke vector font, designed on a 0..5 wide, 0..9 tall grid
# (y grows downward, 0 = cap top, 9 = baseline).  Each glyph is a list
# of strokes; each stroke is a list of (x, y) points joined by lines.

GLYPHS = {
    "A": [[(0, 9), (2.5, 0), (5, 9)], [(1.3, 6), (3.7, 6)]],
    "B": [[(0, 9), (0, 0), (3, 0), (4.2, 1.2), (4.2, 3.2), (3, 4.5),
           (0, 4.5)], [(3, 4.5), (4.4, 5.7), (4.4, 7.8), (3, 9), (0, 9)]],
    "C": [[(4.8, 2.2), (3.4, 0.4), (1.6, 0.4), (0.3, 2), (0.3, 7),
           (1.6, 8.6), (3.4, 8.6), (4.8, 6.8)]],
    "D": [[(0, 9), (0, 0), (2.8, 0), (4.6, 2.2), (4.6, 6.8), (2.8, 9),
           (0, 9)]],
    "E": [[(4.6, 0), (0, 0), (0, 9), (4.6, 9)], [(0, 4.5), (3.6, 4.5)]],
    "F": [[(0, 9), (0, 0), (4.6, 0)], [(0, 4.5), (3.4, 4.5)]],
    "G": [[(4.8, 2.2), (3.4, 0.4), (1.6, 0.4), (0.3, 2), (0.3, 7),
           (1.6, 8.6), (3.6, 8.6), (4.8, 7), (4.8, 5), (2.8, 5)]],
    "H": [[(0, 0), (0, 9)], [(5, 0), (5, 9)], [(0, 4.5), (5, 4.5)]],
    "I": [[(2.5, 0), (2.5, 9)], [(0.6, 0), (4.4, 0)], [(0.6, 9), (4.4, 9)]],
    "J": [[(4.6, 0), (4.6, 7), (3.4, 8.8), (1.4, 8.8), (0.2, 7.4)]],
    "K": [[(0, 0), (0, 9)], [(4.8, 0), (0.4, 4.6), (5, 9)]],
    "L": [[(0, 0), (0, 9), (4.6, 9)]],
    "M": [[(0, 9), (0, 0), (2.5, 4.6), (5, 0), (5, 9)]],
    "N": [[(0, 9), (0, 0), (5, 9), (5, 0)]],
    "O": [[(1.6, 0.4), (3.4, 0.4), (4.7, 2), (4.7, 7), (3.4, 8.6),
           (1.6, 8.6), (0.3, 7), (0.3, 2), (1.6, 0.4)]],
    "P": [[(0, 9), (0, 0), (3.2, 0), (4.6, 1.4), (4.6, 3.4), (3.2, 4.8),
           (0, 4.8)]],
    "Q": [[(1.6, 0.4), (3.4, 0.4), (4.7, 2), (4.7, 7), (3.4, 8.6),
           (1.6, 8.6), (0.3, 7), (0.3, 2), (1.6, 0.4)],
          [(3, 6.4), (5.2, 9.2)]],
    "R": [[(0, 9), (0, 0), (3.2, 0), (4.6, 1.4), (4.6, 3.4), (3.2, 4.8),
           (0, 4.8)], [(2.8, 4.8), (4.9, 9)]],
    "S": [[(4.7, 1.8), (3.4, 0.3), (1.5, 0.3), (0.4, 1.6), (0.9, 3.4),
           (4.1, 5.4), (4.6, 7.2), (3.4, 8.7), (1.4, 8.7), (0.3, 7.2)]],
    "T": [[(0, 0), (5, 0)], [(2.5, 0), (2.5, 9)]],
    "U": [[(0, 0), (0, 6.8), (1.2, 8.6), (3.8, 8.6), (5, 6.8), (5, 0)]],
    "V": [[(0, 0), (2.5, 9), (5, 0)]],
    "W": [[(0, 0), (1, 9), (2.5, 3.6), (4, 9), (5, 0)]],
    "X": [[(0, 0), (5, 9)], [(5, 0), (0, 9)]],
    "Y": [[(0, 0), (2.5, 4.4), (5, 0)], [(2.5, 4.4), (2.5, 9)]],
    "Z": [[(0, 0), (5, 0), (0, 9), (5, 9)]],
    "0": [[(1.6, 0.4), (3.4, 0.4), (4.6, 2), (4.6, 7), (3.4, 8.6),
           (1.6, 8.6), (0.4, 7), (0.4, 2), (1.6, 0.4)],
          [(1, 7), (4, 2)]],
    "1": [[(1.2, 1.8), (3, 0), (3, 9)], [(0.8, 9), (5, 9)]],
    "2": [[(0.4, 2), (1.6, 0.4), (3.4, 0.4), (4.6, 2), (4.4, 3.8),
           (0.2, 9), (4.8, 9)]],
    "3": [[(0.4, 1.6), (1.8, 0.3), (3.4, 0.3), (4.5, 1.8), (3.2, 4.2),
           (1.8, 4.2)], [(3.2, 4.2), (4.6, 5.8), (4.4, 7.6), (3, 8.7),
           (1.4, 8.7), (0.3, 7.4)]],
    "4": [[(3.4, 9), (3.4, 0), (0.2, 6.4), (5, 6.4)]],
    "5": [[(4.7, 0), (0.6, 0), (0.4, 4.2), (3, 3.8), (4.6, 5.2),
           (4.6, 7.2), (3.2, 8.7), (1.2, 8.7), (0.2, 7.6)]],
    "6": [[(4.4, 1.6), (2.8, 0.2), (1.2, 1.4), (0.4, 4), (0.4, 7),
           (1.6, 8.6), (3.4, 8.6), (4.6, 7), (4.4, 5.2), (3, 4.2),
           (0.6, 4.6)]],
    "7": [[(0.2, 0), (4.8, 0), (2, 9)]],
    "8": [[(1.7, 4.3), (0.6, 3), (1, 1.2), (2.5, 0.3), (4, 1.2),
           (4.4, 3), (3.3, 4.3), (4.6, 5.8), (4.2, 7.8), (2.5, 8.7),
           (0.8, 7.8), (0.4, 5.8), (1.7, 4.3)]],
    "9": [[(0.6, 7.4), (2.2, 8.8), (3.8, 7.6), (4.6, 5), (4.6, 2),
           (3.4, 0.4), (1.6, 0.4), (0.4, 2), (0.6, 3.8), (2, 4.8),
           (4.4, 4.4)]],
    ".": [],
    ",": [[(2.6, 8.6), (1.8, 10.2)]],
    "'": [[(2.5, 0), (2.2, 2)]],
    "-": [[(0.8, 4.5), (4.2, 4.5)]],
    ":": [],
    ";": [[(2.6, 8.6), (1.8, 10.2)]],
    "!": [[(2.5, 0), (2.5, 6.4)]],
    "?": [[(0.4, 1.8), (1.6, 0.3), (3.4, 0.3), (4.6, 1.8), (4.2, 3.6),
           (2.5, 5), (2.5, 6.6)]],
    "/": [[(5, 0), (0, 9)]],
    "%": [[(1.4, 0.4), (2.6, 1), (2.4, 2.6), (1.2, 2), (1.4, 0.4)],
          [(5, 0), (0, 9)],
          [(3.8, 6.4), (5, 7), (4.8, 8.6), (3.6, 8), (3.8, 6.4)]],
    "(": [[(3.6, 0.4), (1.8, 2.4), (1.8, 6.6), (3.6, 8.6)]],
    ")": [[(1.4, 0.4), (3.2, 2.4), (3.2, 6.6), (1.4, 8.6)]],
    "&": [[(4.6, 8.6), (1.2, 5.2), (0.6, 3), (1.6, 0.6), (3.2, 0.8),
           (3, 2.8), (0.4, 6.4), (1.2, 8.4), (3.4, 8.6), (4.8, 6.6)]],
    "+": [[(2.5, 2), (2.5, 7)], [(0.4, 4.5), (4.6, 4.5)]],
    "$": [[(2.5, -0.6), (2.5, 9.6)],
          [(4.7, 1.8), (3.4, 0.3), (1.5, 0.3), (0.4, 1.6), (0.9, 3.4),
           (4.1, 5.4), (4.6, 7.2), (3.4, 8.7), (1.4, 8.7), (0.3, 7.2)]],
    "*": [[(2.5, 1), (2.5, 6)], [(0.8, 2), (4.2, 5)], [(4.2, 2), (0.8, 5)]],
}

ADV = 6.4          # glyph advance in grid units (glyph box 5 + gap)
DOT_CHARS = ".:"   # drawn as filled dots, handled in draw_text
BULLET = "•"


def text_width(s, size):
    """Width in final-image pixels of string s at cap-height size."""
    return len(s) * ADV * size / 9.0


def draw_text(cv, s, x, y, size, color, thick=None, align="left"):
    """Draw s with its baseline top at (x, y) in final-image coords.

    size is the cap height in final-image pixels; x, y likewise.
    Coordinates are scaled by SS for the supersampled canvas.
    """
    if thick is None:
        thick = max(1.6, size * 0.16)
    w = text_width(s, size)
    if align == "center":
        x -= w / 2.0
    elif align == "right":
        x -= w
    scale = size / 9.0 * SS
    t = thick * SS
    cx = x * SS
    top = y * SS
    for ch in s:
        if ch == " ":
            cx += ADV * scale
            continue
        if ch in DOT_CHARS:
            n = 1 if ch == "." else 2
            ys = [8.2] if n == 1 else [2.2, 8.2]
            for gy in ys:
                cv.disc(cx + 2.5 * scale, top + gy * scale,
                        max(t * 0.62, 1.4), color)
            cx += ADV * scale
            continue
        if ch == BULLET:
            cv.disc(cx + 2.5 * scale, top + 4.5 * scale,
                    max(t * 0.7, 1.6), color)
            cx += ADV * scale
            continue
        glyph = GLYPHS.get(ch)
        if glyph is None:
            cx += ADV * scale
            continue
        for stroke in glyph:
            pts = [(cx + gx * scale, top + gy * scale) for gx, gy in stroke]
            if len(pts) == 1:
                cv.disc(pts[0][0], pts[0][1], t / 2.0, color)
            else:
                cv.polyline(pts, t, color)
        cx += ADV * scale
    return w


def wrap_text(s, size, max_w):
    """Greedy word wrap; returns list of lines fitting max_w pixels."""
    words = s.split()
    lines = []
    cur = ""
    for wd in words:
        trial = wd if not cur else cur + " " + wd
        if text_width(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def draw_wrapped(cv, s, x, y, size, color, max_w, leading=1.28,
                 align="left", thick=None, max_lines=None):
    lines = wrap_text(s, size, max_w)
    if max_lines:
        lines = lines[:max_lines]
    yy = y
    for ln in lines:
        draw_text(cv, ln, x, yy, size, color, thick=thick, align=align)
        yy += size * leading
    return yy


# ---------------------------------------------------------------- drawing
# All layout coordinates below are in final-image pixels (1024 space);
# helpers scale them onto the supersampled canvas.

def S(v):
    return v * SS


def R(cv, x, y, w, h, c):
    cv.rect(S(x), S(y), S(w), S(h), c)


def DISC(cv, x, y, r, c):
    cv.disc(S(x), S(y), S(r), c)


def LINE(cv, x0, y0, x1, y1, t, c):
    cv.line(S(x0), S(y0), S(x1), S(y1), S(t), c)


def POLY(cv, pts, t, c, close=False):
    cv.polyline([(S(a), S(b)) for a, b in pts], S(t), c, close)


def FILL(cv, pts, c):
    cv.polygon([(S(a), S(b)) for a, b in pts], c)


def border(cv, x, y, w, h, c=INK, t=2.5):
    R(cv, x, y, w, t, c)
    R(cv, x, y + h - t, w, t, c)
    R(cv, x, y, t, h, c)
    R(cv, x + w - t, y, t, h, c)


def burst(cv, cx, cy, r, c, n=8):
    for i in range(n):
        a = 2 * math.pi * i / n
        x1 = cx + r * math.cos(a)
        y1 = cy + r * math.sin(a)
        LINE(cv, cx, cy, x1, y1, 3.4, c)
    DISC(cv, cx, cy, r * 0.22, c)


def drone(cv, cx, cy, s, c=INK):
    """Tiny quadcopter: X arms, four rotor discs, body."""
    d = s * 0.62
    for dx, dy in ((-d, -d), (d, -d), (-d, d), (d, d)):
        LINE(cv, cx, cy, cx + dx, cy + dy, 2.2, c)
        DISC(cv, cx + dx, cy + dy, s * 0.30, c)
    DISC(cv, cx, cy, s * 0.34, c)


def jet(cv, cx, cy, s, c=INK, flip=1):
    """Simple fighter-jet silhouette pointing right (flip=-1: left)."""
    pts = [(cx + 1.5 * s * flip, cy), (cx + 0.2 * s * flip, cy - 0.28 * s),
           (cx - 0.1 * s * flip, cy - 0.95 * s), (cx - 0.55 * s * flip,
           cy - 0.95 * s), (cx - 0.45 * s * flip, cy - 0.25 * s),
           (cx - 1.3 * s * flip, cy - 0.55 * s), (cx - 1.5 * s * flip,
           cy - 0.55 * s), (cx - 1.25 * s * flip, cy),
           (cx - 1.5 * s * flip, cy + 0.55 * s), (cx - 1.3 * s * flip,
           cy + 0.55 * s), (cx - 0.45 * s * flip, cy + 0.25 * s),
           (cx - 0.55 * s * flip, cy + 0.95 * s), (cx - 0.1 * s * flip,
           cy + 0.95 * s), (cx + 0.2 * s * flip, cy + 0.28 * s)]
    FILL(cv, pts, c)


# ------------------------------------------------------------- icons
# Each icon draws inside box (x, y, w, h), final-image pixels.

def icon_bridge(cv, x, y, w, h):
    R(cv, x, y, w, h, SKY)
    gy = y + h * 0.58                     # deck height
    # towers
    R(cv, x + w * 0.16, gy - h * 0.34, w * 0.07, h * 0.34, INK)
    R(cv, x + w * 0.77, gy - h * 0.34, w * 0.07, h * 0.34, INK)
    # deck, broken in the middle
    R(cv, x + w * 0.03, gy, w * 0.40, h * 0.07, INK)
    R(cv, x + w * 0.60, gy, w * 0.37, h * 0.07, INK)
    # fallen span, tilted into the water
    FILL(cv, [(x + w * 0.44, gy + h * 0.05), (x + w * 0.60, gy + h * 0.05),
              (x + w * 0.64, gy + h * 0.24), (x + w * 0.48, gy + h * 0.24)],
         INK)
    # cables
    POLY(cv, [(x + w * 0.20, gy - h * 0.32), (x + w * 0.42, gy - h * 0.02)],
         2, BLUEGREY)
    POLY(cv, [(x + w * 0.80, gy - h * 0.32), (x + w * 0.62, gy - h * 0.02)],
         2, BLUEGREY)
    # blast at the break + drones above
    burst(cv, x + w * 0.51, gy - h * 0.10, w * 0.075, RED)
    drone(cv, x + w * 0.30, y + h * 0.16, w * 0.058)
    drone(cv, x + w * 0.68, y + h * 0.12, w * 0.048)
    drone(cv, x + w * 0.86, y + h * 0.24, w * 0.040)
    # water: from just below the deck line to the bottom of the icon
    # box (the old height formula ran 42% of the box past its bottom,
    # spilling a blue strip across the panels below)
    wy = gy + h * 0.16
    R(cv, x, wy, w, y + h - wy, WATER)
    for i, fx in enumerate((0.10, 0.34, 0.58, 0.82)):
        wy = gy + h * (0.26 + 0.13 * (i % 2))
        POLY(cv, [(x + w * fx, wy), (x + w * (fx + 0.05), wy - h * 0.035),
                  (x + w * (fx + 0.10), wy)], 2.4, WHITE)


def icon_radar(cv, x, y, w, h):
    R(cv, x, y, w, h, SKY)
    cx, cy = x + w * 0.42, y + h * 0.50
    # dish: filled pie slice aimed up-right, feed arm, stand
    pts = [(cx, cy)]
    for i in range(13):
        a = -2.55 + 1.55 * i / 12
        pts.append((cx + w * 0.30 * math.cos(a), cy + h * 0.34 * math.sin(a)))
    FILL(cv, pts, BLUEGREY)
    POLY(cv, pts[1:], 3, INK)
    fx, fy = cx + w * 0.17, cy - h * 0.24
    LINE(cv, cx, cy, fx, fy, 3, INK)
    DISC(cv, fx, fy, 3.6, RED)
    LINE(cv, cx, cy, cx - w * 0.12, y + h * 0.92, 5, INK)
    LINE(cv, cx, cy, cx + w * 0.16, y + h * 0.92, 5, INK)
    R(cv, x, y + h * 0.92, w, h * 0.08, INK)
    # signal arcs leaving the feed
    for r in (0.15, 0.23):
        cv.arc(S(fx), S(fy), S(w * r), -1.25, -0.25, S(3), BLUEGREY)
    # incoming drone + intercept burst (drone in ink: drawn in red it
    # read as a stray "X" mark rather than an aircraft)
    drone(cv, x + w * 0.82, y + h * 0.18, w * 0.085, INK)
    burst(cv, x + w * 0.64, y + h * 0.33, w * 0.08, GOLD)


def icon_manila(cv, x, y, w, h):
    R(cv, x, y, w, h, SKY)
    DISC(cv, x + w * 0.82, y + h * 0.20, w * 0.09, GOLD)
    # skyline
    base = y + h * 0.94
    for bx, bw, bh in ((0.04, 0.16, 0.42), (0.22, 0.13, 0.60),
                       (0.37, 0.17, 0.34), (0.56, 0.13, 0.52),
                       (0.71, 0.16, 0.40), (0.88, 0.10, 0.56)):
        R(cv, x + w * bx, base - h * bh, w * bw, h * bh, BLUEGREY)
    R(cv, x, base, w, h * 0.06, INK)
    # windows
    for i in range(3):
        for j in range(3):
            R(cv, x + w * (0.245 + 0.035 * i), y + h * (0.46 + 0.12 * j),
              w * 0.018, h * 0.05, WHITE)
    jet(cv, x + w * 0.34, y + h * 0.20, w * 0.16, INK)


def icon_japan(cv, x, y, w, h):
    R(cv, x, y, w, h, SKY)
    # Japanese flag: white field, one red disc (concentric rings read
    # as a target, not a flag)
    R(cv, x + w * 0.20, y + h * 0.24, w * 0.60, h * 0.52, WHITE)
    POLY(cv, [(x + w * 0.20, y + h * 0.24), (x + w * 0.80, y + h * 0.24),
              (x + w * 0.80, y + h * 0.76), (x + w * 0.20, y + h * 0.76)],
         2.5, INK, close=True)
    DISC(cv, x + w * 0.50, y + h * 0.50, w * 0.13, RED)
    jet(cv, x + w * 0.26, y + h * 0.13, w * 0.11, INK)
    jet(cv, x + w * 0.74, y + h * 0.88, w * 0.11, BLUEGREY, flip=-1)
    R(cv, x, y + h * 0.94, w, h * 0.06, INK)


def icon_chip(cv, x, y, w, h):
    R(cv, x, y, w, h, LIGHT)
    bx, by, bs = x + w * 0.16, y + h * 0.22, w * 0.44
    for i in range(3):  # pins
        px = bx + bs * (0.18 + 0.27 * i)
        R(cv, px, by - h * 0.10, w * 0.045, h * 0.10, INK)
        R(cv, px, by + bs, w * 0.045, h * 0.10, INK)
        py = by + bs * (0.18 + 0.27 * i)
        R(cv, bx - w * 0.055, py, w * 0.055, h * 0.075, INK)
        R(cv, bx + bs, py, w * 0.055, h * 0.075, INK)
    R(cv, bx, by, bs, bs, INK)
    R(cv, bx + bs * 0.24, by + bs * 0.24, bs * 0.52, bs * 0.52, GOLD)
    # rising arrow
    ax, ay = x + w * 0.70, y + h * 0.80
    POLY(cv, [(ax, ay), (x + w * 0.80, y + h * 0.58),
              (x + w * 0.88, y + h * 0.40)], 5, GREEN)
    FILL(cv, [(x + w * 0.88, y + h * 0.22), (x + w * 0.97, y + h * 0.38),
              (x + w * 0.80, y + h * 0.44)], GREEN)


def icon_knesset(cv, x, y, w, h):
    R(cv, x, y, w, h, LIGHT)
    cx = x + w / 2
    FILL(cv, [(x + w * 0.10, y + h * 0.30), (cx, y + h * 0.08),
              (x + w * 0.90, y + h * 0.30)], INK)
    R(cv, x + w * 0.10, y + h * 0.33, w * 0.80, h * 0.06, INK)
    for i in range(4):
        R(cv, x + w * (0.16 + 0.19 * i), y + h * 0.42, w * 0.075,
          h * 0.36, BLUEGREY)
    R(cv, x + w * 0.10, y + h * 0.80, w * 0.80, h * 0.06, INK)
    # ballot tick in a red disc
    DISC(cv, x + w * 0.82, y + h * 0.80, w * 0.115, RED)
    POLY(cv, [(x + w * 0.765, y + h * 0.80), (x + w * 0.805, y + h * 0.845),
              (x + w * 0.885, y + h * 0.745)], 4.5, WHITE)


def icon_aden(cv, x, y, w, h):
    R(cv, x, y, w, h, WATER)
    # land mass on the left, coastline curving to a port at bottom right
    FILL(cv, [(x, y), (x + w * 0.52, y), (x + w * 0.46, y + h * 0.30),
              (x + w * 0.62, y + h * 0.55), (x + w * 0.55, y + h),
              (x, y + h)], SAND)
    POLY(cv, [(x + w * 0.52, y), (x + w * 0.46, y + h * 0.30),
              (x + w * 0.62, y + h * 0.55), (x + w * 0.55, y + h)],
         3, INK)
    # advance arrow toward the port
    POLY(cv, [(x + w * 0.20, y + h * 0.24), (x + w * 0.44, y + h * 0.50),
              (x + w * 0.66, y + h * 0.72)], 5, RED)
    FILL(cv, [(x + w * 0.66, y + h * 0.56), (x + w * 0.80, y + h * 0.76),
              (x + w * 0.58, y + h * 0.82)], RED)
    # anchor marking the port of Aden
    ax, ay = x + w * 0.82, y + h * 0.60
    cv.ring(S(ax), S(ay - h * 0.10), S(w * 0.045), S(3.4), WHITE)
    LINE(cv, ax, ay - h * 0.05, ax, ay + h * 0.20, 3.6, WHITE)
    LINE(cv, ax - w * 0.07, ay + h * 0.02, ax + w * 0.07, ay + h * 0.02,
         3.6, WHITE)
    POLY(cv, [(ax - w * 0.11, ay + h * 0.13), (ax - w * 0.02, ay + h * 0.22),
              (ax, ay + h * 0.13)], 3.2, WHITE)
    POLY(cv, [(ax + w * 0.11, ay + h * 0.13), (ax + w * 0.02, ay + h * 0.22),
              (ax, ay + h * 0.13)], 3.2, WHITE)


def icon_robot(cv, x, y, w, h):
    R(cv, x, y, w, h, LIGHT)
    cx = x + w / 2
    # antenna + head
    LINE(cv, cx, y + h * 0.16, cx, y + h * 0.30, 4, INK)
    DISC(cv, cx, y + h * 0.13, w * 0.05, RED)
    R(cv, x + w * 0.24, y + h * 0.30, w * 0.52, h * 0.44, INK)
    DISC(cv, x + w * 0.40, y + h * 0.50, w * 0.055, WHITE)
    DISC(cv, x + w * 0.60, y + h * 0.50, w * 0.055, WHITE)
    R(cv, x + w * 0.38, y + h * 0.64, w * 0.24, h * 0.045, WHITE)
    R(cv, x + w * 0.17, y + h * 0.44, w * 0.07, h * 0.16, INK)
    R(cv, x + w * 0.76, y + h * 0.44, w * 0.07, h * 0.16, INK)
    # laurel branches below
    for sgn in (-1, 1):
        for i in range(3):
            lx = cx + sgn * w * (0.13 + 0.09 * i)
            ly = y + h * (0.90 - 0.035 * i)
            cv.arc(S(lx), S(ly), S(w * 0.05), 0.4, 2.4, S(3), GREEN)
    # ban slash
    cv.ring(S(cx), S(y + h * 0.52), S(w * 0.44), S(5), RED)
    LINE(cv, cx - w * 0.31, y + h * 0.52 + h * 0.31,
         cx + w * 0.31, y + h * 0.52 - h * 0.31, 5, RED)


# ------------------------------------------------------------- layout

def panel(cv, x, y, w, h, kicker, icon, headline, sub,
          hsize=23, ssize=13.5, iw=92):
    # repaint the interior first so nothing drawn earlier can bleed
    # through, then border, icon, and text with a wider icon gutter
    R(cv, x, y, w, h, PAPER)
    border(cv, x, y, w, h, INK, 2.2)
    icon(cv, x + 10, y + (h - iw) / 2, iw, iw)
    tx = x + iw + 26
    tw = x + w - tx - 14
    draw_text(cv, kicker, tx, y + 10, 14, RED, thick=2.5)
    yy = draw_wrapped(cv, headline, tx, y + 32, hsize, INK, tw,
                      leading=1.18, thick=hsize * 0.17)
    draw_wrapped(cv, sub, tx, yy + 3, ssize, (58, 58, 60), tw,
                 leading=1.26, thick=ssize * 0.15)


def build():
    cv = Canvas(W, H, PAPER)
    M = 26
    CW = 1024 - 2 * M

    # ---- masthead (tightened by 14px so the story grid below gets
    # the extra vertical room; the date stays the biggest thing on
    # the page)
    draw_text(cv, "THE WORLD IN ONE PICTURE", 512, 16, 25, INK,
              align="center", thick=3.6)
    R(cv, M, 50, CW, 5, RED)
    draw_text(cv, "TUESDAY 17 NOVEMBER 2026", 512, 64, 51, INK,
              align="center", thick=8.2)
    R(cv, M, 128, CW, 2.5, INK)
    draw_text(cv, "EIGHT STORIES - EUROPE - MIDDLE EAST - ASIA - "
              "AMERICA - UNITED NATIONS", 512, 136, 14.5, BLUEGREY,
              align="center", thick=2.2)

    # ---- lead story
    lx, ly, lw, lh = M, 164, CW, 248
    border(cv, lx, ly, lw, lh, INK, 3)
    R(cv, lx, ly, lw, 6, RED)
    icon_bridge(cv, lx + 14, ly + 40, 330, 190)
    draw_text(cv, "CRIMEA - BLACK SEA", lx + 14, ly + 14, 14, RED,
              thick=2.4)
    tx = lx + 366
    tw = lx + lw - tx - 18
    draw_text(cv, "EUROPE - WAR - LEAD STORY", tx, ly + 16, 15, RED,
              thick=2.6)
    yy = draw_wrapped(cv, "UKRAINE BLOWS THE CRIMEA BRIDGE AGAIN",
                      tx, ly + 42, 41, INK, tw, leading=1.2, thick=7)
    draw_wrapped(cv, "SECOND DAY OF STRIKES IN THE LARGEST DRONE "
                 "ATTACK OF THE WAR. RUSSIA SAYS 1,441 DRONES WERE "
                 "DOWNED. KYIV BRIDGES HIT IN REPLY AND POWER CUT "
                 "IN 8 REGIONS.", tx, yy + 8, 18.5, (58, 58, 60), tw,
                 leading=1.3, thick=3)

    # ---- grid of seven
    gy = 426
    gap = 10
    rh1, rh2, rh3 = 164, 164, 160
    hw = (CW - gap) / 2
    panel(cv, M, gy, hw, rh1, "MIDDLE EAST", icon_radar,
          "IRAN DRONES STRIKE US RADAR IN BAHRAIN",
          "IRGC DRONES FIRED AT SHEIKH ISA BASE. BAHRAIN INTERCEPTED "
          "THEM, NO CASUALTIES. THIRD US CARRIER SAILS IN.")
    panel(cv, M + hw + gap, gy, hw, rh1, "ASIA - DIPLOMACY", icon_manila,
          "TRUMP IN MANILA FOR ASEAN TALKS",
          "TRUMP ARRIVED FOR ASEAN AND QUAD MEETINGS. TRILATERAL "
          "WITH XI AND PUTIN FOLLOWS NOV 19 IN SHENZHEN.")
    gy2 = gy + rh1 + gap
    panel(cv, M, gy2, hw, rh2, "ASIA - SECURITY", icon_japan,
          "JAPAN SCRAMBLES JETS OVER RUSSIAN JETS",
          "FIGHTERS LAUNCHED, PROTEST LODGED AFTER TWO SUSPECTED "
          "RUSSIAN JETS ENTERED JAPAN AIRSPACE.")
    panel(cv, M + hw + gap, gy2, hw, rh2, "BUSINESS - TECH", icon_chip,
          "NVIDIA POSTS $116BN QUARTER",
          "Q3 REVENUE $116 BILLION, UP 103 PERCENT, IN FIRST EARNINGS "
          "SINCE CEO JENSEN HUANG EXIT.")
    gy3 = gy2 + rh2 + gap
    tw3 = (CW - 2 * gap) / 3
    panel(cv, M, gy3, tw3, rh3, "ISRAEL - POLITICS", icon_knesset,
          "KNESSET OUSTS SPEAKER IN 66-52 VOTE",
          "NETANYAHU ALLY OHANA REPLACED BY KAHANA OF THE EISENKOT "
          "BLOC.", hsize=19.5, ssize=12.5, iw=84)
    panel(cv, M + tw3 + gap, gy3, tw3, rh3, "YEMEN - WAR", icon_aden,
          "HOUTHIS CLOSE IN ON ADEN",
          "GOVERNMENT FORCES FALL BACK FROM THE RED SEA COAST, "
          "40 MILES OUT.", hsize=19.5, ssize=12.5, iw=84)
    panel(cv, M + 2 * (tw3 + gap), gy3, tw3, rh3, "UNITED NATIONS",
          icon_robot, "128 STATES DEBATE ROBOT BAN",
          "HUMAN CONTROL TALKS IN GENEVA ON LETHAL ROBOT WEAPONS.",
          hsize=19.5, ssize=12.5, iw=84)

    # ---- ticker (a touch smaller than before: the first line ran
    # to within a few pixels of the bar's right edge)
    ty = gy3 + rh3 + 12
    R(cv, M, ty, CW, 54, INK)
    draw_text(cv, "COP31 DRAFT: FASTER FOSSIL PHASE-OUT, $120BN "
              "CLIMATE FINANCE - ICJ PREPARES MYANMAR GENOCIDE RULING",
              512, ty + 6, 13, WHITE, align="center", thick=2)
    draw_text(cv, "12,000+ US FLIGHTS CANCELLED IN FAA GROUND STOP - "
              "TANKERS HIT MINES IN HORMUZ", 512, ty + 29, 13, GOLD,
              align="center", thick=2)
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    cv = build()
    rgb = downscale(cv)
    write_png(os.path.join(out_dir, "entry.png"), rgb, 1024, 1024)


if __name__ == "__main__":
    main()
