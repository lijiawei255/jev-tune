"""Check that label regeneration preserves scientific raster data and timing."""
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

spec = importlib.util.spec_from_file_location(
    "figure_labels", Path(__file__).resolve().parents[1] / "scripts/66_relabel_figures.py")
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


@pytest.mark.parametrize("suffix", [".png", ".gif"])
def test_curve_pixels_and_animation_timing_survive_label_regeneration(tmp_path, suffix):
    first = np.full((80, 120, 3), 255, dtype=np.uint8)
    second = first.copy()
    first[40, 10:110] = [12, 47, 83]
    second[50, 10:110] = [180, 80, 40]
    source, output = tmp_path / ("original" + suffix), tmp_path / ("labelled" + suffix)
    image = Image.fromarray(first)
    if suffix == ".gif":
        image.save(source, save_all=True, append_images=[Image.fromarray(second)],
                   duration=[170, 290], loop=3)
    else:
        image.save(source)
    proof = labels.relabel(source, output, [{"box": [0, 0, 100, 24],
                           "position": [4, 4], "text": "benchmark", "font_size": 12}])
    before, durations, loop, _ = labels.frames(source)
    after, actual_durations, actual_loop, _ = labels.frames(output)
    assert len(after) == len(before)
    assert actual_durations == durations and actual_loop == loop
    for original, regenerated in zip(before, after):
        assert np.array_equal(original[24:], regenerated[24:])
    assert all(row["outside_pixels_equal"] for row in proof["frames"])
    assert all(row["changed_pixels"] > 0 for row in proof["frames"])
