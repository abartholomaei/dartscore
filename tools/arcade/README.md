# Arcade artwork

The arcade graphics were generated once with ChatGPT (image generation) and are stored in
`frontend/public/arcade/`; the game runs offline. Everything was created in one chat so that the
style stays consistent: the first sprite sets the style, every further prompt asks for
"exactly the same style".

Processing: the PNGs were trimmed to their content, padded to a square and saved as WebP
(sprites 384 px with alpha, background 1024 px).

## Prompts (Monster hunt)

1. **blob** – "Create a game sprite for a darts arcade game: a cute, cheeky green slime
   monster. Style: colorful cartoon, thick dark outlines, soft cel shading, big expressive eyes,
   friendly and funny (not scary, kid-friendly), front view, centered, full body, nothing else in
   the picture, no text, no shadow on the ground. Transparent background (PNG), square format.
   I will ask for more monsters in exactly the same style afterwards."
2. **imp** – "…in exactly the same style (same outlines, shading, eye style, level of detail): a
   small cheeky purple imp monster with two little horns, a mischievous grin and tiny arms…"
3. **bat** – "…a funny little orange bat monster flying with spread wings, big eyes, tiny fangs,
   cheerful…"
4. **king** – "…a round, chubby light-blue monster king wearing a shiny golden crown with a red
   jewel, rosy cheeks, proud but funny smile. It is the rare, most valuable monster…"
5. **monster-night** (background, made later with sprite-gen `gen --provider codex` and the
   first meadow background as style reference) – "…in exactly the same style as the attached
   reference image… A spooky but kid-friendly haunted graveyard clearing at night, seen exactly
   from above (top-down), a perfectly round clearing filling the whole square image edge to edge,
   centered. Dark mossy ground and old cobblestones in the middle (calm and fairly plain, so a
   dartboard and monster sprites on top stay clearly visible), around the rim: small cartoon
   tombstones, crooked dead tree roots, a few pumpkins, mushrooms, little candles and glowing
   blue-green wisps, cold moonlight from the top left, darker towards the rim. Colors: deep night
   blue, teal and dark green with small warm orange accents. No monsters, no characters, no text,
   no dartboard lines, square format." (saved as 1024 px WebP)
6. **poof** (catch effect) – "…a cheerful magic 'poof' burst when a monster is caught - a round
   puffy white-and-light-green smoke cloud with little golden stars and sparkles flying outward…
   Transparent background (PNG), square."

All sprite prompts end with: "Front view, centered, full body, no text, no shadow, transparent
background (PNG), square."

## Animations (sprite-gen)

The idle and "caught" animations were made from the still sprites with
[sprite-gen](https://github.com/aldegad/sprite-gen) (Apache-2.0), using the Codex CLI logged in
with ChatGPT as the image provider (`codex login`, Codex ≥ 0.157):

```bash
sprite-gen prepare --out-dir runs/<kind> --character-id <kind> --base-image <kind>.png \
  --description "…" --style "colorful cartoon, thick dark outlines, soft cel shading" \
  --cell-size 256 --request sprite-gen/<kind>-request.json
sprite-gen gen-set --run-dir runs/<kind> --provider codex --concurrency 2   # ~1 min per row
sprite-gen extract --run-dir runs/<kind>
sprite-gen compose-atlas --run-dir runs/<kind>
```

Each state has 8 frames (idle 10 fps loop, hurt 14 fps once, ending in the defeated pose); with
4 frames the motion looked choppy. For the bat idle row the default extraction failed, it was
extracted with `sprite-gen extract --segmentation projection`; the king's hurt row was
regenerated once (`gen-set --states hurt --force`) because three frames came out empty.

The eight 256 px frames of each state (`frames/<state>/frame-N.png`) were joined into one
horizontal strip `frontend/public/arcade/monsters/<kind>-<state>.webp` (2048×256); the arcade
stage clips one cell and steps through the strip with CSS (`idle` loops, `hurt` plays once when
the monster is taken out). Bullet holes, cartridges, sparks, smoke, fireflies, fog and leaves are
drawn in code (SVG/CSS), not images. The request files with the per-state action prompts are in
`sprite-gen/`.
