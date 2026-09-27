"""Generates the stadium caller clips once with ElevenLabs; dartscore then plays them offline.

Usage (from the repository root):
    python tools/caller/generate.py --key-file ~/.env/elevenlabs-key [--only hl_180 ...] [--force]

Clips land in frontend/public/caller/en/ together with manifest.json. Existing clips are kept
unless --force or --only is given, so a rerun only fills gaps (and costs no characters).
Only the Python standard library is needed.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # "George" (ElevenLabs premade voice)
MODEL = "eleven_v3"
FORMAT = "mp3_44100_64"
SETTINGS = {"stability": 0.0, "similarity_boost": 0.8, "style": 1.0, "use_speaker_boost": True}
OUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "caller" / "en"

# three-dart totals that cannot be scored
IMPOSSIBLE = {163, 166, 169, 172, 173, 175, 176, 178, 179}

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen \
fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def words(n: int) -> str:
    """British English: 145 -> 'one hundred and forty-five'."""
    if n < 20:
        return ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return TENS[tens] + (f"-{ONES[ones]}" if ones else "")
    hundreds, rest = divmod(n, 100)
    return f"{ONES[hundreds]} hundred" + (f" and {words(rest)}" if rest else "")


def clips() -> dict[str, str]:
    """clip key -> text sent to ElevenLabs (audio tags steer the delivery)."""
    result = {
        "no_score": "[disappointed] No score.",
        "you_require": "[confident] You require...",
        "game_shot": "[excited] Game shot!",
        "game_shot_match": "[excited] [shouting] Game shot, and the match!",
    }
    for n in range(1, 181):
        # calm but strong: normal visits and "you require ..."
        result[f"num_{n}"] = f"[confident] {words(n).capitalize()}."
    for n in range(140, 181):
        if n in IMPOSSIBLE:
            continue
        text = words(n).upper() if n == 180 else words(n).capitalize()
        tags = "[excited] [shouting]" if n == 180 else "[excited]"
        result[f"hl_{n}"] = f"{tags} {text}!"
    return result


def generate(key: str, text: str) -> bytes:
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}?output_format={FORMAT}",
        data=json.dumps({"text": text, "model_id": MODEL, "voice_settings": SETTINGS}).encode(),
        headers={"xi-api-key": key, "content-type": "application/json", "accept": "audio/mpeg"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:  # rate limited: wait and retry
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit(f"ElevenLabs error {exc.code}: {exc.read().decode(errors='replace')}")
    raise SystemExit("ElevenLabs keeps rate limiting, try again later")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--only", nargs="*", help="regenerate just these clip keys")
    parser.add_argument("--force", action="store_true", help="regenerate every clip")
    parser.add_argument("--dry-run", action="store_true", help="only print the character count")
    args = parser.parse_args()

    wanted = clips()
    if args.only:
        unknown = set(args.only) - set(wanted)
        if unknown:
            sys.exit(f"Unknown clips: {sorted(unknown)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    todo = {
        k: t
        for k, t in wanted.items()
        if (args.only and k in args.only)
        or (not args.only and (args.force or not (OUT_DIR / f"{k}.mp3").exists()))
    }
    chars = sum(len(t) for t in todo.values())
    print(f"{len(todo)} clips, {chars} characters")
    if args.dry_run:
        return
    key = args.key_file.expanduser().read_text().strip()
    for i, (clip, text) in enumerate(todo.items(), 1):
        (OUT_DIR / f"{clip}.mp3").write_bytes(generate(key, text))
        print(f"[{i}/{len(todo)}] {clip}", flush=True)
    available = sorted(k for k in wanted if (OUT_DIR / f"{k}.mp3").exists())
    manifest = {"voice": "George (ElevenLabs)", "model": MODEL, "clips": available}
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"manifest: {len(available)} clips")


if __name__ == "__main__":
    main()
