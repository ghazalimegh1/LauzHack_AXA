"""Repeated finds are merged: same object counted once, boxes never moved."""
from sitecheck import merge


def find(frame, t, kind, box, conf):
    return {"frame": frame, "t": t, "kind": kind, "box": box, "confidence": conf}


def test_overlap_measures():
    a = [0.1, 0.1, 0.5, 0.5]
    assert merge.iou(a, a) == 1.0
    assert merge.iou(a, [0.6, 0.6, 0.9, 0.9]) == 0.0
    assert merge.cover(a, [0.2, 0.2, 0.3, 0.3]) == 1.0          # small box inside a big one


def test_four_near_identical_boxes_in_one_frame_become_one():
    boxes = [[0.10, 0.40, 0.50, 0.70], [0.11, 0.41, 0.50, 0.70],
             [0.10, 0.39, 0.49, 0.71], [0.12, 0.42, 0.48, 0.69]]
    finds = [find(0, 0.0, "outdoor_goods", b, c) for b, c in zip(boxes, [0.7, 0.79, 0.78, 0.7])]
    kept, dropped = merge.merge(finds)
    assert dropped == 3 and len(kept) == 1
    assert kept[0]["confidence"] == 0.79 and kept[0]["box"] == boxes[1]   # best kept, unchanged


def test_different_kinds_or_places_stay_apart():
    finds = [find(0, 0.0, "outdoor_goods", [0.1, 0.1, 0.5, 0.5], 0.8),
             find(0, 0.0, "ramp_down", [0.1, 0.1, 0.5, 0.5], 0.7),   # same box, other kind
             find(0, 0.0, "outdoor_goods", [0.6, 0.6, 0.9, 0.9], 0.8)]        # same kind, elsewhere
    kept, dropped = merge.merge(finds)
    assert dropped == 0 and len(kept) == 3


def test_same_object_in_the_next_key_frame_counts_once():
    a = find(4, 34.0, "outdoor_goods", [0.0, 0.3, 1.0, 0.6], 0.7)
    b = find(5, 34.5, "outdoor_goods", [0.05, 0.32, 1.0, 0.62], 0.75)
    kept, dropped = merge.merge([a, b])
    assert dropped == 1 and kept == [b]


def test_far_apart_frames_are_not_merged():
    a = find(1, 9.0, "outdoor_goods", [0.2, 0.1, 0.6, 0.5], 0.8)
    b = find(0, 0.0, "outdoor_goods", [0.2, 0.1, 0.6, 0.5], 0.8)    # same spot on screen, 9 s apart
    kept, dropped = merge.merge([a, b])
    assert dropped == 0 and kept == [a, b]                        # original order kept


def test_people_from_the_second_look_are_added_for_privacy():
    from sitecheck import privacy
    car = {"kind": "vehicle", "box": [0.0, 0.0, 0.3, 0.3]}
    seen = {"kind": "person", "box": [0.5, 0.5, 0.6, 0.8]}
    again = {"kind": "person", "box": [0.51, 0.5, 0.6, 0.8]}     # same person, second look
    missed = {"kind": "person", "box": [0.8, 0.5, 0.9, 0.8]}     # only the second look saw it
    out = privacy.add_people([car, seen], [again, missed])
    assert out == [car, seen, missed]


def test_unrecognisable_close_ups_get_no_picture():
    import cv2
    import numpy as np
    from sitecheck import render
    rng = np.random.default_rng(1)
    sharp = cv2.resize(rng.integers(0, 255, (48, 64, 3), dtype=np.uint8), (640, 480),
                       interpolation=cv2.INTER_NEAREST)
    smeared = cv2.blur(sharp, (41, 41))
    box = [0.2, 0.2, 0.6, 0.6]
    assert render.photo_ok(sharp, box)
    assert not render.photo_ok(smeared, box)                   # too blurred to recognise
    assert not render.photo_ok(sharp, [0.2, 0.2, 0.23, 0.6])   # too small (19 px wide)


def ai(frame, t, kind, box, source="cheap model"):
    return {**find(frame, t, kind, box, 0.7), "source": source}


def test_box_copied_to_a_later_frame_is_dropped():
    # Seen in our day video: the AI gave frame 4 the exact boxes of frame 3 (11 s earlier).
    first = ai(3, 23.0, "outdoor_goods", [0.49, 0.46, 0.999, 0.64])
    copy = ai(4, 34.0, "outdoor_goods", [0.49, 0.46, 0.999, 0.64])
    kept, dropped = merge.drop_copies([copy, first])
    assert dropped == 1 and kept == [first]                  # the earlier one is kept


def test_real_finds_are_not_taken_for_copies():
    a = ai(3, 23.0, "outdoor_goods", [0.49, 0.46, 0.999, 0.64])
    moved = ai(4, 34.0, "outdoor_goods", [0.50, 0.46, 0.999, 0.64])        # box differs
    other = ai(4, 34.0, "ramp_down", [0.49, 0.46, 0.999, 0.64])           # other kind
    close = ai(2, 22.5, "outdoor_goods", [0.49, 0.46, 0.999, 0.64])        # 0.5 s before: merge decides
    car1 = ai(0, 0.0, "vehicle", [0.1, 0.1, 0.2, 0.2], source="local detector")
    car2 = ai(2, 13.0, "vehicle", [0.1, 0.1, 0.2, 0.2], source="local detector")
    kept, dropped = merge.drop_copies([a, moved, other, close, car1, car2])
    assert dropped == 0 and len(kept) == 6
