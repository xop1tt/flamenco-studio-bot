# Asset credits and licenses

Every image in `public/assets/` is listed here with its source, author,
license and the changes made to it. CC BY 2.0 and CC BY-SA 4.0 both require
attribution, so the site footer links to this file's content on `/credits`.
Keep that in sync when adding or replacing assets.

## Drawn for this project

- Fan (`src/components/home/StageArt.tsx`, `FanArt`) — vector, drawn for this
  project; no third-party source. It replaces the removed photograph below:
  in the hero → directions transition the fan grows to cover the whole
  screen (~4× its hero size), where a raster image turns blurry.
- Castanets (`src/components/home/StageArt.tsx`, `CastanetsArt`) — vector,
  drawn for this project (restored from the earlier homepage scene).

## Removed

- `public/Flamenco_GettyImages-173193034.jpg.webp` — removed: the file name
  points to Getty Images and no license for it was found in the repository.
  It remains in git history.
- `backgrounds/stage-haze.webp` ([Incense smoke against a black sky](https://commons.wikimedia.org/wiki/File:Incense_smoke_against_a_black_sky_-_Flickr_-_Vanessa_Pike-Russell.jpg),
  Vanessa Pike-Russell, [CC BY 2.0](https://creativecommons.org/licenses/by/2.0))
  — removed at the user's request to drop the smoke/fire texture from the
  scene. The dark scenes now rely on `.stage-base`'s gradient and
  `.stage-spot`'s glow alone.
- The castanets, rose and petals (previously `src/components/home/StageArt.tsx`,
  drawn for this project, no third-party source) — removed from the homepage
  scene at the user's request to simplify it to the fan alone.
- `objects/fan.webp` ([Abanico.png](https://commons.wikimedia.org/wiki/File:Abanico.png),
  Kbemcap, [CC0](https://creativecommons.org/publicdomain/zero/1.0/)) —
  removed at the user's request to drop the fan from the homepage scene
  entirely. It was a drawn SVG before being replaced by this photograph;
  now there is no object on the scene at all, only the background layers
  (`.stage-base`, `.stage-spot`, `.stage-tone`).
- Hotlinked Unsplash photos (hero and site backdrop) — replaced, then the
  replacements themselves were removed (see below).
- Photos of a dancer and of dress/skirt fabric (`hero/dancer-body.webp`,
  `objects/skirt-train.webp`, `scenes/dancer-fan.webp`,
  `backgrounds/ruffle-blur.webp`, all CC BY 2.0, photographer Alon) — removed
  at the user's request to drop photos of women and dresses from the
  composition. The site backdrop that used the last of these is now a plain
  CSS gradient.
