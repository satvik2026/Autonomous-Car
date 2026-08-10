#!/usr/bin/env python3
"""
l298n_4wd_obstacle_avoider.py
=============================================================================
4-WHEEL-DRIVE obstacle-avoiding car  --  Raspberry Pi 3B+  --  TWO L298N.

Same behaviour as the 2WD demo (drive forward, stop/reverse/turn on a close
obstacle) but with four driven wheels and two motor drivers for the extra
current. No camera, no route.

WHY TWO L298N FOR FOUR MOTORS
  One L298N channel is rated ~2 A. Rather than hang two motors off a single
  channel (which halves the current each motor can get), we give each SIDE
  its own board:
        L298N #1  -> both LEFT  motors
        L298N #2  -> both RIGHT motors
  On each board the two channels are wired IN PARALLEL and driven by the same
  control lines, so both wheels on a side always move together (that's what
  skid steering needs) while each motor still gets its own H-bridge:
        ENA tied to ENB          -> one PWM controls that side's speed
        IN1 tied to IN3          -> one pin sets that side's "forward"
        IN2 tied to IN4          -> one pin sets that side's "backward"
  Because the two sides move as one unit each, the control code is identical
  to the 2WD demo -- only the wiring (and the current headroom) changes.

HARDWARE
  * 4 DC motors: front-left, rear-left, front-right, rear-right.
  * 2x L298N (one per side). 9 V battery -> BOTH boards' +12V (Vs) terminals.
        Leave each board's 5V-EN jumper ON (9 V -> onboard 5 V logic).
  * 1x HC-SR04 ultrasonic sensor.
  * Raspberry Pi powered SEPARATELY by a 5 V USB power bank.
  * COMMON GROUND: Pi GND <-> both L298N GND <-> 9 V battery (-).

  !!! HC-SR04 ECHO is 5 V -> use a divider to the 3.3 V GPIO (see the SVG).

PINS (BCM GPIO) -- same 6 control pins as the 2WD demo
  LEFT  board (both left  motors) : ENA&ENB=GPIO12  IN1&IN3=GPIO5   IN2&IN4=GPIO6
  RIGHT board (both right motors) : ENA&ENB=GPIO13  IN1&IN3=GPIO20  IN2&IN4=GPIO21
  HC-SR04                         : TRIG=GPIO23      ECHO=GPIO24 (via divider)

RUN   : python3 l298n_4wd_obstacle_avoider.py
STOP  : Ctrl-C
TEST WITH THE WHEELS OFF THE GROUND FIRST.
=============================================================================
"""

import time
from gpiozero import Motor, DistanceSensor

# ---------------------------------------------------------------------------
# PIN CONFIG (BCM). Each "side" object drives one whole L298N board, i.e. the
# two motors on that side (their channels are wired in parallel).
# ---------------------------------------------------------------------------
# LEFT board -> both left motors
LEFT_FWD = 5       # IN1 & IN3 (forward direction)
LEFT_BWD = 6       # IN2 & IN4 (backward direction)
LEFT_EN = 12       # ENA & ENB (PWM speed)
# RIGHT board -> both right motors
RIGHT_FWD = 20     # IN1 & IN3
RIGHT_BWD = 21     # IN2 & IN4
RIGHT_EN = 13      # ENA & ENB
# HC-SR04
TRIG_PIN = 23
ECHO_PIN = 24      # <-- through a 5V->3.3V divider

# ---------------------------------------------------------------------------
# BEHAVIOUR TUNING
# ---------------------------------------------------------------------------
CRUISE_SPEED = 0.6
TURN_SPEED = 0.6
STOP_DISTANCE = 0.25
REVERSE_TIME = 0.4
TURN_TIME = 0.6
LOOP_DELAY = 0.05
MAX_DISTANCE = 2.0

# ---------------------------------------------------------------------------
# HARDWARE OBJECTS -- one Motor per SIDE (= one L298N board = two wheels)
# ---------------------------------------------------------------------------
left = Motor(forward=LEFT_FWD, backward=LEFT_BWD, enable=LEFT_EN, pwm=True)
right = Motor(forward=RIGHT_FWD, backward=RIGHT_BWD, enable=RIGHT_EN, pwm=True)
sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=MAX_DISTANCE)


# ---------------------------------------------------------------------------
# MOVEMENT HELPERS (skid steer)
# ---------------------------------------------------------------------------
def forward(speed=CRUISE_SPEED):
    left.forward(speed)
    right.forward(speed)


def backward(speed=CRUISE_SPEED):
    left.backward(speed)
    right.backward(speed)


def pivot_left(speed=TURN_SPEED):
    left.backward(speed)
    right.forward(speed)


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
    print("4WD obstacle avoider (2x L298N). Ctrl-C to stop.")
    print("Wheels off the ground for the first test!")
    turn_toggle = True

    try:
        while True:
            distance = sensor.distance
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
