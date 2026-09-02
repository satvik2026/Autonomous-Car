#!/usr/bin/env python3
"""
calibrate_terrain.py -- on-site tuning helper.

Point the car's camera at a surface, run this, and it tells you what the
classifier thinks that surface is. Use it to set EXG_VEG and SAT_HARD in
vision/terrain.py for the actual lighting on demo day.

Usage:
    python3 tools/calibrate_terrain.py                 # live camera
    python3 tools/calibrate_terrain.py IMG_1234.jpg    # a saved photo
    python3 tools/calibrate_terrain.py ../../Photos    # a whole folder

What to check:
    * point at the LAWN      -> should read veg > 0.70  (keep-out)
    * point at the MUD COURSE-> should read veg < 0.45  (drivable)
    * point at CEMENT        -> should read hard > 0.80
    * point at GRAVEL        -> should read hard > 0.70
If the lawn reads too low, LOWER EXG_VEG. If the mud course reads as veg,
RAISE EXG_VEG.
"""

import glob
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from vision import terrain  # noqa: E402


def report(bgr, label):
    d = terrain.decide_steering(bgr)
    m = d['mix']
    verdict = ("KEEP-OUT (vegetation)" if m['veg'] > 0.55 else
               "cement/gravel" if m['hard'] > 0.70 else
               "mud/drivable")
    print(f"{label:36s} veg={m['veg']:.2f} hard={m['hard']:.2f} "
          f"mud={m['mud']:.2f}  L/C/R={d['scores'][0]:+.2f}/"
          f"{d['scores'][1]:+.2f}/{d['scores'][2]:+.2f}  "
          f"steer={d['steer']:+.2f}  -> {verdict}")
    return d


def main():
    args = sys.argv[1:]
    if args:
        target = args[0]
        files = (sorted(glob.glob(os.path.join(target, "*.jpg")))
                 if os.path.isdir(target) else [target])
        print(f"{'image':36s} {'mix':^28s} {'scores':^22s}")
        for f in files:
            im = cv2.imread(f)
            if im is None:
                continue
            im = cv2.resize(im, (640, 480))
            report(im, os.path.basename(f))
            if len(files) == 1:
                cv2.imwrite("calib_overlay.jpg", terrain.debug_overlay(im))
                print("\nWrote calib_overlay.jpg "
                      "(RED=vegetation CYAN=cement/gravel GREEN=mud)")
        return

    # live camera
    from picamera2 import Picamera2
    cam = Picamera2()
    cam.configure(cam.create_preview_configuration(
        main={"size": (640, 480), "format": "RGB888"}))
    cam.start()
    import time
    time.sleep(1.0)
    try:
        rgb = cam.capture_array()
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        report(bgr, "live frame")
        cv2.imwrite("calib_frame.jpg", bgr)
        cv2.imwrite("calib_overlay.jpg", terrain.debug_overlay(bgr))
        print("Wrote calib_frame.jpg + calib_overlay.jpg "
              "(RED=vegetation CYAN=cement/gravel GREEN=mud)")
    finally:
        cam.stop()


if __name__ == "__main__":
    main()
