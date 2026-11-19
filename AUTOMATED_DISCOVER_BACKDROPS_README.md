# Nuvio Discover — Automated Violet Platinum Backdrops

This workflow regenerates the five existing Discover `heroBackdropUrl` images from the live catalogs in the user's Nuvio profile.

## Categories and current catalog IDs

- Trending: `mdblist.206584` (movie), `mdblist.207259` (series)
- Popular: `mdblist.221823` (movie), `mdblist.221824` (series)
- Latest Releases: `mdblist.207268` (movie), `mdblist.208593` (series)
- Top Rated: `mdblist.207276` (movie), `mdblist.207277` (series)
- For You: `aicat_list_203374` (movie), `aicat_list_203375` (series), `aicat_list_203376` (movie), `aicat_list_203377` (series)

## Important setup

Add these three repository Actions secrets:

1. `AIO_METADATA_MANIFEST_URL_1`
2. `AIO_METADATA_MANIFEST_URL_2`
3. `BINGECAT_MANIFEST_URL`

Use the two AIO Metadata manifest URLs from the user's installed add-ons screen. The Bingecat manifest URL is:

`https://bingecat.com/stremio/1283f651-7cc0-4d14-aa73-9c83f7866ae7/nuvio/manifest.json`

Do not put personalized manifest URLs in committed source files. They are stored as repository secrets.

## Output paths

The generator updates only these existing files:

- `Discover/Trending/Backdrop/backdrop.webp`
- `Discover/Popular/Backdrop/backdrop.webp`
- `Discover/Latest Releases/Backdrop/backdrop.webp`
- `Discover/Top Rated/Backdrop/backdrop.webp`
- `Discover/For You/Backdrop/backdrop.webp`

The URLs in the Nuvio profile remain unchanged. Cover and Logo folders are not touched.

## Run

- GitHub Actions runs automatically on the first day of each month.
- You can also run it manually from the Actions tab using **Run workflow**.

The script uses the standard Stremio add-on manifest/catalog/meta endpoints. It uses metadata `background` images and composes them into a dark Violet Platinum collage. If a category does not return at least three usable backgrounds, its existing image is left untouched and the workflow fails visibly rather than publishing a blank or broken backdrop.

## Local test

```powershell
py -3 -m pip install requests Pillow
$env:AIO_METADATA_MANIFEST_URL_1="YOUR_FIRST_AIO_METADATA_MANIFEST_URL"
$env:AIO_METADATA_MANIFEST_URL_2="YOUR_SECOND_AIO_METADATA_MANIFEST_URL"
$env:BINGECAT_MANIFEST_URL="YOUR_BINGECAT_MANIFEST_URL"
py -3 .\scripts\generate_discover_backdrops.py
```

Do not commit local `.env` files or manifest URLs.
