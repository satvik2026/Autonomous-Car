#!/usr/bin/env python3
"""
calibrate_ground.py -- size, aim and calibrate the DOWNWARD ultrasonic.

There are two jobs here, and you do them in this order:

  1. GEOMETRY (do this at the bench, no hardware needed)
         python3 tools/calibrate_ground.py --geometry
     Works out where to physically put the sensor: how high, and at what
     angle. Run it before you drill anything -- the wrong mount makes the
     sensor useless, and the wrong mount is the obvious one (bolted to the
     front wall of the chassis).

  2. MEASUREMENT (on the car, on the actual course)
         python3 tools/calibrate_ground.py --measure
     Samples the fitted sensor on flat ground and prints the exact
     DOWN_NOMINAL_M / DOWN_TOLERANCE numbers to paste into
     course_navigator.py. Never guess these -- the reading depends on the
     surface, and mud, gravel and cement do not answer the same way.

WHY THE FRONT WALL DOES NOT WORK
================================
The obvious mounting point is the 2-3 cm lip on the front of the chassis, next
to the camera. For the FORWARD sensor that is exactly right. For a DOWNWARD
sensor it fails on geometry, not on wiring:

A sensor h above the ground, tilted t degrees below horizontal, sees the ground
at slant range h/sin(t), which is h/tan(t) ahead of the sensor. At h = 3 cm the
answer is a few centimetres no matter what angle you choose -- the car reaches
the hole long before it could stop, and the range is down at the sensor's ~2 cm
blind spot. Run --geometry and read the FRONT WALL row: it is in the table so
you can see it fail rather than take my word for it.

The fix is height. Put it on a short mast, ~20 cm up, looking down and forward.
"""

import argparse
import math

# HC-SR04 characteristics
BEAM_HALF_DEG = 15.0       # ~30 degree total cone
MIN_RANGE_M = 0.02         # below this the sensor cannot resolve anything
PITCH_SWING_DEG = 5.0      # how much the chassis pitches on rough ground

# How long the car takes to react once the ground goes wrong: the navigator
# needs DOWN_CONFIRM_FRAMES (3) at LOOP_HZ (10) before it believes the reading,
# and then the wheels have to actually stop. Everything below is measured
# against this budget -- it is what turns a mount into a speed limit.
CONFIRM_S = 0.30
BRAKE_S = 0.20
REACT_S = CONFIRM_S + BRAKE_S


def geometry(h_m, tilt_deg, offset_m=0.08, step_m=0.06, hole_m=0.15):
    """
    Where does a sensor at height h, tilted tilt_deg below horizontal, look --
    and can it tell a step or a hole from ordinary chassis pitching?

    An ultrasonic reports the FIRST echo, not the echo on its axis, so the
    number you will actually read comes from the NEAR edge of the cone. That
    is the value to compare against, and it is why NOMINAL must be measured
    rather than computed.

    It is also the right edge to reason about for a HOLE. As the car rolls up
    to a pit, the pit enters the far side of the footprint first -- but the
    nearest echo is still ordinary ground, so the reading does not move. The
    pit only announces itself once it reaches the NEAR edge. Warning distance
    is therefore measured from there, not from the beam axis.

    offset_m is how far the mast sits ahead of the front wheels; it is free
    extra warning distance, so mount at the very front.
    """
    t = math.radians(tilt_deg)
    near_t = math.radians(min(tilt_deg + BEAM_HALF_DEG, 89.9))

    axis_range = h_m / math.sin(t)          # where the beam centre lands
    near_range = h_m / math.sin(near_t)     # what the sensor most likely reports
    lookahead = h_m / math.tan(near_t) + offset_m   # ahead of the front wheels

    # A step raises the ground under the beam; a hole drops it away.
    step_shift = near_range - max(h_m - step_m, 0.0) / math.sin(near_t)
    hole_shift = (h_m + hole_m) / math.sin(near_t) - near_range

    # Chassis pitch changes the tilt angle, and the reading moves with it.
    # dR/dtheta = -h*cos(t)/sin^2(t), converted to metres per degree.
    pitch_noise = abs(h_m * math.cos(near_t) / math.sin(near_t) ** 2
                      * math.radians(1.0)) * PITCH_SWING_DEG

    return {
        'h_m': h_m, 'tilt_deg': tilt_deg,
        'axis_range': axis_range, 'near_range': near_range,
        'lookahead': lookahead,
        'max_speed': lookahead / REACT_S,
        'step_shift': step_shift, 'hole_shift': hole_shift,
        'pitch_noise': pitch_noise,
        # A mount is sound when the step signal clearly beats the pitch noise
        # and the reading is off the blind spot. Warning distance is not a
        # pass/fail -- it converts into a speed limit instead (max_speed).
        'usable': (step_shift > 2.0 * pitch_noise
                   and near_range > 4 * MIN_RANGE_M),
    }


def recommend(g):
    """Suggested navigator constants for a given mount."""
    # Tolerance must sit above the pitch noise but below the step signal.
    tol = max(0.05, min(1.5 * g['pitch_noise'], 0.6 * g['step_shift']))
    return g['near_range'], tol


def print_geometry_table(offset_m, step_m, hole_m):
    print(f"\nGround-sensor geometry   (mast {offset_m*100:.0f} cm ahead of the "
          f"front wheels, step {step_m*100:.0f} cm, hole {hole_m*100:.0f} cm)")
    print("An ultrasonic hears the nearest echo, so 'reads' is the near edge "
          "of the cone.\n")
    print(f"{'mount':22s} {'reads':>7s} {'ahead':>7s} {'max v':>7s} "
          f"{'step':>7s} {'hole':>7s} {'pitch':>7s}  verdict")
    print(f"{'':22s} {'cm':>7s} {'cm':>7s} {'m/s':>7s} "
          f"{'-cm':>7s} {'+cm':>7s} {'+-cm':>7s}")
    print("-" * 82)

    candidates = [
        ("FRONT WALL 3cm @30", 0.03, 30),
        ("FRONT WALL 3cm @45", 0.03, 45),
        ("mast 15cm @30", 0.15, 30),
        ("mast 20cm @30", 0.20, 30),
        ("mast 20cm @35", 0.20, 35),
        ("mast 20cm @45", 0.20, 45),
        ("mast 25cm @30", 0.25, 30),
        ("mast 25cm @35", 0.25, 35),
        ("mast 30cm @35", 0.30, 35),
    ]
    for name, h, tilt in candidates:
        g = geometry(h, tilt, offset_m, step_m, hole_m)
        why = "OK" if g['usable'] else _why_not(g)
        print(f"{name:22s} {g['near_range']*100:7.1f} {g['lookahead']*100:7.1f} "
              f"{g['max_speed']:7.2f} {g['step_shift']*100:7.1f} "
              f"{g['hole_shift']*100:7.1f} {g['pitch_noise']*100:7.1f}  {why}")

    print(f"""
Reading the table
  reads  what the sensor shows on flat ground (calibrate, do not trust this)
  ahead  how far in front of the FRONT WHEELS that patch of ground is
  max v  the speed limit this mount implies: warning distance divided by the
         {REACT_S:.1f} s the car needs to react ({CONFIRM_S:.1f} s to confirm the reading at
         10 Hz, {BRAKE_S:.1f} s to stop). Drive the pit stage slower than this.
  step   how much SHORTER the reading goes over a step up
  hole   how much LONGER it goes over a pit (or the echo vanishes entirely)
  pitch  how much the reading moves on its own when the chassis pitches +-5deg
         -- this is the noise floor, and 'step' must beat it or you get false
         alarms on rough ground

The trade-off: shallow angles look further ahead (higher max v) but ride the
pitch noise and skim off soft mud; steep angles are quiet and reliable but give
less warning. 30-35 degrees at 20-25 cm is the useful band. Height buys you
both -- go as high as the chassis will carry rigidly.""")


def _why_not(g):
    if g['near_range'] <= 4 * MIN_RANGE_M:
        return "NO - too close to the blind spot"
    if g['step_shift'] <= 2.0 * g['pitch_noise']:
        return "NO - lost in pitch noise"
    return "NO"


def print_mount(h_m, tilt_deg, offset_m, step_m, hole_m):
    g = geometry(h_m, tilt_deg, offset_m, step_m, hole_m)
    nominal, tol = recommend(g)
    print(f"\nMount: {h_m*100:.0f} cm above ground, {tilt_deg:.0f} deg below "
          f"horizontal, {offset_m*100:.0f} cm ahead of the front wheels\n")
    print(f"  beam axis meets the ground   {g['axis_range']*100:6.1f} cm slant")
    print(f"  expected flat-ground reading {g['near_range']*100:6.1f} cm "
          f"(near edge of the cone)")
    print(f"  warning distance             {g['lookahead']*100:6.1f} cm "
          f"ahead of the front wheels")
    print(f"  a {step_m*100:.0f} cm step reads          "
          f"{g['step_shift']*100:6.1f} cm shorter")
    print(f"  a {hole_m*100:.0f} cm hole reads         "
          f"{g['hole_shift']*100:6.1f} cm longer (or no echo at all)")
    print(f"  +-5 deg of chassis pitch      {g['pitch_noise']*100:6.1f} cm "
          f"of noise")
    print(f"\n  geometry: {'SOUND' if g['usable'] else _why_not(g)}")
    print(f"  SPEED LIMIT: {g['max_speed']:.2f} m/s -- above this the car "
          f"reaches the pit\n               before it can confirm and stop.")
    print("\nStarting point for course_navigator.py "
          "(then confirm with --measure):")
    print(f"    DOWN_MOUNT_H_M  = {h_m:.2f}")
    print(f"    DOWN_TILT_DEG   = {tilt_deg:.0f}")
    print(f"    DOWN_NOMINAL_M  = {nominal:.2f}")
    print(f"    DOWN_TOLERANCE  = {tol:.2f}")


def measure(trig, echo, seconds, max_m):
    """Sample the fitted sensor on flat ground and report what it really does."""
    import statistics
    import time
    from gpiozero import DistanceSensor

    print(f"Park the car on FLAT ground of the type you will drive on.")
    print(f"Sampling GPIO trig={trig} echo={echo} for {seconds:.0f} s. "
          f"Keep still.\n")
    sensor = DistanceSensor(echo=echo, trigger=trig, max_distance=max_m)
    time.sleep(0.5)

    good, dropouts, t0 = [], 0, time.monotonic()
    while time.monotonic() - t0 < seconds:
        d = sensor.distance
        if d >= max_m - 0.02:
            dropouts += 1                      # no echo came back
        else:
            good.append(d)
        print(f"  {d*100:6.1f} cm   samples={len(good)} dropouts={dropouts}",
              end="\r")
        time.sleep(0.1)
    print()

    n = len(good) + dropouts
    if len(good) < 10:
        print(f"\nOnly {len(good)}/{n} readings came back. The beam is not "
              f"finding the ground:\n"
              f"  - tilt it STEEPER (more perpendicular to the ground), or\n"
              f"  - check the ECHO divider and the 5 V supply.")
        return

    mean = statistics.fmean(good)
    sd = statistics.pstdev(good)
    tol = max(0.05, 4 * sd)
    print(f"\nflat ground: mean {mean*100:.1f} cm   sd {sd*100:.1f} cm   "
          f"range {min(good)*100:.1f}-{max(good)*100:.1f} cm")
    print(f"dropouts (no echo): {dropouts}/{n} = {100.0*dropouts/n:.0f}%")
    if dropouts > n * 0.1:
        print("  ^ that is high. Steepen the tilt -- soft mud scatters a "
              "grazing beam. Dropouts are read as 'hole', so they cost you "
              "false stops.")
    print(f"\nPaste into course_navigator.py:")
    print(f"    DOWN_NOMINAL_M  = {mean:.2f}")
    print(f"    DOWN_TOLERANCE  = {tol:.2f}")
    print("\nNow re-run with --watch and walk the car up to the step and to "
          "the edge of the pit. You want 'step' and 'hole' to appear before "
          "the front wheels get there, and 'flat' the rest of the time.")


def watch(trig, echo, nominal, tol, max_m):
    """Live classification, for walking the car at the step and the pit."""
    import time
    from gpiozero import DistanceSensor

    sensor = DistanceSensor(echo=echo, trigger=trig, max_distance=max_m)
    print(f"flat = {nominal*100:.0f} +- {tol*100:.0f} cm. Ctrl-C to stop.\n")
    try:
        while True:
            d = sensor.distance
            if d >= max_m - 0.02:
                state = "HOLE (no echo)"
            elif d < nominal - tol:
                state = "STEP"
            elif d > nominal + tol:
                state = "HOLE"
            else:
                state = "flat"
            bar = "#" * int(min(d, 1.0) * 50)
            print(f"  {d*100:6.1f} cm  {state:14s} {bar}", end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Size, aim and calibrate the downward ultrasonic.")
    ap.add_argument("--geometry", action="store_true",
                    help="bench mode: compare mounting positions (no hardware)")
    ap.add_argument("--measure", action="store_true",
                    help="on-car: sample flat ground, print the constants")
    ap.add_argument("--watch", action="store_true",
                    help="on-car: live step/hole classification")
    ap.add_argument("--height", type=float, default=0.20,
                    help="mount height above ground, metres (default 0.20)")
    ap.add_argument("--tilt", type=float, default=35.0,
                    help="degrees below horizontal (default 35)")
    ap.add_argument("--offset", type=float, default=0.08,
                    help="how far the mast sits ahead of the front wheels, m")
    ap.add_argument("--step", type=float, default=0.06,
                    help="step height to detect, metres (default 0.06)")
    ap.add_argument("--hole", type=float, default=0.15,
                    help="pit depth to detect, metres (default 0.15)")
    ap.add_argument("--trig", type=int, default=27)
    ap.add_argument("--echo", type=int, default=22)
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--nominal", type=float, default=0.28)
    ap.add_argument("--tolerance", type=float, default=0.07)
    ap.add_argument("--max", type=float, default=1.0, dest="max_m")
    a = ap.parse_args()

    if a.measure:
        measure(a.trig, a.echo, a.seconds, a.max_m)
    elif a.watch:
        watch(a.trig, a.echo, a.nominal, a.tolerance, a.max_m)
    else:
        print_geometry_table(a.offset, a.step, a.hole)
        print_mount(a.height, a.tilt, a.offset, a.step, a.hole)
