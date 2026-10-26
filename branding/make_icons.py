"""Turns every concept SVG into a real macOS icon: branding/icons/<letter>-<name>.icns (+ a 1024 px PNG)."""
import os, shutil, subprocess, sys, tempfile
import AppKit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icon_concepts import OUT as SVG_DIR, main as draw

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
SIZES = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2)]


def render(svg_path, px, out):
    img = AppKit.NSImage.alloc().initWithContentsOfFile_(svg_path)
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, px, px, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)
    AppKit.NSGraphicsContext.saveGraphicsState()
    ctx = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    ctx.setImageInterpolation_(AppKit.NSImageInterpolationHigh)
    AppKit.NSGraphicsContext.setCurrentContext_(ctx)
    img.drawInRect_(AppKit.NSMakeRect(0, 0, px, px))
    AppKit.NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(out, True)


def main():
    os.makedirs(ICONS, exist_ok=True)
    for slug, *_ in draw():
        svg = os.path.join(SVG_DIR, f"{slug}.svg")
        with tempfile.TemporaryDirectory() as tmp:
            iconset = os.path.join(tmp, "icon.iconset"); os.mkdir(iconset)
            for pt, scale in SIZES:
                name = f"icon_{pt}x{pt}{'@2x' if scale == 2 else ''}.png"
                render(svg, pt * scale, os.path.join(iconset, name))
            subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(ICONS, f"{slug}.icns")], check=True)
            shutil.copy(os.path.join(iconset, "icon_512x512@2x.png"), os.path.join(ICONS, f"{slug}.png"))
        print("made", slug)


if __name__ == "__main__":
    main()
