"""Build static language editions from COPY.md; no packages, network or API calls.
Run from repo root: python3 tests/site/build-locales.py [--base-url https://your-domain]
"""
import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

SITE = Path(__file__).resolve().parents[2] / 'frontend/site'
LANGUAGES = {'en': 'English', 'it': 'Italiano', 'de': 'Deutsch', 'fr': 'Français'}
def esc(value): return html.escape(str(value), quote=True)
def copy_data():
    text = (SITE / 'COPY.md').read_text()
    return json.loads(text.split('<!-- locale-copy -->')[1].split('```json\n')[1].split('\n```')[0])
def url_path(lang): return '' if lang == 'en' else lang + '/'
def links(lang, prefix, data):
    items = ''.join(f'<li><a href="{prefix}{url_path(code) or "index.html"}" lang="{code}" hreflang="{code}"'+(' aria-current="page"' if code == lang else '')+f'>{name}</a></li>' for code,name in LANGUAGES.items())
    return f'<details class="language-menu"><summary aria-label="{esc(data["language"])}">{lang.upper()} ⌄</summary><ul>{items}</ul></details>'
def audience(data):
    items = ''.join(f'<li class="audience-item{" active" if i == 0 else ""}" aria-hidden="{str(i != 0).lower()}"><span class="hand">{esc(title)}</span></li>' for i,(title,body,status) in enumerate(data['audiences']))
    return f'<div class="audience" data-audience><ul class="audience-list">{items}</ul><svg class="audience-underline" viewBox="0 0 200 12" aria-hidden="true"><path d="M2 8 C 40 2, 80 12, 120 6 S 180 4, 198 7"/></svg></div>'
def trust_links(lang, prefix):
    labels = {'en':['Privacy draft','Terms draft','Refunds draft','Cookies & storage','Data requests'], 'it':['Privacy · bozza EN','Condizioni · bozza EN','Rimborsi · bozza EN','Cookie · EN','Richieste dati · EN'], 'de':['Datenschutz · Entwurf EN','Bedingungen · Entwurf EN','Erstattung · Entwurf EN','Cookies · EN','Datenanfragen · EN'], 'fr':['Confidentialité · brouillon EN','Conditions · brouillon EN','Remboursements · brouillon EN','Cookies · EN','Demandes de données · EN']}[lang]
    return '<div class="trust-footer">'+''.join(f'<a href="{prefix}trust.html#{anchor}">{esc(label)}</a>' for anchor,label in zip(['privacy','terms','refunds','cookies','requests'],labels))+'</div>'
def metadata(lang, base):
    if not base: return '<!-- Production domain needed for canonical, hreflang and sitemap. -->'
    tags = [f'<link rel="canonical" href="{esc(base + "/" + url_path(lang))}">']
    tags += [f'<link rel="alternate" hreflang="{code}" href="{esc(base + "/" + url_path(code))}">' for code in LANGUAGES]
    tags += [f'<link rel="alternate" hreflang="x-default" href="{esc(base + "/")}">',f'<meta property="og:url" content="{esc(base + "/" + url_path(lang))}">']
    return '\n'.join(tags)
def heading(parts): return esc(parts[0]) + '<br><em>' + esc(parts[1]) + '</em>'
def page(lang, d, base):
    steps=''.join(f'<article class="frame local-steps"><span class="hand">0{i+1}</span><h3>{esc(a)}</h3><p>{esc(b)}</p></article>' for i,(a,b) in enumerate(d['steps']))
    uses=''.join(f'<article class="frame local-steps"><span class="badge">{esc(status)}</span><h3>{esc(title)}</h3><p>{esc(body)}</p></article>' for title,status,body in d['uses'])
    metrics=''.join(f'<article class="frame stat"><strong>{value}</strong><h3>{esc(title)}</h3><p>{esc(body)}</p></article>' for value,(title,body) in zip(['3,2–4,6 s','3,6–4,4 %'],d['metrics']))
    questions=''.join(f'<details><summary>{esc(q)}<span aria-hidden="true">+</span></summary><p>{esc(a)}</p></details>' for q,a in d['questions'])
    image=base+'/assets/og-image.jpg' if base else '../assets/og-image.jpg'
    return f'''<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(d['title'])}</title><meta name="description" content="{esc(d['description'])}">
<meta name="theme-color" content="#f5f3ec"><meta name="robots" content="index,follow,max-image-preview:large">
<!-- locale-seo -->{metadata(lang,base)}<!-- /locale-seo -->
<meta property="og:type" content="website"><meta property="og:site_name" content="VocalGrid"><meta property="og:locale" content="{dict(it='it_IT',de='de_DE',fr='fr_FR')[lang]}"><meta property="og:title" content="{esc(d['title'])}"><meta property="og:description" content="{esc(d['description'])}"><meta property="og:image" content="{esc(image)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(d['title'])}"><meta name="twitter:description" content="{esc(d['description'])}"><meta name="twitter:image" content="{esc(image)}">
<link rel="icon" href="../assets/icon.svg"><link rel="stylesheet" href="../site.css?v=trust-1"><link rel="preload" href="../assets/fonts/instrument-sans.woff2" as="font" type="font/woff2" crossorigin><script src="../audience.js?v=handwrite-2" defer></script>
</head><body class="local-edition"><a class="skip" href="#main">{esc(d['skip'])}</a>
<header class="nav"><div class="nav-pill"><a class="brand" href="./">vocalgrid</a><nav aria-label="{esc(d['how'])}"><a href="#how">{esc(d['how'])}</a><a href="#pricing">{esc(d['pricing'])}</a></nav><a class="mono tiny" href="../account.html" lang="en">Sign in · EN</a>{links(lang,'../',d)}<a class="btn btn-orange btn-sm" href="https://aayushanupam1--lingosync-web.modal.run" target="_blank" rel="noopener"><span>{esc(d['open'])}</span></a></div></header>
<main id="main"><section class="hero" aria-labelledby="hero-title"><div class="hero-copy">{audience(d)}<h1 id="hero-title">{esc(d['headline'][0])}<br>{esc(d['headline'][1])}<br><em>{esc(d['headline'][2])}</em></h1><p class="lede">{esc(d['lede'])}</p><div class="hero-actions"><a class="btn btn-orange" href="../index.html#fit"><span class="btn-icon" aria-hidden="true">→</span><span>{esc(d['cta'])}</span></a><a class="btn btn-ghost" href="#film"><span class="btn-icon" aria-hidden="true">▶</span><span>{esc(d['watch'])}</span></a></div><p class="mono tiny hero-status">{esc(d['status'])}</p></div>
<div class="hero-art" role="img" aria-label="{esc(d['illustration'])}"><div class="orbit" aria-hidden="true"></div><div class="device-wrap"><div class="device-art"><div class="device-top"><span>vocalgrid</span><span>● ● ●</span></div><div class="device-screen"><div class="screen-meta">{esc(d['preview'])} · IT / EN</div><div class="language-pair">italiano →<br>english</div><div class="local-wave" aria-hidden="true">▂ ▅ ▃ ▇ ▅ ▂ ▆ ▃ ▅ ▇ ▂ ▆</div><div class="sample-transcript"><span lang="it">“Possiamo condividere l’idea venerdì.”</span><p lang="en">“We can share the idea on Friday.”</p></div></div><div class="device-top"><span>{esc(d['voice'])}</span></div></div></div><p class="mono tiny art-caption">{esc(d['illustration'])}</p></div></section>
<section class="how local-how" id="how"><div class="section-head"><p class="mono label">{esc(d['how'])}</p><h2>{heading(d['stepsTitle'])}</h2></div><div class="use-grid">{steps}</div></section>
<section class="uses"><div class="section-head"><h2>{heading(d['usesTitle'])}</h2></div><div class="use-grid">{uses}</div></section>
<section class="languages"><h2>{esc(d['languagesTitle'])}</h2><p class="section-intro">{esc(d['languagesText'])}</p><ul class="lang-list"><li class="tested">Italiano → English</li><li>Deutsch · Français · English · Italiano</li></ul></section>
<section class="film" id="film"><div class="section-head"><h2>{heading(d['filmTitle'])}</h2></div><div class="frame film-frame"><video controls playsinline preload="none" poster="../assets/film-poster.jpg" aria-label="{esc(d['watch'])}"><source src="../assets/conversation-film.mp4" type="video/mp4"><track kind="captions" srclang="en" label="English" src="../assets/film.vtt"><a href="../assets/conversation-film.mp4">{esc(d['watch'])}</a></video></div><p class="mono tiny film-caption">{esc(d['filmNote'])}</p></section>
<section class="evidence"><div class="section-head"><h2>{esc(d['results'])}</h2></div><div class="evidence-grid">{metrics}</div><p class="section-intro">{esc(d['method'])}</p></section>
<section class="pricing" id="pricing"><div class="section-head"><h2>{esc(d['plan'])}</h2></div><article class="frame plan plan-featured"><p class="price">$149<span>{esc(d['period'])}</span></p><p class="plan-intro">{esc(d['planIntro'])}</p><ul>{''.join('<li>'+esc(x)+'</li>' for x in d['features'])}</ul><a class="btn btn-orange" href="../index.html#fit"><span class="btn-icon" aria-hidden="true">→</span><span>{esc(d['cta'])}</span></a><p class="tiny dim">{esc(d['offer'])}</p></article><p class="local-support">{esc(d['support'])}</p></section>
<section class="faq"><div class="section-head"><h2>{esc(d['faq'])}</h2></div><div class="faq-list">{questions}</div></section></main>
<footer class="footer">{trust_links(lang,"../")}<div class="footer-bottom mono tiny"><span>© 2026 VocalGrid</span><button class="text-btn mono tiny" data-local-motion data-pause="{esc(d['pause'])}" data-resume="{esc(d['resume'])}" aria-pressed="false">{esc(d['pause'])}</button><a href="#main">{esc(d['back'])} ↑</a></div></footer></body></html>'''

def build(base='', output=SITE):
    if base:
        parts=urlsplit(base)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Use the final HTTPS site URL without credentials, query or fragment.')
        base=base.rstrip('/')
    d=copy_data()
    root=(SITE/'index.html').read_text()
    group='<!-- audience-start -->'+audience(d['en'])+'<!-- audience-end -->'
    if '<!-- audience-start -->' in root: root=re.sub(r'<!-- audience-start -->.*?<!-- audience-end -->',lambda m:group,root,flags=re.S)
    else: root=re.sub(r'<p class="hand hand-note hero-note">.*?</p>',lambda m:group,root,count=1,flags=re.S)
    menu='<!-- locale-menu -->'+links('en','',d['en'])+'<!-- /locale-menu -->'
    if '<!-- locale-menu -->' in root: root=re.sub(r'<!-- locale-menu -->.*?<!-- /locale-menu -->',lambda m:menu,root,flags=re.S)
    else: root=root.replace('    <span class="scroll-progress"',menu+'\n    <span class="scroll-progress"',1)
    seo='<!-- locale-seo -->'+metadata('en',base)+'<!-- /locale-seo -->'
    if '<!-- locale-seo -->' in root: root=re.sub(r'<!-- locale-seo -->.*?<!-- /locale-seo -->',lambda m:seo,root,flags=re.S)
    else: root=root.replace('</head>',seo+'\n</head>',1)
    if 'audience.js' not in root: root=root.replace('</head>','<script src="audience.js?v=handwrite-2" defer></script>\n</head>',1)
    footer='<!-- trust-links -->'+trust_links('en','')+'<!-- /trust-links -->'
    if '<!-- trust-links -->' in root: root=re.sub(r'<!-- trust-links -->.*?<!-- /trust-links -->',lambda m:footer,root,flags=re.S)
    else: root=root.replace('<footer class="footer">','<footer class="footer">'+footer,1)
    (output/'index.html').write_text(root)
    for lang in ['it','de','fr']:
        (output/lang).mkdir(parents=True,exist_ok=True)
        (output/lang/'index.html').write_text(page(lang,d[lang],base))
    if base:
        urls=''.join('<url><loc>'+esc(base+'/'+url_path(lang))+'</loc></url>' for lang in LANGUAGES)
        (output/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+urls+'</urlset>')
        (output/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+base+'/sitemap.xml\n')
    print('Built English audience component + Italian, German and French landing pages.'+(' SEO URLs configured.' if base else ' Final domain still required for SEO URLs.'))

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='');args=parser.parse_args();build(args.base_url)
