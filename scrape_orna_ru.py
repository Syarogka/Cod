import asyncio, json, os, re, time, zipfile, hashlib
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from tqdm import tqdm
import requests

BASE = 'https://playorna.com/codex/'
START = BASE + '?lang=ru'
OUT = 'output'
IMG_DIR = os.path.join(OUT, 'images')
os.makedirs(IMG_DIR, exist_ok=True)

SECTIONS = ['items','followers','classes','skills','monsters','bosses','raids','buildings','dungeons']
RU_HINTS = ['События','Обновления','Кодекс','Предмет','Питом','Класс','Навык','Монстр','Босс','Редкость','Уровень','Семья','Способности']
BAD_COOKIE = ['informasjonskapsler','Aksepter','Avslå','Privatvern','Begivenheter','Oppdateringer','Varer']

def norm_url(u):
    u = urljoin(BASE, u)
    p = urlparse(u)
    q = dict(parse_qsl(p.query))
    q['lang'] = 'ru'
    return urlunparse((p.scheme, p.netloc, p.path, '', urlencode(q, doseq=True), ''))

def clean_lines(text):
    lines=[]
    for line in text.splitlines():
        s=' '.join(line.split())
        if not s: continue
        if any(b.lower() in s.lower() for b in BAD_COOKIE): continue
        if s in ['Мерч','Google Play','Apple App Store','English','Русский','Blog','Кодекс','События','Обновления']:
            continue
        lines.append(s)
    out=[]
    for s in lines:
        if not out or out[-1] != s:
            out.append(s)
    return out

def category_from_url(url):
    low=url.lower()
    for s in SECTIONS:
        if s in low: return s
    return 'codex'

def img_name(src):
    ext=os.path.splitext(urlparse(src).path)[1].lower()
    if ext not in ['.png','.jpg','.jpeg','.webp','.gif']:
        ext='.png'
    return hashlib.md5(src.encode()).hexdigest()+ext

def extract(html, url):
    soup=BeautifulSoup(html, 'lxml')
    for x in soup(['script','style','noscript','svg']): x.decompose()
    title = ''
    h1 = soup.find('h1')
    if h1: title=' '.join(h1.get_text(' ', strip=True).split())
    if not title and soup.title:
        title=soup.title.get_text(' ', strip=True).split('/')[0].strip()
    main = soup.find('main') or soup.find(class_=re.compile('(codex|content|container|entry|detail)', re.I)) or soup.body or soup
    lines = clean_lines(main.get_text('\n', strip=True))
    # remove title duplication
    desc=[]
    for s in lines:
        if title and s == title: continue
        desc.append(s)
    img=''
    imgs=main.find_all('img') or soup.find_all('img')
    for im in imgs:
        src=im.get('src') or im.get('data-src') or ''
        if src and not any(x in src.lower() for x in ['logo','flag','icon-menu']):
            img=urljoin(url, src); break
    return {'title': title or (lines[0] if lines else url), 'category': category_from_url(url), 'url': url, 'image_url': img, 'lines': desc[:120]}

async def main():
    pages=set([START]); queue=[START]; entries=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context(locale='ru-RU')
        page=await context.new_page()
        await page.goto(START, wait_until='networkidle', timeout=60000)
        # accept cookies if present
        for txt in ['Принять','Accept','Aksepter','Согласен']:
            try:
                await page.get_by_text(txt, exact=False).click(timeout=2000)
                break
            except Exception: pass
        # discover links breadth-first
        max_pages=8000
        while queue and len(pages) < max_pages:
            url=queue.pop(0)
            try:
                await page.goto(url, wait_until='networkidle', timeout=60000)
                html=await page.content()
            except Exception as e:
                continue
            # collect codex links
            hrefs=await page.eval_on_selector_all('a[href]', "els => els.map(a => a.href)")
            for h in hrefs:
                if 'playorna.com/codex' in h:
                    nu=norm_url(h)
                    if nu not in pages:
                        pages.add(nu); queue.append(nu)
            # parse detail-ish pages with enough content
            data=extract(html, url)
            text=' '.join(data['lines'])
            if data['title'] and len(data['lines'])>2 and not any(b in text for b in BAD_COOKIE):
                # require some Cyrillic or lang=ru page title; avoid language index pages
                if re.search('[А-Яа-яЁё]', text + data['title']):
                    entries.append(data)
            if len(pages)%100==0:
                print('discovered', len(pages), 'entries', len(entries))
        await browser.close()
    # de-dup by title/category/url path
    seen=set(); clean=[]
    for e in entries:
        key=(e['category'], e['title'])
        if key in seen: continue
        seen.add(key); clean.append(e)
    # download images
    sess=requests.Session(); sess.headers.update({'User-Agent':'Mozilla/5.0'})
    for e in tqdm(clean, desc='images'):
        if e.get('image_url'):
            try:
                r=sess.get(e['image_url'], timeout=20)
                if r.ok and r.content:
                    name=img_name(e['image_url'])
                    path=os.path.join(IMG_DIR, name)
                    open(path,'wb').write(r.content)
                    e['image']='images/'+name
            except Exception: pass
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT,'orna_ru_database.json'),'w',encoding='utf-8') as f:
        json.dump({'generated':time.strftime('%Y-%m-%d %H:%M:%S'), 'count':len(clean), 'entries':clean}, f, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(os.path.join(OUT,'orna_ru_images.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(IMG_DIR):
            for fn in files:
                full=os.path.join(root,fn)
                z.write(full, os.path.relpath(full, OUT))
    with open(os.path.join(OUT,'report.txt'),'w',encoding='utf-8') as f:
        f.write(f'Russian entries: {len(clean)}\nDiscovered pages: {len(pages)}\n')

if __name__ == '__main__':
    asyncio.run(main())
