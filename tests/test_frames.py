"""Key frame picking (the earlier app's rules): sharpness alone decides, relative to the
video's own median."""
import cv2
import numpy as np

from sitecheck import frames


def scene(seed: int, brightness: float = 1.0, blur: float = 0.0, lamps: int = 0) -> np.ndarray:
    """A distinct 'view': blocky random texture (sharp edges), optionally dim/blurred/lit."""
    rng = np.random.default_rng(seed)
    img = cv2.resize(rng.integers(30, 220, (24, 32), dtype=np.uint8), (320, 240),
                     interpolation=cv2.INTER_NEAREST).astype(np.float32)
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    img *= brightness
    for i in range(lamps):        # sharp, very bright street lamps
        cv2.circle(img, (40 + 60 * i, 40), 7, 255, -1)
    return np.clip(img, 0, 255).astype(np.uint8)


def sample(i: int, t: float, gray: np.ndarray) -> frames.Sample:
    s = frames.Sample(index=i, t=t, jpeg=b"", thumb=b"")
    m = frames.measure(gray)
    s.tiny = m.pop("tiny")
    for k, v in m.items():
        setattr(s, k, v)
    return s


def test_picks_the_sharpest_frame_of_each_part():
    # 3 parts, 4 frames each: every frame is a different view, sharpness varies
    samples, sharpest = [], []
    for part in range(3):
        blurs = [2.5, 0.0, 1.5, 1.0]
        for j, b in enumerate(blurs):
            samples.append(sample(len(samples), part * 4 + j, scene(part * 10 + j, blur=b)))
        sharpest.append(part * 4 + 1)            # blur 0.0 is the sharpest
    picked = frames.pick(samples, 3)
    assert [s.index for s in picked] == sharpest
    for part in range(3):
        group = samples[part * 4: part * 4 + 4]
        best = max((s for s in group if s.reason in ("", "sharper nearby")),
                   key=lambda s: s.sharpness)
        assert best.status == "picked"


def test_blurry_dark_and_overexposed_frames_are_dropped():
    samples = [sample(i, i, scene(i)) for i in range(8)]
    samples.append(sample(8, 8, scene(50, blur=6)))
    samples.append(sample(9, 9, scene(51, brightness=0.1)))
    white = np.full((240, 320), 255, np.uint8)
    samples.append(sample(10, 10, white))
    frames.pick(samples, 4)
    assert samples[8].reason == "blurry"
    assert samples[9].reason == "dark"
    assert samples[10].reason == "overexposed"
    assert all(s.status == "skipped" for s in samples[8:])


def test_night_video_is_judged_against_its_own_median():
    # Everything is dim (as at night): frames must still be picked, not all called "too dark".
    samples = [sample(i, i, scene(i, brightness=0.35, lamps=2)) for i in range(12)]
    picked = frames.pick(samples, 6)
    assert len(picked) == 6
    assert not any(s.reason == "dark" for s in samples)


def test_bright_lamps_do_not_make_a_blurry_frame_look_sharp():
    sharp_dim = scene(1, brightness=0.25)
    blurry_with_lamps = scene(2, brightness=0.25, blur=4, lamps=4)
    assert frames.measure(sharp_dim)["sharpness"] > frames.measure(blurry_with_lamps)["sharpness"]


def test_same_view_is_not_picked_twice():
    base = scene(7)
    shifted = np.roll(base, 1, axis=1)              # same spot, camera moved a little
    samples = [sample(0, 0, base), sample(1, 1, shifted), sample(2, 2, scene(8)), sample(3, 3, scene(9))]
    picked = frames.pick(samples, 3)                 # parts: [0], [1], [2, 3]
    assert {s.index for s in picked} == {0, 2, 3}
    assert any(s.reason == "same view" for s in samples)


def test_read_samples_keeps_two_frames_per_second(tmp_path):
    path = tmp_path / "walk.mp4"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for i in range(40):                              # 4 seconds at 10 fps
        out.write(cv2.cvtColor(scene(i // 5), cv2.COLOR_GRAY2BGR))
    out.release()
    samples, info = frames.read_samples(str(path))
    assert info["frames_in_video"] == 40
    assert 7 <= len(samples) <= 9                     # 2 per second
    gaps = np.diff([s.t for s in samples])
    assert np.allclose(gaps, 0.5, atol=0.11)


def test_brighten_lifts_dim_frames_only():
    dim = cv2.cvtColor(scene(3, brightness=0.2), cv2.COLOR_GRAY2BGR)
    lifted, changed = frames.brighten(dim)
    assert changed and lifted.mean() > dim.mean() + 20
    bright = cv2.cvtColor(scene(3), cv2.COLOR_GRAY2BGR)
    same, changed = frames.brighten(bright)
    assert not changed and same is bright


def test_walking_smear_in_one_direction_counts_as_blurry():
    sharp = scene(4)
    smeared = cv2.blur(sharp, (25, 1))               # smeared left-right only
    assert frames.measure(smeared)["sharpness"] < 0.5 * frames.measure(sharp)["sharpness"]


def test_longer_videos_get_a_few_more_frames_up_to_a_cap():
    from sitecheck.frames import auto_count
    assert [auto_count(s) for s in (5, 24, 30, 30.4, 31, 40, 41, 47, 70, 71, 300)] == \
        [6, 6, 6, 6, 7, 7, 8, 8, 10, 10, 10]
