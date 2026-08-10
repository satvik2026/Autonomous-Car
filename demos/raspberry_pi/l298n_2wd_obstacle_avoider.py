#!/usr/bin/env python3
"""
l298n_2wd_obstacle_avoider.py
=============================================================================
2-WHEEL-DRIVE obstacle-avoiding car  --  Raspberry Pi 3B+  --  ONE L298N.

A self-contained indoor/flat-ground demo. No camera, no route, no map:
drive forward, and when the ultrasonic sensor sees something close, stop,
back up, and turn away.

HARDWARE
  * 2 DC motors (left wheel, right wheel), skid steer.
  * 1x L298N motor driver:
        - Channel A  -> LEFT  motor   (ENA = speed, IN1/IN2 = direction)
        - Channel B  -> RIGHT motor   (ENB = speed, IN3/IN4 = direction)
  * 1x HC-SR04 ultrasonic distance sensor.
  * 9 V battery -> L298N +12V (Vs) terminal (motor supply).
        Leave the L298N 5V-EN jumper ON: at 9 V the onboard regulator makes
        the 5 V logic supply for you.
  * Raspberry Pi powered SEPARATELY by a 5 V USB power bank (micro-USB).
  * COMMON GROUND: Pi GND <-> L298N GND <-> 9 V battery (-).

  !!! HC-SR04 ECHO outputs 5 V; the Pi GPIO is 3.3 V only.
      Put a voltage divider on ECHO (1k in series, 2k to GND) -> ~3.3 V.
      See demos/docs/pinout_rpi_l298n_2wd.svg.

PINS (BCM GPIO numbering)
  Left  motor : ENA=GPIO12  IN1=GPIO5   IN2=GPIO6
  Right motor : ENB=GPIO13  IN3=GPIO20  IN4=GPIO21
  HC-SR04     : TRIG=GPIO23 ECHO=GPIO24 (via divider)

RUN   : python3 l298n_2wd_obstacle_avoider.py
STOP  : Ctrl-C  (motors are cut on exit)
TEST WITH THE WHEELS OFF THE GROUND FIRST.
=============================================================================
"""

import time
from gpiozero import Motor, DistanceSensor

# ---------------------------------------------------------------------------
# PIN CONFIG (BCM)
# ---------------------------------------------------------------------------
# LEFT motor -> L298N channel A
LEFT_IN1 = 5      # IN1 (direction)
LEFT_IN2 = 6      # IN2 (direction)
LEFT_ENA = 12     # ENA (PWM speed)
# RIGHT motor -> L298N channel B
RIGHT_IN3 = 20    # IN3 (direction)
RIGHT_IN4 = 21    # IN4 (direction)
RIGHT_ENB = 13    # ENB (PWM speed)
# HC-SR04
TRIG_PIN = 23
ECHO_PIN = 24     # <-- through a 5V->3.3V divider

# ---------------------------------------------------------------------------
# BEHAVIOUR TUNING
# ---------------------------------------------------------------------------
CRUISE_SPEED = 0.6     # forward speed 0.0-1.0 (PWM duty on ENA/ENB)
TURN_SPEED = 0.6       # wheel speed while pivoting
STOP_DISTANCE = 0.25   # metres: obstacle closer than this -> react
REVERSE_TIME = 0.4     # s to back up
TURN_TIME = 0.6        # s to pivot away
LOOP_DELAY = 0.05      # s between sensor reads (~20 Hz)
MAX_DISTANCE = 2.0     # m: sensor clamps here

# ---------------------------------------------------------------------------
# HARDWARE OBJECTS
# ---------------------------------------------------------------------------
# pwm=True drives the ENA/ENB pins as PWM, so left.forward(0.6) spins the
# motor at 60% via the L298N enable input.
left = Motor(forward=LEFT_IN1, backward=LEFT_IN2, enable=LEFT_ENA, pwm=True)
right = Motor(forward=RIGHT_IN3, backward=RIGHT_IN4, enable=RIGHT_ENB, pwm=True)
sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=MAX_DISTANCE)


# ---------------------------------------------------------------------------
# MOVEMENT HELPERS (skid steer: turn by driving the two sides differently)
# ---------------------------------------------------------------------------
def forward(speed=CRUISE_SPEED):
    left.forward(speed)
    right.forward(speed)


def backward(speed=CRUISE_SPEED):
    left.backward(speed)
    right.backward(speed)


def pivot_left(speed=TURN_SPEED):
    left.backward(speed)   # left wheel reverses,
    right.forward(speed)   # right wheel forward -> spins left on the spot


def pivot_right(speed=TURN_SPEED):
    left.forward(speed)
    right.backward(speed)


def stop():
    left.stop()
    right.stop()


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------
def main():
    print("2WD obstacle avoider (1x L298N). Ctrl-C to stop.")
    print("Wheels off the ground for the first test!")
    turn_toggle = True  # alternate turn direction so we don't rock on a wall

    try:
        while True:
            distance = sensor.distance  # metres
            print(f"distance: {distance * 100:5.1f} cm", end="\r")

            if distance <= STOP_DISTANCE:
                stop()
                time.sleep(0.1)
                backward()
                time.sleep(REVERSE_TIME)
                stop()
                (pivot_left if turn_toggle else pivot_right)()
                turn_toggle = not turn_toggle
                time.sleep(TURN_TIME)
                stop()
            else:
                forward()

            time.sleep(LOOP_DELAY)

    except KeyboardInterrupt:
        print("\nStopping (Ctrl-C).")
    finally:
        stop()


if __name__ == "__main__":
    main()
