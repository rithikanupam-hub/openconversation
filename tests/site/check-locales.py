"""Run: python3 tests/site/check-locales.py"""
import importlib.util
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree
spec=importlib.util.spec_from_file_location('locales',Path(__file__).with_name('build-locales.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class Page(HTMLParser):
    def __init__(self,text):
        super().__init__();self.tags=[];self.feed(text)
    def handle_starttag(self,tag,attrs): self.tags.append((tag,dict(attrs)))
for lang in b.LANGUAGES:
    file=b.SITE/b.url_path(lang)/'index.html'; text=file.read_text(); page=Page(text)
    assert ('html',{'lang':lang}) in page.tags
    assert sum(tag=='h1' for tag,a in page.tags)==1
    assert 'audience-next' not in text
    assert 'audience-position' not in text
    assert sum('audience-item' in a.get('class','') for tag,a in page.tags)==5
    assert '<link rel="canonical"' not in text # No invented production domain.
    for tag,a in page.tags:
        for key in ['href','src','poster']:
            value=a.get(key,'')
            if not value or ':' in value or value.startswith('#'):continue
            target=(file.parent/value.split('#')[0].split('?')[0])
            if target.is_dir():target=target/'index.html'
            assert target.exists(),(lang,value)
    if lang!='en':
        assert '../index.html#fit' in text
        assert b.copy_data()[lang]['support'] in text.replace('&#x27;',"'")
with tempfile.TemporaryDirectory() as folder:
    out=Path(folder);b.build('https://example.test/product',out)
    for lang in b.LANGUAGES:
        page=Page((out/b.url_path(lang)/'index.html').read_text())
        alts=[a for tag,a in page.tags if tag=='link' and a.get('rel')=='alternate']
        assert {a['hreflang'] for a in alts}=={'en','it','de','fr','x-default'}
        assert all(a['href'].startswith('https://example.test/product/') for a in alts)
        canon=[a['href'] for tag,a in page.tags if a.get('rel')=='canonical']
        assert canon==['https://example.test/product/'+b.url_path(lang)]
    tree=ElementTree.parse(out/'sitemap.xml')
    assert len(tree.getroot())==4
try:b.build('https://user:secret@example.test')
except ValueError:pass
else:raise AssertionError('Credential-bearing URL accepted')
print('PASS: four languages, audience count, local links/assets, English fit handoff, canonical/hreflang reciprocity, sitemap and URL validation.')
