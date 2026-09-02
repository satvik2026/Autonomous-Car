"""
Checks on the downward ground sensor: the mount maths, and the debounce.

Both are things you cannot test on demo day. The geometry decides where the
sensor gets bolted -- a decision made once, with a drill -- and the debounce
only misbehaves on ground rough enough to bounce the car, which is exactly
when nobody is watching a terminal.
"""

import unittest

import _load

nav = _load.load("nav", "course_navigator.py")
cg = _load.load("calibrate_ground", "tools/calibrate_ground.py")


class TestMountGeometry(unittest.TestCase):
    """
    The maths behind "put it on a mast, not on the front wall".

    Values are cross-checked against the tables in docs/WIRING.md §2b and
    docs/COURSE_ANALYSIS.md, so if the model changes, the docs stop matching
    and this fails.
    """

    def test_front_wall_mount_is_rejected(self):
        """
        The obvious mounting point -- the 2-3 cm front lip beside the camera --
        must come out unusable, for the stated reason: at that height the
        reading lands inside the sensor's own ~2 cm blind spot.
        """
        g = cg.geometry(0.03, 30)
        self.assertLess(g['near_range'], 4 * cg.MIN_RANGE_M)
        self.assertFalse(g['usable'])
        self.assertIn("blind spot", cg._why_not(g))

    def test_recommended_mount_is_sound(self):
        """20 cm at 35 deg: the mount the docs and the navigator defaults use."""
        g = cg.geometry(0.20, 35)
        self.assertTrue(g['usable'])
        # docs quote 26 cm reading, 25 cm of warning, 0.50 m/s speed limit
        self.assertAlmostEqual(g['near_range'], 0.26, delta=0.01)
        self.assertAlmostEqual(g['lookahead'], 0.25, delta=0.01)
        self.assertAlmostEqual(g['max_speed'], 0.50, delta=0.02)

    def test_step_signal_beats_pitch_noise(self):
        """
        The whole mount is only viable if a real step moves the reading more
        than the car's own bouncing does. Assert the margin, not just the sign.
        """
        g = cg.geometry(0.20, 35)
        self.assertGreater(g['step_shift'], 2.0 * g['pitch_noise'])

    def test_height_buys_warning_distance(self):
        """Height is the lever the docs tell you to pull. Check it pulls."""
        low = cg.geometry(0.15, 35)
        high = cg.geometry(0.25, 35)
        self.assertGreater(high['lookahead'], low['lookahead'])
        self.assertGreater(high['max_speed'], low['max_speed'])

    def test_steeper_tilt_is_quieter_but_shorter_sighted(self):
        """The trade-off the docs describe, asserted in both directions."""
        shallow = cg.geometry(0.20, 30)
        steep = cg.geometry(0.20, 45)
        self.assertLess(steep['pitch_noise'], shallow['pitch_noise'])
        self.assertLess(steep['lookahead'], shallow['lookahead'])

    def test_recommended_tolerance_sits_between_noise_and_signal(self):
        """
        A tolerance below the pitch noise cries wolf; one above the step
        signal is blind to steps. It has to land in between.
        """
        g = cg.geometry(0.20, 35)
        _, tol = cg.recommend(g)
        self.assertGreater(tol, g['pitch_noise'])
        self.assertLess(tol, g['step_shift'])

    def test_navigator_constants_match_their_declared_mount(self):
        """
        DOWN_NOMINAL_M is meant to be MEASURED, so it will not equal theory
        exactly -- but if someone edits the mount height and forgets the
        nominal, the two drift apart silently and every reading is misjudged.
        A loose sanity band catches that without pretending theory is truth.
        """
        g = cg.geometry(nav.DOWN_MOUNT_H_M, nav.DOWN_TILT_DEG)
        self.assertGreater(nav.DOWN_NOMINAL_M, 0.5 * g['near_range'])
        self.assertLess(nav.DOWN_NOMINAL_M, 1.5 * g['near_range'])
        # and the ceiling must be well clear of nominal, or ordinary ground
        # readings would be mistaken for "no echo"
        self.assertGreater(nav.DOWN_MAX_M,
                           nav.DOWN_NOMINAL_M + 3 * nav.DOWN_TOLERANCE)


class FakeSensor:
    """Replays a fixed list of readings in place of a gpiozero DistanceSensor."""

    def __init__(self, readings):
        self.readings = list(readings)

    @property
    def distance(self):
        return self.readings.pop(0)


def run_sequence(readings):
    """Feed readings through Car.ground() and collect the debounced states."""
    car = nav.Car.__new__(nav.Car)          # bypass __init__: it needs GPIO
    car._down_raw, car._down_streak, car._down_state = 'flat', 0, 'flat'
    car.down = FakeSensor(readings)
    return [car.ground()[0] for _ in readings]


class TestGroundDebounce(unittest.TestCase):

    FLAT = 0.26        # matches DOWN_NOMINAL_M
    LONG = 0.40        # well past nominal + tolerance
    SHORT = 0.18       # well under nominal - tolerance
    NO_ECHO = 1.00     # DOWN_MAX_M: nothing came back

    def test_single_spike_is_ignored(self):
        """
        One bad frame must not trigger the emergency stop. Chassis pitch alone
        produces these constantly on rough ground; acting on one would make
        the car back away from nothing, repeatedly.
        """
        states = run_sequence([self.FLAT, self.LONG, self.FLAT, self.LONG,
                               self.FLAT])
        self.assertEqual(states, ['flat'] * 5)

    def test_sustained_long_reading_is_a_hole(self):
        """DOWN_CONFIRM_FRAMES in a row is the real thing."""
        states = run_sequence([self.LONG] * nav.DOWN_CONFIRM_FRAMES)
        self.assertEqual(states[-1], 'hole')
        self.assertEqual(states[:-1], ['flat'] * (nav.DOWN_CONFIRM_FRAMES - 1))

    def test_sustained_no_echo_is_a_hole(self):
        """
        A deep pit scatters the beam and returns nothing, which reads as
        max_distance -- identical to a dropout off soft mud. Both stop the car:
        a needless stop costs seconds, the pit costs the run.
        """
        states = run_sequence([self.NO_ECHO] * nav.DOWN_CONFIRM_FRAMES)
        self.assertEqual(states[-1], 'hole')

    def test_sustained_short_reading_is_a_step(self):
        states = run_sequence([self.SHORT] * nav.DOWN_CONFIRM_FRAMES)
        self.assertEqual(states[-1], 'step')

    def test_one_good_frame_clears_the_state(self):
        """
        Recovery is deliberately not debounced: by the time it matters the car
        has already stopped and backed off, so waiting three more frames only
        delays resuming.
        """
        seq = [self.LONG] * nav.DOWN_CONFIRM_FRAMES + [self.FLAT]
        self.assertEqual(run_sequence(seq)[-1], 'flat')

    def test_unfitted_sensor_reports_nothing(self):
        """
        With no sensor the navigator must get None, not a fabricated 'flat' --
        the run loop uses it to say plainly that nothing can see the pit.
        """
        car = nav.Car.__new__(nav.Car)
        car.down = None
        car._down_raw, car._down_streak, car._down_state = 'flat', 0, 'flat'
        self.assertEqual(car.ground(), (None, None))


if __name__ == "__main__":
    unittest.main()
