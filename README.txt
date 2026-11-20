Nuvio Discover Native-Resolution Backdrop Update

Replace this file in your repository:
scripts/generate_discover_backdrops.py

The updated generator:
- Requires hero source images to be at least 1920x1080.
- Selects the highest-resolution available source per category.
- Never enlarges a hero backdrop; native 4K sources remain 3840x2160.
- Outputs 1440p/1080p at their actual source dimensions when those are the best available.
- Removes aggressive sharpening and reduces color/contrast processing to help avoid emphasizing grain.
- Logs source dimensions, whether the source is native 4K, and final output dimensions.

No workflow YAML, catalog IDs, GitHub secrets, folder paths, or Nuvio image URLs need to change.
