# Wiring & Pinout — Raspberry Pi 3B+ Autonomous Car

Open **`pinout.svg`** in this folder for the visual diagram. This file is the
authoritative pin-by-pin reference.

All GPIO numbers are **BCM** (the numbers the Python code uses), with the
physical header pin in brackets.

---

## 1. Motors → L293D (skid steer: left pair + right pair)

Wire **both left wheels in parallel** onto L293D **channel A**, and **both
right wheels in parallel** onto L293D **channel B**. You steer by driving the
two sides at different speeds — no steering servo needed.

> ⚠️ Two motors in parallel per channel can exceed the L293D's ~0.6 A rating
> under load (uphill on grass). See the README "Hardware reality check" — an
> **L298N** module is a drop-in upgrade and the code is unchanged.

### L293D pin map (16-pin DIP)

```
            L293D (top view, notch at top)
                    ┌───⌒───┐
   EN1  (pin 1) ────┤1     16├──── VCC1  (pin 16)  -> Pi 5V (logic supply)
   IN1  (pin 2) ────┤2     15├──── IN4   (pin 15)
   OUT1 (pin 3) ────┤3     14├──── OUT4  (pin 14)
   GND  (pin 4) ────┤4     13├──── GND   (pin 13)   (all GNDs common)
   GND  (pin 5) ────┤5     12├──── GND   (pin 12)
   OUT2 (pin 6) ────┤6     11├──── OUT3  (pin 11)
   IN2  (pin 7) ────┤7     10├──── IN3   (pin 10)
   VCC2 (pin 8) ────┤8      9├──── EN2   (pin 9)
                    └────────┘
   VCC2 (pin 8)  -> +9V motor battery (motor supply)
```

### Left channel (channel A)

| L293D pin | Connects to | Purpose |
|---|---|---|
| EN1 (pin 1) | **Pi GPIO12 [phys 32]** | PWM speed for left motors |
| IN1 (pin 2) | **Pi GPIO5 [phys 29]** | left direction A |
| IN2 (pin 7) | **Pi GPIO6 [phys 31]** | left direction B |
| OUT1 (pin 3) | Left motors + terminal | — |
| OUT2 (pin 6) | Left motors − terminal | — |

### Right channel (channel B)

| L293D pin | Connects to | Purpose |
|---|---|---|
| EN2 (pin 9) | **Pi GPIO13 [phys 33]** | PWM speed for right motors |
| IN3 (pin 10) | **Pi GPIO20 [phys 38]** | right direction A |
| IN4 (pin 15) | **Pi GPIO21 [phys 40]** | right direction B |
| OUT3 (pin 11) | Right motors + terminal | — |
| OUT4 (pin 14) | Right motors − terminal | — |

### Power & ground for the L293D

| L293D pin | Connects to |
|---|---|
| VCC1 (pin 16) | **Pi 5V [phys 2 or 4]** — logic supply (low current, OK from Pi) |
| VCC2 (pin 8) | **+9 V motor battery** — motor supply |
| GND (pins 4, 5, 12, 13) | **Common ground**: Pi GND + 9 V battery − + sensor GND |

> If a motor spins the "wrong" way, just swap that motor's two OUT wires (or
> swap its IN pins in the code). Do this on the bench first.

---

## 2. HC-SR04 ultrasonic sensor  ← MANDATORY voltage divider

The HC-SR04 runs on 5 V and its **ECHO pin outputs 5 V**. The Pi's GPIO is
**3.3 V only** — connecting ECHO straight to a GPIO can damage the Pi. Drop it
with a two-resistor divider.

| HC-SR04 pin | Connects to |
|---|---|
| VCC | Pi **5V [phys 2/4]** |
| GND | Pi **GND** (common) |
| TRIG | Pi **GPIO23 [phys 16]** (3.3 V trigger is fine) |
| ECHO | **Divider → Pi GPIO24 [phys 18]** |

### ECHO voltage divider (5 V → ~3.3 V)

```
   HC-SR04 ECHO ──────[ R1 = 1kΩ ]──────┬────────► Pi GPIO24 (phys 18)
                                         │
                                     [ R2 = 2kΩ ]   (use 2× 1k in series,
                                         │            or a 2.2k — close enough)
                                         │
                                        GND (common)
```

`Vout = 5V × R2 / (R1 + R2) = 5 × 2k / 3k ≈ 3.3 V`. ✅

*(gpiozero's `DistanceSensor` handles all the trigger/echo timing in software —
you only need to get these four wires right.)*

---

## 2b. Second HC-SR04 — the downward ground sensor

This is the sensor that sees the compost pit. A pit is a **hole**, and a
forward-facing sensor reads "all clear" over a hole right up until the car
falls in; the camera cannot see it either. Pointed down at the ground ahead,
the range **shortens** over a step and **lengthens — or goes silent —** over a
hole.

### Where it goes: NOT on the front wall

The front wall of the chassis is right for the forward sensor and the camera,
side by side as you have them. It is wrong for this one, and the reason is
geometry, not wiring.

A sensor `h` above the ground tilted `t` below horizontal meets the ground at
slant range `h / sin(t)`, which is `h / tan(t)` in front of it. Bolted to a
3 cm lip:

| Mount | Reads on flat | Ground patch ahead of the wheels | Verdict |
|---|---|---|---|
| Front wall, 3 cm, 30° | 4.2 cm | 11 cm | **No** — inside the sensor's own ~2 cm blind spot |
| Front wall, 3 cm, 45° | 3.5 cm | 10 cm | **No** — same |
| Mast, 20 cm, 35° | 26 cm | 25 cm | Yes — 0.5 s of warning at 0.5 m/s |
| Mast, 25 cm, 30° | 35 cm | 33 cm | Yes — 0.66 m/s |

Generate this table for your own build, before drilling:

```bash
python3 course/tools/calibrate_ground.py --geometry
python3 course/tools/calibrate_ground.py --height 0.22 --tilt 35
```

### The mount

```
              ultrasonic, face tilted 35° down
                    ╲  ┌────┐
                     ╲ │ () │  ← 20 cm above the ground
                      ╲└────┘
            mast ──────┐ ╲                     rigid: a floppy mast
         (20 cm)       │  ╲  35°               turns every bump into
                       │   ╲                   a false hole
   ┌───────────────────┴┐   ╲
   │  chassis            │    ╲
   │            [cam][US]│     ╲   ← front wall: camera + FORWARD sensor,
   └──o───────────────o──┘      ╲    side by side, both level
                                 ╲
   ═══════════════════════════════●═══════════  ground
                                  ↑
                     25 cm ahead of the front wheels
```

- **Height 20–25 cm.** Height buys warning distance *and* cuts pitch
  sensitivity — go as high as the chassis will carry **rigidly**.
- **Tilt 30–35°.** Shallower looks further ahead but skims off soft mud and
  rides the pitch noise; steeper is quiet and reliable but gives less warning.
- **As far forward as possible.** Every cm the mast sits ahead of the front
  wheels is a free cm of warning distance.
- **Rigid.** Chassis pitch is the dominant noise source: ±5° of pitch moves
  the reading ~2 cm at this mount. A wobbling mast fabricates holes. Bolt or
  glue it — do not zip-tie it to something springy.
- **Point it away from the forward sensor's cone** (35° down vs level does
  this already) so the two do not hear each other's pings.

### Wiring — identical to the first sensor, including the divider

| HC-SR04 pin | Connects to |
|---|---|
| VCC | Pi **5V [phys 2/4]** |
| GND | Pi **GND** (common) |
| TRIG | Pi **GPIO27 [phys 13]** |
| ECHO | **Its own 1 kΩ/2 kΩ divider → Pi GPIO22 [phys 15]** |

> ⚠️ The second ECHO needs its **own** divider. Do not tee both sensors into
> one — they will load each other and you will read garbage from both.

### Then calibrate it

```bash
python3 course/tools/calibrate_ground.py --measure   # on flat ground
python3 course/tools/calibrate_ground.py --watch     # walk it to the step/pit
```

Paste the printed `DOWN_NOMINAL_M` / `DOWN_TOLERANCE` into
`course/course_navigator.py` and set `DOWN_SENSOR_ENABLED = True`. Never guess
these numbers — mud, gravel and cement do not answer the same way, and the
value depends on your exact mount.

If `--measure` reports more than ~10 % dropouts, **steepen the tilt**. A
grazing beam scatters off soft ground instead of coming back, and the navigator
reads a missing echo as a hole — so dropouts cost you false emergency stops.

---

## 3. (Optional) IR backup obstacle module

Only if you set `USE_IR_BACKUP = True` in `autonomous_car.py`.

| IR module pin | Connects to |
|---|---|
| VCC | Pi **3.3V or 5V** (check your module; most are 3–5 V) |
| GND | Pi **GND** (common) |
| OUT | Pi **GPIO25 [phys 22]** (most modules pull LOW on detection) |

Not recommended as the *only* sensor outdoors — sunlight blinds cheap IR
modules (see README, Q2).

---

## 4. Camera

The Pi camera (even a knockoff) connects to the **CSI camera ribbon port** on
the Pi board — **not** to any GPIO pin. Ribbon contacts face the HDMI port;
lift the black clip, insert, press the clip down. Enable it in `raspi-config`
and verify with `libcamera-hello --list-cameras`.

---

## 5. Power — keep the two supplies SEPARATE

```
  ┌─────────────────┐        ┌──────────────────────────┐
  │  USB power bank  │        │   9 V battery (motors)    │
  │  5V / ≥2.5A      │        │   (upgrade to 7.2V pack   │
  │                  │        │    for real off-roading)  │
  └───────┬──────────┘        └────────┬─────────────────┘
          │ micro-USB                  │ +9V
          ▼                            ▼
   Raspberry Pi 3B+            L293D VCC2 (pin 8)
          │                            │
          └──────────── COMMON GROUND ─┘
        (Pi GND ↔ L293D GND ↔ battery − ↔ sensor GND all tied together)
```

- **Power bank → Pi** (via micro-USB). 5 V, ≥2.5 A (3 A better), short thick cable.
- **9 V (or 7.2 V pack) → motors** via L293D VCC2.
- **Never** run the Pi off the motor battery through the L293D — motor noise
  will brown-out and reboot the Pi.
- **Common ground is mandatory** — tie all grounds together or nothing works
  reliably.

---

## Full GPIO usage summary

| BCM | Phys | Direction | Wired to |
|---|---|---|---|
| GPIO5 | 29 | out | L293D IN1 (left dir A) |
| GPIO6 | 31 | out | L293D IN2 (left dir B) |
| GPIO12 | 32 | out (PWM) | L293D EN1 (left speed) |
| GPIO13 | 33 | out (PWM) | L293D EN2 (right speed) |
| GPIO20 | 38 | out | L293D IN3 (right dir A) |
| GPIO21 | 40 | out | L293D IN4 (right dir B) |
| GPIO23 | 16 | out | HC-SR04 (forward) TRIG |
| GPIO24 | 18 | in | HC-SR04 (forward) ECHO (via divider) |
| GPIO27 | 13 | out | HC-SR04 (downward) TRIG |
| GPIO22 | 15 | in | HC-SR04 (downward) ECHO (via its own divider) |
| GPIO25 | 22 | in | (optional) IR OUT |
| 5V | 2, 4 | pwr | L293D VCC1, both HC-SR04 VCC |
| GND | 6, 9, 14, 20, 25, 30, 34, 39 | gnd | common ground |
| CSI | — | — | camera ribbon |
