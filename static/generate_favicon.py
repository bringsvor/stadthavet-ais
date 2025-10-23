#!/usr/bin/env python3
"""
Generate favicon and PWA icons for Stadthavet AIS
Design: Ship entering a tunnel (representing ships going through Stad ship tunnel)
"""

from PIL import Image, ImageDraw

def create_ship_tunnel_icon(size):
    """Create a ship in tunnel icon at specified size"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Scale factor for drawing
    s = size / 100

    # Background circle (dark blue/ocean)
    draw.ellipse([0, 0, size-1, size-1], fill='#0f172a', outline='#1e40af', width=max(1, int(2*s)))

    # Tunnel (gray arch at top)
    tunnel_top = int(20 * s)
    tunnel_height = int(40 * s)
    tunnel_left = int(15 * s)
    tunnel_right = int(85 * s)

    # Tunnel opening (darker)
    draw.rectangle([tunnel_left, tunnel_top, tunnel_right, tunnel_top + tunnel_height],
                   fill='#1e293b', outline='#475569', width=max(1, int(2*s)))

    # Tunnel arch top
    draw.arc([tunnel_left, tunnel_top - int(20*s), tunnel_right, tunnel_top + int(20*s)],
             start=0, end=180, fill='#475569', width=max(1, int(3*s)))

    # Ship body (simplified ship shape)
    ship_bottom = int(75 * s)
    ship_top = int(55 * s)
    ship_left = int(35 * s)
    ship_right = int(65 * s)

    # Ship hull (white/light gray)
    hull_points = [
        (ship_left + int(5*s), ship_bottom),      # bottom left
        (ship_left, ship_top),                     # top left
        (ship_right, ship_top),                    # top right
        (ship_right - int(5*s), ship_bottom)       # bottom right
    ]
    draw.polygon(hull_points, fill='#e2e8f0', outline='#94a3b8', width=max(1, int(1*s)))

    # Ship superstructure (smaller rectangle on top)
    super_left = int(42 * s)
    super_right = int(58 * s)
    super_top = int(45 * s)
    super_bottom = int(55 * s)
    draw.rectangle([super_left, super_top, super_right, super_bottom],
                   fill='#60a5fa', outline='#3b82f6', width=max(1, int(1*s)))

    # Wave lines (simple waves at bottom)
    wave_y1 = int(78 * s)
    wave_y2 = int(85 * s)
    draw.arc([int(10*s), wave_y1, int(30*s), wave_y2], start=0, end=180,
             fill='#3b82f6', width=max(1, int(2*s)))
    draw.arc([int(25*s), wave_y1, int(45*s), wave_y2], start=0, end=180,
             fill='#3b82f6', width=max(1, int(2*s)))
    draw.arc([int(55*s), wave_y1, int(75*s), wave_y2], start=0, end=180,
             fill='#3b82f6', width=max(1, int(2*s)))
    draw.arc([int(70*s), wave_y1, int(90*s), wave_y2], start=0, end=180,
             fill='#3b82f6', width=max(1, int(2*s)))

    return img

# Generate favicon.ico (16x16, 32x32, 48x48)
print("Generating favicon.ico...")
icon16 = create_ship_tunnel_icon(16)
icon32 = create_ship_tunnel_icon(32)
icon48 = create_ship_tunnel_icon(48)
icon16.save('static/favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])

# Generate PNG versions for various uses
print("Generating favicon-16x16.png...")
icon16.save('static/favicon-16x16.png', format='PNG')

print("Generating favicon-32x32.png...")
icon32.save('static/favicon-32x32.png', format='PNG')

print("Generating apple-touch-icon.png (180x180)...")
icon180 = create_ship_tunnel_icon(180)
icon180.save('static/apple-touch-icon.png', format='PNG')

# Generate PWA icons
print("Generating android-chrome-192x192.png...")
icon192 = create_ship_tunnel_icon(192)
icon192.save('static/android-chrome-192x192.png', format='PNG')

print("Generating android-chrome-512x512.png...")
icon512 = create_ship_tunnel_icon(512)
icon512.save('static/android-chrome-512x512.png', format='PNG')

print("\nAll icons generated successfully!")
print("\nGenerated files:")
print("  - static/favicon.ico (16x16, 32x32, 48x48)")
print("  - static/favicon-16x16.png")
print("  - static/favicon-32x32.png")
print("  - static/apple-touch-icon.png (180x180)")
print("  - static/android-chrome-192x192.png (for PWA)")
print("  - static/android-chrome-512x512.png (for PWA)")
