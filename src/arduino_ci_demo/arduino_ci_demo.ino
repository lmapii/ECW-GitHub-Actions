// Flashed onto the Arduino UNO R4 WiFi by the ECW CI Job Smoke workflow.
//
// Change `val` below and open a PR to change the letter that gets printed
// over serial and shown, static (no scrolling), on the onboard 12x8 LED
// matrix. The CI serial job captures the printed line; the CI camera job
// captures a photo of the board so you can see the LED lit and the letter
// on the matrix.
//
// ArduinoGraphics must be included BEFORE Arduino_LED_Matrix.
#include "ArduinoGraphics.h"
#include "Arduino_LED_Matrix.h"

const char val = 'D';

ArduinoLEDMatrix matrix;

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  matrix.begin();

  char text[2] = {val, '\0'};

  matrix.beginDraw();
  matrix.stroke(0xFFFFFFFF);
  matrix.textFont(Font_5x7);
  matrix.beginText(3, 0, 0xFFFFFF);
  matrix.println(text);
  matrix.endText();  // no scroll direction given -> static, single frame
  matrix.endDraw();
}

void loop() {
  Serial.print("Your value is ");
  Serial.println(val);
  delay(1000);
}
