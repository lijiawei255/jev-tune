"""Regenerate explicit raster label regions while proving other pixels unchanged.

Inputs are an image and a JSON list of labels. Each label declares ``box``
(left, top, right, bottom), ``position``, ``text`` and ``font_size`` in pixels.
Review the boxes to ensure they contain only labels before using this tool.
This does not reconstruct source measurements or validate scientific content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from matplotlib.font_manager import findfont


def digest(data):
    return hashlib.sha256(data).hexdigest()


def frames(path):
    with Image.open(path) as image:
        result = []
        durations = []
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            if image.convert("RGBA").getchannel("A").getextrema() != (255, 255):
                raise ValueError("Only opaque scientific figures are supported")
            result.append(np.asarray(image.convert("RGB")).copy())
            durations.append(image.info.get("duration", 0))
        return result, durations, image.info.get("loop"), image.info.get("dpi")


def exact_palette(original, edited, mask):
    """Keep original pixels exact; map only replacement pixels to its palette."""
    colors, inverse = np.unique(original.reshape(-1, 3), axis=0, return_inverse=True)
    if len(colors) > 256:
        raise ValueError("An animated frame has more than 256 RGB colors")
    indices = inverse.reshape(original.shape[:2]).astype(np.uint8)
    pixels = edited[mask].astype(np.int32)
    unique, mapping = np.unique(pixels, axis=0, return_inverse=True)
    nearest = ((unique[:, None] - colors[None].astype(np.int32)) ** 2).sum(axis=2).argmin(axis=1)
    indices[mask] = nearest[mapping].astype(np.uint8)
    image = Image.fromarray(indices, mode="P")
    palette = colors.ravel().tolist()
    image.putpalette(palette + [0] * (768 - len(palette)))
    return image


def relabel(source, destination, labels):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError("Output already exists")
    originals, durations, loop, dpi = frames(source)
    mask = np.zeros(originals[0].shape[:2], dtype=bool)
    height, width = mask.shape
    for label in labels:
        left, top, right, bottom = label["box"]
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("Label box is outside the image")
        mask[top:bottom, left:right] = True
    outputs = []
    for original in originals:
        edited = Image.fromarray(original)
        for label in labels:
            left, top, right, bottom = label["box"]
            region = Image.new("RGB", (right - left, bottom - top), label.get("background", "white"))
            font = ImageFont.truetype(findfont("DejaVu Sans"), label["font_size"])
            x, y = label["position"]
            ImageDraw.Draw(region).text((x - left, y - top), label["text"],
                                        font=font, fill=label.get("color", "black"), anchor="lt")
            edited.paste(region, (left, top))
        array = np.asarray(edited)
        if source.suffix.lower() == ".gif":
            outputs.append(exact_palette(original, array, mask))
        else:
            outputs.append(edited)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".gif":
        options = {"loop": loop} if loop is not None else {}
        outputs[0].save(destination, save_all=True, append_images=outputs[1:],
                        duration=durations, disposal=2, optimize=False, **options)
    else:
        options = {"dpi": dpi} if dpi else {}
        outputs[0].save(destination, **options)
    actual, actual_durations, actual_loop, _ = frames(destination)
    if len(actual) != len(originals) or actual_durations != durations or actual_loop != loop:
        destination.unlink()
        raise ValueError("Animation frame count or timing changed")
    proof = []
    for index, (before, after) in enumerate(zip(originals, actual)):
        if before.shape != after.shape or not np.array_equal(before[~mask], after[~mask]):
            destination.unlink()
            raise ValueError("Pixels outside the declared label regions changed")
        proof.append({"frame": index, "outside_before_sha256": digest(before[~mask].tobytes()),
                      "outside_after_sha256": digest(after[~mask].tobytes()),
                      "outside_pixels_equal": True,
                      "changed_pixels": int(np.any(before != after, axis=2).sum())})
    return {"input_sha256": digest(source.read_bytes()), "output_sha256": digest(destination.read_bytes()),
            "input_name": source.name, "output_name": destination.name,
            "size": [width, height], "frame_count": len(actual), "durations_ms": durations,
            "loop": loop, "label_regions": labels, "frames": proof,
            "scope": "Only manually reviewed label rectangles may change; no new measurements or curve reconstruction"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--proof", required=True, type=Path)
    args = parser.parse_args()
    if args.proof.exists():
        parser.error("Proof already exists")
    result = relabel(args.input, args.output, json.loads(args.labels.read_text(encoding="utf-8")))
    args.proof.parent.mkdir(parents=True, exist_ok=True)
    args.proof.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "frames": result["frame_count"]}))


if __name__ == "__main__":
    main()
