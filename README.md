# Calvary Castle Rock — Genesis podcast feed (v2)

This version handles Calvary's **lazy-loaded/infinite-scroll Genesis archive**.

It opens the page in a real Chromium browser, scrolls until the page stops
loading additional sermons, extracts the individual sermon pages, finds their
audio files, and writes a Podcast Addict-compatible `feed.xml`.

The expected-series sanity-check currently contains **75 titles**
from January 10, 2021 through January 29, 2023.

## Install in your existing GitHub repository

Replace the previous files with these:
- `generate_feed.py`
- `requirements.txt`
- `expected_titles.json`
- `.github/workflows/update-feed.yml`

Then commit/push.

## Run it

GitHub:
**Actions → Update Genesis podcast feed → Run workflow**

Watch the run log. Near the end you should see:
- `Audio episodes found: ...`
- `Wrote feed.xml with ... episodes.`

The script deliberately refuses to overwrite the feed if it discovers fewer
than 60 audio episodes, protecting you from a temporary site-loading failure.

## Podcast Addict URL for staceriley

Assuming the repository is named `calvary-genesis-feed` and GitHub Pages is
enabled from the `main` branch root:

https://staceriley.github.io/calvary-genesis-feed/feed.xml

In Podcast Addict:
**+ → RSS feed → paste URL → Subscribe**

## Copyright / hosting

This feed does not re-host Calvary's sermon audio. Each RSS enclosure points
to Calvary Castle Rock's own publicly hosted audio file.
