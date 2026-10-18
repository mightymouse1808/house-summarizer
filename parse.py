#!/usr/bin/env python3
"""Lee listados de Zillow, Redfin, Realtor.com y Move with Momentum y actualiza data.json.

Uso:
  python parse.py URL [URL ...]        agrega casas nuevas
  python parse.py --refresh            re-lee las casas de data.json que tengan datos vacíos
  python parse.py --refresh --force    re-lee todo y sobrescribe los campos
  python parse.py URL --browser        usa un navegador real (necesita playwright)
  python parse.py URL --html pagina.html   usa una página que guardaste a mano (Ctrl+S)
Los campos que tú ya llenaste a mano NO se sobrescriben (salvo con --force).
"""
import argparse, json, re, sys, time, uuid
from pathlib import Path
from urllib.parse import urlparse, unquote
import requests
from bs4 import BeautifulSoup

DATA = Path(__file__).with_name("data.json")
FIELDS = ["img", "price", "beds", "baths", "floors", "hoa"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

class Blocked(Exception):
    pass

def norm(u):
    return u.strip().split("?")[0].rstrip("/")

def addr_from_url(u):
    p = urlparse(u); path = unquote(p.path); host = p.netloc
    try:
        if "zillow" in host:
            s = path.split("/")[2].replace("-", " ")
            return re.sub(r" ([A-Z]{2}) (\d{5})$", r", \1 \2", s)
        if "redfin" in host:
            _, st, city, a = path.split("/")[:4]
            z = re.search(r"-(\d{5})$", a)
            a = re.sub(r"-\d{5}$", "", a).replace("-", " ")
            return f"{a}, {city.replace('-', ' ')}, {st}" + (f" {z.group(1)}" if z else "")
        if "realtor" in host:
            s = path.rstrip("/").split("/")[-1].split("_")
            return f"{s[0].replace('-', ' ')}, {s[1]}, {s[2]} {s[3]}"
        if "movewithmomentum" in host:
            return path.rstrip("/").split("/")[-1].replace("-", " ").title() + ", GA"
    except Exception:
        pass
    return u

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    if r.status_code in (403, 429) or re.search(r"px-captcha|Access Denied|are you a robot", r.text[:8000], re.I):
        raise Blocked(f"bloqueado (HTTP {r.status_code})")
    r.raise_for_status()
    return r.text

def fetch_browser(url):
    from playwright.sync_api import sync_playwright
    bad = re.compile(r"px-captcha|Access Denied|press\s*(?:&|and)\s*hold|are you a robot", re.I)
    html, warned = "", False
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False)  # ventana visible: los portales detectan menos
        pg = b.new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        for _ in range(45):  # espera hasta ~90 s por si hay que resolver un captcha
            pg.wait_for_timeout(2000)
            html = pg.content()
            if len(html) > 20000 and not bad.search(html[:20000]):
                break
            if not warned:
                print("   ! El portal pide verificacion. Resuelvela en la ventana del navegador (tienes ~90 segundos)...")
                warned = True
        if not bad.search(html[:20000]):
            for _ in range(10):  # baja la pagina para que carguen las secciones de abajo (pisos, HOA)
                pg.mouse.wheel(0, 2500)
                pg.wait_for_timeout(700)
            html = pg.content()
        b.close()
    if bad.search(html[:20000]):
        raise Blocked("no se paso la verificacion a tiempo")
    return html

def meta(soup, *names):
    for n in names:
        t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if t and t.get("content"):
            return t["content"].strip()
    return ""

def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)

def jsonld(soup):
    out = {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        for d in walk(data):
            if d.get("numberOfBedrooms") and "beds" not in out:
                out["beds"] = str(d["numberOfBedrooms"])
            b = d.get("numberOfBathroomsTotal") or d.get("numberOfFullBathrooms")
            if b and "baths" not in out:
                out["baths"] = str(b)
            if isinstance(d.get("offers"), dict) and d["offers"].get("price") and "price" not in out:
                out["price"] = str(d["offers"]["price"])
            if d.get("numberOfFloors") and "floors" not in out:
                out["floors"] = str(d["numberOfFloors"])
    return out

def money(v):
    d = re.sub(r"\D", "", str(v).split(".")[0])
    return f"${int(d):,}" if d else ""

def floors_of(text):
    m = re.search(r"Stories:?\s*(\d)", text)
    if m: return m.group(1)
    m = re.search(r"Levels:?\s*(One|Two|Three)\b", text, re.I)
    if m: return {"one": "1", "two": "2", "three": "3"}[m.group(1).lower()]
    m = re.search(r"\b(\d)[- ]stor(?:y|ies)\b", text, re.I)
    return m.group(1) if m else ""

def hoa_of(text):
    if re.search(r"Has HOA:\s*Yes|HOA fee:\s*\$\s*[1-9]|HOA (?:dues|fee)s?:?\s*\$\s*[1-9]", text, re.I): return "si"
    if re.search(r"Has HOA:\s*No|\bno HOA\b|No homeowners association|HOA\s*None reported", text, re.I): return "no"
    return ""

def parse(html, url):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    title = meta(soup, "og:title", "twitter:title") or (soup.title.string if soup.title and soup.title.string else "")
    blob = " ".join([title] + [meta(soup, n) for n in ("og:description", "description", "twitter:description")])
    ld = jsonld(soup)
    r = {}
    r["img"] = meta(soup, "og:image", "twitter:image", "twitter:image:src")
    pr = meta(soup, "twitter:text:price") or (re.search(r"\$\s?[\d,]{5,}", blob) or [""])[0] or ld.get("price", "")
    r["price"] = money(pr)
    b = meta(soup, "zillow_fb:beds", "twitter:text:beds") or (re.search(r"(\d+)\s*(?:beds?|bd|bedrooms?)\b", blob, re.I) or [None, ""])[1] or ld.get("beds", "")
    ba = meta(soup, "zillow_fb:baths", "twitter:text:baths") or (re.search(r"([\d.]+)\s*(?:baths?|ba|bathrooms?)\b", blob, re.I) or [None, ""])[1] or ld.get("baths", "")
    r["beds"], r["baths"] = str(b), str(ba)
    r["floors"] = floors_of(text) or ld.get("floors", "")
    r["hoa"] = hoa_of(text)
    addr = re.split(r"\s[|\-]\s", title)[0] if re.match(r"^\d+ .*[A-Z]{2} \d{5}", title) else ""
    return {k: v for k, v in r.items() if v}, addr

def load():
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []

def save(houses):
    DATA.write_text(json.dumps(houses, ensure_ascii=False, indent=1), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--html")
    a = ap.parse_args()
    houses = load()
    by_url = {norm(h["url"]): h for h in houses}
    targets = [(u, by_url.get(norm(u))) for u in a.urls]
    if a.refresh:
        targets += [(h["url"], h) for h in houses if a.force or any(not h.get(f) for f in FIELDS)]
    if not targets:
        ap.print_help(); return
    fails = []
    for i, (url, h) in enumerate(targets):
        print(f"[{i+1}/{len(targets)}] {url}")
        try:
            if a.html:
                html = Path(a.html).read_text(encoding="utf-8", errors="ignore")
            else:
                html = fetch_browser(url) if a.browser else fetch(url)
            data, addr = parse(html, url)
        except Blocked as e:
            print(f"   ✗ {e}"); fails.append(url); continue
        except Exception as e:
            print(f"   ✗ error: {e}"); fails.append(url); continue
        if h is None:
            h = {"id": uuid.uuid4().hex[:8], "url": norm(url) if "?" in url else url.strip(), "addr": addr or addr_from_url(url),
                 "img": "", "price": "", "beds": "", "baths": "", "floors": "", "hoa": "", "notes": ""}
            houses.append(h)
        for k, v in data.items():
            if a.force or not h.get(k):
                h[k] = v
        missing = [f for f in FIELDS if not h.get(f)]
        print(f"   ✓ {h['addr']} | {h.get('price') or '?'} | {h.get('beds') or '?'}hab {h.get('baths') or '?'}ba"
              + (f" | falta: {', '.join(missing)}" if missing else ""))
        save(houses)
        time.sleep(2)
    if fails:
        print("\nNo se pudieron leer:\n  " + "\n  ".join(fails))
        print("Prueba con --browser, o guarda la página (Ctrl+S) y usa --html archivo.html")

if __name__ == "__main__":
    main()
