"""
Tests for the landmark route state machine (Landmarks.RouteSequencer).

These are deliberately hardware- and OpenCV-free: the sequencer takes scripted
(landmark, surface, dt) inputs and returns Directives, so the whole route logic
can be walked and asserted on a plain CI runner. The image recognition itself
needs OpenCV and is checked on the Pi with `Landmarks.py --selftest`.
"""

import unittest

import _load

L = _load.load("Landmarks", "Landmarks.py")


class TestLandmarkGrouping(unittest.TestCase):
    """The reference filenames must map to the meanings the route speaks in."""

    def test_reverse_map_covers_all_refs(self):
        self.assertEqual(L._REF_TO_LOGICAL["4.1"], "turn_left")
        self.assertEqual(L._REF_TO_LOGICAL["4.4"], "turn_left")
        self.assertEqual(L._REF_TO_LOGICAL["3"], "compost_pit")
        self.assertEqual(L._REF_TO_LOGICAL["6"], "gravel_cement")
        self.assertEqual(L._REF_TO_LOGICAL["View"], "crest_view")
        self.assertEqual(L._REF_TO_LOGICAL["1"], "step")

    def test_four_views_are_one_class(self):
        views = {L._REF_TO_LOGICAL[r] for r in ("4.1", "4.2", "4.3", "4.4")}
        self.assertEqual(views, {"turn_left"})


class TestFullRouteHappyPath(unittest.TestCase):
    """Walk the whole route and assert every phase transition in order."""

    def setUp(self):
        self.seq = L.RouteSequencer()

    def phase(self):
        return L.PHASE_NAME[self.seq.phase]

    def test_route(self):
        s = self.seq
        # 1. seeking the step -> ordinary follow
        d = s.update(landmark=None, surface="mud", dt=0.1)
        self.assertEqual(self.phase(), "seek_step")
        self.assertEqual(d.action, "follow")

        # 2. step landmark seen -> cross it with the boost burst
        d = s.update(landmark="step", surface="mud", dt=0.1)
        self.assertEqual(self.phase(), "cross_step")
        self.assertEqual(d.action, "cross_step")

        # 3. cement underfoot ends the crossing
        d = s.update(landmark=None, surface="cement", dt=0.1)
        self.assertEqual(self.phase(), "seek_turn")

        # 4. the turn-left decision point (any 4.x view)
        s.update(landmark="turn_left", surface="cement", dt=0.1)
        self.assertEqual(self.phase(), "pivot_left")

        # 5. finish the ~90 deg pivot -> start climbing
        s.update(landmark=None, surface=None, dt=L.T_PIVOT_90 + 0.1)
        self.assertEqual(self.phase(), "climb")

        # 6. climb cap -> hunt for the crest View
        s.update(landmark=None, surface=None, dt=L.T_CLIMB_MAX + 0.1)
        self.assertEqual(self.phase(), "rotate_to_view")

        # 7. View replicated (closed loop) -> proceed toward the pit
        s.update(landmark=None, surface=None, dt=0.1, view_ok=True)
        self.assertEqual(self.phase(), "follow_to_pit")

        # 8. green sacks / compost pit -> mirror turn (pivot right)
        s.update(landmark="compost_pit", surface=None, dt=0.1)
        self.assertEqual(self.phase(), "pivot_right")

        # 9. finish the right pivot -> descend
        s.update(landmark=None, surface=None, dt=L.T_PIVOT_90 + 0.1)
        self.assertEqual(self.phase(), "descend")

        # 10. gravel underfoot -> cross onto the cement block
        d = s.update(landmark=None, surface="gravel", dt=0.1)
        self.assertEqual(self.phase(), "cross_cement")
        self.assertEqual(d.action, "cross_step")

        # 11. solid cement after the drop -> turn onto the road
        s.update(landmark=None, surface="cement", dt=0.1)
        self.assertEqual(self.phase(), "pivot_to_road")

        # 12. aligned -> down the cement road
        s.update(landmark=None, surface="cement", dt=L.T_PIVOT_90 + 0.1)
        self.assertEqual(self.phase(), "cement_road")

        # 13. road done -> finished
        d = s.update(landmark=None, surface="cement", dt=L.T_ROAD + 0.1)
        self.assertEqual(self.phase(), "done")
        self.assertEqual(d.action, "done")
        self.assertTrue(s.finished)


class TestBranchesAndFallbacks(unittest.TestCase):

    def test_turn_left_before_step_is_not_a_deadlock(self):
        """If the step is never registered, seeing 4.x still advances."""
        s = L.RouteSequencer()
        s.update(landmark="turn_left", surface="mud", dt=0.1)
        self.assertEqual(L.PHASE_NAME[s.phase], "pivot_left")

    def test_veer_right_method_emits_veer(self):
        s = L.RouteSequencer(step_method="veer_right")
        s.update(landmark="step", surface="mud", dt=0.1)          # -> cross_step
        d = s.update(landmark=None, surface="mud", dt=0.1)
        self.assertEqual(d.action, "veer_right")
        self.assertGreater(d.steer, 0.0)                          # steering right

    def test_rotate_gives_up_after_timeout(self):
        """If View is never found, the rotate phase must not spin forever."""
        s = L.RouteSequencer()
        s.phase = L.ROTATE_TO_VIEW
        d = s.update(landmark=None, surface=None, dt=L.T_ROTATE_MAX + 0.1)
        self.assertEqual(L.PHASE_NAME[s.phase], "follow_to_pit")
        self.assertEqual(d.action, "follow")

    def test_descend_falls_back_to_gravel_on_landmark(self):
        s = L.RouteSequencer()
        s.phase = L.DESCEND
        d = s.update(landmark="gravel_cement", surface=None, dt=0.1)
        self.assertEqual(L.PHASE_NAME[s.phase], "cross_cement")
        self.assertEqual(d.action, "cross_step")

    def test_pit_sequence_is_mirror_of_turn(self):
        """Turn uses pivot_left; the pit response uses pivot_right."""
        s = L.RouteSequencer()
        s.phase = L.FOLLOW_TO_PIT
        s.update(landmark="compost_pit", surface=None, dt=0.1)
        d = s.update(landmark=None, surface=None, dt=0.1)
        self.assertEqual(d.action, "pivot_right")


if __name__ == "__main__":
    unittest.main()
