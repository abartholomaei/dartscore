# Arcade artwork

The arcade graphics were generated once with ChatGPT (image generation) and are stored in
`frontend/public/arcade/`; the game runs offline. Everything was created in one chat so that the
style stays consistent: the first sprite sets the style, every further prompt asks for
"exactly the same style".

Processing: the PNGs were trimmed to their content, padded to a square and saved as WebP
(sprites 512 px with alpha, background 1024 px).

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

## Prompts (Fruit samurai)

The game was called "Melon Samurai" when the artwork was made, hence the name in the prompts.

Generated in one Codex session (`codex exec`, image generation with the ChatGPT login) from a
single prompt that asks for the images in the same style. Shared part:

> Sprites for a darts arcade game called 'Melon Samurai' where fruit is sliced with a sword. All
> in exactly the same style: colorful cartoon, thick dark outlines, soft cel shading, juicy
> saturated colors, glossy highlights, friendly and fun (kid-friendly). Each FRUIT image shows a
> perfectly circular cross-section of the fruit seen exactly from above (top-down, flat, no
> perspective, no tilt), the circle is centered and fills the whole square image edge to edge,
> everything outside the circle is fully transparent (PNG with alpha). The rind forms a thin ring
> at the edge. No knife, no hands, no text, no shadow, no plate, square 1024x1024.

1. **watermelon** – regenerated separately (with the orange attached as style reference) because
   the first one looked artificial: "…must look NATURAL, like a real sliced watermelon, not
   artificial or symmetric: the black seeds are scattered IRREGULARLY in a loose, uneven band
   roughly two thirds of the way out, NOT in a perfect ring and NOT evenly spaced: different
   sizes, different angles, some clustered, some gaps, a few small pale white immature seeds in
   between; the red flesh has an organic juicy, slightly grainy/crystalline texture, redder in
   the middle and lighter pink towards the rind - no radial star pattern, no symmetry; a thin
   pale greenish-white layer, then the green rind with slightly irregular dark green stripes."
   Three variants were made, the most irregular one was kept.
2. **orange** – bright orange segments radiating from a pale center, white pith lines, peel ring.
3. **kiwi** – bright green flesh, creamy white core, a ring of small black seeds with fine rays,
   thin brown fuzzy skin.
4. **dragonfruit** – white flesh speckled with tiny black seeds, magenta pink skin ring.
5. **lime** – light green juicy segments radiating from the center, pale pith, green peel ring.
6. **dojo** (background, not transparent) – a perfectly round wooden cutting board seen exactly
   from above on a bamboo tatami mat, filling the square edge to edge; warm wood grain, a few cut
   marks, faint juice drops, darker towards the rim, calm. No fruit, knives, text or board lines.

7. **dojo-scene** (full-screen backdrop, 16:9, made later with the orange as style reference) –
   "…the inside of a traditional Japanese dojo at dusk, seen from the front. Wooden floor, shoji
   paper walls with warm light, a few glowing red paper lanterns at the top corners, bamboo and a
   blossoming cherry tree at the far left and right edges, a few pink petals, a katana rack on
   one side. The CENTER must be calm, dark and empty because a large round game board is placed
   there… No characters, no fruit, no text, no dartboard." Saved as 1600 px WebP.

Processing: the fruits were trimmed to their circle, scaled to 768 px, given a clean round alpha
edge (the game clips to the same circle) and saved as WebP in `frontend/public/arcade/fruit/`;
the background is 1024 px. The golden glow of the last round, slash, juice drops and the flying pieces are drawn in code.

## Animations (puppets, in code)

The monsters are animated like puppets: each kind is **one still** (`monsters/<kind>.webp`, the
ChatGPT sprite trimmed and padded to 512 px), deformed on the GPU every frame by
`frontend/src/components/MonsterPuppets.tsx` (WebGL, a 36×36 grid mesh): breathing (squash &
stretch around the feet), a jelly wave (blob), hops (imp), hovering (bat), swinging arms, ears,
tail, crown and cape, flapping wings, blinking eyelids (the lid is the monster's own skin taken
from just above the eye), and for hits a white flash with a squash, a knock-back tilt and
squeezed eyes; a monster that goes down jumps, flattens like a pancake and fades into the poof.
The rig per kind (eye ellipses, limb pivots and regions in texture space) is in `RIGS`. The
development page `/dev/puppets` shows all of them large with hit/kill buttons.

An earlier try generated 4 and then 8 frames per animation with
[sprite-gen](https://github.com/aldegad/sprite-gen) (image rows via Codex). It was dropped: every
frame is drawn anew by the image model, so size, position and details change from frame to frame
and the motion jitters, however many frames there are. The still stays identical and runs at the
display's frame rate.

Bullet holes, cartridges, sparks, smoke, fireflies, fog and leaves are drawn in code (SVG/CSS),
not images.
