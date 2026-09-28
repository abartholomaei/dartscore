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
5. **monster-meadow** (background) – "…a perfectly round magical forest clearing seen exactly
   from above (top-down), filling the whole square image edge to edge, centered. Soft grass with
   small flowers, mushrooms and pebbles, a few tiny glowing fireflies, slightly darker towards the
   rim, calm and not too busy so that monster sprites on top stay clearly visible. Muted greens
   with a hint of teal, evening mood… No monsters, no characters, no text, no dartboard lines."
6. **poof** (catch effect) – "…a cheerful magic 'poof' burst when a monster is caught - a round
   puffy white-and-light-green smoke cloud with little golden stars and sparkles flying outward…
   Transparent background (PNG), square."

All sprite prompts end with: "Front view, centered, full body, no text, no shadow, transparent
background (PNG), square."

## Prompts (Melon samurai)

Generated in one Codex session (`codex exec`, image generation with the ChatGPT login) from a
single prompt that asks for the images in the same style. Shared part:

> Sprites for a darts arcade game called 'Melon Samurai' where fruit is sliced with a sword. All
> in exactly the same style: colorful cartoon, thick dark outlines, soft cel shading, juicy
> saturated colors, glossy highlights, friendly and fun (kid-friendly). Each FRUIT image shows a
> perfectly circular cross-section of the fruit seen exactly from above (top-down, flat, no
> perspective, no tilt), the circle is centered and fills the whole square image edge to edge,
> everything outside the circle is fully transparent (PNG with alpha). The rind forms a thin ring
> at the edge. No knife, no hands, no text, no shadow, no plate, square 1024x1024.

1. **watermelon** – bright red juicy flesh with black seeds arranged in a ring, thin white layer
   and dark green striped rind.
2. **orange** – bright orange segments radiating from a pale center, white pith lines, peel ring.
3. **kiwi** – bright green flesh, creamy white core, a ring of small black seeds with fine rays,
   thin brown fuzzy skin.
4. **dragonfruit** – white flesh speckled with tiny black seeds, magenta pink skin ring.
5. **lime** – light green juicy segments radiating from the center, pale pith, green peel ring.
6. **dojo** (background, not transparent) – a perfectly round wooden cutting board seen exactly
   from above on a bamboo tatami mat, filling the square edge to edge; warm wood grain, a few cut
   marks, faint juice drops, darker towards the rim, calm. No fruit, knives, text or board lines.

Processing: the fruits were trimmed to their circle, scaled to 768 px, given a clean round alpha
edge (the game clips to the same circle) and saved as WebP in `frontend/public/arcade/melon/`;
the background is 1024 px. The golden glow of the last round, slash, juice drops and the flying pieces are drawn in code.

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

The four 256 px frames of each state (`frames/<state>/frame-N.png`) were joined into one
horizontal strip `frontend/public/arcade/monsters/<kind>-<state>.webp` (1024×256); the arcade
stage clips one cell and steps through the strip with CSS (`idle` loops, `hurt` plays once when
the monster is caught). The request files with the per-state action prompts are in
`sprite-gen/`.
