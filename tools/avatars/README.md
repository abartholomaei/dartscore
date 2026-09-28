# Gallery profile pictures

The gallery pictures in `frontend/public/avatars/` were generated once with ChatGPT image
generation through the Codex CLI (`codex exec`, logged in with ChatGPT) and are shipped with the
web app; nothing is generated at runtime. Processing: 1024 px PNG → 384 px WebP (`cwebp -q 82`).

## Style reference (fox)

"Profile picture avatar for a darts app: a charming fox character, head and shoulders portrait,
looking at the viewer with a friendly confident smile. Style: polished 3D cartoon render like a
modern animated movie, soft studio lighting, subtle rim light, rich warm colors, glossy expressive
eyes, fine fur detail. Background: smooth radial gradient in deep teal, filling the entire square
edge to edge. The character is centered and fits comfortably inside a circle (it will be cropped
round). No text, no frame, no border, square 1024x1024."

## Further pictures

Each with `fox.png` attached as style reference (`codex exec -i fox.png -- "…"`):

"…match its style exactly… Profile picture avatar for a darts app: <subject>. Head and shoulders
portrait, centered, with a little headroom so the head fits comfortably inside a circle. Wearing a
sporty darts jersey in colors that suit the character, holding three darts. Background: smooth
radial gradient in <background>, filling the entire square edge to edge. No text, no logos, no
frame, no border."

| name | subject | background |
|---|---|---|
| owl | a wise but playful owl with big round amber eyes and soft feathers | deep indigo blue |
| bear | a big cuddly brown bear with a warm grin | forest green |
| cat | a sleek cool cat with striking green eyes | warm magenta purple |
| dog | a happy golden retriever dog with floppy ears | sky blue |
| panda | a cheerful giant panda | fresh lime green |
| frog | a funny green tree frog with big bulging eyes | warm sunset orange |
| penguin | a smart little emperor penguin | icy cyan blue |
| tiger | a fierce but friendly tiger | dark royal purple |
| lion | a proud but friendly young lion with a big fluffy golden mane | warm golden amber |
| monkey | a cheeky monkey with a big mischievous grin | jungle teal green |
| unicorn | a magical white unicorn with a shimmering pastel rainbow mane and golden horn | pastel lavender |
| robot | a friendly retro-futuristic robot with glowing blue eyes and polished metal | dark steel blue |
| alien | a cute friendly green alien with big black glossy eyes and little antennae | deep space violet with tiny stars |
| ghost | a cute friendly little white ghost, slightly translucent, glowing softly | midnight blue |
| pirate | a charismatic pirate parrot with an eye patch and a small tricorn hat | deep ocean blue |

A rabbit was planned instead of the lion, but every rabbit prompt was rejected by the image
safety filter; migration 0010 moves profiles that had picked the old rabbit picture to the lion.
