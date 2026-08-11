#!/usr/bin/env python3
"""
capture_landmark.py -- register a "pre-registered frame" landmark.

This is the tool referenced by vision/landmarks.py. It records several views
of one landmark so the car can recognise it later and use it to advance the
mission (see docs/COURSE_ANALYSIS.md, question 5).

WHY SEVERAL VIEWS, AND WHY FROM THE CAR
---------------------------------------
A single stored photo matches almost nothing in the field: the car will never
stand exactly where you stood, and the light will differ. Recording 4-6 views
from slightly different positions makes recognition far more reliable.

Two rules that matter more than anything else in this file:

  1. CAPTURE AT CAR CAMERA HEIGHT, using the car's own camera, with the car
     sitting on the ground. A landmark captured from standing height will not
     match what the car sees at 15 cm.
  2. CAPTURE IN THE LIGHT YOU WILL DRIVE IN. If the demo is at 1 pm, capture
     at 1 pm. If it might be overcast, capture some views on an overcast day.

USAGE
-----
    # live, from the car's camera (press ENTER for each view)
    python3 tools/capture_landmark.py compost_pit

    # or build a landmark from photos you already have
    python3 tools/capture_landmark.py compost_pit --from ../Photos/IMG_A.jpg ../Photos/IMG_B.jpg

    # check what is registered, and test recognition on an image
    python3 tools/capture_landmark.py --list
    python3 tools/capture_landmark.py --test some_frame.jpg

Landmarks are stored as:
    course/landmarks/<name>/00.jpg, 01.jpg, ...
and are loaded automatically by course_navigator.py at startup. Then use them
in a mission stage:

    { "name": "avoid_compost_pit",
      "exit": { "landmark": "compost_pit", "timeout_s": 25 } }

REMEMBER: a landmark never steers the car. It only advances the mission stage.
The terrain classifier and the ultrasonic reflex always keep veto power, so a
false match costs you an early stage change, never a crash.
"""

import argparse
import glob
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from vision.landmarks import LandmarkBook  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "landmarks")


def store_dir(name):
    d = os.path.join(ROOT, name)
    os.makedirs(d, exist_ok=True)
    return d


def next_index(d):
    return len(glob.glob(os.path.join(d, "*.jpg")))


def save_view(name, bgr):
    d = store_dir(name)
    i = next_index(d)
    path = os.path.join(d, f"{i:02d}.jpg")
    cv2.imwrite(path, bgr)
    kp = cv2.ORB_create(700).detectAndCompute(
        cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), None)[0]
    quality = ("GOOD" if len(kp) >= 200 else
               "OK" if len(kp) >= 80 else
               "POOR - too plain, pick a more distinctive view")
    print(f"  saved {path}   {len(kp)} features  [{quality}]")
    return path


def cmd_list():
    if not os.path.isdir(ROOT):
        print("No landmarks registered yet.")
        return
    names = sorted(n for n in os.listdir(ROOT)
                   if os.path.isdir(os.path.join(ROOT, n)))
    if not names:
        print("No landmarks registered yet.")
        return
    print("Registered landmarks:")
    for n in names:
        views = glob.glob(os.path.join(ROOT, n, "*.jpg"))
        warn = "" if len(views) >= 3 else "   <-- add more views (aim for 4-6)"
        print(f"  {n:24s} {len(views)} view(s){warn}")


def cmd_test(path):
    book = LandmarkBook()
    total = 0
    if os.path.isdir(ROOT):
        for n in sorted(os.listdir(ROOT)):
            for f in sorted(glob.glob(os.path.join(ROOT, n, "*.jpg"))):
                im = cv2.imread(f)
                if im is not None and book.add(n, im):
                    total += 1
    if total == 0:
        print("No landmarks registered - nothing to test against.")
        return
    frame = cv2.imread(path)
    if frame is None:
        print("Could not read", path)
        return
    # Match at the SAME resolution the car's camera produces. A full-size
    # phone photo is ~6x larger than the car's 640x480 frame, and that scale
    # gap alone is enough to lose an otherwise good match.
    frame = cv2.resize(frame, (640, 480))
    hit = book.match(frame)
    print(f"Tested {os.path.basename(path)} against {total} view(s): "
          + (f"MATCH '{hit[0]}' ({hit[1]} inliers)" if hit else "no match"))


def cmd_from_files(name, files):
    print(f"Registering landmark '{name}' from {len(files)} file(s):")
    for f in files:
        im = cv2.imread(f)
        if im is None:
            print(f"  skip (unreadable): {f}")
            continue
        save_view(name, cv2.resize(im, (640, 480)))
    cmd_list()


def cmd_live(name, count):
    from picamera2 import Picamera2
    import time
    cam = Picamera2()
    cam.configure(cam.create_preview_configuration(
        main={"size": (640, 480), "format": "RGB888"}))
    cam.start()
    time.sleep(1.0)
    print(f"Capturing landmark '{name}'.")
    print("Move the CAR slightly between views (different angle/distance).")
    try:
        for i in range(count):
            input(f"  view {i + 1}/{count} - position the car, then press ENTER...")
            rgb = cam.capture_array()
            save_view(name, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        cam.stop()
    cmd_list()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", help="landmark name, e.g. compost_pit")
    ap.add_argument("--from", dest="files", nargs="+",
                    help="build from existing image files instead of the camera")
    ap.add_argument("--views", type=int, default=5,
                    help="how many live views to capture (default 5)")
    ap.add_argument("--list", action="store_true", help="list registered landmarks")
    ap.add_argument("--test", metavar="IMAGE", help="test recognition on an image")
    a = ap.parse_args()

    if a.list:
        cmd_list()
    elif a.test:
        cmd_test(a.test)
    elif a.name and a.files:
        cmd_from_files(a.name, a.files)
    elif a.name:
        cmd_live(a.name, a.views)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
