Nuvio Discover Composition Validation Update (v2.4)

Purpose
This update adds a conservative detector for embedded black bars and large uniform black backgrounds around otherwise landscape images. It is intended to prevent poster-like artwork, such as the current Top Rated/Godfather montage, from being selected as a hero backdrop.

Install
1. Extract this ZIP into the root of D:\GitHub\nuvio-artwork.
2. Allow the existing scripts\generate_discover_backdrops.py to be replaced.
3. Do not replace your workflow file; the current workflow already commits Discover\artwork-audit.json.
4. Commit and push the one changed Python file in GitHub Desktop.
5. Run the existing “Regenerate Nuvio Discover Artwork” GitHub Action.

What changes
- Keeps the current catalog IDs, manifest secrets, cover generation, logos, and audit report.
- Adds black-border/background validation to backdrop candidates.
- Records the rejection reason in Discover/artwork-audit.json.
- Does not upscale images.
- If a category has fewer than three acceptable backdrops after filtering, it will fail safely and leave that category's existing artwork in place.

Note
The detector looks for nearly uniform near-black bands along opposite edges and a brighter center. It is deliberately conservative; it cannot understand every artistic composition, so visual review is still useful.
