"""
mission.py -- the course SEQUENCER (the Q3 answer).

HOW YOU BUILD A ROUTE ORDER WITHOUT GPS
=======================================
Your example was:
    "first the entire mud course, then U-turn and tackle the sloped hills,
     avoid the big compost pit, then enter the gravel pit and cross it to
     drive on the cement, then onto the football court OR the cement path."

That is a SEQUENCE OF STAGES, and each stage is really three things:

    1. a BEHAVIOUR     -- what to do while in this stage
                          (follow the open surface / turn in place / cross a
                           step / drive straight for a while)
    2. an EXIT TEST    -- how the car knows the stage is finished
                          (surface changed to gravel / landmark seen /
                           heading changed 180 deg / travelled long enough)
    3. GUARDS          -- what must never happen during this stage
                          (never enter vegetation, never hit anything)

So the "route" is not a map and not a set of coordinates. It is an ORDERED
LIST OF STAGES, each ending on a condition the car can actually sense. This
is called a finite-state machine, and it is the correct tool here because
your course is a chain of distinguishable surfaces -- mud, gravel, cement,
grass -- which the camera can identify (see vision/terrain.py).

WHAT THE CAR CAN SENSE (and therefore what an exit test may use)
----------------------------------------------------------------
  surface     the terrain mix from the camera:  mud / hard / gravel / veg
              (measured, robust: mud court 0.90 mud; gravel 0.87 hard;
               cement 0.94 hard; lawn 0.82 veg)
  landmark    a coloured marker or an ORB landmark (vision/landmarks.py)
  timeout     seconds elapsed in the stage  -- the universal fallback
  distance    ultrasonic range (e.g. "wall ahead within 60 cm" = end of court)
  blocked     the terrain classifier says no drivable column exists

DELIBERATE LIMITATION, STATED HONESTLY
--------------------------------------
Without an IMU/compass the car cannot know its heading, so "U-turn" cannot be
"rotate exactly 180 degrees". It is executed as "pivot for N seconds", which is
open-loop and will drift a few degrees run to run. If you want a repeatable
U-turn, add a cheap MPU-6050 IMU (~2 USD) and the turn becomes closed-loop.
Everything else in the sequence is closed-loop on the camera and does not need
it. This is flagged again in docs/COURSE_ANALYSIS.md.

RESULT: what you actually see when it runs
------------------------------------------
The console prints a live stage trace, e.g.

    [1/6] mud_course      surf=mud   veg=0.31 steer=-0.12  t=12.4s
    [1/6] mud_course      surf=mud   veg=0.29 steer=+0.05  t=13.4s
    -> EXIT mud_course (surface==gravel held 1.5s)
    [2/6] gravel_crossing surf=hard  veg=0.06 steer=+0.00  t=0.4s

so you can watch it move through the sequence, and afterwards you have a log
of exactly where each transition fired.
"""

import json
import time


class Stage:
    """One step of the course."""

    def __init__(self, spec):
        self.name = spec['name']
        self.behaviour = spec.get('behaviour', 'follow')
        self.speed = float(spec.get('speed', 0.55))
        self.exit = spec.get('exit', {})
        self.keepout_bias = float(spec.get('keepout_bias', 0.0))
        # Speed used to punch across a step/ramp in the `cross_step` behaviour.
        # Higher than cruising speed on purpose: a step is cleared with
        # momentum, whereas creeping stalls with the wheel against the riser.
        self.burst_speed = float(spec.get('burst_speed', 0.85))
        self.notes = spec.get('notes', '')
        # exit conditions
        self.exit_surface = self.exit.get('surface')
        self.exit_hold = float(self.exit.get('hold_s', 1.5))
        self.exit_landmark = self.exit.get('landmark')
        self.exit_marker = self.exit.get('marker')
        self.exit_timeout = self.exit.get('timeout_s')
        self.exit_near = self.exit.get('obstacle_within_m')
        self.min_time = float(self.exit.get('min_time_s', 1.0))

    def __repr__(self):
        return f"<Stage {self.name} ({self.behaviour})>"


class Mission:
    """
    Runs an ordered list of stages. Call update() once per control loop with
    what the car currently senses; it returns the active stage and whether it
    just advanced.
    """

    def __init__(self, stages, zones):
        self.stages = [Stage(s) for s in stages]
        self.zones = zones
        self.i = 0
        self.t0 = time.monotonic()
        self._hold_since = None
        self.finished = False
        self.log = []

    @classmethod
    def load(cls, path):
        with open(path) as f:
            data = json.load(f)
        return cls(data['stages'], data.get('zones', {}))

    @property
    def stage(self):
        return self.stages[self.i] if not self.finished else None

    def elapsed(self):
        return time.monotonic() - self.t0

    def _exit_met(self, surface, landmark, marker, distance_m):
        """Evaluate the current stage's exit test."""
        s = self.stage
        if self.elapsed() < s.min_time:
            return False, None

        # timeout is always available as a fallback
        if s.exit_timeout is not None and self.elapsed() >= float(s.exit_timeout):
            return True, f"timeout {s.exit_timeout}s"

        if s.exit_near is not None and distance_m is not None \
                and distance_m <= float(s.exit_near):
            return True, f"obstacle within {s.exit_near}m"

        if s.exit_landmark and landmark == s.exit_landmark:
            return True, f"landmark '{landmark}'"

        if s.exit_marker and marker == s.exit_marker:
            return True, f"marker '{marker}'"

        if s.exit_surface:
            # surface must be held continuously -- a single frame of gravel
            # while crossing a puddle must not advance the mission
            if surface == s.exit_surface:
                if self._hold_since is None:
                    self._hold_since = time.monotonic()
                elif time.monotonic() - self._hold_since >= s.exit_hold:
                    return True, f"surface=={surface} held {s.exit_hold}s"
            else:
                self._hold_since = None
        return False, None

    def update(self, surface=None, landmark=None, marker=None, distance_m=None):
        """
        Advance the mission if the current stage's exit test is satisfied.
        Returns (stage, advanced: bool, reason: str|None).
        """
        if self.finished:
            return None, False, None
        met, reason = self._exit_met(surface, landmark, marker, distance_m)
        if not met:
            return self.stage, False, None

        done = self.stage.name
        self.log.append({'stage': done, 'reason': reason,
                         'duration_s': round(self.elapsed(), 2)})
        self.i += 1
        self.t0 = time.monotonic()
        self._hold_since = None
        if self.i >= len(self.stages):
            self.finished = True
            return None, True, reason
        return self.stage, True, reason

    def progress(self):
        return f"[{min(self.i + 1, len(self.stages))}/{len(self.stages)}]"
