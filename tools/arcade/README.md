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
