"""Makes a short fake 'walk-around' video from one photo, for testing without filming.
It pans across the photo and adds a blurred stretch and a dark stretch on purpose,
so you can see the key-frame picker reject them.

    python tools/make_test_video.py                 # uses a sample street photo
    python tools/make_test_video.py my_photo.jpg    # or your own photo
Writes eval/test_walk.mp4
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FPS, SECONDS, W, H = 30, 12, 960, 540


def _source() -> np.ndarray:
    if len(sys.argv) > 1:
        return cv2.imread(sys.argv[1])
    import ultralytics  # ships with a street photo (bus + people)
    return cv2.imread(os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg"))


def main() -> None:
    src = _source()
    # Scale so the photo is wider than the video frame: then panning shows different views.
    scale = max(W * 1.8 / src.shape[1], H / src.shape[0])
    src = cv2.resize(src, None, fx=scale, fy=scale)
    out_path = ROOT / "eval" / "test_walk.mp4"
    out = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    n = FPS * SECONDS
    for i in range(n):
        x = int((src.shape[1] - W) * i / (n - 1))
        y = (src.shape[0] - H) // 2
        frame = src[y:y + H, x:x + W].copy()
        t = i / FPS
        if 3.0 <= t < 5.0:
            frame = cv2.GaussianBlur(frame, (31, 31), 0)    # 'walking too fast'
        if 8.0 <= t < 9.0:
            frame = (frame * 0.08).astype(np.uint8)         # 'went into a dark corridor'
        out.write(frame)
    out.release()
    print("wrote", out_path)


if __name__ == "__main__":
    main()
