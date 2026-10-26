// Aux fan test - drives the fan by holding IO18 high
const int auxFanPin = 18;

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("AUX_FAN_TEST starting...");

  pinMode(auxFanPin, OUTPUT);
  digitalWrite(auxFanPin, HIGH);

  Serial.println("IO18 HIGH - aux fan ON");
}

void loop() {
  digitalWrite(auxFanPin, HIGH);
}
