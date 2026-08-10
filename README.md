# Autonomous Off-Road Car — Raspberry Pi 3B+

A skid-steer (tank-drive) autonomous car that drives on a wide, rough path,
avoids obstacles with a distance sensor, and uses a camera to stay on the
drivable ground — **without** wandering onto the grassy hill or into the
building.

> **Read this whole README before wiring anything or running code.** There are
> a few places where your parts list will fight physics (a 9 V battery driving
> four motors uphill, an L293D's current limit). Those are called out in
> **[Hardware reality check](#hardware-reality-check)** with cheap fixes.

---

## Contents

- [What's in this repo](#whats-in-this-repo)
- [How the car works (the big picture)](#how-the-car-works-the-big-picture)
- [Your four questions, answered](#your-four-questions-answered)
  1. [How the camera alters the car's direction](#1-how-the-camera-alters-the-cars-direction)
  2. [IR vs. ultrasonic sensing](#2-ir-vs-ultrasonic-sensing)
  3. [Uploading code, OS choice, and powering the Pi](#3-uploading-code-os-choice-and-powering-the-pi)
  4. [GPS / GPX routes — do you need them?](#4-gps--gpx-routes--do-you-need-them)
- [How the "don't drive onto the hill or into the building" logic works](#how-the-dont-drive-onto-the-hill-or-into-the-building-logic-works)
- [Hardware reality check](#hardware-reality-check)
- [Pinout & wiring](#pinout--wiring)
- [Software setup](#software-setup)
- [Running the two programs](#running-the-two-programs)
- [Tuning the vision on-site](#tuning-the-vision-on-site)

---

## What's in this repo

| File | What it is |
|---|---|
| `simple_obstacle_avoider.py` | **Program 1** — bare-bones demo. Drives forward, and when the ultrasonic sensor sees something close, it stops, backs up, and turns. No camera, no route. Use this first to prove your motors, driver, and sensor are wired correctly. |
| `autonomous_car.py` | **Program 2** — the full project. Ultrasonic sensor as the reflex/safety layer **plus** the camera choosing which way to steer so the car stays on the path and off the hill/building. |
| `docs/pinout.svg` | Pinout & wiring diagram (open in a browser). |
| `docs/WIRING.md` | Text version of the pinout: every pin, every wire, and the voltage-divider you must not skip. |
| `requirements.txt` | Python packages to install on the Pi. |
| `examples/route.gpx` | Example GPX file — only relevant **if** you add a GPS module later (see Q4). |

---

## How the car works (the big picture)

There are **two independent decision layers**, and keeping them separate is the
whole trick:

```
                 ┌──────────────────────────────────────────┐
                 │            CONTROL LOOP (~10 Hz)           │
                 └──────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┴──────────────────────────┐
        │                                                     │
   REFLEX LAYER                                        STRATEGY LAYER
   (ultrasonic/IR)                                     (camera + OpenCV)
        │                                                     │
  "Is something                                       "Which direction keeps
   right in front                                      me on the drivable
   of me, NOW?"                                        ground and away from
        │                                              grass/building?"
        │ if too close →                                       │
        ▼ STOP, reverse, turn                                  ▼ pick a steer value
                                                          -1 (hard left) … +1 (hard right)
                    │                                          │
                    └──────────────┬───────────────────────────┘
                                   ▼
                        DIFFERENTIAL DRIVE (skid steer)
              left motors and right motors get different speeds
```

- The **reflex layer** is dumb, fast, and always wins. If the distance sensor
  says "wall 20 cm ahead," the car stops and turns *regardless* of what the
  camera thinks. This is your collision insurance.
- The **strategy layer** is the camera. When the path ahead is clear of
  immediate obstacles, the camera decides *where the drivable route is* and nudges
  the steering so the car follows the open ground and refuses to climb the
  grassy hill or drift into the building.

**Steering itself** is exactly what you described — *skid steer / differential
drive*:

- Go straight → both sides equal speed.
- Small correction → drop one side's speed a little (gentle arc).
- Sharp turn → one side fast forward, other side slow or reversed (pivot).

Because you paired the two left wheels together and the two right wheels
together, you don't need a steering servo — you steer by making one side
spin faster than the other, like a tank or a zero-turn mower. This is ideal
for grass and rough ground.

---

## Your four questions, answered

### 1. How the camera alters the car's direction

The camera never drives the motors directly. It produces **one number** each
frame: a **steer value** between `-1.0` (turn hard left) and `+1.0` (turn hard
right), with `0.0` meaning "straight ahead." The motor code turns that number
into left/right wheel speeds.

Here's the pipeline, frame by frame (all of this is in `autonomous_car.py`,
function `decide_steering()`):

1. **Grab a frame** from the Pi camera (e.g. 640×480).
2. **Look only at the ground in front of the car.** We crop away the top of
   the image (sky, tops of the building, far-away trees) and keep the **bottom
   ~55%** — the patch of terrain the car is about to drive over. This is called
   the *region of interest (ROI)*.
3. **Classify the ground by colour** (in HSV colour space, which is far more
   robust to sunlight/shadow than RGB):
   - **Green** → grass / the hill → **avoid**.
   - **Ground-coloured** (brown dirt, tan, grey gravel — whatever your path is)
     → **drivable**.
   - Everything else (building wall, dark shadow) → **not drivable**.
4. **Split the ROI into three vertical columns:** left, centre, right.
5. **Score each column** = (fraction of drivable pixels) − (penalty for green
   pixels). A column full of dirt scores high; a column full of grass or wall
   scores low.
6. **Pick the winner and produce the steer value:**
   - If **centre** is clearly drivable → steer ≈ `0` (go straight).
   - If the **right** column scores best → positive steer (bear right), with the
     *size* of the steer proportional to how much better right is than the
     current heading. A slightly-better right gives a gentle correction; a
     right that's the only drivable option gives a hard turn.
   - Same idea mirrored for **left**.
   - If **no column** is drivable (grass/wall everywhere) → steer stays put and
     the car slows/stops, letting the reflex layer or a search behaviour take
     over instead of blindly plowing into the hill.

So the camera *biases* the differential drive: it continuously trims the
left/right speed balance to keep the most-drivable ground centred in front of
the car. That's the whole steering-by-camera idea, and it's what implements
"small deviations by reducing the voltage of one motor" — a small steer value
maps to a small speed reduction on one side.

> The colour thresholds (what counts as "green" and "ground") **must be tuned
> at your actual site** under the lighting you'll drive in. See
> [Tuning the vision on-site](#tuning-the-vision-on-site).

### 2. IR vs. ultrasonic sensing

You listed "ultrasound/infrared" as one undecided sensor. They behave very
differently. Short version: **use ultrasonic (HC-SR04) as your main distance
sensor for this outdoor car.** Here's why.

| | **Ultrasonic (e.g. HC-SR04)** | **IR (Sharp analog rangefinder, or a digital IR obstacle module)** |
|---|---|---|
| **How it senses** | Emits a sound pulse, times the echo → gives an actual **distance** (cm). | Emits IR light, measures reflected intensity/angle. Analog Sharp = distance; cheap digital module = just "something is / isn't within ~2–30 cm." |
| **Typical range** | ~2 cm – 4 m | Analog Sharp: ~10–80 cm. Digital module: a few cm to ~30 cm, and often not calibrated. |
| **Gives a real distance?** | **Yes** — you can say "stop at 25 cm." | Analog: yes-ish. Cheap digital module: **no**, just a threshold flag. |
| **Sunlight** | **Unaffected** (it's sound). | **Badly affected.** Outdoor sun is full of IR; it washes out cheap IR sensors and causes false readings. This alone is a strong reason to avoid IR outdoors. |
| **Surface colour / material** | Mostly colour-independent. Struggles with sound-absorbing stuff (soft foam, thick grass tips) and very angled/soft surfaces that scatter the echo. | Struggles with dark, matte, or shiny surfaces (they reflect little/odd IR). Grass is a mixed bag. |
| **Soft grass / uneven ground** | Reads the ground clutter sometimes; mounting height/angle matters. | Even less reliable. |
| **Field of view** | Wide-ish cone (~15–30°) — good for "is anything ahead," poor for pinpointing. | Narrow beam — more precise angle, shorter reach. |
| **Cost / wiring** | Cheap; needs a **voltage divider on ECHO** (its output is 5 V, the Pi GPIO is 3.3 V — see wiring). | Cheap; digital module is 1 wire and 3.3 V-friendly. |
| **Verdict for THIS car** | ✅ Primary obstacle/distance sensor. Real distances + sunlight-proof. | ⚠️ Fine as a cheap *backup* bump-detector, but not your main sensor outdoors. |

**Recommendation:** wire an **HC-SR04 ultrasonic** as the reflex sensor (both
programs assume this). If you already own a digital IR module, you can add it
as a redundant close-range trigger — `autonomous_car.py` has a commented
`USE_IR_BACKUP` hook showing where it would plug in — but don't rely on IR as
the only sensor in the sun.

### 3. Uploading code, OS choice, and powering the Pi

**Are you using the right OS?** **Yes.** Raspberry Pi OS 64-bit (Bookworm) on
the Pi 3B+ is correct and current. One important consequence: on 64-bit
Bookworm the **camera stack is `libcamera` / `picamera2`**, *not* the old
`picamera` library. This project uses **`picamera2`**, which is the right
choice for your OS. (If you find a tutorial using `import picamera`, it's for
the old OS and won't work on yours.)

Enable the camera and (if you use the `pigpio` PWM backend) the relevant
interfaces:

```bash
sudo raspi-config      # Interface Options → enable Camera (legacy off), I2C/SPI as needed
# picamera2 + libcamera are preinstalled on 64-bit Bookworm; verify with:
libcamera-hello --list-cameras
```

**How do I get the code onto the Pi?** Any of these — easiest first:

1. **`git clone` on the Pi** (best). The Pi is on Wi-Fi, so:
   ```bash
   git clone <this-repo-url>
   cd Autonomous-Car
   ```
   To update later: `git pull`.
2. **`scp` from your laptop** over the network (Pi must have SSH enabled in
   `raspi-config`):
   ```bash
   scp simple_obstacle_avoider.py pi@raspberrypi.local:/home/pi/
   ```
   or copy the whole folder: `scp -r Autonomous-Car pi@raspberrypi.local:/home/pi/`
3. **VS Code Remote-SSH** — edit files live on the Pi from your laptop. Nicest
   for tuning.
4. **Sneakernet** — pull the SD card, mount it on your laptop, drop files in
   `/home/pi/`. Works but slow to iterate.

**Powering the Pi on a moving car with 5 V micro-USB — will a power bank do?**
**Yes, a USB power bank is exactly the right answer**, and you should power the
Pi *separately* from the motors. Requirements:

- **Voltage:** 5 V (the Pi 3B+ uses a **micro-USB** power input — matches a
  standard power bank cable). ✅
- **Current:** The Pi 3B+ officially wants **5 V / 2.5 A**. Pick a power bank
  that can output **at least 2.5 A on a single port (3 A is better)**. Many
  cheap banks claim "2.1 A" — that's marginal; under camera + Wi-Fi load you'll
  get *under-voltage warnings* (the yellow lightning bolt) and random reboots.
- **Cable quality matters:** a thin/long micro-USB cable drops voltage. Use a
  short, thick one.
- **Keep it separate from the motor battery.** The motors (via the L293D and
  the 9 V battery) create big voltage spikes and noise. If the Pi shared that
  supply it would brown-out and reboot the moment the wheels bite into grass.
  **Power bank → Pi. 9 V battery → motors. Tie their grounds together (common
  ground) but keep the positive rails separate.** This is the single most
  common reason a Pi car "randomly resets."

So: **a good 5 V / ≥2.5 A USB power bank with a short micro-USB cable is the
recommended Pi supply.** (See [Hardware reality check](#hardware-reality-check)
for the motor-side power, which is the part that actually needs upgrading.)

### 4. GPS / GPX routes — do you need them?

**Short answer: with your current parts list, you neither need nor *can* use a
GPX route — and that's fine, because your terrain is defined by what it *looks*
like, not by exact coordinates.**

Why:

- **You have no GPS module.** Nothing in your list can measure the car's
  latitude/longitude, and nothing can measure heading (you'd want a compass/IMU
  too). So the car literally cannot know where it is on a map. Uploading start/
  end coordinates or a `.gpx` route would give the software numbers it has no
  way to act on.
- **Your route is a *visual* route, not a *survey* route.** You described the
  goal as "stay on the wide path, don't climb the little grassy hill, don't go
  into the building." That's a description of *terrain appearance*, and the
  camera handles it directly (see the next section). This is more reliable than
  hobby GPS anyway: a NEO-6M GPS is accurate to only ~2.5 m, which is *wider
  than your car* — it could happily place you "on route" while you're actually
  half-on the hill.

**So for this build: no coordinates, no GPX.** The "route" is: *follow the
drivable ground the camera sees, and let the ultrasonic sensor stop you hitting
things.*

**If you later add a GPS module** (e.g. a u-blox NEO-6M on the Pi's UART) and
want true waypoint following, here's how it would work and how you'd load a
route — this is why `examples/route.gpx` exists and why `autonomous_car.py`
has an optional, **disabled-by-default** `route` section:

- **You'd upload a GPX**, not just two coordinates. A GPX file is XML listing
  a sequence of `<trkpt lat=... lon=...>` waypoints — the whole path, not only
  the ends — so the car can follow the corridor you actually want, not a
  straight line that might cut across the hill.
- **How you'd create it:** walk the route with a phone GPS app (e.g. an
  OSM/GPX tracker), or draw it on a map tool that exports GPX. Drop the file on
  the Pi (same `git`/`scp` methods as the code).
- **How the code would use it:** read the GPX → list of waypoints; each loop,
  read current GPS fix, compute bearing+distance to the next waypoint, convert
  the bearing error into a steer value, and advance to the next waypoint when
  you're within a few metres. The camera's obstacle/terrain steering would sit
  *on top* as an override so you still don't drive into the building even if GPS
  drifts.
- `examples/route.gpx` shows the exact file format to follow.

Bottom line: **build and run it vision-only first** (that's what
`autonomous_car.py` does today). Add GPS/GPX later only if you need to reach a
specific faraway point that the camera can't see.

---

## How the "don't drive onto the hill or into the building" logic works

This is the safety concern you specifically raised, so here it is in one place —
**this is what the code does, and why it won't climb the hill or hit the
school.**

The camera classifies the ground in front of the car into three buckets by
colour, then only ever steers toward the *drivable* bucket:

1. **Grass / the hill = green.** In HSV, grass has a distinct green hue.
   Any column of the image that is mostly green is scored as **not drivable and
   penalised**. The steering is computed to move the car *away* from green.
   Result: as the car approaches the grassy hill, that side of the image lights
   up green, its score collapses, and the car steers to the other side — it
   physically cannot choose to drive into the grass because grass never wins the
   "best column" contest.
2. **The building = a wall, not ground.** A wall is not ground-coloured and
   fills the column vertically instead of receding into the distance, so that
   column has a **low drivable-pixel fraction** and loses. The car steers away
   from it for the same reason it avoids grass: low score.
3. **The path = ground colour.** Only dirt/tan/gravel-coloured, low-lying
   regions score as drivable, and the car keeps *that* centred.

Three more safety features stack on top:

- **Fail-safe on "no good option."** If *every* column is grass/wall (e.g. the
  car reached a dead-end at the hill), the code does **not** pick the
  least-bad direction and charge; it **slows and stops**, then reverses/searches.
  Blindly committing is how you end up on the hill.
- **The ultrasonic reflex overrides everything.** Even if the camera were
  fooled (odd lighting, a tan-coloured wall), the distance sensor stops the car
  before contact. Vision picks the route; ultrasound prevents collisions.
- **A hard "keep-out" bias you can set.** If the hill is *always* on, say, the
  right and the building *always* on the left, you can switch on
  `EDGE_BIAS` in the config to add a constant gentle pull toward centre — a
  cheap guardrail so the car hugs the middle of the wide path by default.

The honest caveat: colour thresholds depend on lighting and on what your dirt
and grass actually look like. **You must calibrate on-site** (there's a
`--calibrate` mode that saves the camera view and the colour masks so you can
check the car "sees" grass as grass). Do that before trusting it near the hill,
and always test-drive with a hand on the power for the first runs.

---

## Hardware reality check

Your parts list works for a **demo**, but "off-road, uphill, on grass" asks a
lot of two parts. None of this blocks you from building it today — but know
what will happen:

1. **A 9 V PP3 battery cannot drive four motors uphill on grass for long.**
   Those little rectangular 9 V batteries deliver very little current
   (a few hundred mA before the voltage sags). Four gear motors pushing through
   grass can pull **an amp or more each** when loaded. The car will run on the
   bench, then crawl or stall the moment it meets the hill, and the battery
   will die fast.
   **Cheap fix:** power the motors from a **6×AA NiMH pack (7.2 V)** or a
   **2S Li-ion pack (~7.4 V) with decent current**. Keep it separate from the
   Pi's power bank, common-ground them. This one change is the difference
   between "toy" and "climbs the hill."

2. **The L293D is weak and runs hot.** The L293D is an old chip that drops
   ~1.5–2 V internally (so 9 V in → ~7 V at the motors) and is rated only
   ~0.6 A continuous per channel. You're paralleling two motors per channel,
   so you'll likely exceed that under load and the chip will get hot and
   current-limit.
   **Cheap fix (strongly recommended):** swap the L293D for an **L298N module**
   (~2 A/channel, has a heatsink, same 2-input-per-channel + enable-for-PWM
   wiring — the code doesn't change) or a modern **TB6612FNG** (more efficient,
   less voltage drop). If you must use the L293D, keep speeds modest, add a
   heatsink, and don't be surprised by thermal cut-outs on the hill.

3. **Common ground is mandatory.** Pi ground, L293D ground, motor-battery
   ground, and sensor ground must all connect. Skipping this gives you flaky
   sensor readings and motors that ignore commands.

4. **Flyback/back-EMF.** Motors kick voltage spikes back. The L293D/L298N have
   internal protection diodes, but noise can still reboot a poorly-powered Pi —
   another reason for the separate power bank.

The code in this repo runs unchanged whether you use the L293D on 9 V (demo) or
an L298N on a 7.2 V pack (real off-roading) — only the wiring power source
changes.

---

## Pinout & wiring

- **Diagram:** open **[`docs/pinout.svg`](docs/pinout.svg)** in a browser.
- **Full pin/wire table and the mandatory ECHO voltage divider:**
  see **[`docs/WIRING.md`](docs/WIRING.md)**.

Quick GPIO summary (BCM numbering — the numbers the code uses):

| Function | BCM GPIO | Physical pin | Goes to |
|---|---|---|---|
| Left motors — enable/PWM (speed) | **GPIO12** | 32 | L293D EN1 |
| Left motors — direction A | **GPIO5** | 29 | L293D IN1 |
| Left motors — direction B | **GPIO6** | 31 | L293D IN2 |
| Right motors — enable/PWM (speed) | **GPIO13** | 33 | L293D EN2 |
| Right motors — direction A | **GPIO20** | 38 | L293D IN3 |
| Right motors — direction B | **GPIO21** | 40 | L293D IN4 |
| Ultrasonic TRIG | **GPIO23** | 16 | HC-SR04 TRIG |
| Ultrasonic ECHO (via divider!) | **GPIO24** | 18 | HC-SR04 ECHO through 5V→3.3V divider |
| (Optional) IR backup sensor | **GPIO25** | 22 | IR module OUT |
| 5 V logic for L293D | 5V | 2 / 4 | L293D VCC1 (pin 16) |
| Ground (common) | GND | 6/9/14/… | L293D GND + battery − + sensor GND |
| Camera | — | **CSI ribbon port** | Pi camera (not a GPIO pin) |

Motor supply: **9 V battery + → L293D VCC2 (pin 8); battery − → common
ground.** Pi power: **USB power bank → micro-USB (separate supply).**

---

## Software setup

On the Pi (Raspberry Pi OS 64-bit Bookworm):

```bash
sudo apt update
sudo apt install -y python3-gpiozero python3-picamera2 python3-opencv python3-numpy pigpio
sudo systemctl enable --now pigpiod      # better/steadier PWM (optional but recommended)

# from the repo folder:
pip install -r requirements.txt           # only needed for anything not covered by apt
```

`gpiozero`, `picamera2`, and OpenCV are all available as apt packages on
Bookworm — that's the most reliable way to install them on the Pi.

## Running the two programs

**Always bench-test first with the wheels off the ground.**

```bash
# Program 1 — obstacle-avoiding demo (no camera):
python3 simple_obstacle_avoider.py

# Program 2 — full autonomous car (camera + terrain steering + ultrasonic):
python3 autonomous_car.py

# Calibrate the camera colours on-site (saves images you can inspect):
python3 autonomous_car.py --calibrate
```

Stop either program with **Ctrl-C** — both catch it and cut the motors safely.

## Tuning the vision on-site

The colour thresholds at the top of `autonomous_car.py` (`GRASS_HSV_LOW/HIGH`,
`GROUND_HSV_LOW/HIGH`) are starting points. To tune:

1. Put the car where it'll actually drive, in the actual light.
2. Run `python3 autonomous_car.py --calibrate`. It saves `calib_frame.jpg`
   (what the camera sees), `calib_grass_mask.jpg`, and `calib_ground_mask.jpg`.
3. Look at the masks: grass should be white in the grass mask; your path should
   be white in the ground mask; the building should be black in both.
4. Adjust the HSV ranges until that's true, then re-run. Repeat in a few
   lighting conditions (sun, cloud) — outdoor colour shifts a lot.

Only once the masks look right should you let the car drive near the hill.
