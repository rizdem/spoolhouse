"""README banner: branding/banner.png (2x, 1600 x 440). The One Strand mark, the name in the icon's orange
and the tagline. Wordmark font: Nunito (SIL Open Font Licence, branding/fonts/)."""
import os, sys
import AppKit, CoreText, Foundation
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icon_concepts import coil_path

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, R = 1600, 440, 44
ORANGE, AMBER = (1.0, 0.478, 0.239), (1.0, 0.761, 0.294)  # #FF7A3D -> #FFC24B, as in the icon
NAME, TAGLINE = "Spoolhouse", "Filament inventory for Creality CFS"


def rgb(c, a=1.0):
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(*c, a)


def font(size, weight):
    path = os.path.join(HERE, "fonts", "Nunito.ttf")
    descs = CoreText.CTFontManagerCreateFontDescriptorsFromURL(Foundation.NSURL.fileURLWithPath_(path))
    desc = CoreText.CTFontDescriptorCreateCopyWithVariation(descs[0], 0x77676874, weight)  # 'wght'
    return CoreText.CTFontCreateWithFontDescriptor(desc, size, None)


def gradient_text(text, f, height):
    """Text filled with the icon's orange-to-amber gradient, as an NSImage."""
    attrs = {AppKit.NSFontAttributeName: f, AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
             AppKit.NSKernAttributeName: -2.0}
    s = AppKit.NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    size = s.size()
    img = AppKit.NSImage.alloc().initWithSize_((size.width + 8, height))
    img.lockFocus()
    s.drawAtPoint_((4, (height - size.height) / 2))
    grad = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(rgb(ORANGE), rgb(AMBER))
    AppKit.NSGraphicsContext.currentContext().setCompositingOperation_(AppKit.NSCompositingOperationSourceAtop)
    grad.drawInRect_angle_(AppKit.NSMakeRect(0, 0, size.width + 8, height), 20)
    img.unlockFocus()
    return img


def mark():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="262 262 500 520">'
           '<defs><linearGradient id="g" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#FF7A3D"/>'
           '<stop offset="1" stop-color="#FFC24B"/></linearGradient></defs>'
           f'<path d="{coil_path()}" fill="none" stroke="url(#g)" stroke-width="34" stroke-linecap="round" '
           'stroke-linejoin="round"/></svg>')
    data = Foundation.NSData.dataWithBytes_length_(svg.encode(), len(svg.encode()))
    return AppKit.NSImage.alloc().initWithData_(data)


def main():
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, W, H, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)
    AppKit.NSGraphicsContext.saveGraphicsState()
    ctx = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    ctx.setImageInterpolation_(AppKit.NSImageInterpolationHigh)
    AppKit.NSGraphicsContext.setCurrentContext_(ctx)

    # background: the icon's dark slate, rounded so it sits well on GitHub's light and dark themes
    card = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(AppKit.NSMakeRect(0, 0, W, H), R, R)
    card.addClip()
    AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(
        rgb((0.094, 0.161, 0.200)), rgb((0.075, 0.137, 0.180))).drawInRect_angle_(AppKit.NSMakeRect(0, 0, W, H), 90)
    # a faint wound-filament texture behind the mark
    for i in range(9):
        r = 120 + i * 46
        ring = AppKit.NSBezierPath.bezierPathWithOvalInRect_(AppKit.NSMakeRect(270 - r, 220 - r, 2 * r, 2 * r))
        ring.setLineWidth_(2)
        rgb(ORANGE, 0.05).setStroke(); ring.stroke()

    mark().drawInRect_(AppKit.NSMakeRect(130, 70, 290, 302))
    word = gradient_text(NAME, font(172, 850), 230)
    word.drawAtPoint_fromRect_operation_fraction_((478, 168), AppKit.NSZeroRect, AppKit.NSCompositingOperationSourceOver, 1)
    tag = AppKit.NSAttributedString.alloc().initWithString_attributes_(TAGLINE, {
        AppKit.NSFontAttributeName: font(50, 600), AppKit.NSForegroundColorAttributeName: rgb((0.80, 0.85, 0.88)),
        AppKit.NSKernAttributeName: 0.4})
    tag.drawAtPoint_((488, 118))

    AppKit.NSGraphicsContext.restoreGraphicsState()
    out = os.path.join(HERE, "banner.png")
    rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(out, True)
    print(out)


if __name__ == "__main__":
    main()
