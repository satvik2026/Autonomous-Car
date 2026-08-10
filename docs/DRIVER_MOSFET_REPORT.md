# MOSFET Motor-Driver System — Report

**Context:** off-road autonomous car on a Raspberry Pi 3B+, four DC gear
motors, skid-steer, driving on grass and climbing a small hill on an untethered
battery. This report explains how a MOSFET H-bridge driver system works and how
choosing it (instead of the L293D or L298N) changes the car's real-world
behaviour, with the **power supply and the route/terrain** kept front of mind.

Diagrams:
- `docs/pinout_dual_l298n.svg` — the two-L298N system (bipolar, for comparison)
- `docs/pinout_mosfet_tb6612.svg` — the MOSFET system described here

---

## 1. How a MOSFET H-bridge driver works

Every one of these drivers (L293D, L298N, TB6612, DRV8871, BTS7960) is an
**H-bridge**: four electronic switches arranged in an "H" around the motor.
Close the top-left + bottom-right pair and current flows one way (forward);
close the top-right + bottom-left pair and it flows the other way (reverse);
pulse the switches on/off quickly (PWM) and the *average* voltage — hence speed
— is set by the duty cycle. That topology is identical across all of them.

**The difference is what the four switches are made of.**

- **L293D / L298N use bipolar transistors.** A bipolar transistor conducting
  current always drops a roughly *fixed* saturation voltage across itself
  (~1 V per transistor, and there are two in the path), so the motor loses
  **~2–3 V regardless of current**, and that lost voltage becomes **heat**
  (`P = I × V_drop`). That's why the L298N needs a big heatsink and why the
  L293D thermally shuts down.

- **A MOSFET conducts through a channel that behaves like a small resistor**,
  `R_DS(on)`, often just **tens of milliohms**. The voltage it drops is
  `I × R_DS(on)` — proportional to current, and *tiny*: at 1 A through a
  0.2 Ω combined path you lose ~0.2 V, not 2–3 V. Wasted power is
  `I² × R_DS(on)`, which is small, so the driver stays **cool** and the motor
  receives **almost the full battery voltage**.

A MOSFET is *voltage-controlled* (you charge/discharge its gate) rather than
current-controlled, and switching the gate cleanly at PWM frequencies takes a
bit of drive circuitry. **Integrated MOSFET driver chips** — TB6612FNG,
DRV8871, DRV8833, BTS7960 — bundle the four MOSFETs **plus** the gate-drive,
logic-level translation, and protection (thermal shutdown, over-current,
under-voltage, body-diode freewheeling) into one part, so from the Pi's side
you still just drive `IN` (direction) and `PWM/EN` (speed) pins exactly like an
L298N. You get MOSFET efficiency with L298N-style wiring.

**The concrete system for this car (see the MOSFET diagram): 2× TB6612FNG, one
board per side.** The TB6612 is a dual MOSFET H-bridge — the direct low-loss
replacement for an L298N. One board handles the two left motors, the other the
two right motors; each motor sits on its own channel. Control pins map to the
**same 6 GPIO** as the L293D/L298N builds, plus a `STBY` (standby) pin tied
high to enable the chip.

---

## 2. Impact on functionality

| Property | L298N (bipolar) | **TB6612FNG (MOSFET)** | Why it matters here |
|---|---|---|---|
| Voltage drop | ~2–3 V | **~0.1–0.3 V** | Motor gets ~full pack voltage → **more torque per volt** for climbing |
| Waste heat | High (needs heatsink) | **Low** (runs cool) | **No thermal cut-out mid-hill**; safe inside a closed plywood chassis |
| Battery efficiency | Volts burned as heat | **Volts go to the motor** | **Longer runtime** on the same pack — it's untethered |
| Logic voltage | 5 V | **3.3 V native** (VCC=3.3 V) | Drives straight from Pi GPIO; no level issues |
| PWM behaviour | Slow (bipolar), keep ~1 kHz | Fast, clean at higher kHz | **Finer, quieter low-speed control** → smoother small steering deviations |
| Continuous current | 2 A/ch | 1.2 A/ch (3.2 A peak) | *Lower* headroom — see the caveat below |

The functional wins that matter for *this* car:

1. **Better hill climbing on the same battery.** Torque is proportional to
   motor current, and current is driven by the voltage actually reaching the
   motor. The L298N throws away 2–3 V as heat before the motor ever sees it; the
   MOSFET driver hands almost the whole pack to the motor. On a 7.4 V pack the
   difference is roughly *5 V vs 7.2 V at the motor* — a large torque gap
   exactly when you're grinding uphill through grass.
2. **It won't quit halfway up.** The L293D's failure mode on a hill is a
   **thermal shutdown** as it dumps heat; a cool-running MOSFET driver keeps
   pushing. Reliability on the climb is the whole point.
3. **Smoother steering.** Your turning scheme relies on *small* speed
   reductions on one side for gentle course corrections (the camera's fine steer
   values). MOSFET drivers give clean, high-resolution PWM, so those small
   deviations translate into smooth arcs instead of the coarse, buzzy low-speed
   behaviour bipolar drivers show near stall.

---

## 3. Impact on practicality — power supply

- **You can run a smaller/lighter pack for the same result, or the same pack
  lasts longer.** Because ~nothing is wasted in the driver, more of the battery's
  energy reaches the wheels. On a car that carries its own power, that's
  directly more drive time per charge.
- **You don't have to over-spec the voltage.** With the L298N you're tempted to
  raise the pack voltage to compensate for the 2–3 V loss. With a MOSFET driver
  a **7.4 V 2S Li-ion / 6×AA NiMH pack** already delivers near its full voltage
  to the motors — simpler and lighter. (TB6612 VM max is **13.5 V**, so stay at
  7.4 V and avoid a full 3S/12.6 V pack.)
- **Less heat = no bulky heatsink, less thermal risk** on a plywood chassis in
  outdoor sun — a genuine safety and packaging benefit.
- **Cleaner logic supply.** VCC runs at **3.3 V straight from the Pi**, so
  there's no onboard 5 V regulator getting warm and no 5 V logic rail to route.
- **Unchanged golden rules:** still power the **Pi from its own 5 V USB power
  bank**, still tie **all grounds common** (Pi ↔ both driver GNDs ↔ pack −), and
  still keep the motor pack separate from the Pi. The MOSFET swap changes the
  driver, not the two-supply architecture.

---

## 4. Impact on practicality — route / terrain conditions

The route is grass and an uphill section: **high rolling resistance and high
torque demand**, i.e. **high, sustained current**. That is precisely the regime
where driver choice decides whether the car makes it:

- **Grass and slopes pull large, sustained currents.** The L293D can't supply
  them (0.6 A/ch, and it overheats); the L298N can (2 A) but bleeds torque as
  heat; the **MOSFET driver supplies current efficiently and stays cool**, so
  torque is available *continuously*, not just in short bursts before a thermal
  trip.
- **Stall is the danger case.** If a wheel digs in on the hill, current spikes
  toward the stall value. A cool, low-loss MOSFET stage tolerates brief spikes
  better and (in integrated chips) has **over-current/thermal protection** that
  limits rather than fails destructively.
- **Efficiency ≈ range.** Off-road driving is energy-hungry; wasting 30–40% of
  pack voltage in a bipolar driver noticeably shortens how far the car roams.
  MOSFET efficiency keeps more range for the vision system to find and follow
  the path.

**The one caveat, stated plainly:** the TB6612's **continuous** rating (1.2 A/ch)
is *lower* than the L298N's (2 A/ch) — its advantage is efficiency, not raw
current. With **one motor per channel** and modest gear motors that's fine
(peaks to 3.2 A are allowed). But if your motors are large and the grass is
genuinely punishing — repeated near-stall climbing — size up to a higher-current
MOSFET driver:

- **DRV8871** (single motor, ~3.6 A) — one per motor, low drop, current-limit.
- **BTS7960 / "IBT-2"** (MOSFET half-bridges, up to ~40 A per motor) — overkill
  for most, but the go-to when you want zero worry about stall current on steep
  grass. **Note:** BTS7960 uses a **two-PWM-per-motor** control scheme
  (RPWM/LPWM), which **would require a code change** (two PWM outputs per side
  instead of IN+IN+EN), unlike the TB6612 which drops into the existing code.

---

## 5. Bottom line & code impact

- **Recommended:** **2× TB6612FNG** (the MOSFET diagram) for a light, cool,
  efficient system that climbs better on a smaller battery and drops into the
  **existing `autonomous_car.py` with no code change** — wire it per-side and it
  reuses the same GPIO (`Motor(forward, backward, enable, pwm=True)`), with
  `STBY` tied to 3.3 V (or to a spare GPIO if you want an all-motor e-stop).
- **If the motors are big / the hill is steep:** step up to **BTS7960** for
  current headroom, and budget for a small code change (dual-PWM control).
- **Versus the alternatives:** MOSFET > L298N > L293D for this off-road,
  battery-powered, hill-climbing use case — driven mainly by **efficiency
  (torque per volt), cool operation (no thermal cut-out), and battery range**,
  which are exactly the properties the terrain and the untethered power supply
  demand.

| Driver | Drop | Cont. current | Heat | Logic | Code change | Best when |
|---|---|---|---|---|---|---|
| L293D (×1) | ~2 V | 0.6 A/ch | high | 5 V | — (baseline) | tiny motors, flat, demo |
| L298N (×2) | ~2–3 V | 2 A/ch | high (heatsink) | 5 V | none | more current, cost-sensitive |
| **TB6612 (×2)** | **~0.2 V** | 1.2 A/ch (3.2 pk) | **low** | **3.3 V** | **none** | **this project** ✅ |
| BTS7960 (×2/4) | ~0.1 V | up to ~40 A | low | 3.3–5 V | yes (dual PWM) | large motors / steep grass |
