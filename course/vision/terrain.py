"""
terrain.py -- terrain classification and steering decisions for the demo course.

WHY THIS REPLACES THE OLD "green = bad, brown = good" MODEL
===========================================================
The old model in autonomous_car.py used two HSV boxes: GRASS (hue 35-90) and
GROUND (hue 5-30). Measured against the actual course photos, that model fails
in three ways that matter (numbers are % of ROI pixels, measured on the site
photos in Photos/):

  surface            old:%green  old:%ground   what goes wrong
  -----------------  ----------  -----------   ----------------------------
  GRASS lawn             20.9%        52.5%    the dry/yellow-green lawn reads
                                               as DRIVABLE -> car drives onto
                                               the very lawn we must avoid
  CEMENT                  0.0%        96.6%    cement is indistinguishable
                                               from mud -> can't tell surfaces
                                               apart for sequencing
  MUD (wet)               2.1%        46.9%    wet mud falls OUT of the ground
                                               band -> car refuses to drive on
                                               a perfectly good surface

Root cause: hue alone cannot separate these. Dry grass hue (~28) sits inside
the "ground" hue band (5-30), and cement hue (~16) sits on top of mud (~17).

THE FIX -- two axes instead of one:

  1. VEGETATION is detected with the Excess-Green index (ExG), not hue:
         ExG = (2G - R - B) / (R + G + B)
     This is a standard vegetation index. It keys on green being *relatively*
     stronger than red+blue, so it survives dry/yellowed grass, shade and
     overcast light, where a fixed hue window does not.
         grass lawn : 20.9% (old)  ->  81.8% (ExG)   <-- the critical fix
         grass hill : 77.6% (old)  ->  99.8% (ExG)

  2. HARD SURFACE vs MUD is separated by SATURATION, which is what actually
     differs between them:
         cement  S ~ 39  (p10-p90: 25-56)   -> low saturation, washed out grey
         mud     S ~ 88  (p10-p90: 65-128)  -> high saturation, red-brown
     Both are drivable, but telling them apart is what lets the mission
     sequencer know which zone of the course it is in.

Resulting three classes (measured on site photos):

  class            %VEG   %HARD   %MUD    interpretation
  --------------   -----  -----   -----   ---------------------------------
  MUD court dry     0.4%   4.0%   95.6%   drivable, "mud" zone
  MUD trail         1.8%  56.3%   41.9%   drivable
  MUD wet           8.2%  82.8%    9.0%   drivable (wet mud reads low-sat)
  MUD + patchy grass 31.7% 35.9%  32.3%   DRIVABLE - see note below
  GRASS lawn       81.8%   6.0%   12.2%   KEEP OUT
  GRASS hill       99.8%   0.1%    0.1%   KEEP OUT
  CEMENT            0.0%  94.2%    5.8%   drivable, "cement" zone
  GRAVEL            7.2%  87.0%    5.9%   drivable, "gravel" zone
  LEAF LITTER      13.9%  52.8%   33.3%   drivable but hides obstacles

THE MOST IMPORTANT CONSEQUENCE: the mud course is *not* grass-free. It has
grass tufts growing all over it (31.7% vegetation). So "any green -> avoid"
would refuse to drive on the course itself. Vegetation must be treated as a
DENSITY, not a boolean: ~32% veg = drivable mud course, ~82% veg = lawn, keep
out. VEG_BLOCK_FRAC below is that threshold, and it is the single most
important tuning number in this file.
"""

import numpy as np

try:
    import cv2
except ImportError:  # allows import on machines without OpenCV for doc/tests
    cv2 = None

# ---------------------------------------------------------------------------
# TUNING -- calibrate on-site with tools/calibrate_terrain.py
# ---------------------------------------------------------------------------
EXG_VEG = 0.05      # ExG above this = vegetation. Raise if dry mud reads green.
SAT_HARD = 60       # saturation below this (and not veg) = cement/gravel
HORIZON = 0.45      # ignore the top 45% of frame (sky/buildings/far trees)

# A column is "blocked by vegetation" only above this fraction. Between the
# mud course (0.32) and the lawn (0.82); 0.55 leaves margin on both sides.
VEG_BLOCK_FRAC = 0.55
DRIVABLE_MIN = 0.35     # a column needs this much drivable surface to be usable
VEG_PENALTY = 1.5       # how hard vegetation is punished in the column score
CENTER_STICKINESS = 0.15  # prefer straight unless a side clearly beats centre

# Class ids
VEG, HARD, MUD = 0, 1, 2


def classify(bgr):
    """
    Classify every pixel of a BGR image into VEG / HARD / MUD.

    Returns (veg, hard, mud) boolean masks of the same HxW as the input.
    """
    f = bgr.astype(np.float32) / 255.0
    B, G, R = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    total = B + G + R + 1e-6
    exg = (2 * G - R - B) / total                      # vegetation index

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)

    veg = exg > EXG_VEG
    hard = (~veg) & (sat < SAT_HARD)
    mud = (~veg) & (sat >= SAT_HARD)
    return veg, hard, mud


def surface_mix(bgr, horizon=HORIZON):
    """
    Fraction of the drivable region that is each class.
    Used by the mission sequencer to tell WHICH ZONE the car is in
    (mud course vs gravel vs cement), independent of steering.

    Returns dict: {'veg':f, 'hard':f, 'mud':f}
    """
    h = bgr.shape[0]
    roi = bgr[int(h * horizon):, :]
    veg, hard, mud = classify(roi)
    n = float(veg.size)
    return {'veg': veg.sum() / n, 'hard': hard.sum() / n, 'mud': mud.sum() / n}


def decide_steering(bgr, horizon=HORIZON, keepout_bias=0.0):
    """
    Turn one camera frame into a steering decision.

    The frame's lower region is split into left / centre / right columns.
    Each column is scored:

        score = drivable_fraction - VEG_PENALTY * vegetation_fraction

    so a column full of mud/cement/gravel scores ~1.0, and a column full of
    grass scores strongly negative. The car steers toward the best column,
    and the SIZE of the steer scales with how much better that column is than
    going straight -- small advantage = gentle trim, large advantage = hard
    turn. If nothing is drivable it returns drivable=False and the caller
    stops instead of picking the least-bad direction.

    keepout_bias: constant added to steer (+ = pull right). Use it when a
    known hazard is always on one side, e.g. the lawn always on the left.

    Returns dict with steer [-1..1], drivable, blocked, scores, mix.
    """
    h = bgr.shape[0]
    roi = bgr[int(h * horizon):, :]
    veg, hard, mud = classify(roi)

    # Clean speckle so a few stray pixels don't swing the decision
    if cv2 is not None:
        k = np.ones((5, 5), np.uint8)
        vegu = cv2.morphologyEx(veg.astype(np.uint8), cv2.MORPH_OPEN, k).astype(bool)
        veg = vegu

    drivable = (hard | mud).astype(np.float32)
    vegf = veg.astype(np.float32)

    H, W = drivable.shape
    third = W // 3
    cols = [(0, third), (third, 2 * third), (2 * third, W)]

    scores, drive_fracs, veg_fracs = [], [], []
    for x0, x1 in cols:
        d = float(drivable[:, x0:x1].mean())
        v = float(vegf[:, x0:x1].mean())
        drive_fracs.append(d)
        veg_fracs.append(v)
        scores.append(d - VEG_PENALTY * v)

    # A column is usable only if it has enough drivable surface AND is not
    # dominated by vegetation (the lawn / hill test).
    usable = [d >= DRIVABLE_MIN and v < VEG_BLOCK_FRAC
              for d, v in zip(drive_fracs, veg_fracs)]

    mix = {'veg': float(vegf.mean()),
           'hard': float(hard.mean()),
           'mud': float(mud.mean())}

    if not any(usable):
        # Everything ahead is lawn/hill/wall -> do NOT charge the least-bad
        # option. Report blocked and let the caller stop / reverse / search.
        return {'steer': 0.0, 'drivable': False, 'blocked': True,
                'scores': tuple(scores), 'mix': mix}

    # Mask out unusable columns so we never steer INTO the lawn
    masked = [s if u else -9.9 for s, u in zip(scores, usable)]
    best = int(np.argmax(masked))
    best_score = masked[best]
    centre_score = masked[1]

    if centre_score + CENTER_STICKINESS >= best_score:
        steer = 0.0                       # centre is good enough -> straight
    else:
        target = -1.0 if best == 0 else 1.0
        advantage = float(np.clip(best_score - centre_score, 0.0, 1.0))
        steer = target * float(np.clip(0.3 + advantage, 0.0, 1.0))

    steer = float(np.clip(steer + keepout_bias, -1.0, 1.0))
    return {'steer': steer, 'drivable': True, 'blocked': False,
            'scores': tuple(scores), 'mix': mix}


def debug_overlay(bgr, horizon=HORIZON):
    """Colour-coded overlay for calibration: red=veg, cyan=hard, green=mud."""
    vis = bgr.copy()
    h = bgr.shape[0]
    top = int(h * horizon)
    roi = bgr[top:, :]
    veg, hard, mud = classify(roi)
    ov = roi.copy()
    ov[veg] = (0, 0, 255)
    ov[hard] = (255, 200, 0)
    ov[mud] = (0, 255, 0)
    vis[top:, :] = cv2.addWeighted(roi, 0.45, ov, 0.55, 0)
    cv2.line(vis, (0, top), (bgr.shape[1], top), (255, 255, 255), 1)
    return vis
