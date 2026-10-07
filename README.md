# Calvary Castle Rock — Genesis podcast feed

This tiny project converts the public Genesis teaching archive at:

https://calvarycr.com/archives/genesis-2/

into a normal RSS podcast feed that apps such as Podcast Addict can subscribe to.

## Fast setup with GitHub Pages

1. Create a new **public GitHub repository**. A name such as:
   `calvary-genesis-feed`
   works well.

2. Upload all files from this folder to the repository, preserving the
   `.github/workflows/update-feed.yml` path.

3. In GitHub, open **Actions** and run:
   **Update Genesis podcast feed → Run workflow**

4. After the action completes, confirm that a `feed.xml` file appeared in the
   root of the repository.

5. Open **Settings → Pages**.
   Under **Build and deployment**, choose:
   - Source: **Deploy from a branch**
   - Branch: **main**
   - Folder: **/(root)**
   Save.

6. Your podcast URL will normally be:

   `https://YOUR-GITHUB-USERNAME.github.io/calvary-genesis-feed/feed.xml`

   If you chose a different repository name, substitute that name.

## Add it to Podcast Addict

In Podcast Addict:

1. Tap **+**
2. Choose **RSS feed**
3. Paste the GitHub Pages `feed.xml` URL
4. Subscribe

The podcast should appear as:

**Calvary Castle Rock — Genesis Archive**

## Updating

The GitHub Action is scheduled to rebuild the feed once a week. You can also
open **Actions → Update Genesis podcast feed → Run workflow** at any time.

Because the Genesis series is an archive, it generally will not need frequent
updates.

## Local test (optional)

With Python installed:

```bash
pip install -r requirements.txt
python generate_feed.py
```

That creates `feed.xml` in the current folder.

## Notes

- This project does **not** copy or re-host sermon audio. The RSS file only
  points Podcast Addict to Calvary Castle Rock's own public audio files.
- This is an unofficial personal convenience feed.
- If Calvary changes its website structure, `generate_feed.py` may need a small
  update.
