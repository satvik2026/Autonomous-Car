/*
 * vega_4wd_obstacle_avoider.ino
 * ===========================================================================
 * 4-WHEEL-DRIVE obstacle-avoiding car  --  VEGA ARIES v2.0  --  TWO L298N.
 *
 * Obstacle avoidance ONLY (no camera). Same behaviour as the 2WD sketch, but
 * four driven wheels and two L298N boards for the extra current.
 *
 * WHY TWO L298N FOR FOUR MOTORS
 *   One L298N channel is ~2 A. Instead of sharing a channel between two
 *   motors, each SIDE gets its own board:
 *        L298N #1 -> both LEFT  motors
 *        L298N #2 -> both RIGHT motors
 *   On each board the two channels are wired IN PARALLEL and fed the same
 *   control lines, so both wheels on a side move together (what skid steering
 *   needs) while each motor keeps its own H-bridge:
 *        ENA tied to ENB   -> one PWM pin sets that side's speed
 *        IN1 tied to IN3   -> one pin sets that side's "forward"
 *        IN2 tied to IN4   -> one pin sets that side's "backward"
 *   So the control code is the same as the 2WD sketch -- only the wiring and
 *   the current capacity change.
 *
 * WHY THE VEGA ARIES: it tolerates the 5 V HC-SR04 ECHO pulse directly, so no
 * voltage divider is needed (a Raspberry Pi would need one).
 *
 * HARDWARE
 *   * 4 DC motors (front-left, rear-left, front-right, rear-right).
 *   * 2x L298N (one per side). 9 V battery -> BOTH boards' +12V (Vs).
 *     Leave each board's 5V-EN jumper ON (9 V -> onboard 5 V logic).
 *   * 1x HC-SR04 ultrasonic sensor.
 *   * VEGA ARIES powered by its own USB (5 V power bank fine).
 *   * COMMON GROUND: VEGA GND <-> both L298N GND <-> 9 V battery (-).
 *
 * PINS (Arduino pin numbers; ~ = PWM-capable) -- same 6 control pins as 2WD
 *   LEFT  board (both left  motors): EN=9(~)  FWD(IN1&IN3)=8  BWD(IN2&IN4)=7
 *   RIGHT board (both right motors): EN=10(~) FWD(IN1&IN3)=4  BWD(IN2&IN4)=2
 *   HC-SR04                        : TRIG=12  ECHO=11 (direct -- no divider)
 *
 * BUILD/UPLOAD (Arduino IDE)
 *   Tools -> Board -> "VEGA ARIES Boards" -> "ARIES v2.0", select Port, Upload.
 *   Serial Monitor at 115200 baud for distance readings.
 *
 * TEST WITH THE WHEELS OFF THE GROUND FIRST.
 * ===========================================================================
 */

// ---- Motor driver pins. Each "side" = one whole L298N board (two motors). ----
const int LEFT_EN  = 9;    // LEFT  board ENA&ENB (PWM speed)
const int LEFT_FWD = 8;    // LEFT  board IN1&IN3 (forward)
const int LEFT_BWD = 7;    // LEFT  board IN2&IN4 (backward)
const int RIGHT_EN  = 10;  // RIGHT board ENA&ENB (PWM speed)
const int RIGHT_FWD = 4;   // RIGHT board IN1&IN3 (forward)
const int RIGHT_BWD = 2;   // RIGHT board IN2&IN4 (backward)

// ---- Ultrasonic pins ----
const int TRIG_PIN = 12;
const int ECHO_PIN = 11;   // direct to pin -- VEGA tolerates the 5 V pulse

// ---- Behaviour tuning ----
const int   CRUISE_SPEED  = 160;   // 0-255 PWM duty
const int   TURN_SPEED    = 160;
const float STOP_DISTANCE = 25.0;  // cm
const int   REVERSE_MS    = 400;
const int   TURN_MS       = 600;
const long  ECHO_TIMEOUT  = 25000; // us (~4 m)

bool turnToggle = true;

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(LEFT_EN, OUTPUT);  pinMode(LEFT_FWD, OUTPUT);  pinMode(LEFT_BWD, OUTPUT);
  pinMode(RIGHT_EN, OUTPUT); pinMode(RIGHT_FWD, OUTPUT); pinMode(RIGHT_BWD, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  stopMotors();
  Serial.println("VEGA 4WD obstacle avoider (2x L298N). Wheels up for first test!");
}

// ---------------------------------------------------------------------------
void loop() {
  float distance = readDistanceCm();
  Serial.print("distance: ");
  Serial.print(distance, 1);
  Serial.println(" cm");

  if (distance > 0 && distance <= STOP_DISTANCE) {
    stopMotors();
    delay(100);
    moveBackward(CRUISE_SPEED);
    delay(REVERSE_MS);
    stopMotors();
    if (turnToggle) pivotLeft(TURN_SPEED);
    else            pivotRight(TURN_SPEED);
    turnToggle = !turnToggle;
    delay(TURN_MS);
    stopMotors();
  } else {
    moveForward(CRUISE_SPEED);
  }
  delay(50);
}

// ---------------------------------------------------------------------------
// HC-SR04 distance in cm, or -1 on timeout.
// ---------------------------------------------------------------------------
float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT);
  if (duration == 0) return -1;
  return (duration * 0.0343f) / 2.0f;
}

// ---------------------------------------------------------------------------
// MOVEMENT HELPERS (skid steer). Each side drives one whole L298N board.
// ---------------------------------------------------------------------------
void driveLeft(bool forward, int speed) {
  digitalWrite(LEFT_FWD, forward ? HIGH : LOW);
  digitalWrite(LEFT_BWD, forward ? LOW  : HIGH);
  analogWrite(LEFT_EN, speed);
}

void driveRight(bool forward, int speed) {
  digitalWrite(RIGHT_FWD, forward ? HIGH : LOW);
  digitalWrite(RIGHT_BWD, forward ? LOW  : HIGH);
  analogWrite(RIGHT_EN, speed);
}

void moveForward(int speed)  { driveLeft(true,  speed); driveRight(true,  speed); }
void moveBackward(int speed) { driveLeft(false, speed); driveRight(false, speed); }
void pivotLeft(int speed)    { driveLeft(false, speed); driveRight(true,  speed); }
void pivotRight(int speed)   { driveLeft(true,  speed); driveRight(false, speed); }

void stopMotors() {
  analogWrite(LEFT_EN, 0);
  analogWrite(RIGHT_EN, 0);
  digitalWrite(LEFT_FWD, LOW);  digitalWrite(LEFT_BWD, LOW);
  digitalWrite(RIGHT_FWD, LOW); digitalWrite(RIGHT_BWD, LOW);
}
