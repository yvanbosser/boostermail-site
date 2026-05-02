"""Génère les icônes BoosterMail (fusée sur fond bleu) aux 3 tailles 16/32/80.

Décision Yvan 02/05/2026 : remplacer le carré bleu vide par le logo fusée
de BoosterMail dans la barre d'actions Outlook (manifest pointe sur ces 3 PNG).

Approche :
- Fond bleu BoosterMail (#0F6CBD), coins arrondis
- Emoji 🚀 rendu en couleur via Segoe UI Emoji (Windows) qui supporte
  les emojis COLR
- Fallback dessin vectoriel simple si la font emoji n'est pas dispo

Usage : python tools/generate_icons.py
Output : V2/assets/icon-16.png, icon-32.png, icon-80.png
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Couleurs BoosterMail
BG_TOP = (15, 108, 189)     # #0F6CBD
BG_BOTTOM = (25, 118, 210)  # #1976D2 (un peu plus clair pour gradient)
WHITE = (255, 255, 255, 255)

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'V2', 'assets'
)
EMOJI_FONT_PATHS = [
    r'C:\Windows\Fonts\seguiemj.ttf',  # Segoe UI Emoji (Windows)
    '/System/Library/Fonts/Apple Color Emoji.ttc',  # macOS
    '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',  # Linux
]


def make_rounded_gradient(size):
    """Crée un fond carré arrondi avec gradient bleu BoosterMail."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    # Gradient vertical
    for y in range(size):
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * y / size)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * y / size)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * y / size)
        for x in range(size):
            img.putpixel((x, y), (r, g, b, 255))
    # Mask coins arrondis
    mask = Image.new('L', (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    radius = max(2, size // 6)
    mdraw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    img.putalpha(mask)
    return img


def find_emoji_font():
    for path in EMOJI_FONT_PATHS:
        if os.path.exists(path):
            return path
    return None


def render_rocket_emoji(size, font_path):
    """Rend 🚀 sur fond gradient. Retourne RGBA Image ou None si échec."""
    try:
        bg = make_rounded_gradient(size)
        # On rend l'emoji plus petit que la taille du canvas pour avoir
        # un peu de padding (sinon ça touche les bords).
        emoji_size = int(size * 0.65)
        font = ImageFont.truetype(font_path, emoji_size)

        # Render emoji sur layer transparent puis blit sur le fond
        emoji_layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        edraw = ImageDraw.Draw(emoji_layer)
        text = '🚀'
        # bbox avec embedded_color pour les emojis COLR
        try:
            bbox = edraw.textbbox((0, 0), text, font=font, embedded_color=True)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (size - w) // 2 - bbox[0]
            y = (size - h) // 2 - bbox[1]
            edraw.text((x, y), text, font=font, embedded_color=True)
        except Exception:
            # Fallback non-color
            bbox = edraw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (size - w) // 2 - bbox[0]
            y = (size - h) // 2 - bbox[1]
            edraw.text((x, y), text, font=font, fill=WHITE)

        # Vérifier que le rendu n'est pas vide (pas tout transparent)
        bbox_check = emoji_layer.getbbox()
        if not bbox_check:
            return None

        # Combine
        bg.paste(emoji_layer, (0, 0), emoji_layer)
        return bg
    except Exception as e:
        print(f"  emoji render failed at size={size} : {e}")
        return None


def render_rocket_vector(size):
    """Fallback : dessin vectoriel simple d'une fusée blanche.

    Pour les très petites tailles (16 px) où l'emoji rendu est illisible,
    on dessine une silhouette stylisée plus claire visuellement.
    """
    bg = make_rounded_gradient(size)
    draw = ImageDraw.Draw(bg)
    cx = size / 2
    cy = size / 2

    # Corps (triangle isocèle pointe vers le haut)
    body_h = size * 0.55
    body_w = size * 0.28
    top = (cx, cy - body_h * 0.55)
    bot_l = (cx - body_w / 2, cy + body_h * 0.30)
    bot_r = (cx + body_w / 2, cy + body_h * 0.30)
    draw.polygon([top, bot_l, bot_r], fill=WHITE)

    # Hublot circulaire (sur le corps)
    hublot_r = size * 0.06
    draw.ellipse(
        (cx - hublot_r, cy - hublot_r * 1.2, cx + hublot_r, cy + hublot_r * 0.8),
        fill=(15, 108, 189, 255),
    )

    # Ailerons (deux petits triangles latéraux)
    fin_w = size * 0.10
    fin_h = size * 0.18
    # Aileron gauche
    draw.polygon([
        (bot_l[0], bot_l[1] - fin_h * 0.5),
        (bot_l[0] - fin_w, bot_l[1] + fin_h * 0.5),
        (bot_l[0] + fin_w * 0.2, bot_l[1] + fin_h * 0.2),
    ], fill=WHITE)
    # Aileron droit (miroir)
    draw.polygon([
        (bot_r[0], bot_r[1] - fin_h * 0.5),
        (bot_r[0] + fin_w, bot_r[1] + fin_h * 0.5),
        (bot_r[0] - fin_w * 0.2, bot_r[1] + fin_h * 0.2),
    ], fill=WHITE)

    # Flamme (petite forme orangée sous la fusée)
    flame_h = size * 0.20
    flame_top_l = (cx - body_w / 2 + size * 0.02, cy + body_h * 0.30)
    flame_top_r = (cx + body_w / 2 - size * 0.02, cy + body_h * 0.30)
    flame_bot = (cx, cy + body_h * 0.30 + flame_h)
    draw.polygon([flame_top_l, flame_top_r, flame_bot],
                 fill=(255, 165, 50, 255))

    return bg


def generate(size, output_path, source_for_downscale=None):
    """Génère icon de taille `size`.

    Si source_for_downscale (PIL Image plus grande) est fourni, on
    downscale avec LANCZOS — meilleur rendu en petite taille que de
    re-rasteriser l'emoji ou que le dessin vectoriel maison.
    """
    print(f"Génération {size}×{size} → {output_path}")

    if source_for_downscale is not None:
        print(f"  via downscale LANCZOS depuis {source_for_downscale.size[0]}px")
        img = source_for_downscale.resize((size, size), Image.LANCZOS)
        img.save(output_path, 'PNG', optimize=True)
        final_size = os.path.getsize(output_path)
        print(f"  ✓ {final_size} bytes")
        return img

    font_path = find_emoji_font()
    img = None
    if font_path:
        print(f"  via emoji font : {font_path}")
        img = render_rocket_emoji(size, font_path)

    if img is None:
        print(f"  fallback dessin vectoriel")
        img = render_rocket_vector(size)

    img.save(output_path, 'PNG', optimize=True)
    final_size = os.path.getsize(output_path)
    print(f"  ✓ {final_size} bytes")
    return img


def main():
    if not os.path.isdir(ASSETS_DIR):
        os.makedirs(ASSETS_DIR, exist_ok=True)
    # On rend d'abord la version haute résolution, puis on downscale les
    # plus petites tailles. Donne un rendu net en 16×16 et 32×32 sans
    # avoir à re-rasteriser l'emoji (qui s'écrase mal en petites tailles).
    big = generate(80, os.path.join(ASSETS_DIR, 'icon-80.png'))
    generate(32, os.path.join(ASSETS_DIR, 'icon-32.png'), source_for_downscale=big)
    generate(16, os.path.join(ASSETS_DIR, 'icon-16.png'), source_for_downscale=big)
    print("\nFait. Les icônes sont prêtes pour le déploiement OVH.")


if __name__ == '__main__':
    main()
