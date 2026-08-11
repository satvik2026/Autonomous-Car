# Demo Day Guide — what to upload, what to run

Everything you need on the day, in order. If you read only one section, read
[The 10-minute setup](#the-10-minute-setup).

---

## What actually goes on the Raspberry Pi

**Short answer: clone the whole repo. It is under 1 MB of code.**

```bash
git clone https://github.com/satvik2026/Autonomous-Car.git
cd Autonomous-Car
```

You do **not** need the `Photos/` folder or the video on the Pi — those live on
the `satvik2026-course-documentation` branch and are ~750 MB. They are only
needed on a laptop for tuning. The `main` branch deliberately excludes them.

### The files the car actually executes

Only these run on the car:

| File | Role |
|---|---|
| `course/course_navigator.py` | **The program you run.** Main loop. |
| `course/mission.py` | Stage sequencer — reads your route order. |
| `course/missions/demo_course.json` | **Your route.** Edit this, not the code. |
| `course/vision/terrain.py` | Decides what the ground is and where to steer. |
| `course/vision/landmarks.py` | Recognises markers / landmarks / zones. |
| `course/vision/steps.py` | Picks where to cross a step or ramp. |

Everything else is documentation, diagrams, or the simpler demo programs.

---

## The 10-minute setup

```bash
# 1. Install dependencies (once)
sudo apt update
sudo apt install -y python3-gpiozero python3-picamera2 python3-opencv python3-numpy

# 2. Confirm the camera is alive
libcamera-hello --list-cameras

# 3. Bench test — WHEELS OFF THE GROUND
cd Autonomous-Car/course
python3 ../demos/raspberry_pi/l298n_4wd_obstacle_avoider.py   # motors + sensor

# 4. Calibrate the camera on the actual course, in the actual light
python3 tools/calibrate_terrain.py

# 5. Run the course
python3 course_navigator.py --mission missions/demo_course.json
```

Stop anything with **Ctrl-C** — every program cuts the motors on exit.

---

## Step 4 in detail: calibration (do not skip this)

This is the single highest-value thing you can do on the day. Colour thresholds
depend on the light, and the light on demo day is not the light in your photos.

Point the camera at each surface and run:

```bash
python3 tools/calibrate_terrain.py
```

Check the numbers against these targets:

| Point the camera at | You want to see |
|---|---|
| The **lawn** / grass hill | `veg > 0.70` → “KEEP-OUT” |
| The **mud course** | `veg < 0.45` → “mud/drivable” |
| **Cement** | `hard > 0.80` |
| **Gravel** | `hard > 0.70` |

If they're wrong, edit two numbers at the top of `course/vision/terrain.py`:

- Lawn not detected as vegetation → **lower** `EXG_VEG` (try 0.04, 0.03).
- Mud course wrongly flagged as vegetation → **raise** `EXG_VEG` (try 0.06, 0.07).
- Cement and gravel confused → check `SMOOTH_MAX` (cement should read
  roughness well under it, gravel well over).

It also writes `calib_overlay.jpg`. Open it — **red** is what the car refuses
to drive on, **green** is mud, **cyan** is cement/gravel. If the lawn is not
solidly red in that picture, do not let the car near it yet.

---

## Editing your route

Open `course/missions/demo_course.json`. Each stage is:

```json
{
  "name": "gravel_crossing",
  "behaviour": "creep",
  "speed": 0.70,
  "exit": { "surface": "cement", "hold_s": 1.5, "timeout_s": 30 }
}
```

Behaviours: `follow` (normal), `creep` (slow, rough ground), `cross_step`
(square up and burst over a kerb), `pivot_left` / `pivot_right` (turn in
place), `straight`.

Exits: `surface`, `marker`, `landmark`, `obstacle_within_m`, `timeout_s`.

**Always leave a `timeout_s` on every stage** so a missed transition can never
hang the run.

---

## Optional extras

**Landmarks** (if you want a stage to end at a recognised place):
```bash
python3 tools/capture_landmark.py compost_pit      # 5 views, from the car
python3 tools/capture_landmark.py --list
```
Then use `"exit": {"landmark": "compost_pit"}` in your mission. Capture at
**car camera height, in demo-day light** — this matters more than anything else.

**Second (downward) ultrasonic** — optional but recommended. It is the only
sensor that can see the compost pit, because a pit is a *hole* and a
forward-facing sensor reads "all clear" over it. Wire a second HC-SR04 to
GPIO 27 (trig) / 22 (echo), then set `DOWN_SENSOR_ENABLED = True` at the top of
`course_navigator.py`.

---

## Pre-run checklist

- [ ] Power bank charged; **separate** motor battery charged
- [ ] All grounds tied together (Pi ↔ L298N ↔ battery −)
- [ ] `5V-EN` jumper on each L298N; `ENA/ENB` jumpers **removed** (else no speed control)
- [ ] HC-SR04 **ECHO through the 1 kΩ/2 kΩ divider** (Pi is 3.3 V)
- [ ] Camera ribbon seated; `libcamera-hello --list-cameras` works
- [ ] Wheels-off bench test passed
- [ ] Calibrated on site, in today's light; overlay checked
- [ ] **Course swept** — the garden hose in your photos will beach the car
- [ ] Every stage has a `timeout_s`
- [ ] First run done with a hand near the power

---

## If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Pi reboots when motors start | Motor noise on shared supply | Separate power bank; check common ground |
| Motors run full speed only | `ENA/ENB` jumpers still fitted | Remove them |
| Car drives onto the grass | Not calibrated for today's light | Re-run calibration; lower `EXG_VEG` |
| Car stops on good ground | `EXG_VEG` too low | Raise it |
| Stage never advances | Exit condition never true | Check `--replay` output; rely on `timeout_s` |
| Stage advances too early | Surface misread | `ZoneVoter` handles most; raise `hold_s` |
| Distance always 0 or 2 m | ECHO wiring / divider | Recheck the divider |

**Dry-run anything on a laptop, no hardware needed:**
```bash
python3 course_navigator.py --replay ../Photos
```
This runs the exact on-car decision code over your site photos and prints what
the car would do for each one.

---

## Full inventory — everything created for the course analysis

### Code (`course/`)
| File | What it contains |
|---|---|
| `course_navigator.py` | Main program. Reflex → terrain → mission layers. `--replay`, `--calibrate` modes. Optional down-sensor and hole detection. |
| `mission.py` | `Stage` and `Mission` classes: the route sequencer, exit tests, stage log. |
| `missions/demo_course.json` | The route order, the measured zone signatures, and per-stage notes. **This is the file you edit.** |
| `vision/terrain.py` | Terrain classifier: ExG vegetation index, saturation, roughness. Column scoring and steering. |
| `vision/landmarks.py` | Colour markers, ORB `LandmarkBook`, zone matching with confidence margin, `ZoneVoter`. |
| `vision/steps.py` | Step/ramp crossing-point search, with an honest account of what one camera cannot do. |
| `tools/calibrate_terrain.py` | On-site threshold tuning. |
| `tools/capture_landmark.py` | Register landmark views for recognition. |

### Documentation (`docs/`)
| File | What it contains |
|---|---|
| `COURSE_ANALYSIS.md` | The full technical analysis with measurements. |
| `EXPLAINED_SIMPLY.md` | The same five answers in plain language. |
| `DEMO_DAY.md` | This file. |
| `course_validation.jpg` | The classifier's output on real course photos. |
| `WIRING.md`, `pinout*.svg` | Wiring and pin diagrams. |
| `DRIVER_MOSFET_REPORT.md` | Motor-driver comparison. |
| `../CHANGELOG.md` | Full project history. |
