# Asset credits and licenses

Every image in `public/assets/` is listed here with its source, author,
license and the changes made to it. CC BY 2.0 and CC BY-SA 4.0 both require
attribution, so the site footer links to this file's content on `/credits`.
Keep that in sync when adding or replacing assets.

## Photographs (Wikimedia Commons)

| File | Derived from | Author | License | Changes |
|---|---|---|---|---|
| `objects/fan.webp` | [Abanico.png](https://commons.wikimedia.org/wiki/File:Abanico.png) | Kbemcap | [CC0](https://creativecommons.org/publicdomain/zero/1.0/) | Background removed (geometric sector mask fit to the fan's pivot and span, not colour keying — the painted fabric made a plain colour-distance cutout unreliable); recoloured from the photo's own luminance into the site's red/wine/gold ramp (the original is bright green with pastel paint strokes) |
| `backgrounds/stage-haze.webp` | [Incense smoke against a black sky](https://commons.wikimedia.org/wiki/File:Incense_smoke_against_a_black_sky_-_Flickr_-_Vanessa_Pike-Russell.jpg) | Vanessa Pike-Russell | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0) | Converted to a warm red/amber colour ramp |

## Vector objects

The castanets, rose and petals (`src/components/home/StageArt.tsx`) were
drawn for this project. No third-party source. The fan was a drawn SVG too
until it was replaced by the photograph above, at the user's request for a
sourced asset.

## Removed

- `public/Flamenco_GettyImages-173193034.jpg.webp` — removed: the file name
  points to Getty Images and no license for it was found in the repository.
  It remains in git history.
- Hotlinked Unsplash photos (hero and site backdrop) — replaced, then the
  replacements themselves were removed (see below).
- Photos of a dancer and of dress/skirt fabric (`hero/dancer-body.webp`,
  `objects/skirt-train.webp`, `scenes/dancer-fan.webp`,
  `backgrounds/ruffle-blur.webp`, all CC BY 2.0, photographer Alon) — removed
  at the user's request to drop photos of women and dresses from the
  composition. The site backdrop that used the last of these is now a plain
  CSS gradient.
