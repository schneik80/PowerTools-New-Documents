#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Generate version merge branch/timeline icons using Pillow.

Concept: Inverted Y-fork - two version branches at the top converge
downward through a merge point onto a single filled result node at the
bottom. This is the literal inverse of the diff icon and intentionally
omits the diff icon's horizontal dashed comparison arrow (a merge is not
a comparison).

Produces: 16x16, 32x32, 64x64 in both light and dark variants.
"""

from PIL import Image, ImageDraw
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def draw_icon_small(size, stroke_color):
    """Simplified icon for 16x16: bold inverted-Y with 3 nodes.

    Two hollow tips at top-left / top-right converge to a single filled
    result node at the bottom-center. No intermediate merge point or
    chevron, to keep the 16x16 readable.
    """
    ss = 4
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = big / 64.0
    color = stroke_color

    sw = max(3, int(3.5 * s))
    r_node = max(3, int(4.5 * s))

    # Three key points: two branch tips top-left / top-right, result bottom-center
    l_tip = (int(12 * s), int(12 * s))
    r_tip = (int(52 * s), int(12 * s))
    fork = (int(32 * s), int(34 * s))
    result = (int(32 * s), int(54 * s))

    # Left branch (straight)
    draw.line([l_tip, fork], fill=color, width=sw)
    # Right branch (straight)
    draw.line([r_tip, fork], fill=color, width=sw)
    # Trunk down to result
    draw.line([fork, result], fill=color, width=sw)

    # Tip nodes (hollow) - the two versions being merged
    draw.ellipse([l_tip[0] - r_node, l_tip[1] - r_node,
                  l_tip[0] + r_node, l_tip[1] + r_node],
                 fill=None, outline=color, width=sw)
    draw.ellipse([r_tip[0] - r_node, r_tip[1] - r_node,
                  r_tip[0] + r_node, r_tip[1] + r_node],
                 fill=None, outline=color, width=sw)

    # Result node (filled)
    draw.ellipse([result[0] - r_node, result[1] - r_node,
                  result[0] + r_node, result[1] + r_node],
                 fill=color, outline=color)

    img = img.resize((size, size), Image.LANCZOS)
    return img


def draw_icon(size, stroke_color):
    """Draw the inverted-Y merge icon at the given size."""
    # Use 4x supersampling for anti-aliasing
    ss = 4
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = big / 64.0  # scale factor relative to 64px base

    # Stroke widths (scaled for supersampled canvas)
    sw = max(2, int(2.5 * s))
    sw_thin = max(1, int(1.8 * s))

    # Node radii
    r_big = max(3, int(3.5 * s))
    r_small = max(2, int(2.0 * s))

    # Key coordinates (inverted relative to diff icon)
    l_top = (int(13 * s), int(13 * s))   # version A (hollow, top-left)
    r_top = (int(51 * s), int(13 * s))   # version B (hollow, top-right)
    l_mid = (int(21 * s), int(23 * s))   # intermediate on left branch
    r_mid = (int(43 * s), int(23 * s))   # intermediate on right branch
    merge = (int(32 * s), int(38 * s))   # small filled merge point
    result = (int(32 * s), int(56 * s))  # large filled result node

    color = stroke_color

    # --- Draw branches using line segments to approximate curves ---

    # Left branch: l_top -> l_mid -> curve -> merge
    draw.line([l_top, l_mid], fill=color, width=sw)
    steps = 12
    prev = l_mid
    for i in range(1, steps + 1):
        t = i / steps
        # Quadratic bezier: l_mid -> control -> merge
        ctrl = (int(32 * s), int(28 * s))
        x = (1-t)**2 * l_mid[0] + 2*(1-t)*t * ctrl[0] + t**2 * merge[0]
        y = (1-t)**2 * l_mid[1] + 2*(1-t)*t * ctrl[1] + t**2 * merge[1]
        pt = (int(x), int(y))
        draw.line([prev, pt], fill=color, width=sw)
        prev = pt

    # Right branch: r_top -> r_mid -> curve -> merge
    draw.line([r_top, r_mid], fill=color, width=sw)
    prev = r_mid
    for i in range(1, steps + 1):
        t = i / steps
        ctrl = (int(32 * s), int(28 * s))
        x = (1-t)**2 * r_mid[0] + 2*(1-t)*t * ctrl[0] + t**2 * merge[0]
        y = (1-t)**2 * r_mid[1] + 2*(1-t)*t * ctrl[1] + t**2 * merge[1]
        pt = (int(x), int(y))
        draw.line([prev, pt], fill=color, width=sw)
        prev = pt

    # Trunk: merge point down to result
    draw.line([merge, result], fill=color, width=sw)

    # --- Nodes ---
    def filled_circle(center, radius):
        x, y = center
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                      fill=color, outline=color, width=sw)

    def hollow_circle(center, radius):
        x, y = center
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                      fill=None, outline=color, width=sw)

    # Top version nodes (hollow)
    hollow_circle(l_top, r_big)
    hollow_circle(r_top, r_big)

    # Intermediate nodes (filled, smaller)
    filled_circle(l_mid, r_small)
    filled_circle(r_mid, r_small)

    # Merge point (filled, small) and result (filled, large)
    filled_circle(merge, r_small)
    filled_circle(result, r_big)

    # --- Downward chevron just above the result to emphasize merge direction ---
    chev_y = result[1] - r_big - int(5 * s)
    chev_half_w = int(4 * s)
    chev_h = int(3 * s)
    cx = result[0]
    draw.line([(cx - chev_half_w, chev_y - chev_h), (cx, chev_y)],
              fill=color, width=sw_thin)
    draw.line([(cx + chev_half_w, chev_y - chev_h), (cx, chev_y)],
              fill=color, width=sw_thin)

    # Downsample with high-quality resampling
    img = img.resize((size, size), Image.LANCZOS)
    return img


def main():
    sizes = [16, 32, 64]

    # Light theme: dark charcoal
    light_color = (74, 74, 74, 255)     # #4A4A4A
    # Dark theme: silver-gray
    dark_color = (160, 160, 173, 255)   # #A0A0AD

    for size in sizes:
        # Use simplified icon for 16x16
        draw_fn = draw_icon_small if size == 16 else draw_icon

        # Light
        img = draw_fn(size, light_color)
        path = os.path.join(SCRIPT_DIR, f"{size}x{size}.png")
        img.save(path, "PNG")
        print(f"Created {path} ({os.path.getsize(path)} bytes)")

        # Dark
        img = draw_fn(size, dark_color)
        path = os.path.join(SCRIPT_DIR, f"{size}x{size}-dark.png")
        img.save(path, "PNG")
        print(f"Created {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
