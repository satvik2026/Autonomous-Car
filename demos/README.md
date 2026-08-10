# L298N Obstacle-Avoidance Demos

Fresh, standalone demo builds using the **L298N** motor driver and a **9 V
battery** for the motors (flat-ground demos — *not* the off-road build). The
controller is powered separately (Raspberry Pi → USB power bank; VEGA → USB).
**No camera and no route** — obstacle avoidance only.

## Files

| Program | Board | Wheels | Drivers | Sketch/Script |
|---|---|---|---|---|
| Raspberry Pi 2WD | Pi 3B+ | 2 | 1× L298N | `raspberry_pi/l298n_2wd_obstacle_avoider.py` |
| Raspberry Pi 4WD | Pi 3B+ | 4 | 2× L298N | `raspberry_pi/l298n_4wd_obstacle_avoider.py` |
| VEGA 2WD | VEGA ARIES v2.0 | 2 | 1× L298N | `vega_aries/vega_2wd_obstacle_avoider/vega_2wd_obstacle_avoider.ino` |
| VEGA 4WD | VEGA ARIES v2.0 | 4 | 2× L298N | `vega_aries/vega_4wd_obstacle_avoider/vega_4wd_obstacle_avoider.ino` |

Pinout diagrams (open in a browser) in `demos/docs/`:
`pinout_rpi_l298n_2wd.svg`, `pinout_rpi_l298n_4wd.svg`,
`pinout_vega_l298n_2wd.svg`, `pinout_vega_l298n_4wd.svg`.

## Behaviour (all four)

Drive forward; when the HC-SR04 sees an obstacle within ~25 cm, stop, back up,
and pivot away (alternating direction). Skid steer: turn by driving the two
sides at different speeds.

## The key wiring differences

- **Raspberry Pi:** GPIO is 3.3 V, so the HC-SR04 **ECHO needs a 1 kΩ/2 kΩ
  voltage divider** down to ~3.3 V. Pi runs on its own USB power bank.
- **VEGA ARIES v2.0:** tolerates the 5 V ECHO pulse, so **ECHO connects
  directly — no divider**. Its 3.3 V outputs still drive the L298N (input HIGH
  threshold ~2.3 V). Uploaded from the Arduino IDE (board: *ARIES v2.0*).
- **2WD → 4WD:** one L298N (two channels, one motor each) becomes two L298N
  (one board per side; each board's two channels wired in parallel to the same
  control lines for current headroom). Because both wheels on a side move
  together, the control code and the 6 control pins are unchanged from 2WD.
- **9 V battery → L298N +12V (Vs)** on every build. Leave the **5V-EN jumper
  ON** (9 V ≤ 12 V, so the onboard regulator makes the 5 V logic supply) and
  **remove the ENA/ENB jumpers** so PWM controls speed. `L298N drop ≈ 2–3 V →
  motors see ~6–7 V`, fine for a flat demo. **Common ground** everywhere.

## Running

Raspberry Pi:
```bash
sudo apt install -y python3-gpiozero
python3 raspberry_pi/l298n_2wd_obstacle_avoider.py    # or the 4wd file
```

VEGA ARIES v2.0: open the `.ino` in the Arduino IDE, select
**Tools → Board → VEGA ARIES Boards → ARIES v2.0**, pick the port, Upload, and
open Serial Monitor at 115200 baud.

**Test with the wheels off the ground first.**
