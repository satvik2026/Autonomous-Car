# Project Changelog

A record of how this project developed: what was built, what was changed, and
— more importantly — **why**. Newest last.

---

## Stage 1 — Initial off-road car

**Goal:** a Raspberry Pi 3B+ car that drives on a wide dirt track, avoids
obstacles, and uses a camera to stay off a grassy hill on one side and away
from a building on the other.

**Hardware as specified:** plywood chassis, 4 DC gear motors, Pi 3B+ (64-bit
Raspberry Pi OS), L293D driver, Pi camera, ultrasonic/IR sensor, 9 V battery
for the motors, undecided Pi supply.

### Created
| File | Purpose |
|---|---|
| `simple_obstacle_avoider.py` | Ultrasonic-only demo, to prove motors + driver + sensor before adding vision |
| `autonomous_car.py` | Full build: ultrasonic reflex layer + camera terrain steering |
| `docs/WIRING.md`, `docs/pinout.svg` | Pin-by-pin wiring, annotated 40-pin diagram |
| `requirements.txt`, `examples/route.gpx` | Dependencies; GPX format example |
| `README.md` | Full write-up |

### Key decisions
- **Two decision layers, kept separate.** A fast ultrasonic *reflex* that always
  wins, and a slower camera *strategy* layer. Vision picks the route; ultrasound
  prevents collisions. Keeping them independent means a vision failure can never
  cause a collision.
- **Skid steer** — no steering servo. Turning by driving each side at different
  speeds, with small deviations made by easing one side.
- **`picamera2`, not `picamera`** — required by 64-bit Raspberry Pi OS.
- **Vision-only navigation, no GPS.** With no GPS module fitted, coordinates
  could not be acted on; and hobby GPS (~2.5 m) is wider than the car, so it
  could report "on route" while half on the hill. The route was defined by what
  the terrain *looks* like instead.
- **Separate power supplies.** Pi on a 5 V USB power bank, motors on their own
  battery, grounds tied together — the standard fix for brown-out reboots.

### Concerns raised at the time
- A 9 V PP3 battery cannot supply four loaded motors uphill.
- The L293D (~0.6 A/channel, ~2 V drop) is marginal for this job.

---

## Stage 2 — Motor driver investigation

**Trigger:** question about L293D vs two L298N, and how to power the L298N
from 12 V.

**Finding:** the L298N is *not* more efficient than the L293D — it drops
slightly more voltage per amp — but it carries ~3× the current and has a
heatsink, and that headroom is exactly what runs out on a hill.

**Clarified:** no voltage divider is needed on any motor-driver control line
(3.3 V GPIO drives them directly). The divider in this project is only for the
HC-SR04 ECHO pin, and that is unchanged by the driver choice. No boost
converter is needed either — match the battery to the motors and trim with PWM.

---

## Stage 3 — MOSFET drivers

### Created
- `docs/pinout_dual_l298n.svg` — two L298N, one per side
- `docs/pinout_mosfet_tb6612.svg` — MOSFET system
- `docs/DRIVER_MOSFET_REPORT.md` — how MOSFET H-bridges work and what changes

**Core insight:** bipolar drivers (L293D/L298N) drop a fixed ~2–3 V as *heat*
regardless of current; a MOSFET drops `current × a very small resistance`
(~0.1–0.3 V). On a 7.4 V pack that is roughly 5 V vs 7.2 V reaching the motor —
a large torque difference precisely when climbing.

**Design choice:** all three driver options were wired to the **same six GPIO
pins**, per side, so the driver can be swapped **with no code change**.

**Caveat recorded honestly:** the TB6612's *continuous* rating (1.2 A/ch) is
lower than the L298N's (2 A/ch). Its advantage is efficiency, not raw current.
BTS7960 was noted for bigger motors — with a warning that it needs a different
control scheme and *would* require code changes.

---

## Stage 4 — L298N demo builds

**Trigger:** request for fresh, simple demos on a 9 V battery, plus versions
for the VEGA ARIES v2.0 board.

### Created
- `demos/raspberry_pi/l298n_2wd_obstacle_avoider.py` (2WD, 1 driver)
- `demos/raspberry_pi/l298n_4wd_obstacle_avoider.py` (4WD, 2 drivers)
- `demos/vega_aries/vega_2wd_obstacle_avoider/` and `vega_4wd_obstacle_avoider/`
- Four pinout diagrams + `demos/README.md`

**Design choice:** for 4WD, one driver board per *side* with its two channels
wired in parallel. Both wheels on a side always move together — which is what
skid steering needs — so the control code stays identical to the 2WD version
while each motor gets its own H-bridge.

**Platform difference documented:** the VEGA ARIES tolerates the HC-SR04's 5 V
ECHO directly, so it needs **no voltage divider**, unlike the Pi. This was the
stated reason for using it.

---

## Stage 5 — Repository access

Pushing was blocked for several attempts with `403 Resource not accessible by
integration` on both the git relay and the GitHub API — the GitHub App had read
but not write permission. Once granted, all work was pushed.

`main` initially held only an auto-generated stub README on an unrelated
history; the project was merged in with `--allow-unrelated-histories`,
preserving the initial commit. `main` then became the working branch.

*Note: deleting the old `claude/...` branch remotely is blocked by an
environment guardrail and remains a manual step.*

---

## Stage 6 — Course analysis (major conceptual change)

**Trigger:** 98 site photos and a 2m50s video of the real demo course.

### The finding that changed the project

The existing colour model was measured against the real photos and **failed
dangerously**:

| Surface | Old model said | Problem |
|---|---|---|
| Dry lawn grass | 52.5 % "drivable" | **would drive onto the keep-out lawn** |
| Cement | 96.6 % "ground" | indistinguishable from mud |
| Wet mud | 46.9 % "ground" | would refuse perfectly good ground |

Root cause: hue alone cannot separate them — dry grass hue sits *inside* the
"ground" band, and cement sits on top of mud.

### The conceptual shift

1. **Vegetation by Excess-Green index, not hue.** Lawn detection went from
   20.9 % → 81.8 %.
2. **Vegetation is a density, not a boolean.** The single most important
   realisation: **the mud course is itself ~32 % grass tufts**, while the lawn
   is ~82 %. "Avoid anything green" would have refused the course itself.
3. **Drivable surfaces expanded** from mud only to mud + cement + gravel.
4. **Keep-out became a per-stage policy, not a global constant** — this is what
   allows "never drive on grass" and "climb the grassy slope" to coexist.
5. **Route = an ordered list of stages**, each ending on a sensed condition.

### Created
- `course/vision/terrain.py`, `course/vision/landmarks.py`
- `course/mission.py`, `course/missions/demo_course.json`
- `course/course_navigator.py` (with `--replay` for hardware-free dry runs)
- `course/tools/calibrate_terrain.py`
- `docs/COURSE_ANALYSIS.md`, `docs/course_validation.jpg`

### Hazards identified from the imagery
- **The compost pit is a hole** — invisible to a forward ultrasonic, which
  reads "clear" until the car drives in.
- A **garden hose** lying across the course.
- A **~30 cm retaining wall** (not climbable) and a **volleyball net**.
- The **same concrete edge** is a sharp 6–10 cm lip in one place and nearly
  flush in another.

### Also noted
The site video showed the camera held low and angled down, producing frames of
pure ground texture with no route information — hence the recommendation to
mount the camera 15–20 cm up, tilted down 20–30°.

---

## Stage 7 — Defect fixes and honest limits

**Trigger:** follow-up questions on ramps, cement/mud confusion, and landmarks.
Investigating them uncovered **three real defects in Stage 6's code**.

### Defect A — the zone identifier was broken
Measured against ground truth, it scored **2/11 with wrong labels**: the mud
course was never identified at all, cement was reported as gravel, and wet mud
matched cement. Cause: the `mud` signature was wrong, and gravel/cement were
only 0.14 apart while the tolerance was 0.45.

**Consequence:** route stages either never fired or fired early. Because
steering was unaffected (both surfaces are drivable), **the failure was
invisible until the sequence silently broke.**

**Fix — a third axis: surface roughness.** Cement is smooth, gravel is rough,
and this is independent of colour (cement 66 vs gravel 307, ~4.6× apart).
Added a confidence margin (abstain rather than guess) and `ZoneVoter` temporal
voting so one puddle or shadow cannot skip a stage. Signatures were re-measured
through the real code path and the parameters grid-searched under the hard
constraint of **never returning a wrong zone**.

**Result: 13/15 correct, 2 abstain, 0 wrong** — and the 8 original steering
cases still pass unchanged.

### Defect B — ORB landmarks were dead code
`mission.py` supported `exit: {"landmark": ...}`, but the navigator never
supplied a landmark value, so such stages **could never fire**. The tool the
docs told users to run, `tools/capture_landmark.py`, **did not exist**.

**Fix:** wrote the tool, wired `LandmarkBook` into the navigator (throttled,
since ORB is slow on a Pi 3B+), and verified end-to-end. Testing found and
fixed a resolution mismatch (full-size photos vs the car's 640×480 frames).
Final behaviour: recognises the pit from an unseen photo, **zero false
positives** on cement, lawn and mud court.

### Defect C — monocular step detection does not work
Tested directly: a sharp 6–10 cm lip, a flush crossable edge, and plain open
ground all produced **effectively identical** edge signatures. A small step
genuinely looks like flat ground to one camera.

**Consequence:** an earlier crossing-point function was steering off **lighting
gradients** — a plain cement slab produced the strongest apparent "crossing
point" on the whole course.

**Fix:** the code now requires genuine step evidence before steering, and
therefore **does nothing on all site imagery** — going straight instead of
swerving at shadows. This is the correct, safe outcome. Step handling was moved
onto two mechanisms that do work: **route context** (a `cross_step` stage that
squares up and bursts across) and an **optional downward ultrasonic**, which
also detects the compost pit — a hole reads as ground suddenly further away.

### Created
- `course/vision/steps.py`, `course/tools/capture_landmark.py`
- `docs/DEMO_DAY.md`, `docs/EXPLAINED_SIMPLY.md`, `CHANGELOG.md`

### Changed
- `terrain.py` — added `roughness()`, extended `surface_mix()`
- `landmarks.py` — texture-aware matching, confidence margin, `ZoneVoter`
- `mission.py` — added `burst_speed`
- `course_navigator.py` — `cross_step` behaviour, landmark wiring, zone voting,
  optional down-sensor with hole detection
- `missions/demo_course.json` — re-measured signatures, new crossing stage

---

## Themes across the project

- **Measure, don't assume.** Every significant change came from testing against
  real data. Three separate times the intuitive answer was wrong: "green means
  grass", "cement looks different from gravel", and "a camera can see a step".
- **Fail safe, not clever.** When the car cannot tell, it stops or goes
  straight rather than guessing. The zone matcher abstains; the step finder
  does nothing without evidence; the steering refuses rather than picking the
  least-bad option.
- **Layer by authority.** Reflex beats vision; vision beats mission. A landmark
  can only advance a stage — it can never steer the car.
- **Keep the hardware swappable.** One pin layout across all three motor
  drivers, so hardware can change without touching code.
- **State limits plainly.** The timed U-turn drifts; the TB6612 carries less
  current than an L298N; a camera cannot see a 6 cm step. Each is written down
  next to the thing it affects.
