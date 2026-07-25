#!/usr/bin/env python3
"""
simple_obstacle_avoider.py  --  PROGRAM 1 (the demo)
=====================================================

The simplest useful behaviour: drive forward, and whenever the ultrasonic
sensor sees something close ahead, stop, back up a little, and turn away.
No camera, no route, no map -- just a reflex.

Purpose: prove that your motors, L293D driver, and HC-SR04 sensor are all
wired and working BEFORE you add the complexity of the camera. If this
program drives and dodges correctly, your hardware is good.

Hardware (skid-steer / tank drive):
  * Left  motors (both left wheels wired in parallel) -> L293D channel A
  * Right motors (both right wheels wired in parallel) -> L293D channel B
  * HC-SR04 ultrasonic sensor on the front

Wiring / pins: see docs/WIRING.md and docs/pinout.svg.

Run:  python3 simple_obstacle_avoider.py
Stop: Ctrl-C  (motors are cut safely on exit)

TEST WITH THE WHEELS OFF THE GROUND FIRST.
"""

import time
from signal import pause  # noqa: F401  (kept for reference; we use our own loop)

from gpiozero import Motor, DistanceSensor

# gpiozero can use the 'pigpio' backend for smoother PWM. If pigpiod is
# running (sudo systemctl enable --now pigpiod) uncomment the two lines below.
# from gpiozero import Device
# from gpiozero.pins.pigpio import PiGPIOFactory
# Device.pin_factory = PiGPIOFactory()

# ---------------------------------------------------------------------------
# CONFIG  --  pins are BCM GPIO numbers (see the wiring table in the README)
# ---------------------------------------------------------------------------

# Left motor channel (L293D IN1/IN2 for direction, EN1 for PWM speed)
LEFT_FORWARD_PIN = 5    # GPIO5  -> L293D IN1
LEFT_BACKWARD_PIN = 6   # GPIO6  -> L293D IN2
LEFT_ENABLE_PIN = 12    # GPIO12 -> L293D EN1  (PWM = speed)

# Right motor channel (L293D IN3/IN4 for direction, EN2 for PWM speed)
RIGHT_FORWARD_PIN = 20  # GPIO20 -> L293D IN3
RIGHT_BACKWARD_PIN = 21  # GPIO21 -> L293D IN4
RIGHT_ENABLE_PIN = 13   # GPIO13 -> L293D EN2  (PWM = speed)

# HC-SR04 ultrasonic sensor
TRIG_PIN = 23           # GPIO23 -> HC-SR04 TRIG
ECHO_PIN = 24           # GPIO24 <- HC-SR04 ECHO  (THROUGH A VOLTAGE DIVIDER!)
MAX_SENSOR_DISTANCE = 2.0  # metres; readings clamp here

# Behaviour tuning
CRUISE_SPEED = 0.6      # forward speed, 0.0-1.0 (PWM duty cycle)
TURN_SPEED = 0.6        # wheel speed while pivoting
STOP_DISTANCE = 0.25    # metres: obstacle closer than this -> react
REVERSE_TIME = 0.4      # seconds to back up before turning
TURN_TIME = 0.6         # seconds to pivot away from the obstacle
LOOP_DELAY = 0.05       # seconds between sensor checks (~20 Hz)

# ---------------------------------------------------------------------------
# HARDWARE SETUP
# ---------------------------------------------------------------------------

# pwm=True makes gpiozero drive the ENABLE pin as PWM, so motor.forward(0.6)
# spins the motor at 60% via the L293D enable input -- exactly how you set
# speed on an L293D.
left = Motor(forward=LEFT_FORWARD_PIN,
             backward=LEFT_BACKWARD_PIN,
             enable=LEFT_ENABLE_PIN,
             pwm=True)

right = Motor(forward=RIGHT_FORWARD_PIN,
              backward=RIGHT_BACKWARD_PIN,
              enable=RIGHT_ENABLE_PIN,
              pwm=True)

sensor = DistanceSensor(echo=ECHO_PIN,
                        trigger=TRIG_PIN,
                        max_distance=MAX_SENSOR_DISTANCE)


# ---------------------------------------------------------------------------
# MOVEMENT HELPERS  (skid steer: turn by driving the two sides differently)
# ---------------------------------------------------------------------------

def drive_forward(speed=CRUISE_SPEED):
    left.forward(speed)
    right.forward(speed)


def drive_backward(speed=CRUISE_SPEED):
    left.backward(speed)
    right.backward(speed)


def pivot_left(speed=TURN_SPEED):
    # Left side reverses, right side goes forward -> spins on the spot to the left.
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
    print("Simple obstacle avoider running. Ctrl-C to stop.")
    print("(Wheels off the ground for the first test!)")

    # Alternate turn direction each time we hit something so we don't get
    # stuck rocking back and forth against the same wall.
    turn_toggle = True

    try:
        while True:
            distance = sensor.distance  # metres, 0.0 - MAX_SENSOR_DISTANCE
            print(f"distance: {distance * 100:5.1f} cm", end="\r")

            if distance <= STOP_DISTANCE:
                # --- reflex: obstacle ahead ---
                stop()
                time.sleep(0.1)
                drive_backward()
                time.sleep(REVERSE_TIME)
                stop()

                if turn_toggle:
                    pivot_left()
                else:
                    pivot_right()
                turn_toggle = not turn_toggle
                time.sleep(TURN_TIME)
                stop()
            else:
                # --- path clear: cruise ---
                drive_forward()

            time.sleep(LOOP_DELAY)

    except KeyboardInterrupt:
        print("\nStopping (Ctrl-C).")
    finally:
        stop()
        # gpiozero cleans up GPIO on program exit automatically.


if __name__ == "__main__":
    main()
