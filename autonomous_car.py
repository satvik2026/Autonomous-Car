#!/usr/bin/env python3
"""
autonomous_car.py  --  PROGRAM 2 (the full project)
====================================================

A vision-guided autonomous off-road car for a Raspberry Pi 3B+.

Two decision layers, kept deliberately separate:

  1. REFLEX LAYER (ultrasonic HC-SR04)
       Fast + dumb + always wins. If something is close ahead, STOP and turn,
       no matter what the camera thinks. This is collision insurance.

  2. STRATEGY LAYER (Pi camera + OpenCV)
       Looks at the ground in front of the car, classifies it by colour into
       GRASS (the hill -> avoid), GROUND (the drivable path -> follow) and
       everything-else (building wall -> avoid), and produces a single steering
       value in [-1, +1]. That value trims the left/right wheel speeds so the
       car follows the open path and refuses to climb the grassy hill or drift
       into the building.

Why no GPS/GPX route here: the parts list has no GPS module, and the route is
defined by how the terrain LOOKS, not by coordinates. See the README, Q4. An
optional GPS waypoint hook is stubbed at the bottom (disabled by default).

Steering = skid steer / differential drive, exactly as specified:
    * straight        -> both sides equal
    * small deviation -> reduce ONE side's speed a little (gentle arc)
    * hard turn       -> one side fast, other slow/reversed (pivot)

Wiring / pins: see docs/WIRING.md and docs/pinout.svg.

Run:        python3 autonomous_car.py
Calibrate:  python3 autonomous_car.py --calibrate   (saves camera + mask images)
Stop:       Ctrl-C  (motors cut safely on exit)

TEST WITH THE WHEELS OFF THE GROUND FIRST, then hand-on-the-power for early
outdoor runs.
"""

import sys
import time

import numpy as np

from gpiozero import Motor, DistanceSensor

# ---------------------------------------------------------------------------
# PIN CONFIG  --  BCM GPIO numbers (identical to the simple demo)
# ---------------------------------------------------------------------------

LEFT_FORWARD_PIN = 5     # GPIO5  -> L293D IN1
LEFT_BACKWARD_PIN = 6    # GPIO6  -> L293D IN2
LEFT_ENABLE_PIN = 12     # GPIO12 -> L293D EN1 (PWM speed)

RIGHT_FORWARD_PIN = 20   # GPIO20 -> L293D IN3
RIGHT_BACKWARD_PIN = 21  # GPIO21 -> L293D IN4
RIGHT_ENABLE_PIN = 13    # GPIO13 -> L293D EN2 (PWM speed)

TRIG_PIN = 23            # GPIO23 -> HC-SR04 TRIG
ECHO_PIN = 24            # GPIO24 <- HC-SR04 ECHO (THROUGH A VOLTAGE DIVIDER!)
MAX_SENSOR_DISTANCE = 2.0

# Optional cheap digital IR obstacle module as a close-range backup.
USE_IR_BACKUP = False
IR_PIN = 25              # GPIO25 -> IR module OUT (only used if USE_IR_BACKUP)

# ---------------------------------------------------------------------------
# DRIVING TUNING
# ---------------------------------------------------------------------------

BASE_SPEED = 0.55        # cruising forward speed (0..1 PWM duty)
MIN_SPEED = 0.30         # slowest a driving wheel is allowed to spin (below
                         # this, gear motors on grass just stall/buzz)
MAX_STEER_REDUCTION = 0.9  # at full steer, how much we cut the inside wheel
STOP_DISTANCE = 0.30     # m: ultrasonic obstacle -> reflex stop & turn
SLOW_DISTANCE = 0.60     # m: start slowing down before we get that close
REVERSE_TIME = 0.4       # s to back up when boxed in
PIVOT_TIME = 0.6         # s to pivot when reacting/searching
LOOP_HZ = 10             # main control loop rate

# ---------------------------------------------------------------------------
# VISION TUNING  --  HSV colour ranges. THESE MUST BE CALIBRATED ON-SITE.
# HSV in OpenCV: H 0-179, S 0-255, V 0-255.
# Use `python3 autonomous_car.py --calibrate` and inspect the saved masks.
# ---------------------------------------------------------------------------

# Grass / the hill = green. This is what we steer AWAY from.
GRASS_HSV_LOW = np.array([35, 40, 30])
GRASS_HSV_HIGH = np.array([90, 255, 255])

# The drivable path = ground colour (brown dirt / tan / grey gravel).
# The default below is a broad "earthy" band; TIGHTEN it to your real path.
GROUND_HSV_LOW = np.array([5, 20, 40])
GROUND_HSV_HIGH = np.array([30, 200, 230])

FRAME_W, FRAME_H = 640, 480
ROI_TOP_FRACTION = 0.45      # ignore the top 45% (sky, far building, trees);
                             # only judge the ground the car is about to hit.
GRASS_PENALTY = 1.5          # how strongly green is punished in the column score
DRIVABLE_ENOUGH = 0.15       # min drivable fraction for a column to count as OK
CENTER_STICKINESS = 0.10     # prefer going straight unless a side is clearly better

# If the hill is ALWAYS on one side and the building ALWAYS on the other, you
# can nudge the car to hug the middle of the wide path. 0 = off.
# Positive pulls right, negative pulls left. Leave 0 unless you need it.
EDGE_BIAS = 0.0

# ---------------------------------------------------------------------------
# HARDWARE SETUP
# ---------------------------------------------------------------------------

left = Motor(forward=LEFT_FORWARD_PIN, backward=LEFT_BACKWARD_PIN,
             enable=LEFT_ENABLE_PIN, pwm=True)
right = Motor(forward=RIGHT_FORWARD_PIN, backward=RIGHT_BACKWARD_PIN,
              enable=RIGHT_ENABLE_PIN, pwm=True)
sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN,
                        max_distance=MAX_SENSOR_DISTANCE)

ir_sensor = None
if USE_IR_BACKUP:
    from gpiozero import DigitalInputDevice
    # Many IR obstacle modules pull their output LOW when they see something.
    ir_sensor = DigitalInputDevice(IR_PIN)


def ir_blocked():
    """True if the optional IR backup sensor sees a close obstacle."""
    if ir_sensor is None:
        return False
    # active-low module: value == 0 means obstacle detected
    return ir_sensor.value == 0


# ---------------------------------------------------------------------------
# CAMERA SETUP  (picamera2 -- the correct library for 64-bit Raspberry Pi OS)
# ---------------------------------------------------------------------------

def open_camera():
    from picamera2 import Picamera2
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (FRAME_W, FRAME_H), "format": "RGB888"})
    picam2.configure(config)
    picam2.start()
    time.sleep(1.0)  # let auto-exposure settle
    return picam2


# ---------------------------------------------------------------------------
# MOVEMENT HELPERS  (skid steer)
# ---------------------------------------------------------------------------

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def set_wheel_speeds(left_speed, right_speed):
    """Drive each side. Positive = forward, negative = reverse, magnitude 0..1."""
    left_speed = clamp(left_speed, -1.0, 1.0)
    right_speed = clamp(right_speed, -1.0, 1.0)

    if left_speed >= 0:
        left.forward(left_speed)
    else:
        left.backward(-left_speed)

    if right_speed >= 0:
        right.forward(right_speed)
    else:
        right.backward(-right_speed)


def drive_with_steer(steer, base_speed=BASE_SPEED):
    """
    Convert a steering value in [-1, +1] into left/right wheel speeds.

      steer =  0  -> straight (both sides = base_speed)
      steer > 0   -> bear RIGHT by slowing the RIGHT wheels (small steer =
                     small reduction = gentle arc; big steer = big reduction,
                     up to reversing for a pivot)
      steer < 0   -> bear LEFT  by slowing the LEFT wheels

    This is exactly "reduce the voltage of one motor to make a small turn,"
    scaling smoothly up to a full pivot.
    """
    steer = clamp(steer + EDGE_BIAS, -1.0, 1.0)
    mag = abs(steer)

    # The outside wheels stay at base_speed; the inside wheels are reduced
    # (and, for hard turns, reversed) in proportion to the steer magnitude.
    inside = base_speed - mag * (base_speed + MAX_STEER_REDUCTION * base_speed)
    # For gentle turns keep the inside wheel above the stall speed so it still
    # pulls; only let it drop/reverse once the turn is genuinely sharp.
    if inside > 0:
        inside = max(inside, MIN_SPEED) if mag > 0.05 else inside

    if steer > 0:      # turn right: right = inside, left = outside
        set_wheel_speeds(base_speed, inside)
    elif steer < 0:    # turn left: left = inside, right = outside
        set_wheel_speeds(inside, base_speed)
    else:
        set_wheel_speeds(base_speed, base_speed)


def stop():
    left.stop()
    right.stop()


def reverse(t=REVERSE_TIME):
    set_wheel_speeds(-BASE_SPEED, -BASE_SPEED)
    time.sleep(t)
    stop()


def pivot(direction, t=PIVOT_TIME):
    """direction: +1 pivot right, -1 pivot left."""
    if direction >= 0:
        set_wheel_speeds(BASE_SPEED, -BASE_SPEED)
    else:
        set_wheel_speeds(-BASE_SPEED, BASE_SPEED)
    time.sleep(t)
    stop()


# ---------------------------------------------------------------------------
# VISION  --  turn a camera frame into a steering decision
# ---------------------------------------------------------------------------

def analyse_frame(frame_rgb):
    """
    Classify the ground in front of the car and return a decision dict.

    Returns:
        {
          'steer':    float in [-1, +1]  (negative left, positive right),
          'drivable': bool  (is ANY column drivable? if not -> stop/search),
          'scores':   (left, centre, right) column scores (for debugging),
        }
    """
    import cv2

    # 1. Region of interest: only the lower part of the frame (the ground the
    #    car is about to drive over). This throws away sky, far building tops
    #    and distant trees that would otherwise confuse the colour classes.
    roi_top = int(FRAME_H * ROI_TOP_FRACTION)
    roi = frame_rgb[roi_top:FRAME_H, :, :]

    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)

    # 2. Colour masks.
    grass_mask = cv2.inRange(hsv, GRASS_HSV_LOW, GRASS_HSV_HIGH)
    ground_mask = cv2.inRange(hsv, GROUND_HSV_LOW, GROUND_HSV_HIGH)

    # Clean up speckle so a few stray pixels don't swing the score.
    kernel = np.ones((5, 5), np.uint8)
    grass_mask = cv2.morphologyEx(grass_mask, cv2.MORPH_OPEN, kernel)
    ground_mask = cv2.morphologyEx(ground_mask, cv2.MORPH_OPEN, kernel)

    # 3. Split into three columns: left / centre / right.
    h, w = grass_mask.shape
    third = w // 3
    cols = [(0, third), (third, 2 * third), (2 * third, w)]

    scores = []
    drivable_flags = []
    for (x0, x1) in cols:
        area = float(h * (x1 - x0))
        ground_frac = np.count_nonzero(ground_mask[:, x0:x1]) / area
        grass_frac = np.count_nonzero(grass_mask[:, x0:x1]) / area
        # A column is good if it's mostly drivable ground and not grass.
        # Building walls simply have LOW ground_frac (they're not ground
        # colour), so they lose here too -- exactly the behaviour we want.
        score = ground_frac - GRASS_PENALTY * grass_frac
        scores.append(score)
        drivable_flags.append(ground_frac >= DRIVABLE_ENOUGH and
                              grass_frac < ground_frac)

    left_s, centre_s, right_s = scores

    # 4. Turn the three scores into a steering value.
    if not any(drivable_flags):
        # Nothing ahead is safely drivable (grass/wall everywhere). Do NOT
        # pick the least-bad direction and charge -- signal "stop/search".
        return {'steer': 0.0, 'drivable': False, 'scores': tuple(scores)}

    best_idx = int(np.argmax(scores))
    best_score = scores[best_idx]

    # Prefer going straight unless a side beats the centre clearly.
    if centre_s + CENTER_STICKINESS >= best_score:
        target = 0.0  # straight
    elif best_idx == 0:
        target = -1.0  # left column best
    else:
        target = +1.0  # right column best

    # Scale the steer by HOW MUCH better the chosen side is than the centre,
    # so a slightly-better side gives a gentle correction and a much-better
    # side gives a strong turn (small deviations vs. sharp turns).
    if target != 0.0:
        advantage = clamp(best_score - centre_s, 0.0, 1.0)
        steer = target * clamp(0.3 + advantage, 0.0, 1.0)
    else:
        steer = 0.0

    return {'steer': steer, 'drivable': True, 'scores': tuple(scores)}


# ---------------------------------------------------------------------------
# CALIBRATION MODE  --  save what the camera sees + the colour masks
# ---------------------------------------------------------------------------

def calibrate():
    import cv2
    print("Calibration: capturing one frame and saving masks...")
    picam2 = open_camera()
    try:
        frame = picam2.capture_array()  # RGB888
        roi_top = int(FRAME_H * ROI_TOP_FRACTION)
        roi = frame[roi_top:FRAME_H, :, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        grass = cv2.inRange(hsv, GRASS_HSV_LOW, GRASS_HSV_HIGH)
        ground = cv2.inRange(hsv, GROUND_HSV_LOW, GROUND_HSV_HIGH)

        cv2.imwrite("calib_frame.jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        cv2.imwrite("calib_grass_mask.jpg", grass)
        cv2.imwrite("calib_ground_mask.jpg", ground)

        decision = analyse_frame(frame)
        print("Saved: calib_frame.jpg, calib_grass_mask.jpg, calib_ground_mask.jpg")
        print(f"Column scores (L, C, R): {decision['scores']}")
        print(f"Decision -> steer={decision['steer']:+.2f} "
              f"drivable={decision['drivable']}")
        print("Open the images. Grass should be white in the grass mask, your "
              "path white in the ground mask, the building black in both. "
              "Adjust the *_HSV_* values until that's true.")
    finally:
        picam2.stop()
        stop()


# ---------------------------------------------------------------------------
# MAIN CONTROL LOOP
# ---------------------------------------------------------------------------

def main():
    print("Autonomous car running. Ctrl-C to stop.")
    print("(Wheels off the ground for the first test!)")
    picam2 = open_camera()
    loop_period = 1.0 / LOOP_HZ
    search_dir = 1  # which way to pivot when we're boxed in; flips each time

    try:
        while True:
            t0 = time.monotonic()

            # ---- REFLEX LAYER: ultrasonic (and optional IR) has priority ----
            distance = sensor.distance
            if distance <= STOP_DISTANCE or ir_blocked():
                stop()
                time.sleep(0.05)
                reverse()
                pivot(search_dir)
                search_dir *= -1  # alternate so we don't rock against a wall
                continue

            # ---- STRATEGY LAYER: camera chooses the route ----
            frame = picam2.capture_array()  # RGB888 array
            decision = analyse_frame(frame)

            # Slow down as we approach anything, even before the hard stop.
            speed = BASE_SPEED
            if distance < SLOW_DISTANCE:
                # linearly scale speed between MIN_SPEED and BASE_SPEED
                span = SLOW_DISTANCE - STOP_DISTANCE
                frac = (distance - STOP_DISTANCE) / span if span > 0 else 1.0
                speed = MIN_SPEED + (BASE_SPEED - MIN_SPEED) * clamp(frac, 0, 1)

            if not decision['drivable']:
                # Grass/wall fills the view -> don't drive into the hill.
                # Stop, back up, and pivot to search for open ground.
                stop()
                reverse()
                pivot(search_dir)
                search_dir *= -1
            else:
                drive_with_steer(decision['steer'], base_speed=speed)

            print(f"dist:{distance*100:5.1f}cm  "
                  f"steer:{decision['steer']:+.2f}  "
                  f"scores:{tuple(round(s, 2) for s in decision['scores'])}",
                  end="\r")

            # keep a steady loop rate
            dt = time.monotonic() - t0
            if dt < loop_period:
                time.sleep(loop_period - dt)

    except KeyboardInterrupt:
        print("\nStopping (Ctrl-C).")
    finally:
        stop()
        try:
            picam2.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# OPTIONAL GPS WAYPOINT HOOK  (disabled -- you have no GPS module yet)
# ---------------------------------------------------------------------------
#
# If you later add a GPS (e.g. u-blox NEO-6M on the Pi UART) and want to follow
# a GPX route, the shape is:
#
#   1. Parse examples/route.gpx into a list of (lat, lon) waypoints.
#   2. Each loop: read the current GPS fix; compute bearing + distance to the
#      next waypoint; convert the bearing error into a steer value; advance to
#      the next waypoint when within a few metres.
#   3. Let analyse_frame()'s obstacle/terrain steering OVERRIDE the GPS steer
#      so you still never drive into the building even if GPS drifts.
#
# See the README section "GPS / GPX routes" for why this is optional and why
# vision-only navigation is the right first build for your terrain.
#
# def load_gpx(path):
#     import xml.etree.ElementTree as ET
#     ns = {"g": "http://www.topografix.com/GPX/1/1"}
#     tree = ET.parse(path)
#     return [(float(p.attrib["lat"]), float(p.attrib["lon"]))
#             for p in tree.iterfind(".//g:trkpt", ns)]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        calibrate()
    else:
        main()
