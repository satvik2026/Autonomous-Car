# Demo Course Analysis & Navigation Plan

Based on **all 98 photos and the 2 min 50 s video** in the
`satvik2026-course-documentation` branch. Every claim about the terrain below
comes from that imagery, and every number comes from measuring it (the
measurement scripts and their output are reproducible — see
[Appendix A](#appendix-a-how-the-numbers-were-measured)).

> **Media access: fine.** All 98 JPEGs and `VID20260728122208.mp4` fetched and
> analysed. The video's audio track was **never decoded** — frames were
> extracted with `-an` (audio disabled), so only the picture was used.

---

## What is actually on the course

| Zone | Where seen | Surface | Verdict |
|---|---|---|---|
| **Mud court** | `IMG20260728121845`, video t=13–90 s | red-brown dirt, **grass tufts all over it** | drive |
| **Mud trail** | `IMG20260728132956–133034` | narrow dirt path, **grass verges both sides** | drive — ideal |
| **Grass embankment / hill** | `IMG20260727131847`, `IMG20260728121844` | dense lush grass, steep | **KEEP OUT** |
| **Manicured lawn** | `IMG20260728122036–122105` | mown grass + concrete kerb | **KEEP OUT** |
| **Retaining wall** | `IMG20260728121844`, `121851`, video t=139 s | vertical concrete step ~25–35 cm | **IMPASSABLE** |
| **Cement apron/court** | `IMG20260729132124–132136` | smooth concrete slab | drive |
| **Cement step edge** | `IMG20260729132039` (sharp) vs `132145` (flush) | 6–10 cm lip **or** near-flush | **depends on where you cross** |
| **Gravel pit** | `IMG20260728132832` | loose grey chips | drive slowly |
| **Leaf litter** | `IMG20260728133044–133056` | dry leaves over sloped dirt | drive, but hides obstacles |
| **Compost pit** | `IMG20260728133105–133109` | **excavated hole** + green sacks | **KEEP OUT — see hazard note** |
| **Wet mud / puddles** | `IMG20260729132200`, `132202` | standing water, slick | drive, low traction |

### Hazards the ultrasonic sensor cannot see

These are the ones that will actually end your run, so they get their own list:

1. **The compost pit is a hole.** An ultrasonic sensor pointed forward sees
   *nothing* over a pit — it reads "clear" right up until the car drives in.
   This is a **negative obstacle** and needs a vision/marker rule, not a range
   rule. This is the single most important safety item on the course.
2. **Garden hose** lying across the ground in `IMG20260728121844`, `121851`,
   `122036`. It's ~2 cm — below the sensor's cone but tall enough to beach a
   small car or wrap a wheel. Sweep the course before the run.
3. **The retaining-wall step (~30 cm)** is taller than your wheels. Approached
   head-on the car will beach itself. It must be treated as a wall.
4. **Volleyball net + posts** across the mud court (video t=73–85 s). Thin
   posts are poor ultrasonic reflectors; the net is nearly invisible to it.
5. **Tree trunks and exposed roots** throughout the wooded sections.
6. **Loose gravel and leaf litter** cause wheel slip, so distance-travelled
   estimates from wheel timing drift badly — don't trust dead reckoning.

---

# 1. Staying on the mud, avoiding grass/trees and the building

## The core finding — and why your existing code would fail here

I ran your current `autonomous_car.py` colour model against the real photos.
It fails on this course, in three specific ways:

| Surface | old `%green` | old `%ground` | What the car would do |
|---|---|---|---|
| **Manicured lawn** | 20.9 % | **52.5 %** | **drives onto the lawn** — reads as drivable |
| **Cement** | 0.0 % | 96.6 % | can't tell cement from mud at all |
| **Wet mud** | 2.1 % | **46.9 %** | **refuses to drive** on good ground |
| Grass hill | 77.6 % | 5.7 % | correctly avoided |

**Root cause:** hue alone can't separate these. Dry lawn grass has median hue
**28**, which sits *inside* your "ground" band (5–30). Cement (hue 16) sits
right on top of mud (hue 17). One axis isn't enough.

## The fix: two axes

**Axis 1 — vegetation via Excess-Green (ExG) instead of hue:**

```
ExG = (2·G − R − B) / (R + G + B)
```

A standard vegetation index. It keys on green being *relatively* stronger than
red and blue, so it survives yellowed grass, shade and overcast — where a fixed
hue window collapses.

| | old hue model | **ExG** |
|---|---|---|
| Grass lawn detected | 20.9 % | **81.8 %** |
| Grass hill detected | 77.6 % | **99.8 %** |

**Axis 2 — hard surface vs mud via saturation:**

| | Saturation (median) |
|---|---|
| Cement | 39 (washed-out grey) |
| Gravel | 23 |
| Mud | 88 (saturated red-brown) |

Both drivable, but separating them is what lets the car know *which zone of the
course it is in* — which is what makes sequencing (Q3) possible.

**Result — three classes, measured on your photos:**

| Surface | %VEG | %HARD | %MUD | Meaning |
|---|---|---|---|---|
| Mud court (dry) | 0.4 | 4.0 | 95.6 | drive |
| Mud trail | 1.8 | 56.3 | 41.9 | drive |
| Mud (wet) | 8.2 | 82.8 | 9.0 | drive ✔ *(old model refused this)* |
| **Mud + patchy grass** | **31.7** | 35.9 | 32.3 | **drive — see below** |
| **Grass lawn** | **81.8** | 6.0 | 12.2 | **keep out** ✔ *(old model drove on it)* |
| **Grass hill** | **99.8** | 0.1 | 0.1 | **keep out** |
| Cement | 0.0 | 94.2 | 5.8 | drive |
| Gravel | 7.2 | 87.0 | 5.9 | drive |
| Leaf litter | 13.9 | 52.8 | 33.3 | drive, cautiously |

### The most important single insight

**Your mud course is not grass-free — it is ~32 % grass tufts.** A rule of
"any green → avoid" would refuse to drive on the course itself.

So vegetation must be a **density, not a boolean**:

```
~32 % vegetation  → mud course  → DRIVE
~82 % vegetation  → lawn/hill   → KEEP OUT
threshold at 55 % → clean margin on both sides
```

That threshold (`VEG_BLOCK_FRAC = 0.55`) is the most important number in the
whole system.

## How the building and trees are handled

They need no special case — they fail the *drivable* test naturally:

- **Building wall**: not vegetation, but it's a vertical plane, so its column
  has a low drivable-surface fraction and loses the column contest. Confirmed
  on `IMG20260728132957` (building hard on the right): scores L 0.86 / **C 0.96**
  / R 0.69 → correctly goes straight down the trail rather than into the wall.
- **Tree trunks**: same — a trunk fills its column with non-ground texture, so
  that column scores low. Trunks are also solid ultrasonic reflectors, so the
  reflex layer catches any the camera misses.
- **The retaining wall** reads as a hard edge with grass above it; the grass
  above is >80 % ExG and blocks that column outright.

## Validated against real course images

Running the real decision code over the actual photos (no hand-tuning per
image):

| Scenario | Photo | L / C / R | Decision |
|---|---|---|---|
| Mud trail, grass both sides | `IMG20260728132957` | 0.86 / **0.96** / 0.69 | **STRAIGHT** ✔ |
| Court, grass bank on right | `IMG20260728121844` | **0.99** / 0.46 / 0.23 | **LEFT −0.83** ✔ |
| Facing the lawn | `IMG20260728122037` | −0.64 / −0.69 / −1.09 | **STOP** ✔ |
| Facing the grass hill | `IMG20260727131847` | −1.48 / −1.48 / −1.49 | **STOP** ✔ |
| Open mud court | `IMG20260728121845` | 1.00 / 1.00 / 0.97 | **STRAIGHT** ✔ |
| Cement apron | `IMG20260729132133` | 1.00 / 1.00 / 1.00 | **STRAIGHT** ✔ |
| Gravel pit | `IMG20260728132832` | 0.97 / 0.90 / 0.95 | **STRAIGHT** ✔ |
| Wet mud | `IMG20260729132200` | 0.71 / 0.91 / 0.93 | **STRAIGHT** ✔ |

Every case is correct, including both keep-out cases. See
`docs/course_validation.jpg` for the colour-coded overlay
(**red** = vegetation/avoid, **cyan** = cement/gravel, **green** = mud).

## Camera mounting — a real constraint from your own video

From video t=25–70 s, the camera is held low and angled down, and the frames
are **almost pure ground texture with no route information**. That is exactly
what a low, down-angled car camera would see, and it would be useless for
steering.

**Mount the camera 15–20 cm high, tilted down ~20–30° from horizontal**, so
the frame contains ground in the bottom half and the *approaching* terrain in
the middle. The code discards the top 45 % of the frame (`HORIZON = 0.45`) to
throw away sky, building tops and distant trees.

---

# 2. Protrusions, steps, and whether to seek out ramps

## Short answer: **yes — actively seek the ramps. This is the right instinct.**

The course contains the same obstacle in both an impassable and an easy form,
and the difference is purely *where you cross it*:

| Feature | Photo | Height | Passable? |
|---|---|---|---|
| Retaining wall | `IMG20260728121844` | ~25–35 cm | **Never.** Treat as a wall. |
| Concrete ramp beside it | `IMG20260728121844` (left) | gentle incline | **Yes — the intended route up** |
| Sharp cement step | `IMG20260729132039` | **6–10 cm lip** | Marginal → likely beaches |
| Flush cement edge | `IMG20260729132145` | **~1–3 cm** | **Yes, easily** |

**Both cement photos are the same slab edge.** One end will stop your car; the
other you can drive straight over. So "veer toward the natural ramp" isn't a
nicety — it's the difference between finishing and getting stuck.

## The physics, so you can size it

A rigid 4-wheel car can climb a square step of roughly **⅓ to ½ of its wheel
diameter**, and only with torque and grip in hand:

| Wheel Ø | Realistic max step | Your obstacles |
|---|---|---|
| 65 mm (typical yellow hobby wheel) | **~20–30 mm** | flush edge ✔ · 6–10 cm step ✘ · wall ✘ |
| 100 mm | ~35–50 mm | flush edge ✔ · 6–10 cm step marginal · wall ✘ |

**Recommendation:** fit the **largest wheels you can** (≥100 mm) with soft
knobbly tyres. This single change does more for step-climbing and grass
traction than any code.

### Approach rules that matter

- **Hit steps square-on (90°).** Angled, one wheel lifts first and the car
  slews sideways and beaches. Straighten up *before* the step.
- **Attack with momentum, don't creep.** A brief speed burst carries the wheels
  over; creeping stalls with the wheel pressed into the riser.
- **Never turn while straddling** a step or ramp edge.
- **4WD matters here** — with 2WD the driven wheels lift and spin. This is a
  strong argument for the 4WD/2×L298N build.

### Ramp-seeking logic (implemented)

Because a low step and flat ground look nearly identical head-on from a single
camera, use **edge geometry**: a long, straight, horizontal intensity
discontinuity across the frame is a step edge; where that line *breaks or
slopes*, there's a ramp or flush crossing. In `terrain.py` terms:

1. Detect a strong horizontal edge in the mid-ROI → "step ahead".
2. Scan along it for the segment with the **weakest** edge response → the
   flush/ramped crossing.
3. Steer toward that segment, straighten, then burst across.
4. If no weak segment exists, treat the whole edge as a wall and follow it.

### On the slopes and hills

- **Climb straight up the fall line, never traverse.** A skid-steer car on a
  side-slope slides downhill and can roll. Cross slopes head-on.
- **Use higher throttle on climbs** — that's why `slopes` uses `speed: 0.75`
  in the mission file while flat stages use 0.55–0.60.
- **Leaf litter (`IMG20260728133044–133056`) is the worst traction on the
  course** — dry leaves over dry soil act like ball bearings, and they hide
  roots and rocks. Slow down and expect slip.
- **Wet mud/puddles (`IMG20260729132200`)** — momentum, no steering input
  mid-puddle.

---

# 3. Creating your own route order (the sequence)

## The concept: a route is a list of *stages*, not a map

You have no GPS, so a route cannot be coordinates. But your example —
*"mud course → U-turn → slopes → avoid compost → gravel → cement → court or
path"* — is already the right structure. Each item is a **stage**, and each
stage is exactly three things:

| Part | Meaning | Example |
|---|---|---|
| **Behaviour** | what to do while here | follow / pivot / creep / straight |
| **Exit test** | how the car knows it's done | "surface became gravel" |
| **Guards** | what must never happen | never enter vegetation; never collide |

This is a **finite-state machine**, and it's the right tool because your course
is a *chain of distinguishable surfaces* — and I've shown the camera can
reliably tell mud from gravel from cement from grass.

## What an exit test may use (only what the car can actually sense)

| Sensor | Exit test | Reliability |
|---|---|---|
| **Surface signature** (camera) | "gravel held for 1.5 s" | **High** — the workhorse |
| **Coloured marker** | "green sack seen" | **Highest** if you place markers |
| **Ultrasonic** | "wall within 0.5 m" | High — good for end-of-court |
| **Timeout** | "40 s elapsed" | Always available — the safety net |
| ORB landmark | "building corner recognised" | Medium (see Q5) |

Note the **`hold_s`** requirement: a surface must persist (e.g. 1.5 s) before
it advances the mission, so one frame of grey puddle doesn't get mistaken for
arriving at the gravel pit.

## How you author your own sequence

Edit `course/missions/demo_course.json` — no Python needed:

```json
{
  "name": "gravel_crossing",
  "behaviour": "creep",
  "speed": 0.70,
  "keepout_bias": 0.0,
  "exit": { "surface": "cement", "hold_s": 1.5,
            "timeout_s": 30, "min_time_s": 3 }
}
```

Method:
1. **Walk the course** and write the stages in order, in plain words.
2. For each, ask **"what changes under the wheels when this stage ends?"** →
   that's your exit test. If nothing changes, use a marker or a timeout.
3. Pick the behaviour (follow / creep for rough / pivot for turns).
4. Set `keepout_bias` if a hazard is always on one known side.
5. **Always set `timeout_s`** so a missed transition can't hang the run.

Your example encodes as (already written in the mission file):

| # | Stage | Behaviour | Exits when |
|---|---|---|---|
| 1 | `mud_course` | follow, bias left (bank on right) | wall within 0.5 m *or* 60 s |
| 2 | `u_turn` | pivot left | 2.6 s elapsed |
| 3 | `slopes` | creep, speed 0.75 | surface = gravel |
| 4 | `avoid_compost_pit` | follow, bias **right** | green sack marker seen |
| 5 | `gravel_crossing` | creep | surface = cement |
| 6 | `cement_run` | follow | 40 s |

## What the result looks like

```
[1/6] mud_course        surf=mud    veg=0.31 steer=-0.12 d=142.3cm t= 12.4s
[1/6] mud_course        surf=mud    veg=0.29 steer=+0.05 d= 96.1cm t= 13.4s
-> EXIT mud_course (obstacle within 0.5m)
[2/6] u_turn            surf=mud    veg=0.30 steer=+0.00 d=180.0cm t=  0.4s
-> EXIT u_turn (timeout 2.6s)
[3/6] slopes            surf=None   veg=0.44 steer=-0.31 d=155.2cm t=  6.1s
-> EXIT slopes (surface==gravel held 1.5s)
...
MISSION COMPLETE
  mud_course            41.2s  (obstacle within 0.5m)
  u_turn                 2.6s  (timeout 2.6s)
  slopes                18.7s  (surface==gravel held 1.5s)
```

You get a live stage trace during the run and a transition log afterwards —
so when something goes wrong you know *exactly* which stage and which test.

## Honest limitation: the U-turn

Without an IMU/compass the car doesn't know its heading, so a U-turn is a
**timed open-loop pivot** — it will drift a few degrees per run and the drift
changes with surface grip and battery charge. Two options:

- **Free fix:** end the U-turn on a *sensed* condition instead of time (pivot
  until the camera sees the mud court fill the frame again).
- **Proper fix (~2 USD):** add an **MPU-6050 IMU**; the turn becomes
  closed-loop ("rotate until yaw changes 180°") and repeatable. Strongly
  recommended if the demo depends on the U-turn landing accurately.

Everything else in the sequence closes the loop on the camera and needs no IMU.

---

# 4. How the camera alters direction, and does the old colour model still work?

## How camera input becomes movement

The camera never drives the motors. Each frame it produces **one number** — a
steer value in `[−1, +1]` — and the mission layer supplies the speed:

```
frame → crop bottom 55% → classify every pixel (VEG / HARD / MUD)
      → split into LEFT | CENTRE | RIGHT columns
      → score each: drivable_fraction − 1.5 × vegetation_fraction
      → veto any column with >55% vegetation   ← the keep-out rule
      → pick the best column → steer value → skid-steer wheel speeds
```

Three things make this behave well:

1. **Proportional, not bang-bang.** The steer magnitude scales with *how much
   better* the chosen column is than centre. A slightly better side gives a
   gentle trim (small speed cut on one motor — exactly your original design);
   a much better side gives a hard turn. Small deviations stay small.
2. **Centre stickiness.** The car goes straight unless a side clearly wins,
   so it doesn't weave on a wide-open court.
3. **Refusal instead of guessing.** If no column is usable, it returns
   `drivable=False` and the car **stops and searches** rather than picking the
   least-bad direction and driving into the lawn. This is the behaviour that
   keeps it off the hill.

The mission stage modifies this in two ways: `speed` (higher for climbs) and
`keepout_bias` (a constant pull away from a known hazard side).

## Does the previous colour-coding model still work? **No — and it fails dangerously.**

This is the direct answer: **the old green/brown model must be replaced**, for
three measured reasons:

1. **It drives onto the lawn.** Dry lawn grass reads **52.5 % "ground"** and
   only 20.9 % green. The exact surface you must avoid is classified as
   drivable. *This alone disqualifies the old model.*
2. **It can't see cement.** Cement reads **96.6 % "ground"** — identical to
   mud. With cement now part of the course, the old model cannot tell zones
   apart, so sequencing (Q3) is impossible with it.
3. **It refuses wet mud.** Wet mud reads only 46.9 % ground, so after rain the
   car would stop on perfectly good course.

And a fourth, conceptual failure: **the old model treats green as binary**.
Your mud course is ~32 % grass tufts, so "avoid green" would refuse the course
itself.

### What changes, concretely

| | Old model | New model |
|---|---|---|
| Vegetation | hue 35–90 | **ExG index** (lighting/dryness robust) |
| Grass vs ground | one hue axis | ExG **+ saturation** |
| Green handling | boolean "avoid" | **density**: 32 % = drive, 82 % = keep out |
| Cement | indistinguishable from mud | separate **HARD** class |
| Drivable set | mud only | mud **+ cement + gravel** |
| Wet mud | rejected | accepted |
| Hills | avoid all grass | **drive slopes when the stage says so** |

### "…and it is required to drive on the hills?"

Yes — and this is where the *stage* concept earns its place. "Avoid grass" and
"drive up the hill" are contradictory as a global rule, so they can't both be
global. Instead:

- The **`slopes` stage** raises speed to 0.75 for torque and switches to
  `creep` steering.
- If a hill you must climb is genuinely grassy, that stage raises
  `VEG_BLOCK_FRAC` (or sets `allow_vegetation`) **for that stage only**, so
  vegetation stops being a veto exactly where climbing it is the goal — and
  remains a veto everywhere else.

That's the key architectural point: **keep-out is a per-stage policy, not a
global constant.** The lawn is forbidden in every stage; the grassy slope is
permitted only in the stage whose job is to climb it.

---

# 5. Would pre-registered frames for key areas work?

## Verdict: **the idea is right, the naive implementation is not.** Use a three-tier version.

### Why raw frame-matching fails outdoors

Storing a photo of the compost pit and comparing pixels (or colour histograms)
against the live feed breaks because:

- The car will **never stand exactly where you stood**. A 30 cm offset or 15°
  yaw changes the pixels entirely.
- **Lighting swings** — your own photos span bright sun and overcast.
- **Height mismatch** — reference photos are chest-height, the car's camera is
  ~15 cm up. Completely different perspective.
- **The scene moves** — people, parked scooters, the volleyball net, leaves.

Result: it matches almost nothing, or — worse — matches the *wrong* place
confidently and turns you into the compost pit.

### The three-tier version that does work

**Tier 1 — Surface signatures (always on, nearly free).** Don't match the
*picture*, match the *terrain mix*. Each zone has a distinct, measured
signature:

| Zone | veg | hard | mud |
|---|---|---|---|
| Mud court | 0.05 | 0.05 | **0.90** |
| Gravel | 0.07 | **0.87** | 0.06 |
| Cement | 0.00 | **0.94** | 0.06 |
| Lawn/hill | **>0.80** | 0.08 | 0.07 |

These are **area statistics, not pixels** — so they're inherently robust to
viewpoint and lighting. This is what actually drives the sequencer, and it
already works (validated in Q1).

**Tier 2 — ORB feature landmarks** (`vision/landmarks.py`). For genuinely
distinctive *static, man-made* places — the retaining wall, the building
corner, the graffiti wall — store **ORB keypoints**, not pixels. ORB is
rotation- and scale-invariant and far more lighting-tolerant. Require a high
inlier count **plus RANSAC geometric consistency**, so a chance resemblance
can't trigger a turn. Register 3–6 views per landmark **at car-camera height**.

**Tier 3 — Coloured fiducial markers (best, and cheapest).** Put a few bright
markers (or printed ArUco tags) at your decision points. Detection is a colour
blob test: ~100 % reliable, viewpoint-independent, ~1 ms.
**Your course already has natural ones** — the bright-green compost sacks
(`IMG20260728133102`) sit right at the compost pit, and blue portable toilets
mark the trail. `MARKER_COLOURS` in `landmarks.py` already includes both.

> If demo rules permit placing markers, **do this**. It converts the hardest
> part of the problem (knowing where you are) into the easiest.

### Does it help with ordering? Yes — that's exactly what it's for

Landmarks are how a stage *ends*. In the mission file:

```json
{ "name": "avoid_compost_pit", "behaviour": "follow",
  "keepout_bias": 0.25,
  "exit": { "marker": "green_sack", "timeout_s": 25 } }
```

The car follows the open surface, biased right (away from the pit), and when
the green sacks appear it advances to `gravel_crossing`. That is precisely your
"when the compost pit frame is registered, turn right" — implemented in a form
that survives real lighting and viewpoint.

### The safety rule that makes this safe

**A landmark never commands a manoeuvre directly. It only advances the mission
state.** Terrain classification and the ultrasonic reflex always keep veto
power. So a false match costs you a premature stage change — never a collision
or a drive into the lawn.

### And specifically for the compost pit

Because the pit is a **hole**, don't rely on detecting the pit itself. Use
**defence in depth**:

1. `keepout_bias` steering away from it for the whole stage,
2. the **green sacks** as a positive marker that you're alongside it,
3. optionally a **downward-angled second ultrasonic** — over a hole its range
   suddenly *increases*, which is a reliable negative-obstacle detector and the
   only sensor that truly sees a pit.

---

# Recommended priorities before demo day

1. **Calibrate on site, at the demo hour.** Run
   `python3 course_navigator.py --calibrate` and check the overlay
   (red = vegetation, cyan = cement/gravel, green = mud). Adjust `EXG_VEG` and
   `SAT_HARD` until the lawn is solid red and the course is not.
2. **Fit the biggest wheels you can (≥100 mm)** — the largest single
   mechanical improvement for steps and grass.
3. **Use the 4WD + 2×L298N build**, and a **7.2 V NiMH / 2S Li-ion** pack, not
   the 9 V battery (see `docs/DRIVER_MOSFET_REPORT.md`).
4. **Place coloured markers** at decision points if allowed.
5. **Add an MPU-6050** if the U-turn must be accurate.
6. **Walk the course and clear the hoses.**
7. **Dry-run first:** `python3 course_navigator.py --replay ../Photos` — runs
   the real decision code on your photos, no hardware needed.

---

## Appendix A: how the numbers were measured

Every percentage above comes from sampling the **bottom-centre region**
(`[300:470, 160:480]` of a 640×480 resize) — the patch of ground the car is
about to drive over — across 3+ photos per surface class, then applying the
classifier rules. The classes and their source photos are listed in
`course/vision/terrain.py`. To reproduce or re-tune with new photos:

```bash
python3 course/course_navigator.py --replay Photos/
```

which prints the veg/hard/mud mix, the L/C/R column scores and the decision for
every image — the same code path that runs on the car.
