/*
 * vega_2wd_obstacle_avoider.ino
 * ===========================================================================
 * 2-WHEEL-DRIVE obstacle-avoiding car  --  VEGA ARIES v2.0  --  ONE L298N.
 *
 * Obstacle avoidance ONLY (no camera). Drive forward; when the HC-SR04
 * ultrasonic sensor sees something close, stop, back up, and turn away.
 *
 * WHY THE VEGA ARIES (and why no voltage divider):
 *   The VEGA ARIES v2.0 tolerates the HC-SR04's 5 V ECHO pulse on its
 *   digital inputs, so ECHO connects DIRECTLY to a pin -- no divider needed
 *   (unlike a Raspberry Pi, whose 3.3 V GPIO requires one). Its 3.3 V logic
 *   outputs still sit above the L298N input HIGH threshold (~2.3 V), so it
 *   drives the L298N directly too.
 *
 * HARDWARE
 *   * 2 DC motors (left, right), skid steer.
 *   * 1x L298N:  Channel A -> LEFT motor,  Channel B -> RIGHT motor.
 *   * 1x HC-SR04 ultrasonic sensor.
 *   * 9 V battery -> L298N +12V (Vs). Leave the 5V-EN jumper ON so the
 *     onboard regulator makes the 5 V logic supply.
 *   * VEGA ARIES powered by its own USB (a 5 V power bank is fine).
 *   * COMMON GROUND: VEGA GND <-> L298N GND <-> 9 V battery (-).
 *
 * PINS (Arduino pin numbers as used by the VEGA core; ~ = PWM-capable)
 *   Left  motor : ENA=9(~)  IN1=8   IN2=7
 *   Right motor : ENB=10(~) IN3=4   IN4=2
 *   HC-SR04     : TRIG=12    ECHO=11   (ECHO direct -- no divider)
 *
 * BUILD/UPLOAD (Arduino IDE)
 *   1. Install the VEGA board package and select:
 *        Tools -> Board -> "VEGA ARIES Boards" -> "ARIES v2.0".
 *   2. Select the correct Port, then Upload.
 *   3. Open Serial Monitor at 115200 baud to see distance readings.
 *
 * TEST WITH THE WHEELS OFF THE GROUND FIRST.
 * ===========================================================================
 */

// ---- Motor driver pins (single L298N) ----
const int ENA = 9;    // LEFT  speed  (PWM)
const int IN1 = 8;    // LEFT  dir A
const int IN2 = 7;    // LEFT  dir B
const int ENB = 10;   // RIGHT speed  (PWM)
const int IN3 = 4;    // RIGHT dir A
const int IN4 = 2;    // RIGHT dir B

// ---- Ultrasonic pins ----
const int TRIG_PIN = 12;
const int ECHO_PIN = 11;   // direct to pin -- VEGA tolerates the 5 V pulse

// ---- Behaviour tuning ----
const int   CRUISE_SPEED  = 160;   // 0-255 PWM duty (forward)
const int   TURN_SPEED    = 160;   // 0-255 PWM duty (pivot)
const float STOP_DISTANCE = 25.0;  // cm: obstacle closer than this -> react
const int   REVERSE_MS    = 400;   // back up time
const int   TURN_MS       = 600;   // pivot time
const long  ECHO_TIMEOUT  = 25000; // us (~4 m) pulseIn timeout

bool turnToggle = true;            // alternate turn direction

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  stopMotors();
  Serial.println("VEGA 2WD obstacle avoider (1x L298N). Wheels up for first test!");
}

// ---------------------------------------------------------------------------
void loop() {
  float distance = readDistanceCm();
  Serial.print("distance: ");
  Serial.print(distance, 1);
  Serial.println(" cm");

  if (distance > 0 && distance <= STOP_DISTANCE) {
    // Obstacle: stop, reverse, then pivot away (alternating each time).
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
  delay(50);   // ~20 Hz loop
}

// ---------------------------------------------------------------------------
// HC-SR04: trigger a ping and time the echo. Returns distance in cm,
// or -1 on timeout (no echo / out of range).
// ---------------------------------------------------------------------------
float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT);
  if (duration == 0) return -1;                 // timeout
  return (duration * 0.0343f) / 2.0f;           // speed of sound -> cm
}

// ---------------------------------------------------------------------------
// MOVEMENT HELPERS (skid steer)
// ---------------------------------------------------------------------------
void driveLeft(bool forward, int speed) {
  digitalWrite(IN1, forward ? HIGH : LOW);
  digitalWrite(IN2, forward ? LOW  : HIGH);
  analogWrite(ENA, speed);
}

void driveRight(bool forward, int speed) {
  digitalWrite(IN3, forward ? HIGH : LOW);
  digitalWrite(IN4, forward ? LOW  : HIGH);
  analogWrite(ENB, speed);
}

void moveForward(int speed)  { driveLeft(true,  speed); driveRight(true,  speed); }
void moveBackward(int speed) { driveLeft(false, speed); driveRight(false, speed); }
void pivotLeft(int speed)    { driveLeft(false, speed); driveRight(true,  speed); }
void pivotRight(int speed)   { driveLeft(true,  speed); driveRight(false, speed); }

void stopMotors() {
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
}
