Nuvio randomized Discover artwork generator update

This update replaces only:
  scripts/generate_discover_backdrops.py

It keeps the existing category IDs, output paths, 4K backdrop size (3840x2160),
cover size (1536x864), workflow file, secrets, and separate white serif logos.

Install:
1. Extract this ZIP into D:\GitHub\nuvio-artwork, preserving folder paths.
2. Allow it to replace scripts\generate_discover_backdrops.py.
3. In GitHub Desktop, review the one changed file.
4. Commit and push the update.
5. Run Actions > Regenerate Nuvio Discover Artwork > Run workflow.

Each run shuffles catalog order and item selection, chooses among the highest-
resolution available backdrop scenes, and varies the cover layout. Source images
are still required to meet the existing minimum backdrop dimensions. Randomized
selection cannot guarantee a different result if the catalog supplies too few
unique usable images.
