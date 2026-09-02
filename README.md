# Autonomous Off-Road Car — Raspberry Pi 3B+

A skid-steer (tank-drive) autonomous car that runs a **known sequence of
outdoor terrain** — mud, slope, gravel, cement — using a camera to stay on the
drivable ground, an ultrasonic sensor to avoid collisions, and a small
finite-state "mission" to move through the course in order. It steers by
vision, sequences by the terrain under its wheels, and never needs GPS.

The project grew in two halves, and both are in the repo:

- **Starter programs** (repo root) — two small scripts to prove the hardware
  and the basic camera-steering idea. Build these first.
- **The course navigation system** (`course/`) — the real deliverable: a
  two-axis terrain classifier, a mission sequencer, landmark/colour cues, step
  crossing, and an optional downward ground sensor that sees holes. This is
  what runs the demo course end to end.

> **Read this whole README before wiring anything or running code.** A couple
> of places in a typical parts list fight physics (a 9 V battery driving four
> motors uphill, an L293D's current limit). Those are called out in
> **[Hardware reality check](#hardware-reality-check)** with cheap fixes.

---

## Contents

- [What's in this repo](#whats-in-this-repo)
- [The three decision layers](#the-three-decision-layers)
- [The course as a sequence of stages](#the-course-as-a-sequence-of-stages)
- [Seeing the ground: the two-axis terrain model](#seeing-the-ground-the-two-axis-terrain-model)
- [Knowing where you are without GPS](#knowing-where-you-are-without-gps)
- [The downward ground sensor (holes and steps)](#the-downward-ground-sensor-holes-and-steps)
- [Sensing: IR vs. ultrasonic](#sensing-ir-vs-ultrasonic)
- [Software, OS, and powering the Pi](#software-os-and-powering-the-pi)
- [Hardware reality check](#hardware-reality-check)
- [Pinout & wiring](#pinout--wiring)
- [Setup](#setup)
- [Running it](#running-it)
- [Calibrating on-site](#calibrating-on-site)
- [Tests & CI](#tests--ci)
- [Where to read next](#where-to-read-next)

---

## What's in this repo

**Starter programs (repo root) — prove the hardware first**

| File | What it is |
|---|---|
| `simple_obstacle_avoider.py` | Drives forward; when the ultrasonic sensor sees something close, it stops, backs up, and turns. No camera, no route. Use it to prove your motors, driver, and sensor are wired correctly. |
| `autonomous_car.py` | The original full build: ultrasonic reflex layer **plus** a simple hue-based camera steer. Superseded on the real course by `course/` (see the note below), but still the clearest small example of camera-plus-reflex. |

**The course navigation system (`course/`) — the real project**

| File | What it contains |
|---|---|
| `course/course_navigator.py` | Main program. Ties the three layers together; `--replay` and `--calibrate` modes. Optional downward ground sensor with hole/step detection. |
| `course/mission.py` | The route sequencer: `Stage` and `Mission`, exit tests, the stage log. |
| `course/missions/demo_course.json` | The route order, the measured zone signatures, and per-stage notes. **This is the file you edit to define a route.** |
| `course/vision/terrain.py` | Two-axis terrain classifier (ExG vegetation + saturation + roughness) and the column-scoring steer. |
| `course/vision/landmarks.py` | Colour cues, ORB landmark matching, zone matching, and a vote filter. |
| `course/vision/steps.py` | Where to cross a step or slab edge — with an honest account of what one camera cannot do. |
| `course/tools/calibrate_terrain.py` | On-site terrain-threshold tuning. |
| `course/tools/calibrate_ground.py` | Downward-sensor mount geometry, flat-ground calibration, live step/hole watch. |
| `course/tools/capture_landmark.py` | Register landmark views for recognition. |

**Demos, docs, tests**

| Path | What it is |
|---|---|
| `demos/` | Standalone L298N obstacle-avoiders for the Pi and the VEGA ARIES v2.0 board (2WD and 4WD), plus driver pinout diagrams. |
| `docs/` | The full write-up — see [Where to read next](#where-to-read-next). |
| `tests/`, `.github/workflows/checks.yml` | The test suite and the CI that runs it. |
| `examples/route.gpx` | Example GPX — only relevant if you add a GPS module later (see [Knowing where you are without GPS](#knowing-where-you-are-without-gps)). |

> **Which program is "the" car?** For the demo course, it's
> `course/course_navigator.py`. The root `autonomous_car.py` uses a simpler
> green-vs-brown colour rule that was measured to fail on the real course (dry
> lawn reads as drivable, cement is indistinguishable from mud). The `course/`
> terrain model fixes that — see
> [the two-axis terrain model](#seeing-the-ground-the-two-axis-terrain-model).

---

## The three decision layers

Keeping these separate — and ranked by authority — is the whole trick:

```
                 ┌──────────────────────────────────────────┐
                 │            CONTROL LOOP (~10 Hz)           │
                 └──────────────────────────────────────────┘
                                  │
   ┌──────────────────────────────┼──────────────────────────────┐
   │                              │                              │
 REFLEX                        TERRAIN                        MISSION
 (ultrasonic)                  (camera + OpenCV)              (sequencer)
   │                              │                              │
 "Is something                 "Which way is                 "Which STAGE of
  right in front                 drivable ground,             the course am I in,
  of me NOW?"                    and never into               and when do I
   │                             vegetation."                 advance?"
   │ if close →                    │ steer −1…+1                 │ pick behaviour,
   ▼ STOP, reverse, turn           ▼                             ▼ test for exit
   └───────────────────────────────┴──────────────┬─────────────┘
                                                   ▼
                                     DIFFERENTIAL DRIVE (skid steer)
                              left pair and right pair at different speeds
```

- **Reflex** is dumb, fast, and always wins. "Wall 25 cm ahead" stops and turns
  the car regardless of what the camera or mission want. Collision insurance.
- **Terrain** is the camera. Each frame it produces **one number** — a steer
  value in `[-1, +1]` — that keeps the most-drivable ground centred and refuses
  to steer into vegetation. It never sets speed and never commands a manoeuvre.
- **Mission** is the sequencer. It knows the course is an *ordered list of
  stages*, picks the behaviour for the current stage (follow / creep / cross a
  step / pivot), and decides when the stage is done.

**Layer by authority:** reflex beats terrain; terrain beats mission. A landmark
or a mission cue can only *advance a stage* — it can never steer the car into
something. So a misread never becomes a collision.

**Steering** is skid steer / differential drive: both left wheels ganged, both
right wheels ganged, no steering servo. Straight = equal speed; gentle arc =
ease one side; pivot = one side forward, the other slow or reversed. Ideal for
grass and rough ground.

---

## The course as a sequence of stages

There's no GPS and no map. A route here is **not coordinates** — it is an
ordered list of *stages*, each of which is exactly three things:

| Part | Meaning | Example |
|---|---|---|
| **Behaviour** | what to do while in this stage | follow / creep / cross_step / pivot |
| **Exit test** | how the car knows the stage is done | "surface became gravel for 1.5 s" |
| **Guards** | what must never happen | never enter vegetation; never collide |

That's a finite-state machine, and it's the right tool because the course is a
*chain of distinguishable surfaces* the camera can tell apart. The shipped
example (`course/missions/demo_course.json`) encodes this route:

| # | Stage | Behaviour | Exits when |
|---|---|---|---|
| 1 | `mud_course` | follow, bias left (grass bank on the right) | obstacle within 0.5 m *or* 60 s |
| 2 | `turn_to_slopes` | pivot left (~90°) | 1.3 s elapsed |
| 3 | `slopes` | creep (more torque for the climb) | surface = gravel |
| 4 | `avoid_compost_pit` | follow, bias right, **slow** | green sacks seen *or* 25 s |
| 5 | `gravel_crossing` | creep (low traction) | surface = cement |
| 6 | `cross_onto_cement` | square up, then burst over the lip | surface = cement *or* 12 s |
| 7 | `cement_run` | follow to the finish | 40 s |

You author your own route by editing that JSON — no Python needed. Two rules
that keep a run safe:

- **Every stage has a `timeout_s`.** It's the universal fallback so a missed
  cue can never hang the run forever.
- **Timed pivots are open-loop, so re-time them on the day.** Grip and battery
  charge change the turn rate. The route deliberately uses a **simple ~90°
  turn, not a U-turn**: open-loop error scales with the angle, and the `follow`
  stage that comes next steers on the camera and washes out the few degrees of
  drift — so **no IMU is needed** for a turn this size.

---

## Seeing the ground: the two-axis terrain model

The original green-vs-brown rule (still in root `autonomous_car.py`) was
measured against real course photos and fails three ways: dry lawn reads as
drivable, cement is indistinguishable from mud, and wet mud gets refused. Hue
alone cannot separate these — dry grass sits inside the "ground" hue band, and
cement sits on top of mud.

`course/vision/terrain.py` fixes it with **two axes**:

1. **Vegetation via Excess-Green (ExG),** not hue:
   `ExG = (2G − R − B) / (R + G + B)`. It keys on green being *relatively*
   stronger, so it survives yellowed grass, shade, and overcast — where a fixed
   hue window collapses. (Grass lawn detection: 20.9 % old → 81.8 % ExG.)
2. **Hard surface vs. mud via saturation.** Cement is washed-out grey (low
   saturation); mud is saturated red-brown. Both drive fine, but telling them
   apart is what lets the mission know *which zone* it's in.

A third **roughness** axis separates a smooth cement slab from grey gravel,
which colour alone cannot do.

**The most important consequence:** the mud course is **not** grass-free — it's
~32 % grass tufts. So "any green → avoid" would refuse to drive on the course
itself. Vegetation is treated as a **density, not a boolean**: ~32 % veg =
drivable mud, ~82 % veg = lawn, keep out. `VEG_BLOCK_FRAC` (0.55) is that
threshold and the single most important tuning number.

How a frame becomes a steer value: crop to the ground ahead → classify every
pixel VEG / HARD / MUD → split into left | centre | right columns → score each
`drivable − 1.5 × vegetation` → **veto any column over 55 % vegetation** (the
keep-out rule) → steer toward the best remaining column, or stop if none is
drivable. Keep-out is per-stage, so climbing a grassy *slope* is still allowed
when that's the job — a bias, not a blanket ban.

---

## Knowing where you are without GPS

**You don't need coordinates, and with no GPS module you can't use them.** A
hobby GPS (~2.5 m) is wider than the car — it could report "on route" while
you're half on the hill. The route is *visual*: follow the drivable ground,
sequence on the surface under the wheels.

Recognising *where* you are, cheapest-first:

- **Surface signatures (always on).** Match the *terrain mix*, not the picture.
  Each zone has a measured signature (mud ~0.90 mud; gravel ~0.87 hard; cement
  ~0.94 hard; lawn >0.80 veg) that is robust to viewpoint and lighting. This is
  the workhorse that drives the sequencer.
- **Colour cues (bonus).** A big saturated colour blob detects near-perfectly
  in ~1 ms. **Nothing may be placed on this course**, so this is limited to
  objects already there — the bright-green compost sacks by the pit, the blue
  toilets on the trail. Because you don't control where they are or whether
  they've moved, a colour cue is always a **bonus exit behind a timeout**,
  never the only way out of a stage.
- **ORB landmarks (occasional).** For genuinely distinctive, static, man-made
  places, store ORB keypoints (not pixels) with a geometric-consistency check.
  Throttled, because ORB is slow on a Pi 3B+.

**If you later add a GPS module** and want true waypoint following,
`examples/route.gpx` shows the file format and `course_navigator` could layer
GPS bearing under the camera override. Build and run vision-only first.

---

## The downward ground sensor (holes and steps)

The one hazard nothing else on the car can see is a **hole** — the compost pit
is an *excavated hole*. A forward ultrasonic reads "all clear" over a pit right
up until the car drives in, and one camera cannot measure the depth of a small
step or drop either (this is measured, not assumed — see `course/vision/steps.py`).

A **second HC-SR04, angled down at the ground ahead**, is the only sensor that
sees both: its range **shortens** over a step and **lengthens — or goes
silent —** over a hole. It's ~2 USD and off by default (`DOWN_SENSOR_ENABLED`).
Two concepts make it work:

- **It goes on a short mast, ~20 cm up and ~35° down — not on the front wall.**
  Bolted to the 2–3 cm front lip beside the camera it reads ~4 cm on flat
  ground (inside its own ~2 cm blind spot) and watches a patch 11 cm ahead,
  which arrives before the car could stop. Height fixes both. The front wall
  stays for the forward sensor and camera, side by side. Run
  `python3 course/tools/calibrate_ground.py --geometry` before drilling.
- **Readings are debounced and a missing echo counts as a hole.** Chassis pitch
  swings the reading ~2 cm per ±5°, so a real detection needs three consecutive
  bad frames; and a deep pit (or a grazing beam off soft mud) returns no echo,
  which is treated as a hole — a needless stop costs seconds, the pit costs the
  run.

The mount implies a **speed limit** (warning distance ÷ reaction time, ~0.5 m/s
at the recommended geometry), which is why the pit stage runs slower than the
rest of the route. Full mount sketch, wiring (it needs its **own** voltage
divider), and calibration steps are in **`docs/WIRING.md` §2b**.

---

## Sensing: IR vs. ultrasonic

Use **ultrasonic (HC-SR04)** as the main distance sensor for an outdoor car.

| | **Ultrasonic (HC-SR04)** | **IR (Sharp analog, or digital obstacle module)** |
|---|---|---|
| Senses | Times a sound echo → real **distance** (cm). | Reflected IR intensity. Cheap digital module = just a near/far flag. |
| Range | ~2 cm – 4 m | Sharp: ~10–80 cm. Digital: a few cm to ~30 cm. |
| Real distance? | **Yes** — "stop at 25 cm." | Analog: yes-ish. Digital: no, a threshold. |
| Sunlight | **Unaffected** (it's sound). | **Badly affected** — outdoor IR washes cheap sensors out. |
| Verdict here | ✅ Primary sensor: real distances, sunlight-proof. | ⚠️ Fine as a cheap backup bump-detector, not the main sensor. |

Wire an HC-SR04 as the reflex sensor (every program assumes this). `autonomous_car.py`
has a commented `USE_IR_BACKUP` hook if you want IR as a redundant close-range trigger.

---

## Software, OS, and powering the Pi

**OS:** Raspberry Pi OS 64-bit (Bookworm) is correct. One consequence: the
camera stack is **`libcamera` / `picamera2`**, *not* the old `picamera`. This
project uses `picamera2`. (A tutorial doing `import picamera` is for the old OS
and won't work.)

**Getting code onto the Pi:** `git clone` on the Pi (then `git pull` to
update) is easiest; `scp` or VS Code Remote-SSH also work.

**Powering the Pi:** a **5 V / ≥2.5 A USB power bank** (3 A better) with a
short, thick micro-USB cable — powered **separately from the motors**. Motor
noise on a shared supply is the single most common reason a Pi car "randomly
resets." **Power bank → Pi. Motor battery → motors. Common-ground them, keep
the positive rails separate.**

---

## Hardware reality check

Your parts list works for a **demo**, but "off-road, uphill, on grass" asks a
lot of two parts:

1. **A 9 V PP3 battery cannot drive four motors uphill on grass for long.** It
   delivers little current before sagging; loaded gear motors pull an amp or
   more each. **Fix:** a **6×AA NiMH (7.2 V)** or **2S Li-ion (~7.4 V)** pack,
   separate from the Pi, common-grounded. This is the "toy → climbs the hill"
   change.
2. **The L293D is weak and runs hot** (~1.5–2 V drop, ~0.6 A/channel). **Fix:**
   an **L298N module** (~2 A/channel, drop-in, code unchanged) or a **TB6612FNG**
   (more efficient). The `course/` pins match a **dual-L298N 4WD build** (one
   driver per side). See `docs/DRIVER_MOSFET_REPORT.md` for the comparison and
   `demos/` for ready-to-run L298N examples.
3. **Common ground is mandatory** — Pi, driver, motor battery, sensors all tied
   together, or you get flaky readings and ignored commands.
4. **Back-EMF** from the motors can reboot a poorly-powered Pi — another reason
   for the separate power bank.

---

## Pinout & wiring

- **Diagrams:** `docs/pinout.svg` (single L293D), `docs/pinout_dual_l298n.svg`
  (the 4WD course build), `docs/pinout_mosfet_tb6612.svg`.
- **Full pin/wire tables, both voltage dividers, and the ground-sensor mount:**
  **`docs/WIRING.md`** (the downward sensor is §2b).

Quick GPIO summary (BCM numbering, as used by `course/course_navigator.py`):

| Function | BCM GPIO | Physical | Goes to |
|---|---|---|---|
| Left pair — direction A / B | GPIO5 / GPIO6 | 29 / 31 | left driver IN1 / IN2 |
| Left pair — enable/PWM | GPIO12 | 32 | left driver ENA |
| Right pair — direction A / B | GPIO20 / GPIO21 | 38 / 40 | right driver IN1 / IN2 |
| Right pair — enable/PWM | GPIO13 | 33 | right driver ENB |
| Forward ultrasonic TRIG / ECHO | GPIO23 / GPIO24 | 16 / 18 | HC-SR04 (ECHO via divider) |
| **Downward ultrasonic** TRIG / ECHO | GPIO27 / GPIO22 | 13 / 15 | 2nd HC-SR04 (its **own** divider) |
| (Optional) IR backup | GPIO25 | 22 | IR module OUT |
| Camera | — | CSI ribbon | Pi camera (not a GPIO pin) |

> The root `autonomous_car.py` uses the same left/right pins on a single L293D.
> The ground-sensor pins are only used when `DOWN_SENSOR_ENABLED = True`.

---

## Setup

On the Pi (Raspberry Pi OS 64-bit Bookworm):

```bash
sudo apt update
sudo apt install -y python3-gpiozero python3-picamera2 python3-opencv python3-numpy pigpio
sudo systemctl enable --now pigpiod      # steadier PWM (optional but recommended)
```

`gpiozero`, `picamera2`, and OpenCV install most reliably as apt packages on
Bookworm. `requirements.txt` lists the pip names for non-apt environments.

---

## Running it

**Always bench-test first, wheels off the ground.**

```bash
# Starter — obstacle-avoiding demo (no camera):
python3 simple_obstacle_avoider.py

# The course navigator (camera + terrain + mission + ultrasonic):
python3 course/course_navigator.py --mission missions/demo_course.json

# Dry-run the real decision code over site photos on a laptop — no hardware:
python3 course/course_navigator.py --replay ../Photos

# Save a calibration frame + overlay from the live camera:
python3 course/course_navigator.py --calibrate
```

`--replay` is the one to run before demo day: it executes the exact on-car
decision code over saved photos and prints what the car *would* do for each,
so you can tune thresholds on a laptop. Stop any program with **Ctrl-C** — all
of them cut the motors safely.

---

## Calibrating on-site

Outdoor colour shifts a lot, so calibrate in the light you'll drive in:

- **Terrain:** `python3 course/tools/calibrate_terrain.py ../Photos` re-measures
  the zone signatures and the veg/hard/mud thresholds for your conditions.
- **Ground sensor:** `python3 course/tools/calibrate_ground.py --measure` on
  flat ground prints the `DOWN_NOMINAL_M` / `DOWN_TOLERANCE` to paste into
  `course_navigator.py`, then `--watch` classifies step/hole live as you walk
  the car to the pit edge. **Never guess these** — mud, gravel, and cement
  don't answer the same way.
- **Landmarks:** `python3 course/tools/capture_landmark.py <name>` records views
  at car-camera height for ORB matching.

---

## Tests & CI

`tests/` holds a small suite that runs without any hardware, and
`.github/workflows/checks.yml` runs it on every pull request and on pushes to
`main`. It can't test driving — there's no Pi on a CI runner — so it tests what
is decided at a keyboard and only fails on the course: everything compiles, the
mission file is sane (every stage can time out, behaviours are spelled right,
colour cues name something real, the pit stage stays slow), and the
ground-sensor geometry and debounce hold.

```bash
python3 -m unittest discover -s tests -t tests -v
```

---

## Where to read next

| Doc | What's in it |
|---|---|
| `docs/COURSE_ANALYSIS.md` | The full technical analysis with measurements — terrain model, sequencing, landmarks, the ground sensor, the timed turn. |
| `docs/EXPLAINED_SIMPLY.md` | The same answers in plain language. |
| `docs/DEMO_DAY.md` | The run-day checklist and quick reference. |
| `docs/WIRING.md` | Pin-by-pin wiring, both voltage dividers, and the ground-sensor mount (§2b). |
| `docs/DRIVER_MOSFET_REPORT.md` | L293D vs. L298N vs. TB6612 motor-driver comparison. |
| `CHANGELOG.md` | How the project developed, and **why** — newest last. |
