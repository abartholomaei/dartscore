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
