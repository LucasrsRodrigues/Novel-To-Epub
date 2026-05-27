#!/usr/bin/env python3
"""Gera o icone do app — livrinho cream com bookmark ribbon, alinhado com a
estetica "Modern Paperback Library" do app.

Outputs:
  build/icon.icns       (macOS, multi-size iconset)
  build/icon.png        (1024x1024, usado como fallback/Linux)
  build/icon.ico        (Windows, multi-size ICO)
  resources/icon.png    (lido pelo main process do Electron via ?asset import)

Uso:
  cd electron && ../backend/.venv/bin/python scripts/build_icon.py
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# Paleta (mesma do app — index.css)
CREAM_LIGHT = "#fdf9f1"  # paper-100
CREAM = "#faf6ee"  # paper-50
TAN = "#ebe0c6"  # paper-300
BORDER_TAN = "#d4c6a9"

INK_DARK = (31, 26, 20)  # ink-900

BOOK_RED = "#b85b3f"  # book-1 (terracotta)
BOOK_RED_DARK = "#8c4530"
SPINE_DARK = "#5e2e21"

BOOKMARK = "#e5a93d"  # bookmark-ribbon
BOOKMARK_DARK = "#b07e22"

SIZE = 1024
CORNER = 230  # ~22% — squircle-ish


def make_icon(size: int = SIZE) -> Image.Image:
    """Devolve a Image RGBA com o icone renderizado no tamanho pedido (a partir de 1024)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ===== Background: rounded square cream c/ borda sutil =====
    draw.rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=CORNER, fill=CREAM_LIGHT, outline=BORDER_TAN, width=3
    )

    # vignette quente (overlay com leve gradiente sintetizado por 3 elipses)
    vign = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vign)
    vd.ellipse([-200, -200, size + 200, size + 200], fill=(196, 150, 90, 18))
    vd.ellipse([200, 600, size + 200, size + 200], fill=(180, 120, 60, 22))
    # mascara pra ficar dentro do rounded
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=CORNER, fill=255)
    vign.putalpha(Image.eval(vign.split()[-1], lambda v: int(v * 0.7)))
    img.paste(vign, (0, 0), mask)
    draw = ImageDraw.Draw(img)

    # ===== Book layer (separado pra poder rotacionar) =====
    BW, BH = 540, 700  # tamanho da capa
    PAD = 200  # margem extra p/ ribbon + shadow
    layer = Image.new("RGBA", (BW + PAD * 2, BH + PAD * 2), (0, 0, 0, 0))
    L = ImageDraw.Draw(layer)

    bx = PAD
    by = PAD

    # Shadow (oval embaixo + gaussian blur)
    shadow_l = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_l)
    sd.ellipse(
        [bx - 60, by + BH - 30, bx + BW + 60, by + BH + 50],
        fill=(*INK_DARK, 130),
    )
    shadow_l = shadow_l.filter(ImageFilter.GaussianBlur(28))
    layer = Image.alpha_composite(layer, shadow_l)
    L = ImageDraw.Draw(layer)

    # Back cover peek (desloca p/ direita-baixo p/ dar profundidade)
    L.rounded_rectangle(
        [bx + 36, by + 30, bx + BW + 36, by + BH + 30], radius=24, fill=(*INK_DARK, 180)
    )

    # Spine (faixa escura na esquerda)
    L.rounded_rectangle([bx, by, bx + 70, by + BH], radius=20, fill=SPINE_DARK)

    # Cover (terracotta) — sobreposta ao spine
    L.rounded_rectangle([bx + 46, by, bx + BW, by + BH], radius=20, fill=BOOK_RED)

    # Spine divider (linha sutil entre spine e cover)
    L.rectangle([bx + 70, by, bx + 76, by + BH], fill=(0, 0, 0, 50))

    # Top page edge (cream sliver)
    L.rectangle([bx + 56, by, bx + BW - 8, by + 20], fill=CREAM_LIGHT)
    # Right page edge
    L.rectangle([bx + BW - 18, by + 20, bx + BW, by + BH - 12], fill=TAN)

    # Decoracao na capa: duas linhas finas (suggestion of title)
    line_y = by + BH // 2 + 60
    L.rounded_rectangle(
        [bx + 130, line_y, bx + BW - 80, line_y + 14], radius=7, fill=(255, 255, 255, 95)
    )
    L.rounded_rectangle(
        [bx + 170, line_y + 36, bx + BW - 130, line_y + 46], radius=5, fill=(255, 255, 255, 65)
    )

    # Bookmark ribbon hanging from bottom (gold, com notch)
    rib_w = 110
    rib_cx = bx + BW // 2 + 20
    rib_left = rib_cx - rib_w // 2
    rib_right = rib_cx + rib_w // 2
    rib_top = by + BH - 60
    rib_bot = by + BH + 130
    notch_y = rib_bot - 60
    L.polygon(
        [
            (rib_left, rib_top),
            (rib_right, rib_top),
            (rib_right, rib_bot),
            (rib_cx, notch_y),
            (rib_left, rib_bot),
        ],
        fill=BOOKMARK,
    )
    # Ribbon top fold shadow
    L.rectangle([rib_left, rib_top, rib_right, rib_top + 16], fill=(0, 0, 0, 100))
    # Ribbon subtle right-edge shadow
    L.polygon(
        [(rib_right - 8, rib_top + 16), (rib_right, rib_top + 16), (rib_right, rib_bot)],
        fill=(0, 0, 0, 50),
    )

    # Rotaciona o book layer levemente
    layer = layer.rotate(-4, resample=Image.BICUBIC, expand=False)

    # Cola centralizado (leve offset para cima compensando o ribbon que estica p/ baixo)
    lw, lh = layer.size
    paste_x = (size - lw) // 2
    paste_y = (size - lh) // 2 - 30
    img.paste(layer, (paste_x, paste_y), layer)

    return img


def write_iconset_and_icns(master: Image.Image, icns_path: Path) -> None:
    """Cria um .iconset folder + usa iconutil pra gerar .icns."""
    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "app.iconset"
        iconset.mkdir()
        for fname, px in sizes:
            resized = master.resize((px, px), Image.LANCZOS)
            resized.save(iconset / fname, "PNG")
        subprocess.run(
            ["iconutil", "--convert", "icns", "--output", str(icns_path), str(iconset)],
            check=True,
        )


def write_ico(master: Image.Image, ico_path: Path) -> None:
    """PIL salva ICO multi-size de uma vez."""
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(ico_path, format="ICO", sizes=sizes)


def main() -> None:
    here = Path(__file__).resolve().parent.parent  # electron/
    build_dir = here / "build"
    resources_dir = here / "resources"
    build_dir.mkdir(exist_ok=True)
    resources_dir.mkdir(exist_ok=True)

    print("Renderizando icone 1024x1024…")
    master = make_icon(SIZE)

    png_path = build_dir / "icon.png"
    master.save(png_path, "PNG")
    print(f"  → {png_path.relative_to(here)} ({png_path.stat().st_size // 1024} KB)")

    # Linux + Electron main process leem de resources/icon.png
    shutil.copyfile(png_path, resources_dir / "icon.png")
    print(f"  → resources/icon.png (copy)")

    icns_path = build_dir / "icon.icns"
    write_iconset_and_icns(master, icns_path)
    print(f"  → {icns_path.relative_to(here)} ({icns_path.stat().st_size // 1024} KB)")

    ico_path = build_dir / "icon.ico"
    write_ico(master, ico_path)
    print(f"  → {ico_path.relative_to(here)} ({ico_path.stat().st_size // 1024} KB)")

    print("Pronto.")


if __name__ == "__main__":
    main()
