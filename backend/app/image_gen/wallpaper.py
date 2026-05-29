"""Deriva wallpapers (proporcoes diferentes) da arte de capa via Pillow — GRATIS.

A capa nasce em 2:3 retrato. Pra wallpaper de celular (9:16) cabe bem com um
crop leve (scale-to-cover). Pra desktop (16:9 paisagem) um crop destruiria a
arte retrato, entao usamos "blur-fill": a arte inteira centrada sobre um fundo
desfocado dela mesma. Variantes NATIVAS (Gemini, na proporcao certa) ficam em
``cover_generator`` — isto aqui e o caminho gratis/instantaneo.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageEnhance, ImageFilter

# Presets (largura, altura) por formato. Resolucoes comuns de wallpaper.
PRESETS: dict[str, tuple[int, int]] = {
    "phone": (1080, 1920),  # 9:16 vertical
    "pc": (1920, 1080),     # 16:9 horizontal
}

# Aspect ratio que o Gemini usa pra cada formato (geracao nativa).
ASPECT_BY_FORMAT: dict[str, str] = {
    "phone": "9:16",
    "pc": "16:9",
}


def _scale_cover(img: Image.Image, tw: int, th: int) -> Image.Image:
    """Preenche tw x th cobrindo tudo (pode cortar bordas). Centro preservado."""
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    nw, nh = round(sw * scale), round(sh * scale)
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def _blur_fill(img: Image.Image, tw: int, th: int) -> Image.Image:
    """Arte inteira (contain) centrada sobre um fundo desfocado dela mesma.
    Ideal pra colocar arte retrato numa tela paisagem sem cortar nada."""
    bg = _scale_cover(img, tw, th).filter(ImageFilter.GaussianBlur(42))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)  # escurece pra destacar o foco
    sw, sh = img.size
    scale = min(tw / sw, th / sh)
    nw, nh = round(sw * scale), round(sh * scale)
    fg = img.resize((nw, nh), Image.LANCZOS)
    canvas = bg.copy()
    canvas.paste(fg, ((tw - nw) // 2, (th - nh) // 2))
    return canvas


def derive_wallpaper(raw_bytes: bytes, fmt: str) -> tuple[bytes, str]:
    """Gera um wallpaper local a partir da arte crua. ``fmt`` in PRESETS.
    Retorna ``(jpeg_bytes, "image/jpeg")``."""
    if fmt not in PRESETS:
        raise ValueError(f"formato de wallpaper desconhecido: {fmt}")
    tw, th = PRESETS[fmt]
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    # Celular (vertical) ~ proporcao da capa → crop leve. Desktop (horizontal) →
    # blur-fill pra nao destruir a composicao retrato.
    out_img = _scale_cover(img, tw, th) if th >= tw else _blur_fill(img, tw, th)
    out = BytesIO()
    out_img.save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue(), "image/jpeg"
