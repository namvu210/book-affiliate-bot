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
        import numpy as np
        arr = np.array(bg, dtype=np.float32)
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        delta = max_c - min_c
        # Hue calculation (simplified for red detection)
        hue = np.zeros_like(max_c)
        mask = delta > 0
        rm = (max_c == r) & mask
        hue[rm] = ((g[rm] - b[rm]) / delta[rm]) % 6
        hue = hue / 6.0  # normalize to 0-1
        safe_max = np.where(max_c > 0, max_c, 1)
        sat = np.where(max_c > 0, delta / safe_max, 0) / 255.0
        # Keep red hues (h<0.1 or h>0.95) with saturation > 0.4
        is_red = ((hue < 0.1) | (hue > 0.95)) & (sat > 0.4)
        gray = np.array(ImageOps.grayscale(bg), dtype=np.uint8)
        result = np.stack([gray, gray, gray], axis=2)
        result[is_red] = np.array(bg, dtype=np.uint8)[is_red]
        return Image.fromarray(result)

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

    # --- Light / Particle overlays ---

    elif effect == "halo":
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        cx, cy = W // 2, H // 3
        radius = int(W * 0.35 + W * 0.05 * math.sin(gp * math.pi * 2))
        for i in range(30):
            alpha = int(60 * (1 - i / 30))
            r = radius + i * 4
            d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=(255, 240, 200, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "scanning_light":
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        y_pos = int(H * ((gp * 2) % 1.0))
        for i in range(60):
            alpha = int(80 * (1 - abs(i - 30) / 30))
            d.rectangle([(0, y_pos - 30 + i), (W, y_pos - 30 + i + 1)], fill=(255, 255, 255, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "light_leak":
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        phase = gp * math.pi * 2
        cx = int(W * (0.7 + 0.3 * math.sin(phase)))
        cy = int(H * 0.3)
        for i in range(50):
            alpha = int(40 * (1 - i / 50))
            r = int(W * 0.2) + i * 8
            d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(255, 180, 80, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "sparkles":
        import random
        random.seed(int(gp * 1000))
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        for _ in range(25):
            x, y = random.randint(0, W), random.randint(0, H)
            sz = random.randint(2, 6)
            alpha = random.randint(150, 255)
            d.ellipse([(x, y), (x + sz, y + sz)], fill=(255, 255, 255, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "gold_sparkles":
        import random
        random.seed(int(gp * 1000))
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        colors = [(255, 215, 0), (255, 200, 50), (255, 230, 100)]
        for _ in range(30):
            x, y = random.randint(0, W), random.randint(0, H)
            sz = random.randint(2, 8)
            c = colors[random.randint(0, 2)]
            alpha = random.randint(150, 255)
            d.ellipse([(x, y), (x + sz, y + sz)], fill=(*c, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "snowfall":
        import random
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        random.seed(42)
        for i in range(40):
            x_base = random.randint(0, W)
            speed = random.uniform(0.5, 1.5)
            drift = random.uniform(-0.3, 0.3)
            x = int((x_base + drift * gp * W) % W)
            y = int((gp * speed * H + i * H / 40) % H)
            sz = random.randint(3, 7)
            d.ellipse([(x, y), (x + sz, y + sz)], fill=(255, 255, 255, 200))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "glitter_bomb":
        import random
        random.seed(int(gp * 500))
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        colors = [(255, 215, 0), (255, 100, 200), (100, 200, 255), (200, 255, 100), (255, 255, 255)]
        for _ in range(50):
            x, y = random.randint(0, W), random.randint(0, H)
            sz = random.randint(2, 6)
            c = colors[random.randint(0, len(colors) - 1)]
            alpha = random.randint(120, 255)
            d.ellipse([(x, y), (x + sz, y + sz)], fill=(*c, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "starlights":
        import random
        random.seed(int(gp * 800))
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        for _ in range(15):
            x, y = random.randint(20, W - 20), random.randint(20, H - 20)
            sz = random.randint(8, 20)
            alpha = random.randint(100, 220)
            # 4-point star
            d.line([(x - sz, y), (x + sz, y)], fill=(255, 255, 255, alpha), width=2)
            d.line([(x, y - sz), (x, y + sz)], fill=(255, 255, 255, alpha), width=2)
            d.line([(x - sz//2, y - sz//2), (x + sz//2, y + sz//2)], fill=(255, 255, 255, alpha // 2), width=1)
            d.line([(x + sz//2, y - sz//2), (x - sz//2, y + sz//2)], fill=(255, 255, 255, alpha // 2), width=1)
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "neon_glow":
        bg = crop_animated(src, gp, size, zoom_ratio)
        import numpy as np
        arr = np.array(bg, dtype=np.float32)
        bright = np.max(arr, axis=2)
        mask = (bright > 180).astype(np.float32)
        mask_img = Image.fromarray((mask * 255).astype(np.uint8), "L")
        glow = mask_img.filter(ImageFilter.GaussianBlur(radius=20))
        glow_colored = Image.merge("RGB", (glow, Image.new("L", (W, H), 0), glow))
        return Image.blend(bg, glow_colored, 0.3)

    elif effect == "shockwave":
        bg = crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        cx, cy = W // 2, H // 2
        radius = int(max(W, H) * gp)
        alpha = int(150 * (1 - gp))
        for i in range(5):
            r = radius + i * 3
            d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=(255, 255, 255, max(0, alpha - i * 20)))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    # --- Color / Noise effects ---

    elif effect == "chromatic":
        bg = crop_animated(src, gp, size, zoom_ratio)
        offset = int(4 + 3 * math.sin(gp * math.pi * 2))
        r, g, b = bg.split()
        r = r.transform(r.size, Image.AFFINE, (1, 0, offset, 0, 1, 0))
        b = b.transform(b.size, Image.AFFINE, (1, 0, -offset, 0, 1, 0))
        return Image.merge("RGB", (r, g, b))

    elif effect == "club_mood":
        bg = crop_animated(src, gp, size, zoom_ratio)
        phase = gp * math.pi * 4
        r_tint = int(128 + 127 * math.sin(phase))
        g_tint = int(128 + 127 * math.sin(phase + 2.1))
        b_tint = int(128 + 127 * math.sin(phase + 4.2))
        tint = Image.new("RGB", (W, H), (r_tint, g_tint, b_tint))
        return Image.blend(bg, tint, 0.2)

    elif effect == "cyberpunk":
        bg = crop_animated(src, gp, size, zoom_ratio)
        from PIL import ImageEnhance
        bg = ImageEnhance.Contrast(bg).enhance(1.4)
        tint = Image.new("RGB", (W, H), (20, 0, 60))
        bg = Image.blend(bg, tint, 0.15)
        # Scanlines
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(0, 255, 200, 20))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "negative":
        import numpy as np
        bg = crop_animated(src, gp, size, zoom_ratio)
        arr = np.array(bg, dtype=np.uint8)
        return Image.fromarray(255 - arr)

    elif effect == "black_noise":
        import random, numpy as np
        random.seed(int(gp * 2000))
        bg = crop_animated(src, gp, size, zoom_ratio)
        noise = np.random.randint(0, 40, (H, W, 3), dtype=np.uint8)
        bg_arr = np.array(bg, dtype=np.int16)
        result = np.clip(bg_arr + noise - 20, 0, 255).astype(np.uint8)
        return Image.fromarray(result)

    elif effect == "film_grain":
        import numpy as np
        bg = crop_animated(src, gp, size, zoom_ratio)
        noise = np.random.randint(0, 30, (H, W), dtype=np.uint8)
        noise_rgb = np.stack([noise, noise, noise], axis=2)
        bg_arr = np.array(bg, dtype=np.int16)
        result = np.clip(bg_arr + noise_rgb - 15, 0, 255).astype(np.uint8)
        return Image.fromarray(result)

    elif effect == "x_signal":
        import random
        bg = crop_animated(src, gp, size, zoom_ratio)
        random.seed(int(gp * 300))
        if random.random() > 0.6:
            # Horizontal tear
            y1 = random.randint(0, H - 30)
            strip_h = random.randint(5, 30)
            strip = bg.crop((0, y1, W, y1 + strip_h))
            bg.paste(strip, (random.randint(-40, 40), y1))
        # VHS-style color offset
        r, g, b = bg.split()
        offset = int(3 * math.sin(gp * math.pi * 6))
        g = g.transform(g.size, Image.AFFINE, (1, 0, 0, 0, 1, offset))
        return Image.merge("RGB", (r, g, b))

    elif effect == "flash_2":
        bg = crop_animated(src, gp, size, zoom_ratio)
        # Double flash pattern
        pulse = abs(math.sin(gp * math.pi * 12))
        if pulse > 0.92:
            return Image.blend(bg, Image.new("RGB", (W, H), (255, 255, 255)), 0.7)
        return bg

    elif effect == "black_flash":
        bg = crop_animated(src, gp, size, zoom_ratio)
        pulse = abs(math.sin(gp * math.pi * 10))
        if pulse > 0.93:
            return Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.8)
        return bg

    elif effect == "camera_focus":
        bg = crop_animated(src, gp, size, zoom_ratio)
        # Center sharp, edges blurred (rack focus effect)
        blurred = bg.filter(ImageFilter.GaussianBlur(radius=8))
        mask = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(mask)
        cx, cy = W // 2, H // 2
        r = int(min(W, H) * 0.3)
        d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=40))
        return Image.composite(bg, blurred, mask)

    elif effect == "star_power":
        import random
        random.seed(int(gp * 600))
        bg = crop_animated(src, gp, size, zoom_ratio)
        from PIL import ImageEnhance
        bg = ImageEnhance.Brightness(bg).enhance(1.1)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        for _ in range(20):
            x, y = random.randint(0, W), random.randint(0, H)
            sz = random.randint(10, 25)
            alpha = random.randint(80, 180)
            # Draw a simple cross star
            d.line([(x - sz, y), (x + sz, y)], fill=(255, 255, 200, alpha), width=2)
            d.line([(x, y - sz), (x, y + sz)], fill=(255, 255, 200, alpha), width=2)
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "rainbow_heart":
        import random
        random.seed(int(gp * 400))
        bg = center_crop(src, W, H) if src.size == (W, H) else crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        colors = [(255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 255, 0), (0, 127, 255), (139, 0, 255)]
        for _ in range(16):
            x, y = random.randint(40, W - 40), random.randint(40, H - 40)
            sz = random.randint(30, 55)
            c = colors[random.randint(0, len(colors) - 1)]
            alpha = random.randint(140, 220)
            r = sz // 3
            d.ellipse([(x - r, y - r), (x + r, y + r)], fill=(*c, alpha))
            d.ellipse([(x + r - r//2, y - r), (x + r + r + r//2, y + r)], fill=(*c, alpha))
            d.polygon([(x - r, y + r//2), (x + r * 2 + r//2, y + r//2), (x + r//2 + r//4, y + sz)], fill=(*c, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    elif effect == "pink_hearts":
        import random
        random.seed(int(gp * 400))
        bg = center_crop(src, W, H) if src.size == (W, H) else crop_animated(src, gp, size, zoom_ratio)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        for _ in range(20):
            x, y = random.randint(40, W - 40), random.randint(40, H - 40)
            sz = random.randint(30, 60)
            alpha = random.randint(140, 240)
            c = (255, random.randint(80, 160), random.randint(150, 200))
            # Heart shape: two overlapping circles + triangle point
            r = sz // 3
            d.ellipse([(x - r, y - r), (x + r, y + r)], fill=(*c, alpha))
            d.ellipse([(x + r - r//2, y - r), (x + r + r + r//2, y + r)], fill=(*c, alpha))
            d.polygon([(x - r, y + r//2), (x + r * 2 + r//2, y + r//2), (x + r//2 + r//4, y + sz)], fill=(*c, alpha))
        return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    # --- Body-aware effects (mediapipe) ---

    elif effect in ("aura", "contour", "wings", "thermal_aura", "phantom", "ghost"):
        from video.body import apply_body_effect
        return apply_body_effect(src, effect, gp, size)

    else:  # none
        return center_crop(src, W, H)


# === Transition effects (applied between image switches) ===

TRANSITION_FRAMES = 4  # frames for transition (~0.17s at 24fps)


def apply_transition(prev_img, next_img, progress, transition, size):
    """Apply transition between two images. progress=0→1 over TRANSITION_FRAMES."""
    W, H = size
    img1 = center_crop(prev_img, W, H)
    img2 = center_crop(next_img, W, H)

    if transition == "whip_pan":
        # Horizontal motion blur swipe
        blend = progress
        offset = int((1 - progress) * W * 0.3)
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        # Outgoing image slides left with blur
        if progress < 0.5:
            shifted = img1.transform((W, H), Image.AFFINE, (1, 0, int(progress * W * 0.6), 0, 1, 0))
            blurred = shifted.filter(ImageFilter.GaussianBlur(radius=int(20 * progress * 2)))
            return blurred
        else:
            # Incoming image slides in from right with blur
            p2 = (progress - 0.5) * 2
            shift = int((1 - p2) * W * 0.6)
            shifted = img2.transform((W, H), Image.AFFINE, (1, 0, -shift, 0, 1, 0))
            blurred = shifted.filter(ImageFilter.GaussianBlur(radius=int(20 * (1 - p2))))
            return blurred

    elif transition == "glitch_trans":
        # RGB split + horizontal slice displacement
        if progress < 0.5:
            bg = img1
        else:
            bg = img2
        r, g, b = bg.split()
        offset_x = int(15 * math.sin(progress * math.pi))
        r = r.transform(r.size, Image.AFFINE, (1, 0, offset_x, 0, 1, 0))
        b = b.transform(b.size, Image.AFFINE, (1, 0, -offset_x, 0, 1, 0))
        result = Image.merge("RGB", (r, g, b))
        # Add horizontal slice displacement
        import random
        random.seed(int(progress * 100))
        for _ in range(3):
            y1 = random.randint(0, H - 60)
            h = random.randint(20, 60)
            strip = result.crop((0, y1, W, y1 + h))
            dx = random.randint(-20, 20)
            result.paste(strip, (dx, y1))
        return result

    elif transition == "shutter":
        # Rapid flash of multiple images
        n_img = len([prev_img, next_img])
        # Flash white then show next
        if progress < 0.3:
            return Image.blend(img1, Image.new("RGB", (W, H), (255, 255, 255)), progress / 0.3 * 0.8)
        elif progress < 0.5:
            return Image.new("RGB", (W, H), (255, 255, 255))
        elif progress < 0.7:
            p = (progress - 0.5) / 0.2
            return Image.blend(Image.new("RGB", (W, H), (255, 255, 255)), img2, p)
        else:
            return img2

    elif transition == "zoom_through":
        # Zoom into current → zoom out of next
        if progress < 0.5:
            # Zoom into img1
            z = 1.0 + progress * 2 * 0.5  # 1.0 → 1.5
            cw, ch = int(W / z), int(H / z)
            cx, cy = (W - cw) // 2, (H - ch) // 2
            return img1.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.LANCZOS)
        else:
            # Zoom out from img2
            p2 = (progress - 0.5) * 2
            z = 1.5 - p2 * 0.5  # 1.5 → 1.0
            cw, ch = int(W / z), int(H / z)
            cx, cy = (W - cw) // 2, (H - ch) // 2
            return img2.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.LANCZOS)

    elif transition == "split_reveal":
        # Horizontal split from center revealing next image
        split_h = int(H * progress / 2)
        result = img2.copy()
        if split_h < H // 2:
            top = img1.crop((0, 0, W, H // 2 - split_h))
            bottom = img1.crop((0, H // 2 + split_h, W, H))
            result.paste(top, (0, 0))
            result.paste(bottom, (0, H // 2 + split_h))
        return result

    elif transition == "circle_iris":
        # Circle wipe expanding from center
        mask = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(mask)
        max_r = int(math.sqrt(W**2 + H**2) / 2)
        r = int(max_r * progress)
        cx, cy = W // 2, H // 2
        d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=255)
        return Image.composite(img2, img1, mask)

    elif transition == "slip":
        # img1 slides down, img2 revealed behind
        offset = int(H * progress)
        canvas = img2.copy()
        shifted = img1.crop((0, 0, W, H - offset))
        canvas.paste(shifted, (0, offset))
        return canvas

    elif transition == "scroll_h":
        # Horizontal scroll — img1 exits left, img2 enters right
        offset = int(W * progress)
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        canvas.paste(img1.crop((offset, 0, W, H)), (0, 0))
        canvas.paste(img2.crop((0, 0, offset, H)), (W - offset, 0))
        return canvas

    elif transition == "scroll_v":
        # Vertical scroll — img1 exits up, img2 enters below
        offset = int(H * progress)
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        canvas.paste(img1.crop((0, offset, W, H)), (0, 0))
        canvas.paste(img2.crop((0, 0, W, offset)), (0, H - offset))
        return canvas

    elif transition == "rotate_wipe":
        # Rotating mask reveal
        mask = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(mask)
        cx, cy = W // 2, H // 2
        angle = progress * 360
        # Draw a pie slice that grows with progress
        d.pieslice([(cx - W, cy - H), (cx + W, cy + H)], start=-90, end=-90 + angle, fill=255)
        return Image.composite(img2, img1, mask)

    elif transition == "zoom_in":
        # img2 grows from center point
        scale = max(0.01, progress)
        new_w, new_h = int(W * scale), int(H * scale)
        small = img2.resize((new_w, new_h), Image.LANCZOS)
        canvas = img1.copy()
        x = (W - new_w) // 2
        y = (H - new_h) // 2
        canvas.paste(small, (x, y))
        return canvas

    elif transition == "shooting_frame":
        # Frame border shrinks in revealing img2
        border = int(max(W, H) * 0.5 * (1 - progress))
        if border <= 0:
            return img2
        canvas = img2.copy()
        # Draw border from img1
        top = img1.crop((0, 0, W, border))
        bot = img1.crop((0, H - border, W, H))
        left = img1.crop((0, 0, border, H))
        right = img1.crop((W - border, 0, W, H))
        canvas.paste(top, (0, 0))
        canvas.paste(bot, (0, H - border))
        canvas.paste(left, (0, 0))
        canvas.paste(right, (W - border, 0))
        return canvas

    elif transition == "countdown":
        # Flash black then reveal (countdown feel)
        if progress < 0.4:
            return Image.blend(img1, Image.new("RGB", (W, H), (0, 0, 0)), progress / 0.4)
        elif progress < 0.6:
            return Image.new("RGB", (W, H), (0, 0, 0))
        else:
            p = (progress - 0.6) / 0.4
            return Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img2, p)

    elif transition == "switch_on":
        # TV switch on — horizontal line expands to full
        line_h = int(H * progress)
        if line_h <= 0:
            return img1
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        y_start = (H - line_h) // 2
        strip = img2.crop((0, (H - line_h) // 2, W, (H + line_h) // 2))
        canvas.paste(strip, (0, y_start))
        return canvas

    elif transition == "switch_off":
        # TV switch off — shrinks to horizontal line then black
        line_h = int(H * (1 - progress))
        if line_h <= 0:
            return img2
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        y_start = (H - line_h) // 2
        strip = img1.crop((0, (H - line_h) // 2, W, (H + line_h) // 2))
        canvas.paste(strip, (0, y_start))
        if progress > 0.8:
            return Image.blend(canvas, img2, (progress - 0.8) / 0.2)
        return canvas

    # Default: simple crossfade
    return Image.blend(img1, img2, progress)


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
