"""
rot.rocks brainrot scraper - v3
Navigates every page, extracts correct name + rarity, downloads all images.
 
Install: pip install playwright requests
         python -m playwright install chromium
Run:     python scrape_brainrots.py
"""
 
import os
import re
import requests
from playwright.sync_api import sync_playwright
 
VALID_RARITIES = {
    "common", "uncommon", "epic", "legendary",
    "mythic", "brainrot god", "secret", "og"
}
 
def download_image(url, path, headers):
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"    [!] Download failed: {e}")
        return False
 
 
def extract_cards(page):
    """Pull every brainrot card from the current page view."""
    return page.evaluate("""
        () => {
            const RARITIES = new Set([
                "common","uncommon","epic","legendary",
                "mythic","brainrot god","secret","og"
            ]);
            const results = [];
 
            const candidates = document.querySelectorAll('a[href*="brainrot"], div[class*="rounded"]');
 
            for (const el of candidates) {
                const img = el.querySelector('img');
                if (!img) continue;
 
                const allText = [...el.querySelectorAll('*')]
                    .map(n => (n.childNodes.length === 1 && n.firstChild.nodeType === 3)
                        ? n.innerText.trim() : '')
                    .filter(t => t.length > 0 && t.length < 80);
 
                let name = '';
                let rarity = 'Unknown';
 
                for (const t of allText) {
                    const lower = t.toLowerCase();
                    if (RARITIES.has(lower)) {
                        rarity = t;
                    } else if (!name && t.length > 1 && !/^\\d/.test(t) && !t.includes('$') && !t.includes('R$')) {
                        name = t;
                    }
                }
 
                if (!name) continue;
 
                const imgSrc = img.src
                    || img.getAttribute('data-src')
                    || img.getAttribute('data-lazy-src')
                    || '';
 
                results.push({ name, rarity, imageUrl: imgSrc });
            }
 
            const seen = new Set();
            return results.filter(r => {
                if (seen.has(r.name)) return false;
                seen.add(r.name);
                return true;
            });
        }
    """)
 
 
def scrape_brainrots():
    print("=" * 50)
    print("  rot.rocks Brainrot Scraper v3")
    print("=" * 50)
 
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
 
    all_brainrots = {}
    api_data = []
 
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=headers["User-Agent"])
        page.set_default_timeout(30000)
 
        def handle_response(response):
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            try:
                data = response.json()
                items = data if isinstance(data, list) else None
                if items is None:
                    for v in (data.values() if isinstance(data, dict) else []):
                        if isinstance(v, list) and len(v) > 20:
                            items = v
                            break
                if items and len(items) > 20:
                    sample = items[:3]
                    if all(isinstance(x, dict) and "name" in x for x in sample):
                        api_data.append(items)
                        print(f"  [API] {response.url}  ->  {len(items)} items")
            except Exception:
                pass
 
        page.on("response", handle_response)
 
        print("\n[1] Loading rot.rocks/brainrots ...")
        page.goto("https://rot.rocks/brainrots", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
 
        if api_data:
            raw = max(api_data, key=len)
            print(f"[+] API returned {len(raw)} brainrots.")
            for item in raw:
                name = str(item.get("name", "")).strip()
                rarity = str(item.get("rarity", "Unknown")).strip()
                img = (item.get("imageUrl") or item.get("image_url")
                       or item.get("image") or "")
                if name:
                    all_brainrots[name] = {"rarity": rarity, "imageUrl": img}
        else:
            print("[2] No API found — scraping page by page ...\n")
 
            page_num = 1
            while True:
                print(f"  --- Page {page_num} ---")
 
                try:
                    page.wait_for_selector("img", timeout=10000)
                except Exception:
                    print("    [!] No images — stopping.")
                    break
 
                page.wait_for_timeout(1500)
 
                cards = extract_cards(page)
                new = 0
                for c in cards:
                    if c["name"] not in all_brainrots:
                        all_brainrots[c["name"]] = {
                            "rarity": c["rarity"],
                            "imageUrl": c["imageUrl"]
                        }
                        new += 1
 
                print(f"    {len(cards)} cards, {new} new  (total: {len(all_brainrots)})")
 
                went_next = False
 
                # Strategy A: aria-label or text "Next"
                for selector in [
                    'button[aria-label="Next page"]',
                    'button[aria-label="next"]',
                    'a[aria-label="Next page"]',
                    'button:has-text("Next")',
                    'a:has-text("Next")',
                ]:
                    try:
                        btn = page.query_selector(selector)
                        if btn and btn.is_visible() and btn.is_enabled():
                            btn.click()
                            page.wait_for_timeout(2000)
                            went_next = True
                            page_num += 1
                            break
                    except Exception:
                        pass
 
                # Strategy B: click next page number
                if not went_next:
                    try:
                        clicked = page.evaluate(f"""
                            () => {{
                                const btns = [...document.querySelectorAll('button, a')];
                                const next = String({page_num + 1});
                                const found = btns.find(b =>
                                    b.innerText.trim() === next && !b.disabled
                                );
                                if (found) {{ found.click(); return true; }}
                                return false;
                            }}
                        """)
                        if clicked:
                            page.wait_for_timeout(2000)
                            went_next = True
                            page_num += 1
                    except Exception:
                        pass
 
                # Strategy C: chevron ">" button
                if not went_next:
                    try:
                        found = page.evaluate("""
                            () => {
                                const btns = [...document.querySelectorAll('button, a')];
                                const next = btns.find(b => {
                                    const t = b.innerText.trim();
                                    return (t === '>' || t === '\u203a' || t === '\u2192' || t === '\u00bb')
                                        && !b.disabled
                                        && !b.hasAttribute('disabled');
                                });
                                if (next) { next.click(); return true; }
                                return false;
                            }
                        """)
                        if found:
                            page.wait_for_timeout(2000)
                            went_next = True
                            page_num += 1
                    except Exception:
                        pass
 
                if not went_next:
                    print(f"  [+] No more pages after page {page_num}.")
                    break
 
        browser.close()
 
    if not all_brainrots:
        print("\n[!] No brainrot data collected.")
        return
 
    brainrot_list = list(all_brainrots.items())
    print(f"\n[+] Total unique brainrots: {len(brainrot_list)}")
 
    img_folder = "brainrot_images"
    os.makedirs(img_folder, exist_ok=True)
 
    text_lines = []
    base_url = "https://rot.rocks"
 
    for i, (name, info) in enumerate(brainrot_list, 1):
        rarity = info["rarity"]
        text_lines.append(f"{name} - {rarity}")
 
        safe_name = re.sub(r'[<>:"/\\|?*]', '', name).strip()
        img_path = os.path.join(img_folder, f"{safe_name}.png")
 
        img_url = info["imageUrl"]
        if img_url and not img_url.startswith("http"):
            img_url = base_url + ("" if img_url.startswith("/") else "/") + img_url
 
        if img_url and not os.path.exists(img_path):
            ok = download_image(img_url, img_path, headers)
            print(f"  [{i:3d}/{len(brainrot_list)}] {'OK  ' if ok else 'FAIL'} {safe_name}.png")
        elif os.path.exists(img_path):
            print(f"  [{i:3d}/{len(brainrot_list)}] skip {safe_name}.png")
        else:
            print(f"  [{i:3d}/{len(brainrot_list)}] NO URL  {name}")
 
    with open("brainrots.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(text_lines))
 
    print("\n" + "=" * 50)
    print(f"  brainrots.txt  ->  {len(text_lines)} entries")
    print(f"  Images in brainrot_images/")
    print("\n  Sample:")
    for line in text_lines[:10]:
        print(f"    {line}")
    print("=" * 50)
 
 
if __name__ == "__main__":
    scrape_brainrots()