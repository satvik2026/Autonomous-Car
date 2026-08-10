#!/usr/bin/env python3
"""
course_navigator.py -- full course-running program for the demo day.

Puts together the three layers:

  REFLEX   (ultrasonic)  : stop/reverse/turn on anything close. Always wins.
  TERRAIN  (camera)      : which way is drivable; never steer into vegetation.
                           vision/terrain.py -- ExG vegetation index +
                           saturation, validated against the site photos.
  MISSION  (sequencer)   : which STAGE of the course we are in and when to
                           advance. mission.py + missions/*.json

Run:
    python3 course_navigator.py --mission missions/demo_course.json
    python3 course_navigator.py --calibrate          # save overlay images
    python3 course_navigator.py --replay ../Photos   # dry-run on the photos
                                                     # (no motors, no camera)

The --replay mode is the important one before demo day: it runs the exact
decision code over your site photos on a laptop and prints what the car would
have done for each, so you can tune thresholds without touching hardware.

TEST WITH THE WHEELS OFF THE GROUND FIRST.
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vision import terrain            # noqa: E402
from vision import landmarks as lm    # noqa: E402
from mission import Mission           # noqa: E402

# ---------------------------------------------------------------------------
# PINS (BCM) -- matches docs/pinout_dual_l298n.svg (two L298N, one per side)
# ---------------------------------------------------------------------------
LEFT_FWD, LEFT_BWD, LEFT_EN = 5, 6, 12
RIGHT_FWD, RIGHT_BWD, RIGHT_EN = 20, 21, 13
TRIG_PIN, ECHO_PIN = 23, 24

STOP_DISTANCE = 0.30
SLOW_DISTANCE = 0.60
MIN_SPEED = 0.35
LOOP_HZ = 10
FRAME_W, FRAME_H = 640, 480


# ---------------------------------------------------------------------------
# Hardware (imported lazily so --replay works on a laptop)
# ---------------------------------------------------------------------------
class Car:
    def __init__(self):
        from gpiozero import Motor, DistanceSensor
        self.left = Motor(forward=LEFT_FWD, backward=LEFT_BWD,
                          enable=LEFT_EN, pwm=True)
        self.right = Motor(forward=RIGHT_FWD, backward=RIGHT_BWD,
                           enable=RIGHT_EN, pwm=True)
        self.sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN,
                                     max_distance=2.0)

    def wheels(self, l, r):
        l = float(np.clip(l, -1, 1))
        r = float(np.clip(r, -1, 1))
        (self.left.forward if l >= 0 else self.left.backward)(abs(l))
        (self.right.forward if r >= 0 else self.right.backward)(abs(r))

    def drive(self, steer, speed):
        """Skid steer: reduce the inside wheel in proportion to |steer|."""
        mag = abs(steer)
        inside = speed - mag * (speed + 0.9 * speed)
        if 0 < inside < MIN_SPEED and mag > 0.05:
            inside = MIN_SPEED
        if steer > 0:
            self.wheels(speed, inside)
        elif steer < 0:
            self.wheels(inside, speed)
        else:
            self.wheels(speed, speed)

    def stop(self):
        self.left.stop()
        self.right.stop()

    def pivot(self, direction, speed=0.6):
        self.wheels(speed * direction, -speed * direction)

    def distance(self):
        return self.sensor.distance


def open_camera():
    from picamera2 import Picamera2
    cam = Picamera2()
    cam.configure(cam.create_preview_configuration(
        main={"size": (FRAME_W, FRAME_H), "format": "RGB888"}))
    cam.start()
    time.sleep(1.0)
    return cam


# ---------------------------------------------------------------------------
# Zone identification from the surface mix
# ---------------------------------------------------------------------------
def identify_surface(mix, zones):
    """Map a measured surface mix onto a named zone (mud/gravel/cement/grass)."""
    return lm.match_zone(mix, zones) if zones else None


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def run(mission_path):
    import cv2
    car = Car()
    cam = open_camera()
    mis = Mission.load(mission_path)
    period = 1.0 / LOOP_HZ
    search_dir = 1

    print(f"Course navigator: {len(mis.stages)} stages. Ctrl-C to stop.")
    try:
        while not mis.finished:
            t0 = time.monotonic()
            stage = mis.stage

            # ---------- REFLEX ----------
            dist = car.distance()
            if dist <= STOP_DISTANCE:
                car.stop(); time.sleep(0.05)
                car.wheels(-0.55, -0.55); time.sleep(0.4)
                car.pivot(search_dir); time.sleep(0.6)
                car.stop()
                search_dir *= -1
                continue

            # ---------- PERCEPTION ----------
            rgb = cam.capture_array()
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            d = terrain.decide_steering(bgr, keepout_bias=stage.keepout_bias)
            surface = identify_surface(d['mix'], mis.zones)

            marker = None
            if stage.exit_marker:
                hit = lm.detect_marker(bgr, stage.exit_marker)
                if hit:
                    marker = stage.exit_marker

            # ---------- MISSION ----------
            _, advanced, reason = mis.update(surface=surface, marker=marker,
                                             distance_m=dist)
            if advanced:
                print(f"\n-> EXIT {stage.name} ({reason})")
                car.stop(); time.sleep(0.2)
                continue

            # ---------- ACT ----------
            speed = stage.speed
            if dist < SLOW_DISTANCE:
                span = SLOW_DISTANCE - STOP_DISTANCE
                frac = (dist - STOP_DISTANCE) / span if span > 0 else 1.0
                speed = MIN_SPEED + (stage.speed - MIN_SPEED) * float(np.clip(frac, 0, 1))

            if stage.behaviour == 'pivot_left':
                car.pivot(-1, stage.speed)
            elif stage.behaviour == 'pivot_right':
                car.pivot(+1, stage.speed)
            elif stage.behaviour == 'straight':
                car.drive(0.0, speed)
            elif not d['drivable']:
                # Vegetation/wall fills the view -> never charge it.
                car.stop()
                car.wheels(-0.55, -0.55); time.sleep(0.35)
                car.pivot(search_dir); time.sleep(0.5)
                car.stop()
                search_dir *= -1
            else:
                if stage.behaviour == 'creep':
                    speed = min(speed, max(MIN_SPEED, speed))
                car.drive(d['steer'], speed)

            print(f"{mis.progress()} {stage.name:18s} surf={str(surface):7s} "
                  f"veg={d['mix']['veg']:.2f} steer={d['steer']:+.2f} "
                  f"d={dist*100:5.1f}cm t={mis.elapsed():5.1f}s", end="\r")

            dt = time.monotonic() - t0
            if dt < period:
                time.sleep(period - dt)

        print("\nMISSION COMPLETE")
        for e in mis.log:
            print(f"  {e['stage']:20s} {e['duration_s']:6.1f}s  ({e['reason']})")
    except KeyboardInterrupt:
        print("\nStopping (Ctrl-C).")
    finally:
        car.stop()
        try:
            cam.stop()
        except Exception:
            pass


def calibrate():
    import cv2
    cam = open_camera()
    try:
        rgb = cam.capture_array()
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite("calib_frame.jpg", bgr)
        cv2.imwrite("calib_overlay.jpg", terrain.debug_overlay(bgr))
        d = terrain.decide_steering(bgr)
        print("mix:", {k: round(v, 3) for k, v in d['mix'].items()})
        print("scores L/C/R:", tuple(round(s, 2) for s in d['scores']))
        print("steer:", round(d['steer'], 2), "drivable:", d['drivable'])
        print("Wrote calib_frame.jpg and calib_overlay.jpg")
        print("In the overlay: RED=vegetation(avoid) CYAN=cement/gravel GREEN=mud")
    finally:
        cam.stop()


def replay(folder):
    """Dry-run the decision code over saved photos. No hardware needed."""
    import cv2
    import glob
    files = sorted(glob.glob(os.path.join(folder, "*.jpg")))
    if not files:
        print("no .jpg found in", folder)
        return
    print(f"Replaying {len(files)} images from {folder}\n")
    print(f"{'image':34s} {'veg':>5s} {'hard':>5s} {'mud':>5s} "
          f"{'L':>6s} {'C':>6s} {'R':>6s}  decision")
    for f in files:
        im = cv2.imread(f)
        if im is None:
            continue
        im = cv2.resize(im, (FRAME_W, FRAME_H))
        d = terrain.decide_steering(im)
        m = d['mix']
        if not d['drivable']:
            dec = "STOP (no drivable route)"
        elif abs(d['steer']) < 0.01:
            dec = "STRAIGHT"
        else:
            dec = f"{'RIGHT' if d['steer'] > 0 else 'LEFT'} {d['steer']:+.2f}"
        print(f"{os.path.basename(f):34s} {m['veg']:5.2f} {m['hard']:5.2f} "
              f"{m['mud']:5.2f} {d['scores'][0]:6.2f} {d['scores'][1]:6.2f} "
              f"{d['scores'][2]:6.2f}  {dec}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mission", default="missions/demo_course.json")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--replay", metavar="FOLDER")
    a = ap.parse_args()
    if a.replay:
        replay(a.replay)
    elif a.calibrate:
        calibrate()
    else:
        run(a.mission)
