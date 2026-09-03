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

# 1b. Bookworm GPIO library (see "GPIO library on Bookworm" below). The
#     pre-installed RPi.GPIO does NOT work on Bookworm and can make the motor/
#     sensor objects fail or hang at startup — the classic "car does nothing".
sudo apt remove -y python3-rpi.gpio
sudo apt install -y python3-rpi-lgpio      # or: python3-lgpio

# 2. Confirm the camera is alive
libcamera-hello --list-cameras

# 3. Prove the GPIO first — WHEELS OFF THE GROUND. This is new and it is the
#    fastest way to catch a silent car: it tests the motors and the sensor
#    SEPARATELY and reads the sensor with a timeout, so a bad sensor prints a
#    clear message instead of freezing.
cd Autonomous-Car/course
python3 tools/gpio_selftest.py

# 4. Bench test the full demo — WHEELS OFF THE GROUND
python3 ../demos/raspberry_pi/l298n_4wd_obstacle_avoider.py   # motors + sensor

# 5. Calibrate the camera on the actual course, in the actual light
python3 tools/calibrate_terrain.py

# 6. Run the course
python3 course_navigator.py --mission missions/demo_course.json

# 6b. OR run the LANDMARK-driven route (recognises the 9 route photos and does
#     the turn/step/pit sequences). Runs on top of the same Car + camera.
python3 Landmarks.py --drive
```

Stop anything with **Ctrl-C** — every program cuts the motors on exit.

---

## If the car does nothing (no motion, no motor sound, screen looks frozen)

This happened on trial day. Work through it in this order — `gpio_selftest.py`
(step 3 above) turns most of this into a one-line answer.

1. **GPIO library (most likely on Bookworm).** See below — install
   `python3-rpi-lgpio`. If creating the motors/sensor errors or hangs, this is
   usually why, and it makes BOTH the demo and the navigator silent.
2. **The sensor read was hanging.** The programs read the ultrasonic BEFORE they
   power the motors, so a sensor that never answers used to freeze everything.
   `course_navigator.py` now times the read out and prints
   *"ultrasonic not responding"* instead of freezing — if you see that, fix the
   ECHO wiring (divider to GPIO24) and check the sensor faces forward.
3. **The screen only LOOKED frozen.** The status line rewrites one line; it now
   flushes and drops a fresh line every ~3 s, so a running loop is visibly
   alive. If it truly stopped printing, it is stuck, not slow.
4. **Motors silent but the loop is alive** → motor battery, common ground, or
   the ENA/ENB jumpers (they must be OFF so the GPIO drives enable).

### GPIO library on Bookworm (64-bit Raspberry Pi OS)

Bookworm ships an `RPi.GPIO` that does **not** work with its kernel; gpiozero
uses **lgpio** instead. If an old tutorial or a `pip install RPi.GPIO` pulled in
the wrong one, gpiozero throws `PinFactoryFallback` / `BadPinFactory` /
`can not open gpiochip`, or the device objects hang. Fix:

```bash
sudo apt remove -y python3-rpi.gpio
sudo apt install -y python3-rpi-lgpio
# force the factory if needed:
export GPIOZERO_PIN_FACTORY=lgpio
```

Verify with `python3 -c "from gpiozero import Device; Device.ensure_pin_factory(); print(Device.pin_factory)"` — it should print an lgpio factory, not fall back.

### Powering the Pi: under-voltage warnings

A high-mAh power bank is not enough on its own — the **cable** is usually the
culprit. The Pi warns (rainbow square / `Under-voltage detected`) when the
voltage at the board dips below ~4.63 V, and a thin or long micro-USB cable
drops enough voltage under camera + Wi-Fi load to trip it even from a 3 A bank.

- Use a **short, thick** micro-USB cable rated for high current.
- Pick a bank that holds **≥5.1 V under load** (many sag to 4.8–5.0 V).
- Is it safe to ignore? A brief warning at motor start (the motors are on their
  OWN battery, so this is only the Pi's supply path) is usually harmless. A
  **sustained** warning is real: the Pi throttles the CPU and can freeze — do
  not ignore that one. Since the motors are separately powered here, a constant
  warning points squarely at the bank or the cable, not motor draw.

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
hang the run. This matters more here than in most projects: nothing is placed
on the course, so `marker` can only ever refer to something that happens to be
standing there (the green compost sacks, the blue toilets) — treat it as a
bonus exit, never the only one.

Timed pivots (`pivot_left` / `pivot_right`) are open loop, so **re-time them on
the day's surface**: pivot for 5 s at the stage speed, count the turns, divide.
Grip and battery charge both change the rate. The route uses a simple ~90°
turn, where a few degrees of drift is washed out by the next `follow` stage —
that is why no IMU is needed.

---

## Optional extras

**Landmarks** (if you want a stage to end at a recognised place):
```bash
python3 tools/capture_landmark.py compost_pit      # 5 views, from the car
python3 tools/capture_landmark.py --list
```
Then use `"exit": {"landmark": "compost_pit"}` in your mission. Capture at
**car camera height, in demo-day light** — this matters more than anything else.

**Second (downward) ultrasonic** — the one upgrade that adds a sense the car
does not otherwise have. It is the only sensor that can see the compost pit,
because a pit is a *hole* and a forward-facing sensor reads "all clear" over
it. It also detects the cement lip, which no camera can.

**It goes on a short mast, ~20 cm up and 35° down — not on the front wall.**
At 3 cm height it looks 11 cm ahead and sits in its own blind spot. The front
wall is for the camera and the forward sensor, side by side.

```bash
python3 course/tools/calibrate_ground.py --geometry   # bench: pick the mount
python3 course/tools/calibrate_ground.py --measure    # on site: get the numbers
python3 course/tools/calibrate_ground.py --watch      # walk it to the pit edge
```

Wire it to GPIO 27 (trig) / 22 (echo) **with its own divider**, paste the
measured numbers in, then set `DOWN_SENSOR_ENABLED = True` at the top of
`course_navigator.py`. Full detail in `WIRING.md` §2b.

The mount buys about **0.5 s of warning**, so the pit stage runs at speed 0.50
— fast enough to climb, slow enough that the car can still stop. Without the
sensor, nothing on the car detects the pit at all; the mission falls back to
`keepout_bias` and a wide berth, which is open loop.

---

## Pre-run checklist

- [ ] `python3-rpi-lgpio` installed; `RPi.GPIO` removed (Bookworm GPIO library)
- [ ] `gpio_selftest.py` passed — motors buzz, sensor returns a number (no hang)
- [ ] Ultrasonic **two barrels face FORWARD** (pins up/down doesn't matter; the
      barrels pointing at the sky or the ground does — it must see ahead)
- [ ] Pi cable **short and thick**; no sustained under-voltage warning
- [ ] Power bank charged; **separate** motor battery charged
- [ ] All grounds tied together (Pi ↔ L298N ↔ battery −)
- [ ] `5V-EN` jumper on each L298N; `ENA/ENB` jumpers **removed** (else no speed control)
- [ ] HC-SR04 **ECHO through the 1 kΩ/2 kΩ divider** (Pi is 3.3 V) — **one
      divider per sensor** if the ground sensor is fitted
- [ ] Ground sensor mast **rigid** and calibrated today (`--measure`, then
      `--watch` at the pit edge); dropouts under ~10 %
- [ ] Pivot stages **re-timed on today's surface**
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
| `vision/landmarks.py` | Colour cues, ORB `LandmarkBook`, zone matching with confidence margin, `ZoneVoter`. |
| `vision/steps.py` | Step/ramp crossing-point search, with an honest account of what one camera cannot do. |
| `tools/calibrate_terrain.py` | On-site threshold tuning. |
| `tools/capture_landmark.py` | Register landmark views for recognition. |
| `tools/calibrate_ground.py` | Downward-sensor mount geometry, flat-ground calibration, live step/hole watch. |

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
