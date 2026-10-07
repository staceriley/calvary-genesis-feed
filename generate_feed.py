#!/usr/bin/env python3
from __future__ import annotations
import asyncio, email.utils, hashlib, html, json, re, sys, time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ARCHIVE_URL = "https://calvarycr.com/archives/genesis-2/"
OUTPUT = Path("feed.xml")
EXPECTED = json.loads(Path("expected_titles.json").read_text(encoding="utf-8"))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
session = requests.Session()
session.headers.update({"User-Agent": UA})

@dataclass
class Episode:
    title: str
    page_url: str
    audio_url: str
    pubdate: datetime
    description: str = ""

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

async def load_all_archive_links():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(user_agent=UA, viewport={"width": 1400, "height": 1200})
        await page.goto(ARCHIVE_URL, wait_until="domcontentloaded", timeout=90000)

        stable_rounds = 0
        last_height = 0
        last_count = 0

        for _ in range(80):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)

            height = await page.evaluate("document.body.scrollHeight")
            links = await page.locator("a[href]").evaluate_all(
                """els => els.map(a => ({
                    href: a.href,
                    text: (a.innerText || '').trim()
                }))"""
            )
            candidates = [
                x for x in links
                if x["href"].startswith("https://calvarycr.com/")
                and "/archives/" not in x["href"]
                and "/wp-content/" not in x["href"]
                and (
                    "read more" in x["text"].lower()
                    or "genesis" in x["text"].lower()
                    or "dispensations" in x["text"].lower()
                    or "jacob i have loved" in x["text"].lower()
                )
            ]
            count = len({x["href"].split("#")[0] for x in candidates})

            if height == last_height and count == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0

            last_height, last_count = height, count
            if stable_rounds >= 4:
                break

        # Extract links from article/card title and Read More anchors.
        links = await page.locator("a[href]").evaluate_all(
            """els => els.map(a => ({
                href: a.href,
                text: (a.innerText || '').trim(),
                parent: (a.parentElement?.innerText || '').trim()
            }))"""
        )
        await browser.close()

    out = {}
    for x in links:
        href = x["href"].split("#")[0]
        if not href.startswith("https://calvarycr.com/"):
            continue
        if any(bad in href for bad in ["/archives/", "/wp-content/", "/category/", "/tag/", "/author/"]):
            continue
        hay = (x["text"] + " " + x["parent"]).lower()
        if (
            "genesis" in hay
            or "dispensations" in hay
            or "jacob i have loved" in hay
            or x["text"].lower() == "read more"
        ):
            out[href] = True
    return sorted(out)

def fetch(url):
    r = session.get(url, timeout=40)
    r.raise_for_status()
    return r.text

def find_audio(soup, page_url):
    candidates = []
    for tag in soup.find_all(["audio", "source"]):
        src = tag.get("src")
        if src:
            candidates.append(urljoin(page_url, src))
    for a in soup.find_all("a", href=True):
        u = urljoin(page_url, a["href"])
        if re.search(r"\.(mp3|m4a|aac|ogg)(?:$|\?)", u, re.I):
            candidates.append(u)
    raw = str(soup)
    candidates += re.findall(r'https?://[^"\'<>\s]+?\.mp3(?:\?[^"\'<>\s]*)?', raw, re.I)
    for u in candidates:
        if re.search(r"\.(mp3|m4a|aac|ogg)(?:$|\?)", u, re.I):
            return html.unescape(u)
    return None

def parse_date(soup, text):
    for tag in soup.find_all(["time","meta"]):
        val = tag.get("datetime") or tag.get("content")
        if not val:
            continue
        try:
            dt = datetime.fromisoformat(val.replace("Z","+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,\s+(20\d{2})\b", text, re.I)
    if m:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").replace(tzinfo=timezone.utc)
    return datetime(2000,1,1,tzinfo=timezone.utc)

def parse_episode(url):
    try:
        body = fetch(url)
    except Exception as e:
        print(f"WARN fetch {url}: {e}", file=sys.stderr)
        return None
    soup = BeautifulSoup(body, "html.parser")
    audio = find_audio(soup, url)
    if not audio:
        return None
    h1 = soup.find("h1")
    title = clean(h1.get_text(" ", strip=True)) if h1 else clean(soup.title.get_text() if soup.title else "")
    title = re.sub(r"\s+[|–-]\s+Calvary Castle Rock.*$", "", title, flags=re.I)
    text = clean(soup.get_text(" ", strip=True))
    if not any(k in (title+" "+text[:2500]).lower() for k in ["genesis","dispensations","jacob i have loved"]):
        return None
    date = parse_date(soup, text)
    return Episode(title, url, audio, date, f"Teaching from Calvary Castle Rock. Original page: {url}")

def esc(s): return html.escape(s or "", quote=True)

def build_feed(episodes):
    episodes = sorted(episodes, key=lambda e: e.pubdate, reverse=True)
    items=[]
    for ep in episodes:
        guid=hashlib.sha256(ep.audio_url.encode()).hexdigest()
        items.append(f"""    <item>
      <title>{esc(ep.title)}</title>
      <link>{esc(ep.page_url)}</link>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{email.utils.format_datetime(ep.pubdate)}</pubDate>
      <description>{esc(ep.description)}</description>
      <enclosure url="{esc(ep.audio_url)}" length="0" type="audio/mpeg"/>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Calvary Castle Rock — Genesis Archive</title>
    <link>{ARCHIVE_URL}</link>
    <description>Unofficial RSS wrapper for the public Calvary Castle Rock Genesis teaching archive.</description>
    <language>en-us</language>

    <image>
      <url>https://calvarycr.com/wp-content/uploads/2021/01/Genesis-01-700x394.jpg</url>
      <title>Calvary Castle Rock — Genesis Archive</title>
      <link>{ARCHIVE_URL}</link>
    </image>

    <itunes:image href="https://calvarycr.com/wp-content/uploads/2021/01/Genesis-01-700x394.jpg"/>
    <itunes:author>Pastor Dave Love / Calvary Castle Rock</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <atom:link href="feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
"""

async def main():
    print("Opening Genesis archive in Chromium and scrolling until all lazy-loaded entries appear...")
    links = await load_all_archive_links()
    print(f"Candidate sermon links found: {len(links)}")
    episodes=[]
    for i,u in enumerate(links,1):
        print(f"[{i}/{len(links)}] {u}")
        ep=parse_episode(u)
        if ep:
            episodes.append(ep)

    # Dedupe audio.
    episodes=list({e.audio_url:e for e in episodes}.values())
    found_titles={clean(e.title).lower() for e in episodes}
    missing=[t for t in EXPECTED if clean(t).lower() not in found_titles]

    print(f"Audio episodes found: {len(episodes)}")
    if missing:
        print("WARNING: expected Genesis-series titles not matched:")
        for t in missing:
            print("  -", t)
    if len(episodes) < 60:
        raise SystemExit("Too few episodes were discovered; refusing to overwrite feed.xml.")

    OUTPUT.write_text(build_feed(episodes), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(episodes)} episodes.")

if __name__ == "__main__":
    asyncio.run(main())
