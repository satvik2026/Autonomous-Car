"""
landmarks.py -- "pre-registered frame" recognition (the Q5 idea).

THE IDEA YOU PROPOSED
=====================
"When the compost-pit pre-registered frame is recognised, turn right."

VERDICT: the idea is RIGHT, but raw whole-frame matching is the wrong
mechanism. Here is why, and what to do instead.

WHY RAW FRAME MATCHING FAILS OUTDOORS
-------------------------------------
Comparing the live frame to a stored photo pixel-by-pixel (or by colour
histogram) breaks because:
  * the car will never stand exactly where you stood when you took the photo;
    a 30 cm offset or 15 degree yaw changes the pixels completely,
  * sun vs cloud changes every brightness value (the site photos in Photos/
    span bright sun and overcast),
  * the camera is ~10 cm off the ground on the car but the reference photos
    were taken at chest height -- totally different perspective,
  * leaves, people, parked scooters and the volleyball net move between runs.
A single stored JPEG therefore matches almost nothing, or matches the wrong
place with high confidence (worse).

WHAT ACTUALLY WORKS -- three tiers, cheapest first
--------------------------------------------------
Tier 1  SURFACE SIGNATURE (always on, nearly free)
        Don't match the picture -- match the *terrain mix*. Each zone of the
        course has a distinct signature from terrain.surface_mix():
            mud court : mud ~0.90, hard ~0.05, veg ~0.05
            gravel    : hard ~0.87, mud ~0.06, veg ~0.07
            cement    : hard ~0.94, mud ~0.06, veg ~0.00
            lawn/hill : veg  >0.80
        These are robust to viewpoint and lighting because they are area
        statistics, not pixels. This is what drives the mission sequencer.

Tier 2  ORB FEATURE LANDMARKS (this file)
        For the few genuinely distinctive, *static, man-made* places -- the
        retaining-wall step, the building corner, the graffiti wall -- store
        ORB keypoints, not pixels. ORB is rotation/scale invariant and
        tolerates lighting far better than raw pixels. Require a high inlier
        count plus geometric consistency (RANSAC homography) before declaring
        a match, so a chance similarity cannot trigger a turn.

Tier 3  COLOUR CUES FROM WHAT IS ALREADY THERE
        Detecting a big saturated colour blob is the most reliable trick
        available -- ~1 ms, viewpoint-independent, and it does not care about
        exposure. The catch: NOTHING MAY BE PLACED ON THIS COURSE, so this
        tier is limited to objects that happen to be there anyway. Two are
        usable: the bright-green compost sacks flanking the pit and the blue
        portable toilets along the trail (Photos/IMG20260728133102.jpg).

        The difference from a placed marker is not detection quality, it is
        CONTROL. A marker goes exactly where the decision point is and stays
        put; the sacks are where somebody left them, may be moved between now
        and demo day, and are only in frame from certain approach angles. So
        a colour cue here is a BONUS EXIT, never the only one: every stage
        that uses one also carries a timeout, and the surface signature
        (Tier 1) stays the workhorse.

SAFETY RULE THAT MAKES ANY OF THIS SAFE
---------------------------------------
A landmark never *commands* a manoeuvre directly. It only advances the
mission state (see mission.py). The terrain classifier and the ultrasonic
sensor always retain veto power. So a false landmark match causes at worst a
premature stage change, never a drive into the lawn or a collision.
"""

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


# ---------------------------------------------------------------------------
# Tier 3 -- colour cues from objects already on the course
# ---------------------------------------------------------------------------
# HSV ranges. Tune with tools/calibrate_terrain.py, on the day, in the day's
# light -- a green sack in overcast is not the same green as in full sun.
#
# Both entries are things that are ALREADY on the course. There is no entry for
# a cone or a tag because nothing may be placed: if you add a key here, it has
# to be for something that will be standing there on demo day regardless.
MARKER_COLOURS = {
    # the bright-green compost sacks flanking the pit
    'green_sack': ((40, 120, 60), (85, 255, 255)),
    # blue portable toilets / blue doors seen along the trail
    'blue_object': ((95, 120, 60), (125, 255, 255)),
}


def detect_marker(bgr, name, min_area_frac=0.004):
    """
    Detect a large blob of one of the MARKER_COLOURS.

    Returns None, or dict(area_frac, cx, side) where cx is the blob centre in
    normalised image x (-1 left .. +1 right) -- so you can react to WHICH SIDE
    the marker is on, not just that it exists.
    """
    lo, hi = MARKER_COLOURS[name]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    H, W = mask.shape
    frac = area / float(H * W)
    if frac < min_area_frac:
        return None
    M = cv2.moments(c)
    if M['m00'] == 0:
        return None
    cx = M['m10'] / M['m00']
    return {'area_frac': frac,
            'cx': (cx - W / 2) / (W / 2),
            'side': 'left' if cx < W / 2 else 'right'}


# ---------------------------------------------------------------------------
# Tier 2 -- ORB feature landmarks
# ---------------------------------------------------------------------------
class LandmarkBook:
    """
    Stores ORB descriptors for reference views of static landmarks and matches
    live frames against them.

    Usage:
        book = LandmarkBook()
        book.add('retaining_wall', cv2.imread('ref/wall1.jpg'))
        book.add('retaining_wall', cv2.imread('ref/wall2.jpg'))  # several views
        hit = book.match(frame)     # -> ('retaining_wall', 42) or None

    Register 3-6 views per landmark, taken AT CAR CAMERA HEIGHT, in the
    lighting you expect. Use tools/capture_landmark.py.
    """

    def __init__(self, n_features=700, min_inliers=18, ratio=0.75):
        self.orb = cv2.ORB_create(n_features)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.min_inliers = min_inliers
        self.ratio = ratio
        self.refs = {}   # name -> list of (keypoints, descriptors)

    def add(self, name, bgr):
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(g, None)
        if des is None or len(kp) < 10:
            return False
        self.refs.setdefault(name, []).append((kp, des))
        return True

    def match(self, bgr):
        """
        Returns (name, inlier_count) for the best landmark above threshold,
        else None. Uses Lowe's ratio test + RANSAC homography so that a match
        must be geometrically consistent, not just visually similar.
        """
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        kp2, des2 = self.orb.detectAndCompute(g, None)
        if des2 is None or len(kp2) < 10:
            return None

        best = (None, 0)
        for name, views in self.refs.items():
            for kp1, des1 in views:
                matches = self.bf.knnMatch(des1, des2, k=2)
                good = [m for m, n in matches
                        if m.distance < self.ratio * n.distance]
                if len(good) < self.min_inliers:
                    continue
                src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
                _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
                if mask is None:
                    continue
                inliers = int(mask.sum())
                if inliers >= self.min_inliers and inliers > best[1]:
                    best = (name, inliers)
        return best if best[0] else None


# ---------------------------------------------------------------------------
# Tier 1 -- surface signature matching (most robust; used by mission.py)
# ---------------------------------------------------------------------------
# Tuned by grid search over the site photos against hand-labelled ground truth,
# with the hard constraint that the matcher must NEVER return a wrong zone
# (abstaining is safe; a wrong zone silently skips a mission stage).
# Result: 13/15 correct, 2 abstain, 0 wrong -- up from 2/11 with mislabels.
ROUGH_WEIGHT = 0.8   # how much the texture axis counts vs the colour axes


def signature_distance(mix, signature):
    """
    Distance between a measured surface mix and a zone signature.

    Uses the three colour fractions PLUS the normalised roughness, because
    colour alone puts cement and gravel only 0.14 apart -- close enough that
    cement was being mis-identified as gravel. Roughness separates them by
    ~4.7x, so it is weighted a little higher than any single colour axis.

    Signatures that omit 'rough_n' fall back to colour-only, so old mission
    files keep working.
    """
    d = sum(abs(mix.get(k, 0.0) - signature.get(k, 0.0))
            for k in ('veg', 'hard', 'mud'))
    if 'rough_n' in signature and 'rough_n' in mix:
        d += ROUGH_WEIGHT * abs(mix['rough_n'] - signature['rough_n'])
    return d


def match_zone(mix, zones, max_distance=0.55, margin=0.04):
    """
    Identify which zone of the course the car is on.

    Two guards, because a wrong answer here silently breaks the route order:

      max_distance : the best match must actually be close.
      margin       : the best match must beat the RUNNER-UP by this much.
                     Without it, cement (0.30 from gravel, 0.34 from cement)
                     is reported as gravel on a coin-flip. With it, an
                     ambiguous reading correctly returns None instead of
                     guessing and advancing the mission early.

    Returns the zone name, or None if the reading is not confident.
    """
    ranked = sorted(((signature_distance(mix, sig), name)
                     for name, sig in zones.items()))
    if not ranked:
        return None
    best_d, best = ranked[0]
    if best_d > max_distance:
        return None
    if len(ranked) > 1 and (ranked[1][0] - best_d) < margin:
        return None          # too close to call -- do not guess
    return best


class ZoneVoter:
    """
    Temporal filter over match_zone().

    A single frame can be wrong: a puddle, a shadow, a patch of leaves or one
    over-exposed frame can all flip the instantaneous reading. Because a zone
    change advances the mission, one bad frame could skip a whole stage.

    This requires the same zone to win a majority of the last N frames before
    it is reported, which makes stage transitions stable without adding much
    latency (at 10 Hz, N=7 is under a second).

    Usage:
        voter = ZoneVoter()
        stable = voter.update(match_zone(mix, zones))
    """

    def __init__(self, window=7, min_votes=4):
        self.window = window
        self.min_votes = min_votes
        self.history = []
        self.stable = None

    def update(self, zone):
        self.history.append(zone)
        if len(self.history) > self.window:
            self.history.pop(0)
        counts = {}
        for z in self.history:
            if z is not None:
                counts[z] = counts.get(z, 0) + 1
        if counts:
            top, n = max(counts.items(), key=lambda kv: kv[1])
            if n >= self.min_votes:
                self.stable = top
        return self.stable
