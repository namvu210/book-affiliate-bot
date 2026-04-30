"""Image effects and subtitle rendering."""

import math

from PIL import Image, ImageDraw, ImageFilter

from config import strip_emoji
from video.text import get_font, wrap_text
from video.media import crop_animated, center_crop


def apply_effect(src, effect, gp, lp, all_imgs, img_idx, size, zoom_ratio=0.15):
    """Apply image effect. gp=global progress 0-1, lp=local progress 0-1."""
    from PIL import ImageEnhance, ImageOps
    W, H = size

    if effect == "ken_burns":
        return crop_animated(src, gp, size, zoom_ratio)

    elif effect == "slide_lr":
        max_x = src.width - W
        x = int(max_x * gp)
        y = (src.height - H) // 2
        return src.crop((x, y, x + W, y + H))

    elif effect == "slide_ud":
        x = (src.width - W) // 2
        max_y = src.height - H
        y = int(max_y * gp)
        return src.crop((x, y, x + W, y + H))

    elif effect == "bounce_zoom":
        z = 1.0 + zoom_ratio * math.sin(gp * math.pi * 4)
        cw, ch = int(W / z), int(H / z)
        cx = (src.width - cw) // 2
        cy = (src.height - ch) // 2
        return src.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.LANCZOS)

    elif effect == "grayscale":
        bg = crop_animated(src, gp, size)
        return ImageOps.grayscale(bg).convert("RGB")

    elif effect == "sepia":
        bg = crop_animated(src, gp, size)
        gray = ImageOps.grayscale(bg)
        r = gray.point(lambda p: min(255, int(p * 1.2)))
        g = gray.point(lambda p: min(255, int(p * 1.0)))
        b = gray.point(lambda p: min(255, int(p * 0.8)))
        return Image.merge("RGB", (r, g, b))

    elif effect == "saturation":
        return ImageEnhance.Color(crop_animated(src, gp, size)).enhance(1.8)

    elif effect == "contrast":
        return ImageEnhance.Contrast(crop_animated(src, gp, size)).enhance(1.5)

    elif effect == "color_tint":
        bg = crop_animated(src, gp, size)
        tint = Image.new("RGB", bg.size, (255, 200, 150))
        return Image.blend(bg, tint, 0.15)

    elif effect == "color_pop":
        bg = crop_animated(src, gp, size)
        import colorsys
        gray = ImageOps.grayscale(bg)
        pixels = bg.load()
        gray_px = gray.load()
        result = bg.copy()
        rp = result.load()
        for y in range(bg.height):
            for x in range(bg.width):
                r, g, b = pixels[x, y]
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                if not (0.95 < h or h < 0.1) or s < 0.4:
                    rp[x, y] = (gray_px[x, y], gray_px[x, y], gray_px[x, y])
        return result

    elif effect == "vignette":
        bg = crop_animated(src, gp, size)
        vig = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(vig)
        for i in range(40):
            alpha = int(255 * (i / 40))
            margin = i * max(W, H) // 80
            d.ellipse([(margin, margin), (W - margin, H - margin)], fill=alpha)
        return Image.composite(bg.convert("RGB"), Image.new("RGB", bg.size, (0, 0, 0)), vig)

    elif effect == "soft_glow":
        bg = crop_animated(src, gp, size)
        glow = bg.filter(ImageFilter.GaussianBlur(radius=15))
        return Image.blend(bg, glow, 0.3)

    elif effect == "mirror":
        return ImageOps.mirror(crop_animated(src, gp, size))

    elif effect == "pixelate_reveal":
        bg = crop_animated(src, gp, size)
        pix = max(1, int(32 * (1 - gp)))
        small = bg.resize((W // pix, H // pix), Image.NEAREST)
        return small.resize((W, H), Image.NEAREST)

    elif effect == "split_screen":
        half_w = W // 2
        idx2 = (img_idx + 1) % len(all_imgs)
        left = center_crop(all_imgs[img_idx], half_w, H)
        right = center_crop(all_imgs[idx2], half_w, H)
        combined = Image.new("RGB", (W, H))
        combined.paste(left, (0, 0))
        combined.paste(right, (half_w, 0))
        return combined

    elif effect == "blur_bg":
        return center_crop(src, W, H).filter(ImageFilter.GaussianBlur(radius=8))

    elif effect == "brightness":
        return ImageEnhance.Brightness(crop_animated(src, gp, size)).enhance(1.3)

    elif effect == "darken":
        return ImageEnhance.Brightness(crop_animated(src, gp, size)).enhance(0.7)

    elif effect == "crossfade":
        idx2 = (img_idx + 1) % len(all_imgs)
        bg1 = crop_animated(src, gp, size, zoom_ratio)
        bg2 = crop_animated(all_imgs[idx2], gp, size, zoom_ratio)
        return Image.blend(bg1, bg2, min(1.0, max(0.0, lp)))

    elif effect == "zoom_center":
        zoom = 1.0 + zoom_ratio * 2 * gp
        cw, ch = int(W / zoom), int(H / zoom)
        cx = (src.width - cw) // 2
        cy = (src.height - ch) // 2
        return src.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.LANCZOS)

    elif effect == "parallax":
        fg_zoom = 1.0 + zoom_ratio * gp
        bg_zoom = 1.0 + zoom_ratio * 0.3 * gp
        bg_cw, bg_ch = int(W / bg_zoom), int(H / bg_zoom)
        bg_cx = (src.width - bg_cw) // 2
        bg_cy = (src.height - bg_ch) // 2
        bg_layer = src.crop((bg_cx, bg_cy, bg_cx + bg_cw, bg_cy + bg_ch)).resize((W, H), Image.LANCZOS)
        bg_layer = bg_layer.filter(ImageFilter.GaussianBlur(radius=3))
        fg_cw, fg_ch = int(W / fg_zoom), int(H / fg_zoom)
        fg_cx = int((src.width - fg_cw) * (0.3 + 0.4 * gp))
        fg_cy = (src.height - fg_ch) // 2
        fg_cx = max(0, min(fg_cx, src.width - fg_cw))
        fg_layer = src.crop((fg_cx, fg_cy, fg_cx + fg_cw, fg_cy + fg_ch)).resize((W, H), Image.LANCZOS)
        return Image.blend(bg_layer, fg_layer, 0.85)

    elif effect == "shake":
        import random
        base = crop_animated(src, gp, size, zoom_ratio * 0.5)
        dx = random.randint(-8, 8)
        dy = random.randint(-8, 8)
        shifted = Image.new("RGB", (W, H), (0, 0, 0))
        shifted.paste(base, (dx, dy))
        return shifted

    elif effect == "flash":
        bg = crop_animated(src, gp, size, zoom_ratio)
        if math.sin(gp * math.pi * 8) > 0.95:
            return Image.blend(bg, Image.new("RGB", (W, H), (255, 255, 255)), 0.6)
        return bg

    elif effect == "before_after":
        idx2 = (img_idx + 1) % len(all_imgs)
        img1 = center_crop(src, W, H)
        img2 = center_crop(all_imgs[idx2], W, H)
        split_x = int(W * gp)
        result = img1.copy()
        result.paste(img2.crop((split_x, 0, W, H)), (split_x, 0))
        ImageDraw.Draw(result).line([(split_x, 0), (split_x, H)], fill=(255, 255, 255), width=3)
        return result

    elif effect == "rotate_tilt":
        bg = crop_animated(src, gp, size, zoom_ratio)
        angle = 3 * math.sin(gp * math.pi * 2)
        rotated = bg.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0))
        return center_crop(rotated, W, H)

    elif effect == "glitch":
        bg = crop_animated(src, gp, size, zoom_ratio)
        import random
        if random.random() > 0.7:
            y1 = random.randint(0, H - 40)
            strip = bg.crop((0, y1, W, y1 + random.randint(10, 40)))
            bg.paste(strip, (random.randint(-30, 30), y1))
            r, g, b = bg.split()
            r = r.transform(r.size, Image.AFFINE, (1, 0, random.randint(-5, 5), 0, 1, 0))
            bg = Image.merge("RGB", (r, g, b))
        return bg

    else:  # none
        return center_crop(src, W, H)


def draw_word_highlight_frame(
    bg: Image.Image,
    sentence: str,
    word_progress: float,
    size: tuple[int, int],
    subtitle_style: str = "tiktok",
    highlight_color: str = "#FFD700",
) -> Image.Image:
    """Draw sentence at bottom with configurable style."""
    W, H = size
    img = bg.copy()
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    font = get_font(52, bold=True)
    pad = 50
    clean = strip_emoji(sentence)
    words = clean.split()
    if not words:
        return img
    lines = wrap_text(clean, font, W - pad * 2, odraw)[:3]
    line_height = 68
    block_h = len(lines) * line_height + 30
    text_y = H - block_h - 80
    hc = tuple(int(highlight_color.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
    if subtitle_style == "news":
        odraw.rectangle([(0, text_y - 15), (W, text_y + block_h)], fill=(0, 0, 0, 200))
    elif subtitle_style != "minimal":
        odraw.rounded_rectangle([(pad - 20, text_y - 15), (W - pad + 20, text_y + block_h)], radius=24, fill=(0, 0, 0, 150))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    total_words = len(words)
    highlight_idx = int(word_progress * total_words)
    word_counter = 0
    y = text_y
    for line in lines:
        line_words = line.split()
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        x = (W - line_w) // 2
        for w in line_words:
            w_bbox = draw.textbbox((0, 0), w, font=font)
            w_w = w_bbox[2] - w_bbox[0]
            if word_counter <= highlight_idx:
                if subtitle_style == "tiktok":
                    for dx in [-2, -1, 0, 1, 2]:
                        for dy in [-2, -1, 0, 1, 2]:
                            if dx == 0 and dy == 0: continue
                            draw.text((x + dx, y + dy), w, fill=hc, font=font)
                    draw.text((x, y), w, fill=(255, 255, 255), font=font)
                elif subtitle_style == "karaoke":
                    draw.text((x, y), w, fill=hc, font=font)
                else:
                    draw.text((x, y), w, fill=(255, 255, 255), font=font)
            else:
                if subtitle_style == "tiktok":
                    for dx in [-2, -1, 0, 1, 2]:
                        for dy in [-2, -1, 0, 1, 2]:
                            if dx == 0 and dy == 0: continue
                            draw.text((x + dx, y + dy), w, fill=(0, 0, 0), font=font)
                    draw.text((x, y), w, fill=(160, 160, 170), font=font)
                elif subtitle_style == "karaoke":
                    draw.text((x, y), w, fill=(180, 180, 180), font=font)
                elif subtitle_style == "news":
                    draw.text((x, y), w, fill=(200, 200, 200), font=font)
                else:
                    draw.text((x, y), w, fill=(200, 200, 200, 180), font=font)
            sp_bbox = draw.textbbox((0, 0), " ", font=font)
            x += w_w + (sp_bbox[2] - sp_bbox[0])
            word_counter += 1
        y += line_height
    return img.convert("RGB")
