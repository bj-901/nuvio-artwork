Nuvio Discover Artwork Audit Update

This update preserves the existing category catalog IDs, Discover folder structure,
cover design, Violet Platinum grading, and separate logo assets.

What changes:
- Rejects catalog items whose explicit media type is not the expected movie/series type.
- Rejects hero images smaller than 1920x1080.
- Rejects portrait/square promotional artwork as hero backdrops (minimum 1.50 aspect ratio).
- Logs the title, movie/series type, catalog ID, source host, original image dimensions,
  and acceptance/rejection reason for each processed catalog item.
- Records the selected hero title and source/output dimensions in Discover/artwork-audit.json.
- Adds the audit report to the GitHub Actions commit list.
- Never upscales a hero backdrop; 4K is only labelled native when the source itself is at least 3840x2160.

Install:
1. Close any editor currently changing these files.
2. Extract this ZIP into D:\GitHub\nuvio-artwork, allowing it to overwrite the two existing files.
3. Confirm these exact paths were replaced:
   scripts\generate_discover_backdrops.py
   .github\workflows\regenerate-discover-backdrops.yml
4. Review the changes in GitHub Desktop, commit, and push to main.
5. Run the existing GitHub Actions workflow manually.
6. After it completes, open Discover\artwork-audit.json in the repository to see the selected title and image-source details for each category.

Important:
- Keep your existing GitHub Actions secrets. This update does not require changing them.
- The audit stores source hostnames, not full image URLs or manifest credentials.
- Image metadata can tie a backdrop URL to a movie/series record and filter obvious bad aspect ratios,
  but it cannot visually prove that every image depicts the correct scene. The audit makes the
  source title visible so questionable matches can be caught and corrected.
