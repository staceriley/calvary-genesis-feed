#!/usr/bin/env python3
"""
Build a Podcast Addict-compatible RSS feed from the Calvary Castle Rock
Genesis archive.

Source archive:
https://calvarycr.com/archives/genesis-2/

The script:
1. Crawls the Genesis archive and its pagination.
2. Collects sermon/article links.
3. Opens each sermon page.
4. Finds a direct MP3/audio URL.
5. Creates feed.xml with podcast enclosures.

Designed to run locally or from GitHub Actions.
"""

from __future__ import annotations

import email.utils
import hashlib
import html
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ARCHIVE_URL = "https://calvarycr.com/archives/genesis-2/"
OUTPUT = Path("feed.xml")
CHANNEL_TITLE = "Calvary Castle Rock — Genesis Archive"
CHANNEL_LINK = ARCHIVE_URL
CHANNEL_DESCRIPTION = (
    "Unofficial personal RSS wrapper for the publicly available Genesis "
    "teaching archive from Calvary Castle Rock."
)
USER_AGENT = (
    "Mozilla/5.0 (compatible; CalvaryGenesisFeed/1.0; "
    "+https://github.com/)"
)
TIMEOUT = 30

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


@dataclass
class Episode:
    title: str
    page_url: str
    audio_url: str
    pubdate: datetime
    description: str = ""


def fetch(url: str) -> str:
    last_exc = None
    for attempt in range(4):
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_exc}")


def same_site(url: str) -> bool:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host in {"calvarycr.com", "calvarycastlerock.com"}


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def archive_pages(start_url: str) -> list[str]:
    """Follow archive pagination only."""
    seen = set()
    todo = [start_url]
    pages = []

    while todo:
        url = todo.pop(0)
        if url in seen:
            continue
        seen.add(url)

        try:
            body = fetch(url)
        except Exception as e:
            print(f"WARN archive page: {e}", file=sys.stderr)
            continue

        pages.append(url)
        soup = BeautifulSoup(body, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            text = clean_text(a.get_text(" ", strip=True)).lower()
            # WordPress pagination patterns, but stay within the Genesis archive.
            is_genesis_archive = "/archives/genesis-2/" in href
            looks_paged = (
                "/page/" in href
                or "paged=" in href
                or text in {"next", "older", "older posts", "next page", "›", "»"}
            )
            if is_genesis_archive and looks_paged and href not in seen:
                todo.append(href)

    return pages


def sermon_links_from_archive(page_url: str) -> set[str]:
    body = fetch(page_url)
    soup = BeautifulSoup(body, "html.parser")
    links = set()

    # Prefer links associated with article titles/read-more blocks.
    selectors = [
        "article h2 a[href]",
        "article h3 a[href]",
        ".fusion-post-title a[href]",
        ".entry-title a[href]",
        "a.more-link[href]",
        "a.fusion-read-more[href]",
    ]
    for sel in selectors:
        for a in soup.select(sel):
            href = urljoin(page_url, a.get("href", ""))
            if same_site(href) and href.rstrip("/") != page_url.rstrip("/"):
                links.add(href.split("#")[0])

    # Fallback: if theme markup changes, accept likely same-site post links,
    # while excluding navigation/assets/archive pages.
    if not links:
        for a in soup.find_all("a", href=True):
            href = urljoin(page_url, a["href"]).split("#")[0]
            path = urlparse(href).path.lower()
            if not same_site(href):
                continue
            if any(x in path for x in (
                "/wp-content/", "/wp-admin/", "/feed", "/archives/",
                "/author/", "/speaker/", "/category/", "/tag/"
            )):
                continue
            txt = clean_text(a.get_text(" ", strip=True)).lower()
            if txt and ("genesis" in txt or "read more" in txt):
                links.add(href)

    return links


def find_audio(soup: BeautifulSoup, page_url: str) -> str | None:
    candidates = []

    # Direct audio elements.
    for tag in soup.find_all(["audio", "source"]):
        src = tag.get("src")
        if src:
            candidates.append(urljoin(page_url, src))

    # Direct download links.
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        txt = clean_text(a.get_text(" ", strip=True)).lower()
        typ = (a.get("type") or "").lower()
        if (
            re.search(r"\.(mp3|m4a|aac|ogg)(?:$|\?)", href, re.I)
            or "audio/mpeg" in typ
            or txt in {"audio", "download audio", "download"}
        ):
            candidates.append(href)

    # Some pages include raw MP3 URLs in text/scripts.
    raw = str(soup)
    for m in re.findall(r'https?://[^"\'<>\s]+?\.mp3(?:\?[^"\'<>\s]*)?', raw, re.I):
        candidates.append(html.unescape(m))

    # Prefer actual audio extensions.
    for u in candidates:
        if re.search(r"\.(mp3|m4a|aac|ogg)(?:$|\?)", u, re.I):
            return u

    return None


def parse_date(soup: BeautifulSoup, page_text: str) -> datetime:
    # Structured datetime first.
    for tag in soup.find_all(["time", "meta"]):
        val = tag.get("datetime") or tag.get("content")
        if not val:
            continue
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass

    # Common Calvary page pattern: YYYY-MM-DD HH:MM:SS
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})(?:\s+\d{2}:\d{2}:\d{2})?", page_text)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Human-readable month format.
    m = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,\s+(20\d{2})\b",
        page_text,
        re.I,
    )
    if m:
        return datetime.strptime(
            f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y"
        ).replace(tzinfo=timezone.utc)

    return datetime(2000, 1, 1, tzinfo=timezone.utc)


def parse_episode(url: str) -> Episode | None:
    try:
        body = fetch(url)
    except Exception as e:
        print(f"WARN sermon page: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(body, "html.parser")
    audio = find_audio(soup, url)
    if not audio:
        return None

    h1 = soup.find("h1")
    title = clean_text(h1.get_text(" ", strip=True)) if h1 else ""
    if not title:
        title = clean_text((soup.title.string if soup.title and soup.title.string else "Genesis Sermon"))
        title = re.sub(r"\s+[–|-]\s+Calvary Castle Rock.*$", "", title, flags=re.I)

    # Avoid accidentally pulling unrelated audio if a fallback link slipped in.
    page_text = clean_text(soup.get_text(" ", strip=True))
    if "genesis" not in (title + " " + page_text[:1500]).lower():
        return None

    pubdate = parse_date(soup, page_text)

    desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        desc = clean_text(meta["content"])
    if not desc:
        desc = f"Genesis teaching from Calvary Castle Rock. Original page: {url}"

    return Episode(
        title=title,
        page_url=url,
        audio_url=audio,
        pubdate=pubdate,
        description=desc,
    )


def xml_escape(s: str) -> str:
    return html.escape(s or "", quote=True)


def build_feed(episodes: list[Episode]) -> str:
    # Most podcast apps expect newest first in RSS.
    episodes = sorted(episodes, key=lambda e: e.pubdate, reverse=True)
    now = email.utils.format_datetime(datetime.now(timezone.utc))

    items = []
    for ep in episodes:
        guid = hashlib.sha256(ep.audio_url.encode()).hexdigest()
        pub = email.utils.format_datetime(ep.pubdate)
        items.append(f"""\
    <item>
      <title>{xml_escape(ep.title)}</title>
      <link>{xml_escape(ep.page_url)}</link>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{pub}</pubDate>
      <description>{xml_escape(ep.description)}</description>
      <enclosure url="{xml_escape(ep.audio_url)}" length="0" type="audio/mpeg"/>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{xml_escape(CHANNEL_TITLE)}</title>
    <link>{xml_escape(CHANNEL_LINK)}</link>
    <description>{xml_escape(CHANNEL_DESCRIPTION)}</description>
    <language>en-us</language>
    <itunes:author>Calvary Castle Rock</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <atom:link href="feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
"""


def main():
    print(f"Crawling archive: {ARCHIVE_URL}")
    apages = archive_pages(ARCHIVE_URL)
    print(f"Archive pages found: {len(apages)}")

    sermon_links = set()
    for p in apages:
        try:
            sermon_links |= sermon_links_from_archive(p)
        except Exception as e:
            print(f"WARN link extraction from {p}: {e}", file=sys.stderr)

    print(f"Candidate sermon pages: {len(sermon_links)}")

    episodes = []
    for i, url in enumerate(sorted(sermon_links), 1):
        print(f"[{i}/{len(sermon_links)}] {url}")
        ep = parse_episode(url)
        if ep:
            print(f"  + {ep.title} -> {ep.audio_url}")
            episodes.append(ep)

    # Deduplicate by audio URL.
    unique = {}
    for ep in episodes:
        unique[ep.audio_url] = ep
    episodes = list(unique.values())

    if not episodes:
        raise SystemExit(
            "No Genesis audio episodes were found. The site markup may have changed "
            "or the server may be temporarily blocking requests."
        )

    OUTPUT.write_text(build_feed(episodes), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(episodes)} episodes.")


if __name__ == "__main__":
    main()
