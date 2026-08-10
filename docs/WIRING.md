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
| GPIO23 | 16 | out | HC-SR04 TRIG |
| GPIO24 | 18 | in | HC-SR04 ECHO (via divider) |
| GPIO25 | 22 | in | (optional) IR OUT |
| 5V | 2, 4 | pwr | L293D VCC1, HC-SR04 VCC |
| GND | 6, 9, 14, 20, 25, 30, 34, 39 | gnd | common ground |
| CSI | — | — | camera ribbon |
