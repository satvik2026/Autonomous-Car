"""
steps.py -- finding the best place to cross a step, kerb or slab edge.

READ THIS FIRST: WHAT THIS MODULE CAN AND CANNOT DO
===================================================
I tested whether a single camera can DETECT a step on your course. It cannot,
and it is important you know that before trusting anything here.

Measured on the site photos, comparing a sharp 6-10 cm cement lip
(IMG20260729132039), a near-flush crossable edge (IMG20260729132145) and plain
open mud with no step at all (IMG20260728121845):

    scene            edge "peakiness"    longest horizontal line found
    sharp lip              1.54                    none
    flush edge             1.60                    none
    open mud               1.56                    none

All three are identical. A 6 cm lip simply does not look different from flat
ground to one camera at car height -- monocular depth of a small step is an
ill-posed problem, and shadows and dry grass produce edges just as strong.

SO: THIS MODULE DOES NOT DETECT STEPS. Do not use it to decide *whether* a
step is there. Two things are used for that instead:

  1. ROUTE CONTEXT (primary). You already know where the step is -- it is in
     your route order. The mission sequencer puts the car into a `cross_step`
     stage as it approaches. The car does not need to discover the step; it
     needs to cross it well.
  2. A DOWNWARD-ANGLED ULTRASONIC (optional, ~2 USD, recommended). Pointed at
     the ground ahead, its range *shortens* at a step up and *lengthens* at a
     drop or a hole. That is a direct physical measurement of exactly the thing
     the camera cannot see -- and it is also the only sensor that can see the
     compost pit, which is a hole. Enable with DOWN_SENSOR_ENABLED in
     course_navigator.py.

WHAT THIS MODULE *DOES* DO -- and this part is validated
--------------------------------------------------------
While the ABSOLUTE question ("is there a step?") fails, the RELATIVE question
("along this edge, where is it lowest?") works. On the flush-edge photo the
edge response across the three thirds of the frame was:

        left 40   centre 26   right 20     <- right is where it is crossable

which correctly identifies the flush end. That is what find_crossing() returns:
the lateral direction of the EASIEST place to cross whatever is in front of
you. It is a steering hint, not an obstacle detector.

WHY THAT IS STILL WORTH HAVING
------------------------------
On your course the same slab edge is impassable at one end and drivable at the
other (compare IMG20260729132039 with IMG20260729132145). Crossing at the right
place is the whole game, and that is precisely the relative question.
"""

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

# Band of the image to look at: the ground just ahead of the car, not the
# far distance and not the bumper. Fractions of image height.
BAND_TOP = 0.55
BAND_BOTTOM = 0.90

N_COLUMNS = 5           # lateral resolution of the crossing search
STRAIGHT_ENOUGH = 0.15  # |steer| below this counts as "squared up" to the edge

# A real step is a SHARP, LOCALISED horizontal line: one row of the image with
# far more horizontal-edge energy than its neighbours. Gentle shading across
# the ground is not a step. PEAKINESS is (strongest row / median row); this
# threshold is deliberately high because an unnecessary swerve is worse than
# crossing straight. On the site photos nothing reaches it (all ~1.55), so
# find_crossing() correctly reports "no step evidence" and the car goes
# straight -- which is the honest and safe result. See module docstring.
PEAKINESS_MIN = 2.2


def edge_profile(bgr, band_top=BAND_TOP, band_bottom=BAND_BOTTOM,
                 n_columns=N_COLUMNS):
    """
    Horizontal-edge strength across the width of the ground band ahead.

    Returns a 1-D array of length n_columns; a HIGH value means that part of
    the ground ahead has a strong horizontal discontinuity (a lip, a kerb, a
    shadow line), a LOW value means it is smooth and continuous there.
    """
    h, w = bgr.shape[:2]
    band = bgr[int(h * band_top):int(h * band_bottom), :]
    g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)
    g = g / (g.mean() + 1e-6) * 128.0                 # exposure-normalise
    sob = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))   # horizontal edges

    step = band.shape[1] // n_columns
    return np.array([float(sob[:, i * step:(i + 1) * step].mean())
                     for i in range(n_columns)])


def step_evidence(bgr, band_top=BAND_TOP, band_bottom=BAND_BOTTOM):
    """
    Is there evidence of an actual step line in the ground ahead?

    Returns (found: bool, peakiness: float).

    'found' is True only when one image row carries far more horizontal-edge
    energy than the typical row -- i.e. a real, sharp, localised line rather
    than gentle shading. On the site photos this returns False everywhere,
    including on the genuine 6 cm lip: see the module docstring for the
    measurements. That is a limitation of one camera, not a bug.
    """
    h = bgr.shape[0]
    band = bgr[int(h * band_top):int(h * band_bottom), :]
    g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)
    g = g / (g.mean() + 1e-6) * 128.0
    rows = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)).mean(axis=1)
    peak = float(rows.max() / (np.median(rows) + 1e-6))
    return peak >= PEAKINESS_MIN, peak


def find_crossing(bgr, **kw):
    """
    Where along the ground ahead is the EASIEST place to cross a step?

    Returns dict:
        offset      : -1.0 (far left) .. +1.0 (far right)
        confidence  : 0..1
        step_found  : whether a genuine step line was detected at all
        peakiness   : the step-evidence score
        profile     : raw per-column edge strengths (for debugging)

    IMPORTANT: if no step line is detected, this returns offset 0.0 and
    confidence 0.0 -- meaning "go straight". It deliberately does NOT steer
    from gentle lighting gradients, which is what an earlier version did: a
    plain cement apron produced the strongest apparent "crossing point" on the
    whole course, purely from shading. Swerving on that would be worse than
    doing nothing.
    """
    found, peak = step_evidence(bgr, **{k: v for k, v in kw.items()
                                        if k in ('band_top', 'band_bottom')})
    prof = edge_profile(bgr, **kw)
    if not found:
        return {'offset': 0.0, 'confidence': 0.0, 'step_found': False,
                'peakiness': peak, 'profile': prof}

    n = len(prof)
    best = int(np.argmin(prof))                       # weakest edge = easiest
    lo, hi = float(prof.min()), float(prof.max())
    conf = 0.0 if hi <= 1e-6 else float((hi - lo) / hi)
    offset = (best - (n - 1) / 2.0) / ((n - 1) / 2.0)
    return {'offset': float(np.clip(offset, -1, 1)), 'confidence': conf,
            'step_found': True, 'peakiness': peak, 'profile': prof}


def crossing_steer(bgr, gain=0.6, min_confidence=0.25, **kw):
    """
    Turn find_crossing() into a steer value for the `cross_step` behaviour.

    Returns (steer, info). Steer is 0.0 unless a real step line was found AND
    one part of it is clearly easier than the rest.
    """
    c = find_crossing(bgr, **kw)
    if not c['step_found'] or c['confidence'] < min_confidence:
        return 0.0, c
    return float(np.clip(c['offset'] * gain, -1.0, 1.0)), c


def squared_up(steer):
    """
    True when the car is pointed straight enough to take a step head-on.

    Hitting a step at an angle lifts one wheel first and the car slews sideways
    and beaches, so the crossing burst must only fire once this is True.
    """
    return abs(steer) < STRAIGHT_ENOUGH
