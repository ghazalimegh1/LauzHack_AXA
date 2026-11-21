"""Display-only clean-up of pictures shown to people (render.for_display / display_crop)."""
import cv2
import numpy as np

from sitecheck import render


def scene(level: int, seed: int = 0) -> np.ndarray:
    """A small street-like picture: a gradient, a few shapes and some grain, around `level`."""
    rng = np.random.default_rng(seed)
    img = np.tile(np.linspace(-25, 25, 320, dtype=np.float32), (240, 1))[:, :, None].repeat(3, 2)
    img += level
    img[60:140, 40:160] += 30         # a lit wall
    img[150:220, 200:300] -= 15       # a dark car
    img += rng.normal(0, 4, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def lightness(img: np.ndarray) -> float:
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[:, :, 0].mean())


def test_dim_picture_gets_brighter():
    dark = scene(45)
    assert render.dimness(dark) == 1.0
    assert lightness(render.for_display(dark)) > lightness(dark) + 8


def test_bright_picture_stays_nearly_unchanged():
    day = scene(170)
    assert render.dimness(day) == 0.0
    out = render.for_display(day)
    assert abs(lightness(out) - lightness(day)) < 1.5
    assert float(np.abs(out.astype(int) - day.astype(int)).mean()) < 4   # only light sharpening


def test_small_crop_is_enlarged_and_big_one_is_not_shrunk():
    frame = scene(60)
    small = cv2.imdecode(np.frombuffer(render.display_crop(frame, [0.4, 0.4, 0.5, 0.5]), np.uint8), 1)
    assert max(small.shape[:2]) == render.DISPLAY_PX
    big = np.full((900, 1200, 3), 150, np.uint8)
    assert render.for_display(big, render.DISPLAY_PX).shape == big.shape
