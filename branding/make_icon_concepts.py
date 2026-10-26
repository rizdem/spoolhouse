"""Spoolhouse icon concepts: writes one SVG per concept (1024 x 1024, macOS rounded-square)
and a preview page showing them at real sizes."""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon-concepts")
TILE = 'x="100" y="100" width="824" height="824" rx="186"'  # macOS app icon body on a 1024 canvas


def icon(defs, body, bg):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
            f'<defs>{defs}<linearGradient id="shine" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#fff" stop-opacity=".18"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
            f'<rect {TILE} fill="{bg}"/>{body}<rect {TILE} fill="url(#shine)"/></svg>')


def spool_front(cx, cy, r, filament, flange="#26343D", hub="#F6F1E7", rings=True):
    """A spool seen face-on: dark flange, filament, wound lines, hub with its hole."""
    lines = "".join(f'<circle cx="{cx}" cy="{cy}" r="{r * f:.1f}" fill="none" stroke="#000" stroke-opacity=".13" stroke-width="{max(2, r * .035):.1f}"/>'
                    for f in (.72, .6, .48)) if rings else ""
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{flange}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r * .84:.1f}" fill="{filament}"/>{lines}'
            f'<circle cx="{cx}" cy="{cy}" r="{r * .34:.1f}" fill="{hub}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r * .12:.1f}" fill="{flange}"/>')


CONCEPTS = []

# A - Spool Home: a house whose front is a spool
CONCEPTS.append(("a-spool-home", "Spool Home", "A little house whose front is a spool of filament. Says \"home for your spools\" at a glance.",
    icon('<linearGradient id="bgA" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#21495E"/><stop offset="1" stop-color="#112835"/></linearGradient>',
         '<path d="M512 232 L790 468 L234 468 Z" fill="#FF7A3D" stroke="#FF7A3D" stroke-width="44" stroke-linejoin="round"/>'
         '<rect x="296" y="446" width="432" height="350" rx="40" fill="#F6F1E7"/>'
         + spool_front(512, 622, 132, "#FF7A3D"),
         "url(#bgA)")))

# B - Roofed Spool: side-on spool with a roof, the spool is the house
winds = "".join(f'<path d="M380 {y} Q512 {y + 14} 644 {y}" fill="none" stroke="#000" stroke-opacity=".16" stroke-width="7"/>' for y in range(468, 790, 30))
CONCEPTS.append(("b-roofed-spool", "Roofed Spool", "A spool seen from the side with a roof on top: the spool is the house. Bold and simple.",
    icon('<linearGradient id="bgB" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF8F4A"/><stop offset="1" stop-color="#E8590C"/></linearGradient>',
         '<rect x="372" y="440" width="280" height="370" rx="10" fill="#FFF6EC"/>' + winds +
         '<ellipse cx="349" cy="625" rx="44" ry="240" fill="#1E2A33"/>'
         '<ellipse cx="675" cy="625" rx="44" ry="240" fill="#1E2A33"/>'
         '<ellipse cx="349" cy="625" rx="14" ry="60" fill="#FF8F4A"/>'
         '<path d="M270 360 L512 196 L754 360" fill="none" stroke="#1E2A33" stroke-width="64" stroke-linecap="round" stroke-linejoin="round"/>',
         "url(#bgB)")))

def coil_path(cx=512, cy=612, r0=26, r1=148, turns=2.6):
    """A spiral winding out to the bottom of the coil, then the same line drawing the house."""
    import math
    pts, n = [], 160
    for i in range(n + 1):
        t = i / n
        a = math.radians(90 - 360 * turns * (1 - t))
        r = r0 + (r1 - r0) * t
        pts.append(f"{cx + r * math.cos(a):.1f} {cy + r * math.sin(a):.1f}")
    return "M" + " L".join(pts) + " L300 760 L300 470 L512 292 L724 470 L724 760 L640 760"


# C - One Strand: a single line draws the house and coils into a spool
CONCEPTS.append(("c-one-strand", "One Strand", "One continuous line of filament draws the house, then winds into a spool. The most elegant, least literal.",
    icon('<linearGradient id="strand" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#FF7A3D"/><stop offset="1" stop-color="#FFC24B"/></linearGradient>',
         f'<path d="{coil_path()}" fill="none" stroke="url(#strand)" stroke-width="34" stroke-linecap="round" stroke-linejoin="round"/>',
         "#13232E")))

# D - The CFS: a house holding four spools, like the CFS's four slots
slots = (spool_front(436, 560, 64, "#F4F4F2", flange="#3A4750", hub="#DADDE0", rings=False)
         + spool_front(588, 560, 64, "#E5484D", flange="#3A4750", rings=False)
         + spool_front(436, 706, 64, "#FF7A3D", flange="#3A4750", rings=False)
         + spool_front(588, 706, 64, "#2FA36B", flange="#3A4750", rings=False))
CONCEPTS.append(("d-the-cfs", "The CFS", "A house holding four spools in your real colours, like the four slots of a CFS. Playful and specific.",
    icon('<linearGradient id="bgD" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1C3A52"/><stop offset="1" stop-color="#0F2233"/></linearGradient>',
         '<path d="M512 222 L800 450 L224 450 Z" fill="#F2C14E" stroke="#F2C14E" stroke-width="44" stroke-linejoin="round"/>'
         '<rect x="320" y="440" width="384" height="384" rx="44" fill="#F6F1E7"/>' + slots,
         "url(#bgD)")))

# E - Keyhole: a big spool whose centre hole is a house
CONCEPTS.append(("e-keyhole", "Keyhole", "A big spool whose centre is a house-shaped opening. Clean, and still reads at tiny sizes.",
    icon('<linearGradient id="bgE" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#13A08B"/><stop offset="1" stop-color="#0A6658"/></linearGradient>',
         '<circle cx="512" cy="512" r="318" fill="#F6F1E7"/>'
         '<circle cx="512" cy="512" r="272" fill="#FF7A3D"/>'
         + "".join(f'<circle cx="512" cy="512" r="{r}" fill="none" stroke="#000" stroke-opacity=".12" stroke-width="9"/>' for r in (236, 202, 168)) +
         '<circle cx="512" cy="512" r="134" fill="#F6F1E7"/>'
         '<path d="M512 420 L590 486 L590 586 L434 586 L434 486 Z" fill="#0C7B6B" stroke="#0C7B6B" stroke-width="18" stroke-linejoin="round"/>',
         "url(#bgE)")))


def main():
    os.makedirs(OUT, exist_ok=True)
    for slug, _, _, svg in CONCEPTS:
        with open(os.path.join(OUT, f"{slug}.svg"), "w") as f:
            f.write(svg)
    print("wrote", len(CONCEPTS), "concepts to", OUT)
    return CONCEPTS


if __name__ == "__main__":
    main()
