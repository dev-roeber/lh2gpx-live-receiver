#!/usr/bin/env python3
"""Einmaliges Build-Skript zur Erzeugung der PWA-Icons (manifest.json,
apple-touch-icon). Nicht Teil der Laufzeit-Dependencies der App — nur per
system-python3 (mit Pillow) ausgeführt, Ergebnis-PNGs werden ins Repo
eingecheckt. Vorlage: webui/static/gen_icons.py (YT-DL-CLI), angepasst auf
das iOS-Dark-Theme dieser App: Mint-Akzent (--mint: #30D158, siehe
app/static/css/app.css) über dunklem Verlauf, Glyph = Standort-Pin (die App
ist primär Live-GPS-Tracking, kein generischer Pfeil).
"""
from PIL import Image, ImageDraw

MINT = (48, 209, 88)      # #30D158 — --mint
MINT_DEEP = (10, 90, 46)  # dunklerer Mint-Ton für Verlaufstiefe
DARK = (10, 10, 10)       # Glyph-Farbe (fast Schwarz, wie --bg)


def gradient_bg(size: int, radius_frac: float) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1)) if size > 1 else 0
            r = round(MINT_DEEP[0] + (MINT[0] - MINT_DEEP[0]) * t)
            g = round(MINT_DEEP[1] + (MINT[1] - MINT_DEEP[1]) * t)
            b = round(MINT_DEEP[2] + (MINT[2] - MINT_DEEP[2]) * t)
            px[x, y] = (r, g, b, 255)
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    radius = int(size * radius_frac)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def draw_pin(img: Image.Image, scale: float) -> None:
    """Standort-Pin: Kreis oben, spitz zulaufend nach unten, mit Loch."""
    size = img.width
    d = ImageDraw.Draw(img)
    s = size * scale
    cx = size / 2
    top = size / 2 - s * 0.55
    head_r = s * 0.36
    head_cy = top + head_r
    tip_y = top + s * 1.15

    # Hintergrundfarbe am Lochmittelpunkt VOR dem Zeichnen des Pins sampeln,
    # sonst würde nach dem Pin-Zeichnen nur noch DARK zurückgegeben.
    hole_r = head_r * 0.42
    bg_sample = img.getpixel((int(cx), int(head_cy)))

    # Pin-Körper: Kreis + Dreieck als Polygon approximiert, dann Kreis erneut
    # oben drüber gezeichnet für glatte Rundung.
    d.polygon(
        [
            (cx - head_r * 0.92, head_cy + head_r * 0.35),
            (cx + head_r * 0.92, head_cy + head_r * 0.35),
            (cx, tip_y),
        ],
        fill=DARK,
    )
    d.ellipse(
        [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
        fill=DARK,
    )

    # Loch in der Mitte des Pin-Kopfs (Hintergrundfarbe durchscheinen lassen)
    d.ellipse(
        [cx - hole_r, head_cy - hole_r, cx + hole_r, head_cy + hole_r],
        fill=bg_sample,
    )


def make_icon(size: int, radius_frac: float, pin_scale: float, path: str) -> None:
    img = gradient_bg(size, radius_frac)
    draw_pin(img, pin_scale)
    img.save(path)
    print(f"wrote {path} ({size}x{size})")


if __name__ == "__main__":
    # Reguläre Icons: abgerundetes Quadrat, Pin füllt gut aus.
    make_icon(192, 0.22, 0.62, "icon-192.png")
    make_icon(512, 0.22, 0.62, "icon-512.png")
    # Maskable: voller Bleed ohne eigene Rundung (das OS legt die Maske selbst
    # an), Pin kleiner skaliert damit er innerhalb der garantierten
    # Safe-Zone (Kreis mit ~80% Durchmesser mittig) bleibt.
    make_icon(192, 0.0, 0.42, "icon-maskable-192.png")
    make_icon(512, 0.0, 0.42, "icon-maskable-512.png")
    # Apple-Touch-Icon: iOS rundet selbst ab, erwartet volles Quadrat ohne
    # Transparenz -> voller Bleed (radius_frac=0) wie maskable, RGB geflattet.
    apple = gradient_bg(180, 0.0)
    draw_pin(apple, 0.55)
    apple.convert("RGB").save("apple-touch-icon.png")
    print("wrote apple-touch-icon.png (180x180)")
