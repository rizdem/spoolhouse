"""Builds branding/icon-concepts/preview.html: every concept at real sizes, light and dark."""
import base64, html, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icon_concepts import OUT, main

concepts = main()
uri = lambda svg: "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
img = lambda svg, px, alt: f'<img src="{uri(svg)}" width="{px}" height="{px}" alt="{html.escape(alt)}">'

cards = []
for n, (slug, name, blurb, svg) in enumerate(CONCEPTS := concepts):
    letter = slug[0].upper()
    sizes = "".join(f'<figure>{img(svg, px, name)}<figcaption>{px}</figcaption></figure>' for px in (128, 64, 32, 16))
    cards.append(f'''<article class="card">
  <div class="hero">{img(svg, 208, name + " icon")}</div>
  <div class="info">
    <h2><span class="tag">{letter}</span>{html.escape(name)}</h2>
    <p>{html.escape(blurb)}</p>
    <div class="strip light">{sizes}</div>
    <div class="strip dark">{sizes}</div>
    <div class="mini"><span class="mini-ic">{img(svg, 22, "")}</span><b>Spoolhouse</b><span class="mute">sidebar</span></div>
  </div>
</article>''')

dock = "".join(f'<div class="dk">{img(svg, 64, name)}<span>{slug[0].upper()}</span></div>' for slug, name, _, svg in CONCEPTS)

page = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spoolhouse Icon Concepts</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Instrument+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
/* Layout: a header, a mock Dock with all five side by side, then one card per concept (big icon left, real sizes right). */
:root{{
  --bg:#F3F1EC; --surface:#FFFFFF; --ink:#18232B; --muted:#5E6A72; --line:#DDD8CE; --accent:#E8590C;
  --display:"Fraunces", Georgia, serif; --body:"Instrument Sans", system-ui, -apple-system, sans-serif;
}}
@media (prefers-color-scheme: dark){{ :root:not([data-theme="light"]){{
  --bg:#11181D; --surface:#1A242B; --ink:#EEF1F2; --muted:#9AA7AF; --line:#2B3740; --accent:#FF8F4A; color-scheme:dark; }} }}
:root[data-theme="dark"]{{ --bg:#11181D; --surface:#1A242B; --ink:#EEF1F2; --muted:#9AA7AF; --line:#2B3740; --accent:#FF8F4A; color-scheme:dark; }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 var(--body)}}
main{{max-width:1040px;margin:0 auto;padding:40px 16px 64px;display:grid;gap:28px}}
h1{{font:600 clamp(32px,5vw,48px)/1.05 var(--display);margin:0;text-wrap:balance}}
h1 em{{font-style:normal;color:var(--accent)}}
.lede{{color:var(--muted);max-width:62ch;margin:8px 0 0}}
.dock{{justify-self:center;display:flex;gap:18px;flex-wrap:wrap;justify-content:center;padding:14px 22px;border-radius:26px;
  background:color-mix(in srgb,var(--surface) 70%,transparent);border:1px solid var(--line);box-shadow:0 10px 30px rgba(0,0,0,.12)}}
.dk{{display:grid;justify-items:center;gap:4px;font-size:12px;color:var(--muted);font-weight:600}}
.card{{display:grid;grid-template-columns:240px 1fr;gap:28px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:24px}}
.hero{{display:grid;place-items:center}}
.hero img{{filter:drop-shadow(0 12px 18px rgba(0,0,0,.22))}}
.info{{display:grid;gap:12px;min-width:0}}
h2{{font:600 26px/1.1 var(--display);margin:0;display:flex;gap:10px;align-items:center}}
.tag{{font:600 13px/1 var(--body);background:var(--accent);color:#fff;border-radius:7px;padding:5px 8px}}
.info p{{margin:0;color:var(--muted);max-width:60ch}}
.strip{{display:flex;gap:22px;align-items:flex-end;flex-wrap:wrap;padding:14px 16px;border-radius:12px}}
.strip.light{{background:#ECEEF0;color:#5E6A72}} .strip.dark{{background:#1E1E20;color:#9A9A9E}}
figure{{margin:0;display:grid;justify-items:center;gap:4px}} figcaption{{font-size:11px;font-variant-numeric:tabular-nums}}
.mini{{display:flex;align-items:center;gap:8px;font-size:15px}} .mini-ic img{{display:block;border-radius:5px}}
.mute{{color:var(--muted);font-size:12px}}
@media (max-width:640px){{ .card{{grid-template-columns:1fr}} .hero img{{width:160px;height:160px}} }}
</style></head>
<body><main>
<header><h1>Spoolhouse <em>icon concepts</em></h1>
<p class="lede">Five directions, each shown at Dock size and at the small sizes macOS really uses: 32 px in Finder lists and 16 px in menus. The two strips show the icon on a light and a dark desktop. Pick a letter, or mix ideas (say, B's shape in E's colours).</p></header>
<div class="dock" aria-label="All five side by side, as in the Dock">{dock}</div>
{"".join(cards)}
</main></body></html>'''
path = os.path.join(OUT, "preview.html")
open(path, "w").write(page)
print(path)
