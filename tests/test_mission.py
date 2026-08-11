"""
Checks on the mission file -- the file you actually edit before a run.

These are not unit tests of clever logic. They are the checks that catch the
mistakes that would only show up on the course, in front of people: a stage
that can never end, a colour cue whose name no longer exists, a typo'd
behaviour that silently falls through to "follow".
"""

import json
import unittest

import _load

mission_mod = _load.load("mission", "mission.py")
landmarks = _load.load("landmarks", "vision/landmarks.py")

BEHAVIOURS = {'follow', 'creep', 'straight', 'cross_step',
              'pivot_left', 'pivot_right'}


class TestDemoMission(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(_load.mission_path()) as f:
            cls.raw = json.load(f)
        cls.mission = mission_mod.Mission.load(_load.mission_path())

    def test_every_stage_has_a_timeout(self):
        """
        The docs promise this on every page, so make the repo keep the promise.
        A stage whose only exit is a surface change or a colour cue hangs the
        run forever if that cue never comes -- which, with nothing placed on
        the course, is a real possibility rather than a theoretical one.
        """
        for stage in self.mission.stages:
            with self.subTest(stage=stage.name):
                self.assertIsNotNone(stage.exit_timeout,
                                     f"{stage.name} can never time out")
                self.assertGreater(stage.exit_timeout, 0)

    def test_min_time_below_timeout(self):
        """min_time_s >= timeout_s would make the stage unexitable."""
        for stage in self.mission.stages:
            with self.subTest(stage=stage.name):
                self.assertLess(stage.min_time, stage.exit_timeout,
                                f"{stage.name}: min_time_s >= timeout_s")

    def test_behaviours_are_real(self):
        """
        A misspelled behaviour is not an error at runtime -- the navigator's
        if/elif chain just falls through to ordinary following. That is the
        kind of bug you discover by watching the car drive straight into
        something it was supposed to pivot away from.
        """
        for stage in self.mission.stages:
            with self.subTest(stage=stage.name):
                self.assertIn(stage.behaviour, BEHAVIOURS)

    def test_colour_cues_exist(self):
        """
        Every `marker` exit must name a real entry in MARKER_COLOURS.

        This is the regression guard for the no-placed-markers change:
        `pink_marker` was removed because a placed cone is not an option on
        this course, and a mission still referencing it would raise KeyError
        mid-run, inside the perception loop.
        """
        for stage in self.mission.stages:
            if stage.exit_marker:
                with self.subTest(stage=stage.name):
                    self.assertIn(stage.exit_marker, landmarks.MARKER_COLOURS)

    def test_speeds_in_range(self):
        """Throttle fractions, not m/s: anything outside 0..1 is a mistake."""
        for stage in self.mission.stages:
            with self.subTest(stage=stage.name):
                self.assertGreater(stage.speed, 0.0)
                self.assertLessEqual(stage.speed, 1.0)
                self.assertGreater(stage.burst_speed, 0.0)
                self.assertLessEqual(stage.burst_speed, 1.0)

    def test_zones_present(self):
        """Surface exits are meaningless without the zone signatures."""
        zones = self.raw.get('zones', {})
        self.assertTrue(zones, "mission has no zone signatures")
        for stage in self.mission.stages:
            if stage.exit_surface:
                with self.subTest(stage=stage.name):
                    self.assertIn(stage.exit_surface, zones)

    def test_pit_stage_is_slow(self):
        """
        The compost-pit stage must stay slower than the rest of the route.

        The downward sensor buys a fixed warning DISTANCE, which is only worth
        anything if the car is slow enough to stop inside it. If someone
        speeds this stage up to match the others, the sensor is still fitted,
        still working, and still too late -- so the constraint is asserted
        here rather than left in a comment.
        """
        stages = {s.name: s for s in self.mission.stages}
        pit = stages.get('avoid_compost_pit')
        self.assertIsNotNone(pit, "expected an avoid_compost_pit stage")
        others = [s.speed for n, s in stages.items()
                  if n != 'avoid_compost_pit' and s.behaviour == 'follow']
        self.assertLessEqual(pit.speed, min(others),
                             "the pit stage must not be the fastest follow stage")


if __name__ == "__main__":
    unittest.main()
