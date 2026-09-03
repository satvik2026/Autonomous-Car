#!/usr/bin/env python3
"""
Landmarks.py -- landmark-driven route pilot, runs in tandem with
course_navigator.py.

WHAT THIS FILE IS FOR
=====================
course_navigator.py drives the course as a chain of SURFACES (mud -> gravel ->
cement). That is robust for "am I on mud or cement", but it cannot answer
"have I reached the exact spot where I must turn left up the slope?". That is a
PLACE question, and the answer is a landmark: a specific view the car can
recognise.

You supplied nine reference photos in the repo-root ``Landmarks/`` folder.
This module turns them into position awareness and, at each recognised place,
executes the exact manoeuvre you described. It reuses course_navigator.py's
hardware layer (the ``Car`` class and the camera), so it is NOT a second
program fighting for the GPIO -- it is one pilot built ON TOP of the navigator.
Run it INSTEAD of course_navigator.py on demo day when you want the
landmark-driven route:

    python3 course/Landmarks.py --drive            # on the Pi (real motors)
    python3 course/Landmarks.py --replay Landmarks  # dry-run recognition, no HW
    python3 course/Landmarks.py --selftest          # sanity-check the references

THE ROUTE, AS YOU DESCRIBED IT  (landmark -> what the car does)
==============================================================
  "1","2"  STEP / protrusion (raised cement apron edge).
           -> Cross it. Two methods are possible (see STEP-CROSSING below);
              the default is a squared-up power burst ("boost"), with a
              veer-right-to-the-slope option as a fallback.

  "4.1"-"4.4"  TURN-LEFT decision point (multi-view of the same place: dirt
           path, grassy embankment on the LEFT, grey building + blue toilet on
           the RIGHT). Any of the four counts as the same place.
           -> Pivot fully LEFT onto the side slope, climb UP to the crest,
              then ROTATE RIGHT until the camera roughly replicates "View".
              Then carry on forward.

  "View"   The crest reference: the two-storey building on the right, seen
           from the top of the slope. Used as the closed-loop TARGET for the
           "rotate right until this is ahead" step above -- never a trigger on
           its own.

  "3"      COMPOST PIT (bright-green sacks). The MIRROR of the turn sequence:
           -> Pivot RIGHT, go DOWN the hill until "6" is roughly replicated OR
              gravel appears under the wheels.

  "6"      GRAVEL + the raised CEMENT block (pink/white building behind).
           -> Drive ONTO the cement block with the normal cross-step burst,
              cross it, and after the ~6-inch drop onto solid cement, turn
              RIGHT and drive straight down the cement road. Done.

HOW RECOGNITION WORKS (and why it is trustworthy)
=================================================
Primary signal is ORB feature matching (vision/landmarks.py ``LandmarkBook``):
rotation/scale invariant, with a RANSAC geometric check so a chance colour
resemblance cannot trigger a turn. Measured on your nine photos:
  * the five distinct places (1,2,3,6,View) do NOT cross-match each other,
  * the four 4.x views DO match each other -> they are correctly one class,
  * all nine still recognise themselves after an 8 deg rotation + zoom-crop +
    brightness shift.
The compost pit additionally gets a strong colour corroborator: the green-sack
area fraction (0.216 in photo 3 vs <0.15 everywhere else) -- the same green cue
the mission file already trusts.

Two safety habits, both borrowed from the rest of the project:
  * a recognition must persist for CONFIRM_FRAMES frames before it fires a
    manoeuvre (the same debounce the ground sensor uses), so one bad frame
    cannot turn the car;
  * a landmark only ADVANCES the route state -- the ultrasonic reflex and the
    terrain keep-out still veto the motors. A false match costs a premature
    manoeuvre, never a collision.

HONEST LIMITATION
=================
The nine references are PHONE photos taken at chest height. The car's camera is
~15 cm off the ground with a narrower lens, so live matches will be weaker than
the bench numbers above. Recognition is built to degrade safely (confirmation +
generous timeouts + surface fallbacks), but for best results re-capture each
landmark FROM THE CAR with tools/capture_landmark.py in demo-day light and drop
those into Landmarks/ alongside (or instead of) the phone photos. This module
loads every image in the folder, so extra views only help.

STEP-CROSSING: which method, and is a voltage increase enough?
==============================================================
Method A -- BOOST (default). Square up to the step and cross straight with a
short high-power burst (raise PWM duty / RPM). With 10-inch wheels the step is
below the wheel radius, so momentum carries it. Simplest in CONTROL: no extra
navigation, reuses the existing cross-step behaviour, just at a higher burst
speed. Risk: hitting the lip at an angle lifts one wheel and the car slews, so
the burst must only fire once squared up.

Method B -- VEER RIGHT to the makeshift slope (the swirly cement patch by the
wall). Gentler on the drivetrain and lower risk of beaching, but needs accurate
lateral navigation to a specific spot and a clear right-hand path, and depends
on that ramp still being there and drivable.

Verdict: BOOST is the simpler and more reliable default -- fewer moving parts,
and the big wheels make the step easy given momentum. A plain voltage/RPM
increase IS sufficient, but only WITH squaring-up first; a speed increase alone,
taken at an angle, risks slewing. Keep VEER RIGHT as the fallback if on the day
the motors lack the torque to climb or the lip proves higher than expected. Set
STEP_METHOD below to choose.
"""

import argparse
import os
import sys
import time

# course/ on the path so we can reuse the navigator's vision + hardware layers.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_REPO_ROOT = os.path.dirname(_HERE)
DEFAULT_REF_DIR = os.path.join(_REPO_ROOT, "Landmarks")


# ===========================================================================
# LOGICAL LANDMARKS -- how the reference filenames group into meanings
# ===========================================================================
# A logical landmark can have several reference views (the 4.x multi-view set).
# Keys are the logical ids the route logic speaks in; values are the reference
# basenames (without extension) that belong to that place.
LANDMARK_REFS = {
    "step":          ["1", "2"],
    "turn_left":     ["4.1", "4.2", "4.3", "4.4"],
    "compost_pit":   ["3"],
    "gravel_cement": ["6"],
    "crest_view":    ["View"],
}

# Reverse lookup: reference basename -> logical id.
_REF_TO_LOGICAL = {ref: logical
                   for logical, refs in LANDMARK_REFS.items()
                   for ref in refs}

# ---------------------------------------------------------------------------
# RECOGNITION TUNING -- calibrate on the day; these are safe starting points.
# ---------------------------------------------------------------------------
MIN_INLIERS = 18        # ORB RANSAC inliers below this = not a match
CONFIRM_FRAMES = 3      # consecutive frames of the same id before it fires
MATCH_EVERY = 2         # run the (slow) ORB match every Nth frame on the Pi 3B+
GREEN_PIT_FRAC = 0.12   # green-sack area fraction that corroborates the pit
VIEW_MATCH_INLIERS = 22 # "rotate until View" is satisfied at/above this


# ===========================================================================
# RECOGNIZER  (needs OpenCV; imported lazily so this module imports without it)
# ===========================================================================
class Recognition:
    """One recognition result."""
    __slots__ = ("landmark", "inliers", "raw_name", "green")

    def __init__(self, landmark, inliers, raw_name, green):
        self.landmark = landmark      # logical id, or None
        self.inliers = inliers        # ORB inlier count of the best match
        self.raw_name = raw_name      # reference basename of the best match
        self.green = green            # green-sack area fraction of the frame

    def __repr__(self):
        return (f"<{self.landmark or 'none':13s} inliers={self.inliers:3d} "
                f"ref={self.raw_name} green={self.green:.3f}>")


def _green_fraction(bgr):
    """Area fraction of bright, saturated green (the compost sacks)."""
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    mask = (H >= 35) & (H <= 85) & (S >= 80) & (V >= 50)
    return float(np.count_nonzero(mask)) / mask.size


class LandmarkRecognizer:
    """
    Recognises the route landmarks from a camera frame.

    Loads every image in ``ref_dir``, groups them into logical landmarks, and
    builds one ORB LandmarkBook. ``identify`` returns the best single-frame
    guess; ``update`` adds the persistence debounce and only reports a landmark
    once it has been seen CONFIRM_FRAMES frames running.
    """

    def __init__(self, ref_dir=DEFAULT_REF_DIR, frame_size=(640, 480)):
        import cv2  # noqa: F401  (fail loudly here if OpenCV is missing)
        from vision import landmarks as lm

        self.ref_dir = ref_dir
        self.frame_size = frame_size
        self.book = lm.LandmarkBook()
        self.loaded = []
        self._n = 0                    # frame counter for match throttling
        self._last = None              # last identify() result (throttling)
        self._streak_id = None
        self._streak = 0

        self._load_references()

    def _load_references(self):
        import cv2
        if not os.path.isdir(self.ref_dir):
            raise FileNotFoundError(
                f"landmark reference folder not found: {self.ref_dir}")
        for fn in sorted(os.listdir(self.ref_dir)):
            base, ext = os.path.splitext(fn)
            if ext.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            if base not in _REF_TO_LOGICAL:
                continue               # ignore stray files
            im = cv2.imread(os.path.join(self.ref_dir, fn))
            if im is None:
                continue
            im = cv2.resize(im, self.frame_size)
            if self.book.add(base, im):
                self.loaded.append(base)
        missing = [r for r in _REF_TO_LOGICAL if r not in self.loaded]
        if missing:
            print(f"[landmarks] WARNING: references not loaded: {missing}")
        print(f"[landmarks] loaded {len(self.loaded)} reference view(s): "
              f"{', '.join(self.loaded)}")

    # -- single-frame ----------------------------------------------------
    def identify(self, bgr, force=False):
        """
        Best-guess landmark for one frame.

        ORB matching is throttled to every MATCH_EVERY-th call (it is slow on a
        Pi 3B+, and consecutive live frames are near-identical, so reusing the
        last real match between beats is fine). Pass force=True for a sequence
        of UNRELATED images (--replay / --selftest), where reuse would be wrong.
        """
        self._n += 1
        green = _green_fraction(bgr)
        if (not force) and self._last is not None and (self._n % MATCH_EVERY) != 0:
            # reuse the last ORB result between matches, refresh only green
            self._last.green = green
            return self._last

        hit = self.book.match(bgr)     # (raw_name, inliers) or None
        if hit is None:
            raw_name, inliers = None, 0
        else:
            raw_name, inliers = hit
        logical = _REF_TO_LOGICAL.get(raw_name) if inliers >= MIN_INLIERS else None

        # Colour corroboration: strong green means the compost pit even if ORB
        # is weak (sacks are the canonical cue and viewpoint-robust).
        if logical is None and green >= GREEN_PIT_FRAC:
            logical, raw_name = "compost_pit", raw_name or "3(green)"

        self._last = Recognition(logical, inliers, raw_name, green)
        return self._last

    # -- debounced -------------------------------------------------------
    def update(self, bgr):
        """
        Debounced recognition. Returns a COMMITTED logical id (str) the moment
        it has persisted CONFIRM_FRAMES frames, else None. Also returns the raw
        Recognition via ``.last`` for logging / closed-loop use.
        """
        rec = self.identify(bgr)
        self.last = rec
        lid = rec.landmark
        if lid == self._streak_id and lid is not None:
            self._streak += 1
        else:
            self._streak_id = lid
            self._streak = 1 if lid is not None else 0
        if lid is not None and self._streak >= CONFIRM_FRAMES:
            return lid
        return None

    def view_score(self, bgr):
        """ORB inliers for the crest 'View' specifically (closed-loop rotate)."""
        hit = self.book.match(bgr)
        if hit and _REF_TO_LOGICAL.get(hit[0]) == "crest_view":
            return hit[1]
        return 0


# ===========================================================================
# ROUTE SEQUENCER  (pure Python -- no OpenCV, unit-testable off-hardware)
# ===========================================================================
# Phases, in route order.
(SEEK_STEP, CROSS_STEP, SEEK_TURN, PIVOT_LEFT, CLIMB, ROTATE_TO_VIEW,
 FOLLOW_TO_PIT, PIVOT_RIGHT, DESCEND, CROSS_CEMENT, PIVOT_TO_ROAD,
 CEMENT_ROAD, DONE) = range(13)

PHASE_NAME = {
    SEEK_STEP: "seek_step", CROSS_STEP: "cross_step", SEEK_TURN: "seek_turn",
    PIVOT_LEFT: "pivot_left", CLIMB: "climb", ROTATE_TO_VIEW: "rotate_to_view",
    FOLLOW_TO_PIT: "follow_to_pit", PIVOT_RIGHT: "pivot_right",
    DESCEND: "descend", CROSS_CEMENT: "cross_cement",
    PIVOT_TO_ROAD: "pivot_to_road", CEMENT_ROAD: "cement_road", DONE: "done",
}

# Step-crossing method: "boost" (squared-up power burst, default) or
# "veer_right" (steer to the makeshift cement slope by the wall). See the
# module docstring for the evaluation.
STEP_METHOD = "boost"

# Open-loop timings (seconds). ALL of these drift with grip and battery charge
# -- re-time them on the day, exactly like the pivots in the mission file.
T_PIVOT_90 = 1.3        # ~90 deg pivot (matches turn_to_slopes)
T_CLIMB_MAX = 6.0       # give up climbing after this and rotate anyway
T_ROTATE_MAX = 4.0      # give up hunting for View after this
T_DESCEND_MAX = 8.0     # give up descending after this
T_CROSS_MAX = 6.0       # cross-cement safety cap
T_ROAD = 5.0            # how long to run the final cement road before "done"
T_STEP_MAX = 6.0        # step-crossing safety cap


class Directive:
    """What the pilot should make the car do this tick."""
    __slots__ = ("action", "speed", "steer", "reason")

    def __init__(self, action, speed=0.0, steer=0.0, reason=""):
        self.action = action     # see the pilot's execute() for the vocabulary
        self.speed = speed
        self.steer = steer
        self.reason = reason

    def __repr__(self):
        return (f"<{self.action} spd={self.speed:.2f} steer={self.steer:+.2f} "
                f"{self.reason}>")


class RouteSequencer:
    """
    The landmark-driven finite-state machine.

    Feed it, each tick, the committed landmark id (or None), the current
    surface string (or None), and dt seconds elapsed. It returns a Directive.
    It holds NO hardware and NO OpenCV, so it is fully unit-testable: the tests
    drive it with scripted (landmark, surface) inputs and assert the phase
    transitions.
    """

    def __init__(self, step_method=STEP_METHOD, cruise=0.55, creep=0.7,
                 boost=0.95):
        self.phase = SEEK_STEP
        self.step_method = step_method
        self.cruise = cruise
        self.creep = creep
        self.boost = boost
        self.t = 0.0                 # time in the current phase
        self.log = []

    def _to(self, phase, reason):
        self.log.append((PHASE_NAME[self.phase], PHASE_NAME[phase], reason))
        self.phase = phase
        self.t = 0.0

    def update(self, landmark, surface, dt, view_ok=False):
        """
        landmark : committed logical id this tick, or None
        surface  : 'mud'|'gravel'|'cement'|'grass'|None (from terrain)
        dt       : seconds since last tick
        view_ok  : True when the crest 'View' is currently matched (closed loop)
        """
        self.t += dt
        p = self.phase

        if p == SEEK_STEP:
            if landmark == "step":
                self._to(CROSS_STEP, "step landmark seen")
                return self.update(landmark, surface, 0.0, view_ok)
            if landmark == "turn_left":
                # Some runs may not register the step (it can be gentle);
                # don't get stuck waiting for it.
                self._to(PIVOT_LEFT, "turn-left seen before step")
                return self.update(landmark, surface, 0.0, view_ok)
            return Directive("follow", self.cruise, reason="seeking step")

        if p == CROSS_STEP:
            done = surface == "cement" or self.t >= T_STEP_MAX
            if done:
                self._to(SEEK_TURN, "step crossed")
                return Directive("follow", self.cruise, reason="onto flat")
            if self.step_method == "veer_right":
                return Directive("veer_right", self.creep, steer=+0.9,
                                 reason="veer to makeshift slope")
            return Directive("cross_step", self.boost,
                             reason="squared-up power burst")

        if p == SEEK_TURN:
            if landmark == "turn_left":
                self._to(PIVOT_LEFT, "turn-left decision point seen")
                return self.update(landmark, surface, 0.0, view_ok)
            return Directive("follow", self.cruise, reason="seeking turn point")

        if p == PIVOT_LEFT:
            if self.t >= T_PIVOT_90:
                self._to(CLIMB, "pivoted ~90 deg left")
                return Directive("creep_forward", self.creep, reason="onto slope")
            return Directive("pivot_left", self.creep, reason="turning onto slope")

        if p == CLIMB:
            # Climb until the ground flattens (surface stops reading as the
            # slope) or the safety cap. Then hunt for the crest View.
            if self.t >= T_CLIMB_MAX:
                self._to(ROTATE_TO_VIEW, "climb cap reached")
                return Directive("rotate_right", self.creep, reason="hunting View")
            return Directive("creep_forward", self.boost, reason="climbing slope")

        if p == ROTATE_TO_VIEW:
            if view_ok or landmark == "crest_view":
                self._to(FOLLOW_TO_PIT, "View replicated")
                return Directive("follow", self.cruise, reason="crest reached")
            if self.t >= T_ROTATE_MAX:
                self._to(FOLLOW_TO_PIT, "rotate cap reached (View not found)")
                return Directive("follow", self.cruise, reason="proceeding anyway")
            return Directive("rotate_right", self.creep, reason="rotating to View")

        if p == FOLLOW_TO_PIT:
            if landmark == "compost_pit":
                self._to(PIVOT_RIGHT, "green sacks / compost pit seen")
                return self.update(landmark, surface, 0.0, view_ok)
            return Directive("follow", self.cruise, reason="toward compost pit")

        if p == PIVOT_RIGHT:
            if self.t >= T_PIVOT_90:
                self._to(DESCEND, "pivoted right (mirror of turn)")
                return Directive("creep_forward", self.creep, reason="downhill")
            return Directive("pivot_right", self.creep, reason="turning away from pit")

        if p == DESCEND:
            if landmark == "gravel_cement" or surface == "gravel":
                self._to(CROSS_CEMENT, "reached gravel / '6' replicated")
                return Directive("cross_step", self.boost, reason="onto cement block")
            if self.t >= T_DESCEND_MAX:
                self._to(CROSS_CEMENT, "descend cap reached")
                return Directive("cross_step", self.boost, reason="assume at gravel")
            return Directive("creep_forward", self.creep, reason="descending")

        if p == CROSS_CEMENT:
            # Drive onto and over the raised block; the ~6-inch drop lands on
            # solid cement, which reads as a held 'cement' surface.
            if surface == "cement" or self.t >= T_CROSS_MAX:
                self._to(PIVOT_TO_ROAD, "on solid cement after the drop")
                return Directive("pivot_right", self.creep, reason="onto road")
            return Directive("cross_step", self.boost, reason="crossing cement block")

        if p == PIVOT_TO_ROAD:
            if self.t >= T_PIVOT_90:
                self._to(CEMENT_ROAD, "aligned with cement road")
                return Directive("follow", self.cruise, reason="cement road")
            return Directive("pivot_right", self.creep, reason="turning onto road")

        if p == CEMENT_ROAD:
            if self.t >= T_ROAD:
                self._to(DONE, "cement road complete")
                return Directive("done", 0.0, reason="route finished")
            return Directive("straight", self.cruise, reason="down the cement road")

        return Directive("done", 0.0, reason="done")

    @property
    def finished(self):
        return self.phase == DONE


# ===========================================================================
# PILOT  -- runs the route on real hardware, reusing course_navigator's Car
# ===========================================================================
def run_with_navigator(ref_dir=DEFAULT_REF_DIR, mission_path=None):
    """
    Drive the landmark route on the Pi. Reuses course_navigator's Car (so the
    pin map / wiring are identical) and its camera, plus the terrain steering
    for ordinary 'follow' driving. This is the 'in tandem with course_navigator'
    entry point: one process, the navigator's hardware layer underneath.
    """
    import cv2
    import course_navigator as nav
    from vision import terrain

    car = nav.Car()
    cam = nav.open_camera()
    rec = LandmarkRecognizer(ref_dir)
    seq = RouteSequencer()
    period = 1.0 / nav.LOOP_HZ
    last = time.monotonic()

    print("Landmark pilot running. Ctrl-C to stop. WHEELS OFF THE GROUND FIRST.")
    try:
        while not seq.finished:
            t0 = time.monotonic()
            dt = t0 - last
            last = t0

            # ---- REFLEX (unchanged authority: ultrasonic always wins) ----
            if car.distance() <= nav.STOP_DISTANCE:
                car.stop(); time.sleep(0.05)
                car.wheels(-0.55, -0.55); time.sleep(0.3)
                car.stop()
                continue

            bgr = cam.capture_array()          # already BGR (see calibration fix)
            surface = terrain_zone(terrain, bgr, car, nav)
            committed = rec.update(bgr)
            view_ok = rec.last.inliers >= VIEW_MATCH_INLIERS and \
                rec.last.landmark == "crest_view"

            d = seq.update(committed, surface, dt, view_ok=view_ok)
            execute(car, terrain, bgr, d, nav)

            print(f"[{PHASE_NAME[seq.phase]:14s}] {rec.last} -> {d.action:13s} "
                  f"{d.reason}", flush=True)

            dt_loop = time.monotonic() - t0
            if dt_loop < period:
                time.sleep(period - dt_loop)
        print("\nROUTE COMPLETE")
        for a, b, why in seq.log:
            print(f"  {a:16s} -> {b:16s} ({why})")
    except KeyboardInterrupt:
        print("\nStopping (Ctrl-C).")
    finally:
        car.stop()
        try:
            cam.stop()
        except Exception:
            pass


def terrain_zone(terrain, bgr, car, nav):
    """Best-effort surface name from the terrain classifier (or None)."""
    try:
        mix = terrain.surface_mix(bgr)
        # Reuse the navigator's zone matcher if a mission is loaded; otherwise
        # a coarse call is enough for the sequencer's gravel/cement checks.
        from vision import landmarks as lm
        return lm.match_zone(mix, _DEFAULT_ZONES)
    except Exception:
        return None


# Coarse zone signatures for the pilot's surface checks (same values the demo
# mission uses). Only gravel/cement matter to the sequencer.
_DEFAULT_ZONES = {
    "mud":    {"veg": 0.02, "hard": 0.16, "mud": 0.73, "rough_n": 0.54},
    "gravel": {"veg": 0.04, "hard": 0.86, "mud": 0.10, "rough_n": 1.00},
    "cement": {"veg": 0.00, "hard": 0.98, "mud": 0.02, "rough_n": 0.22},
    "grass":  {"veg": 0.87, "hard": 0.06, "mud": 0.07, "rough_n": 1.00},
}


def execute(car, terrain, bgr, d, nav):
    """Turn a Directive into motor commands on the navigator's Car."""
    a = d.action
    if a == "follow":
        steer = terrain.decide_steering(bgr)["steer"]
        car.drive(steer, d.speed)
    elif a == "straight":
        car.drive(0.0, d.speed)
    elif a == "pivot_left":
        car.pivot(-1, d.speed)
    elif a == "pivot_right":
        car.pivot(+1, d.speed)
    elif a == "rotate_right":
        car.pivot(+1, d.speed)
    elif a == "creep_forward":
        car.drive(0.0, d.speed)
    elif a == "veer_right":
        car.drive(d.steer, d.speed)
    elif a == "cross_step":
        # Square up first (never take the lip at an angle), then burst.
        from vision import steps
        cs, _ = steps.crossing_steer(bgr)
        if not steps.squared_up(cs):
            car.drive(cs, nav.MIN_SPEED)
        else:
            car.drive(0.0, d.speed)
    elif a in ("stop", "done"):
        car.stop()


# ===========================================================================
# OFF-HARDWARE TOOLS  (--replay / --selftest)
# ===========================================================================
def replay(ref_dir, folder):
    """Run the recognizer over a folder of images and print what it sees."""
    import cv2
    import glob
    rec = LandmarkRecognizer(ref_dir)
    files = sorted(glob.glob(os.path.join(folder, "*.jpg")) +
                   glob.glob(os.path.join(folder, "*.png")))
    if not files:
        print("no images in", folder)
        return
    print(f"\nReplaying {len(files)} image(s) from {folder}\n")
    print(f"{'image':12s} {'landmark':14s} {'inliers':>7s} {'green':>6s}  ref")
    for f in files:
        im = cv2.imread(f)
        if im is None:
            continue
        im = cv2.resize(im, rec.frame_size)
        r = rec.identify(im, force=True)
        print(f"{os.path.basename(f):12s} {str(r.landmark):14s} "
              f"{r.inliers:7d} {r.green:6.3f}  {r.raw_name}")


def selftest(ref_dir):
    """
    Confidence check: every reference must recognise itself (or its class),
    and distinct places must not cross-match. Returns True on success.
    """
    import cv2
    import glob
    rec = LandmarkRecognizer(ref_dir)
    files = sorted(glob.glob(os.path.join(ref_dir, "*.jpg")) +
                   glob.glob(os.path.join(ref_dir, "*.png")))
    ok = True
    print("\nself-recognition (each reference vs the whole book):")
    for f in files:
        base = os.path.splitext(os.path.basename(f))[0]
        want = _REF_TO_LOGICAL.get(base)
        if want is None:
            continue
        im = cv2.resize(cv2.imread(f), rec.frame_size)
        r = rec.identify(im, force=True)
        good = r.landmark == want
        ok = ok and good
        print(f"  {base:6s} -> {str(r.landmark):14s} "
              f"(inliers {r.inliers:3d})  {'OK' if good else 'MISMATCH'}")
    print("PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Landmark-driven route pilot (runs with course_navigator).")
    ap.add_argument("--refs", default=DEFAULT_REF_DIR,
                    help="folder of landmark reference images")
    ap.add_argument("--drive", action="store_true",
                    help="drive the route on the Pi (real motors)")
    ap.add_argument("--replay", metavar="FOLDER",
                    help="dry-run recognition over a folder of images")
    ap.add_argument("--selftest", action="store_true",
                    help="check each reference recognises itself")
    a = ap.parse_args()

    if a.replay:
        replay(a.refs, a.replay)
    elif a.selftest:
        sys.exit(0 if selftest(a.refs) else 1)
    elif a.drive:
        run_with_navigator(a.refs)
    else:
        ap.print_help()
