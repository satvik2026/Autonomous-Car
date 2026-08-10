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

Tier 3  COLOURED FIDUCIAL MARKERS (recommended for demo day)
        The single most reliable option, and cheap: put a few brightly
        coloured markers (or printed ArUco tags) at the decision points.
        The course already contains bright-green compost sacks and blue
        portable toilets that act as natural high-saturation landmarks --
        see Photos/IMG20260728133102.jpg. Detection is a colour-blob test:
        near-100% reliable, unaffected by viewpoint, and takes ~1 ms.
        If the demo rules allow placing markers, DO THIS.

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
# Tier 3 -- coloured fiducial markers (most reliable)
# ---------------------------------------------------------------------------
# HSV ranges for saturated marker colours. Tune with tools/calibrate_terrain.py.
MARKER_COLOURS = {
    # the bright-green compost sacks already on site
    'green_sack': ((40, 120, 60), (85, 255, 255)),
    # blue portable toilets / blue doors seen along the trail
    'blue_object': ((95, 120, 60), (125, 255, 255)),
    # add your own: e.g. a pink/orange cone placed at a decision point
    'pink_marker': ((160, 120, 90), (175, 255, 255)),
}


def detect_marker(bgr, name, min_area_frac=0.004):
    """
    Detect a coloured marker blob.

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
def signature_distance(mix, signature):
    """
    L1 distance between a measured surface mix and a zone signature.
    Both are dicts with keys veg/hard/mud. Smaller = better match.
    """
    return sum(abs(mix.get(k, 0.0) - signature.get(k, 0.0))
               for k in ('veg', 'hard', 'mud'))


def match_zone(mix, zones, max_distance=0.45):
    """
    Given a measured surface mix and {zone_name: signature}, return the best
    matching zone name, or None if nothing is close enough.
    """
    best, bd = None, 1e9
    for name, sig in zones.items():
        d = signature_distance(mix, sig)
        if d < bd:
            best, bd = name, d
    return best if bd <= max_distance else None
