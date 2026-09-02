#!/usr/bin/env python3
"""
gpio_selftest.py -- prove the motors and the ultrasonic BEFORE a full run.

WHY THIS EXISTS
===============
On trial day the car went silent: running the 4WD demo or the navigator
produced no motor sound and the terminal looked frozen. The reason that failure
is so confusing is that BOTH programs read the ultrasonic sensor at the TOP of
their loop and only command the motors AFTER that read. So if the sensor read
hangs (a miswired ECHO, no divider, sensor unpowered), the motors are never
reached -- you get silence and a frozen prompt, and it looks like the whole
program died.

This tool tests the two subsystems SEPARATELY and, crucially, reads the sensor
with a TIMEOUT, so a dead sensor prints a clear message instead of freezing the
way the real programs do. Run it first; it turns a silent mystery into a
one-line diagnosis.

    python3 course/tools/gpio_selftest.py           # motors + sensor
    python3 course/tools/gpio_selftest.py --motors  # motors only
    python3 course/tools/gpio_selftest.py --sensor  # sensor only

PUT THE WHEELS OFF THE GROUND before running the motor test.
"""

import argparse
import sys
import time

# Pin map -- MUST match course_navigator.py and the dual-L298N diagram.
# Printed below so you can eyeball it against docs/pinout_dual_l298n.svg.
LEFT_FWD, LEFT_BWD, LEFT_EN = 5, 6, 12
RIGHT_FWD, RIGHT_BWD, RIGHT_EN = 20, 21, 13
TRIG_PIN, ECHO_PIN = 23, 24


def _print_pins():
    print("Pin map this test uses (BCM) -- cross-check docs/pinout_dual_l298n.svg:")
    print(f"  LEFT  side : dirA=GPIO{LEFT_FWD}  dirB=GPIO{LEFT_BWD}  "
          f"EN(PWM)=GPIO{LEFT_EN}")
    print(f"  RIGHT side : dirA=GPIO{RIGHT_FWD}  dirB=GPIO{RIGHT_BWD}  "
          f"EN(PWM)=GPIO{RIGHT_EN}")
    print(f"  HC-SR04    : TRIG=GPIO{TRIG_PIN}  ECHO=GPIO{ECHO_PIN} (via divider)")
    print()


def _make_devices():
    """Construct gpiozero devices, explaining the common failure loudly."""
    try:
        from gpiozero import Motor, DistanceSensor
    except Exception as e:  # pragma: no cover - hardware only
        print("!! could not import gpiozero:", e)
        print("   On Raspberry Pi OS Bookworm: sudo apt install python3-gpiozero")
        sys.exit(2)
    try:
        left = Motor(forward=LEFT_FWD, backward=LEFT_BWD, enable=LEFT_EN, pwm=True)
        right = Motor(forward=RIGHT_FWD, backward=RIGHT_BWD, enable=RIGHT_EN,
                      pwm=True)
        sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=2.0)
    except Exception as e:  # pragma: no cover - hardware only
        print("!! could not create GPIO devices:", e)
        print("   Common causes:")
        print("   - pigpio pin factory selected but pigpiod not running:")
        print("       sudo systemctl enable --now pigpiod")
        print("   - a pin is already in use by another process.")
        sys.exit(2)
    return left, right, sensor


def test_motors(left, right):
    print("== MOTOR TEST ==  (wheels OFF the ground)")
    moves = [
        ("LEFT  forward", lambda: left.forward(0.7), left),
        ("LEFT  backward", lambda: left.backward(0.7), left),
        ("RIGHT forward", lambda: right.forward(0.7), right),
        ("RIGHT backward", lambda: right.backward(0.7), right),
    ]
    for name, go, dev in moves:
        print(f"  {name} for 1.0 s ... listen for the motor", flush=True)
        go()
        time.sleep(1.0)
        dev.stop()
        time.sleep(0.4)
    print("  If a side was SILENT: check that side's EN pin, the ENA/ENB")
    print("  jumper (remove it to use PWM), the motor battery, and COMMON GROUND.")
    print("  If a side ran the WRONG way: swap that side's two motor wires.\n")


def _read_distance_with_timeout(sensor, timeout=2.0):
    """
    Read sensor.distance in a background thread so a dead sensor cannot freeze
    us. Returns metres, or None if the read did not complete in `timeout` s --
    which is exactly the hang that silences the real programs.
    """
    import threading
    result = {}

    def worker():
        try:
            result["d"] = sensor.distance
        except Exception as e:  # pragma: no cover - hardware only
            result["err"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None
    if "err" in result:
        raise result["err"]
    return result.get("d")


def test_sensor(sensor, samples=10):
    print("== ULTRASONIC TEST ==")
    print("  Reading distance 10x, each with a 2 s timeout.")
    hung = 0
    for i in range(samples):
        d = _read_distance_with_timeout(sensor, timeout=2.0)
        if d is None:
            hung += 1
            print(f"  {i+1:2d}: NO READING in 2 s  <-- this is the freeze the "
                  "real programs hit", flush=True)
        else:
            print(f"  {i+1:2d}: {d*100:6.1f} cm", flush=True)
        time.sleep(0.2)
    print()
    if hung:
        print("  DIAGNOSIS: the sensor read blocks. In course_navigator.py and")
        print("  the demos the motor commands come AFTER this read, so a blocked")
        print("  read = silent motors + frozen prompt. Check:")
        print("   - ECHO wired through the 1k/2k divider to GPIO24 (not direct),")
        print("   - TRIG on GPIO23, sensor VCC=5V, GND common with the Pi,")
        print("   - the sensor is the right way round.")
    else:
        print("  Sensor OK: readings returned without hanging.")
    print()


def main():
    ap = argparse.ArgumentParser(description="Pre-run GPIO self-test.")
    ap.add_argument("--motors", action="store_true", help="motor test only")
    ap.add_argument("--sensor", action="store_true", help="sensor test only")
    a = ap.parse_args()

    _print_pins()
    left, right, sensor = _make_devices()
    try:
        if not a.sensor:
            test_motors(left, right)
        if not a.motors:
            test_sensor(sensor)
        print("Self-test done. If both subsystems passed here but a full run")
        print("still stalls, suspect the camera pipeline or a weak Pi supply.")
    finally:
        left.stop()
        right.stop()


if __name__ == "__main__":
    main()
