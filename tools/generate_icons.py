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
    """Dessin vectoriel d'une fusée stylisée (cohérent avec l'onboarding).

    Reproduit le visuel demandé par Yvan 02/05/2026 :
    - Pointe rouge (triangle haut)
    - Corps blanc/gris clair (rectangle)
    - Hublot bleu (cercle)
    - Ailerons rouges (triangles latéraux)
    - Flamme orange/jaune (triangle bas)

    Sur fond gradient bleu BoosterMail arrondi.
    """
    RED = (231, 76, 60, 255)        # #e74c3c (pointe + ailerons)
    WHITE_BODY = (236, 240, 241, 255)  # #ecf0f1 (corps)
    BLUE_HUBLOT = (52, 152, 219, 255)  # #3498db (hublot)
    ORANGE = (243, 156, 18, 255)       # #f39c12 (flamme externe)
    YELLOW = (241, 196, 15, 255)       # #f1c40f (flamme interne)

    bg = make_rounded_gradient(size)
    draw = ImageDraw.Draw(bg)

    # Coordonnées normalisées sur la base d'un canvas size×size
    # La fusée occupe ~70% du canvas, centrée et inclinée légèrement
    cx = size / 2
    cy = size * 0.50  # centre du corps légèrement au-dessus du milieu

    # Corps : rectangle haut
    body_w = size * 0.28
    body_h = size * 0.42
    body_top = cy - body_h / 2
    body_bot = cy + body_h / 2
    # Corps blanc
    draw.rectangle(
        (cx - body_w / 2, body_top, cx + body_w / 2, body_bot),
        fill=WHITE_BODY,
    )
    # Pointe rouge (triangle au-dessus du corps)
    nose_h = size * 0.20
    draw.polygon([
        (cx - body_w / 2, body_top),
        (cx, body_top - nose_h),
        (cx + body_w / 2, body_top),
    ], fill=RED)
    # Hublot bleu (cercle au centre du corps)
    hublot_r = size * 0.06
    draw.ellipse(
        (cx - hublot_r, cy - hublot_r * 0.4 - hublot_r,
         cx + hublot_r, cy - hublot_r * 0.4 + hublot_r),
        fill=BLUE_HUBLOT,
    )
    # Ailerons rouges (2 triangles latéraux pointant vers le bas)
    fin_w = size * 0.13
    fin_h = size * 0.18
    # Aileron gauche
    draw.polygon([
        (cx - body_w / 2, body_bot - fin_h * 0.4),
        (cx - body_w / 2 - fin_w, body_bot + fin_h * 0.5),
        (cx - body_w / 2, body_bot),
    ], fill=RED)
    # Aileron droit (miroir)
    draw.polygon([
        (cx + body_w / 2, body_bot - fin_h * 0.4),
        (cx + body_w / 2 + fin_w, body_bot + fin_h * 0.5),
        (cx + body_w / 2, body_bot),
    ], fill=RED)
    # Flamme orange (triangle pointe vers le bas)
    flame_h = size * 0.16
    draw.polygon([
        (cx - body_w / 2 + size * 0.02, body_bot),
        (cx + body_w / 2 - size * 0.02, body_bot),
        (cx, body_bot + flame_h),
    ], fill=ORANGE)
    # Flamme interne jaune (plus petite)
    if size >= 32:  # détail à omettre en 16px
        draw.polygon([
            (cx - body_w / 4, body_bot + size * 0.02),
            (cx + body_w / 4, body_bot + size * 0.02),
            (cx, body_bot + flame_h * 0.7),
        ], fill=YELLOW)

    return bg


def generate(size, output_path, source_for_downscale=None):
    """Génère icon de taille `size`.

    Si source_for_downscale (PIL Image plus grande) est fourni, on
    downscale avec LANCZOS — meilleur rendu en petite taille que de
    re-rasteriser le dessin vectoriel directement.

    Décision Yvan 02/05/2026 : on utilise UNIQUEMENT le dessin vectoriel
    de la fusée stylisée (cohérent avec les SVG de l'onboarding). Plus
    d'emoji 🚀 (qui rendait différemment et perdait les détails en petite
    taille).
    """
    print(f"Génération {size}×{size} → {output_path}")

    if source_for_downscale is not None:
        print(f"  via downscale LANCZOS depuis {source_for_downscale.size[0]}px")
        img = source_for_downscale.resize((size, size), Image.LANCZOS)
        img.save(output_path, 'PNG', optimize=True)
        final_size = os.path.getsize(output_path)
        print(f"  ✓ {final_size} bytes")
        return img

    print(f"  via dessin vectoriel fusée stylisée")
    img = render_rocket_vector(size)
    img.save(output_path, 'PNG', optimize=True)
    final_size = os.path.getsize(output_path)
    print(f"  ✓ {final_size} bytes")
    return img


def main():
    if not os.path.isdir(ASSETS_DIR):
        os.makedirs(ASSETS_DIR, exist_ok=True)
    # On rend d'abord la version haute résolution (80px) en vectoriel,
    # puis on downscale les plus petites tailles. Donne un rendu net en
    # 16×16 et 32×32 grâce au LANCZOS (anti-aliasing).
    big = generate(80, os.path.join(ASSETS_DIR, 'icon-80.png'))
    generate(32, os.path.join(ASSETS_DIR, 'icon-32.png'), source_for_downscale=big)
    generate(16, os.path.join(ASSETS_DIR, 'icon-16.png'), source_for_downscale=big)
    print("\nFait. Les icônes sont prêtes pour le déploiement OVH.")


if __name__ == '__main__':
    main()
