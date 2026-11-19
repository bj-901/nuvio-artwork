# Nuvio Discover artwork update

This update changes the existing monthly workflow so it refreshes **Cover** and **Backdrop** assets from live catalog content. It also installs the separate Violet Platinum typography logos into the existing Logo folders.

## What changes
- `Cover/cover.webp`: generated monthly from current movie and series poster artwork. The image itself contains no category text.
- `Backdrop/backdrop.webp`: generated monthly at **3840 × 2160 (4K UHD)** from current title backdrop artwork. It requests original-resolution TMDB images when available, requires source images of at least 1280 × 720, prioritizes the largest source, uses lighter color overlays, and applies careful final sharpening.
- `Logo/logo.webp`: separate transparent Violet Platinum typography. These are static because category names do not change.

## Important
- Existing collection JSON and catalog IDs are not changed.
- Existing `coverImageUrl`, `titleLogoUrl`, and `heroBackdropUrl` URLs remain unchanged.
- The generator only writes a category's new cover/backdrop after it has enough valid source images. A 4K output file does not guarantee native 4K detail if a provider only supplies a 1080p source; the script now requests original TMDB assets where possible and avoids small thumbnails.
- The workflow is scheduled monthly and can also be run manually.
- GitHub Actions secrets remain the same: `AIO_METADATA_MANIFEST_URL_1`, `AIO_METADATA_MANIFEST_URL_2`, and `BINGECAT_MANIFEST_URL`.

## Install
1. Extract the ZIP into `D:\GitHub\nuvio-artwork`.
2. Open PowerShell in that repository folder.
3. Preview:
   `.\Install_Nuvio_Discover_Artwork_Update.ps1`
4. Apply:
   `.\Install_Nuvio_Discover_Artwork_Update.ps1 -Apply`
5. Review the changed files in GitHub Desktop, then commit and push.

The installer backs up the previous generator, workflow, and logo files under a timestamped `_Nuvio_Artwork_Update_Backup_...` folder.

## Expected GitHub changes
- `scripts/generate_discover_backdrops.py`
- `.github/workflows/regenerate-discover-backdrops.yml`
- five `Discover/<Category>/Logo/logo.webp` files; hero backdrops are output at 3840 × 2160

After the commit and push, run **Regenerate Nuvio Discover Artwork** from GitHub Actions. The workflow will publish the five new Cover and Backdrop images.
