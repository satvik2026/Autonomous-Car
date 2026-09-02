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
   This is a **negative obstacle**: a forward range rule cannot help, and one
   camera cannot measure depth either. The only sensor that detects it
   directly is a **downward-angled second ultrasonic** (§ "Fitting the ground
   sensor"). Without one, the pit is handled by route context alone. This is
   the single most important safety item on the course.
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
*"mud course → turn → slopes → avoid compost → gravel → cement → court or
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
| **Ultrasonic** | "wall within 0.5 m" | High — good for end-of-court |
| **Timeout** | "40 s elapsed" | Always available — the safety net |
| **Colour cue** | "green sack seen" | Medium — detection is near-perfect, but nothing may be placed, so it depends on an object being where you last saw it |
| **Ground sensor** (downward) | "hole ahead" | High, if fitted — the only pit detector |
| ORB landmark | "building corner recognised" | Medium (see Q5) |

Note what moved: **colour cues are no longer the top row.** Placing markers is
off the table for this course, so the only coloured objects available are ones
that happen to be standing there — the green compost sacks, the blue toilets.
The *detection* is still near-100 %; what you lose is control over where they
are and whether they are still there on the day. That demotes them from
"primary exit test" to "bonus exit, always backed by a timeout".

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
   that's your exit test. If nothing changes, fall back to a timeout (and add
   a colour cue in front of it if a suitable object happens to be there).
3. Pick the behaviour (follow / creep for rough / pivot for turns).
4. Set `keepout_bias` if a hazard is always on one known side.
5. **Always set `timeout_s`** so a missed transition can't hang the run.

Your example encodes as (already written in the mission file):

| # | Stage | Behaviour | Exits when |
|---|---|---|---|
| 1 | `mud_course` | follow, bias left (bank on right) | wall within 0.5 m *or* 60 s |
| 2 | `turn_to_slopes` | pivot left | 1.3 s elapsed (~90°) |
| 3 | `slopes` | creep, speed 0.75 | surface = gravel |
| 4 | `avoid_compost_pit` | follow, bias **right**, slow | green sacks seen *or* 25 s |
| 5 | `gravel_crossing` | creep | surface = cement |
| 6 | `cross_onto_cement` | square up, burst | surface = cement *or* 12 s |
| 7 | `cement_run` | follow | 40 s |

## What the result looks like

```
[1/7] mud_course        surf=mud    veg=0.31 steer=-0.12 d=142.3cm t= 12.4s
[1/7] mud_course        surf=mud    veg=0.29 steer=+0.05 d= 96.1cm t= 13.4s
-> EXIT mud_course (obstacle within 0.5m)
[2/7] turn_to_slopes    surf=mud    veg=0.30 steer=+0.00 d=180.0cm t=  0.4s
-> EXIT turn_to_slopes (timeout 1.3s)
[3/7] slopes            surf=None   veg=0.44 steer=-0.31 d=155.2cm t=  6.1s
-> EXIT slopes (surface==gravel held 1.5s)
...
MISSION COMPLETE
  mud_course            41.2s  (obstacle within 0.5m)
  turn_to_slopes         1.3s  (timeout 1.3s)
  slopes                18.7s  (surface==gravel held 1.5s)
```

You get a live stage trace during the run and a transition log afterwards —
so when something goes wrong you know *exactly* which stage and which test.

## Honest limitation: the timed turn

The car has no compass, so a turn is a **timed open-loop pivot** — it drifts,
and the drift changes with surface grip and battery charge.

**How much this matters depends entirely on the angle**, which is why the route
now uses a **simple ~90° turn** rather than a half turn. The error is roughly
proportional to the angle: if the pivot rate is off by 10 %, a 180° turn lands
18° out, while a 90° turn lands 9° out. And what happens next is not "hope" —
the following stage is `follow`, which steers on the camera, so a heading error
of that size is corrected within a metre of driving. A 90° turn is comfortably
inside what the next stage can absorb.

So: **no IMU is needed for this route.** What *is* needed is re-timing the
pivot on the day:

```
pivot for 5 s at the stage speed, count the turns, divide
```

The mission ships 1.3 s at speed 0.55, which assumes ~70°/s. That is a starting
point, not a measurement — grip on wet mud differs from dry, and a flat battery
turns slower than a fresh one. Re-time it on site and edit `timeout_s`.

If you later need a turn to land precisely (a tight gap, a half turn), the two
fixes still stand: end the pivot on a *sensed* condition instead of time, or
add an **MPU-6050 IMU** (~2 USD) and close the loop on yaw. Neither is required
at 90°.

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

**Tier 3 — Colour cues from what is already there.** Detecting a big saturated
colour blob is ~100 % reliable, viewpoint-independent and takes ~1 ms. Placed
markers would be the ideal version of this — but **nothing may be placed on
this course**, so the tier is limited to objects that will be standing there
anyway: the bright-green compost sacks at the pit (`IMG20260728133102`) and the
blue portable toilets along the trail. `MARKER_COLOURS` in `landmarks.py`
carries exactly those two.

> What you lose without placed markers is not detection quality — it is
> **control**. A marker goes precisely at the decision point and stays put; a
> sack is where somebody left it, might be moved before demo day, and is only
> in frame from certain angles. So a colour cue is a **bonus exit test, never
> the only one**: every stage using one also carries a `timeout_s`, and the
> surface signature (Tier 1) stays the workhorse.

### Does it help with ordering? Yes — that's exactly what it's for

Landmarks are how a stage *ends*. In the mission file:

```json
{ "name": "avoid_compost_pit", "behaviour": "follow",
  "keepout_bias": 0.25,
  "exit": { "marker": "green_sack", "timeout_s": 25 } }
```

The car follows the open surface, biased right (away from the pit), and when
the green sacks appear it advances to `gravel_crossing` — or the timeout does
it. That is precisely your "when the compost pit frame is registered, turn
right" — implemented in a form that survives real lighting and viewpoint, with
a fallback for the day the sacks have been moved.

### The safety rule that makes this safe

**A landmark never commands a manoeuvre directly. It only advances the mission
state.** Terrain classification and the ultrasonic reflex always keep veto
power. So a false match costs you a premature stage change — never a collision
or a drive into the lawn.

### And specifically for the compost pit

Because the pit is a **hole**, don't rely on detecting the pit itself. Use
**defence in depth**:

1. `keepout_bias` steering away from it for the whole stage,
2. a **low stage speed** (0.50), so the car stays inside the warning distance
   the ground sensor can actually give it,
3. the **green sacks** as a positive cue that you're alongside it,
4. a **timeout** behind the sacks, in case they've moved,
5. the **downward-angled second ultrasonic** — over a hole its range suddenly
   increases or the echo vanishes. This is the only layer that senses the pit
   itself rather than inferring it from the route.

Without layer 5, layers 1–4 are all route context: the car never knows the pit
is there, it just drives past where you told it the pit would be.

## Fitting the ground sensor

**Is it necessary?** Strictly, no — the car completes the route without it, on
route context alone. But with markers off the table, layers 1–4 above are all
open-loop, and the pit is the one hazard on this course that ends the run
outright. It is ~2 USD and two spare GPIO for the only closed-loop detection of
that hazard, so: fit it.

**Where it goes is the part that decides whether it works.** The intuitive
mounting point — the 2–3 cm lip on the front wall, beside the camera — fails on
geometry. A sensor `h` above the ground tilted `t` below horizontal meets the
ground at slant range `h/sin(t)`, i.e. `h/tan(t)` in front of itself:

| Mount | Reads flat | Ground ahead of wheels | Speed limit | Verdict |
|---|---|---|---|---|
| Front wall, 3 cm, 30° | 4.2 cm | 11 cm | 0.22 m/s | **No** — inside its own ~2 cm blind spot |
| Mast, 15 cm, 30° | 21 cm | 23 cm | 0.46 m/s | Workable |
| **Mast, 20 cm, 35°** | **26 cm** | **25 cm** | **0.50 m/s** | **Recommended** |
| Mast, 25 cm, 30° | 35 cm | 33 cm | 0.66 m/s | Better, if it stays rigid |

Reproduce for your own build with
`python3 course/tools/calibrate_ground.py --geometry`.

Three things that decide whether it works in the field:

- **Height, not angle, is the lever.** Height buys warning distance *and*
  reduces pitch sensitivity. Go as high as the chassis will carry rigidly.
- **Chassis pitch is the noise floor.** The reading moves with the tilt angle,
  so bouncing over rough ground swings it — about 2 cm per ±5° at the
  recommended mount, against a 7.8 cm signal from a 6 cm step. That is why the
  mount must be *rigid* and why the navigator requires three consecutive bad
  frames before it believes a hole.
- **A missing echo means the same thing as a long one.** A grazing beam
  scatters off soft mud and returns nothing; so does a deep pit. The code
  treats both as "hole" — stopping needlessly is cheap. If flat-ground
  calibration shows >10 % dropouts, steepen the tilt.

The mount implies a **speed limit**: warning distance ÷ the ~0.5 s the car
needs to confirm the reading and stop. At the recommended mount that is
~0.5 m/s, which is why the pit stage runs slower than the rest of the route.

Wiring, the mount sketch and calibration steps: `WIRING.md` §2b.

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
4. **Fit the downward ground sensor** on a rigid ~20 cm mast, 35° down, then
   calibrate it on site (`tools/calibrate_ground.py --measure`). Nothing may be
   placed on the course, so this is the only sensor that will ever detect the
   compost pit.
5. **Re-time the pivot stage** on the day's surface. The ~90° turn needs no
   IMU, but it does need today's turn rate.
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
