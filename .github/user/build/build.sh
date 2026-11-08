#!/usr/bin/env bash
# Project-owned build script.
#
# ci-job-smoke.yml's Build job never changes to build a different project or
# board -- it only ever runs `.github/user/build/build.sh`. Everything
# specific to *this* project (which board, which core, which sketch, how to
# compile it) lives here instead, so changing the build process never means
# touching the workflow.
#
# Contract with the workflow:
#   - Runs from the repository root, after checkout.
#   - Must leave exactly one *.bin file inside ./build/ (the whole
#     directory is uploaded as the artifact; the Upload job finds that one
#     file by extension, not by name, so it can be called anything).

set -euo pipefail

FQBN="arduino:renesas_uno:unor4wifi"
ARDUINO_CORE="arduino:renesas_uno"
FIRMWARE_SKETCH="src/arduino_ci_demo"

if ! command -v arduino-cli >/dev/null 2>&1; then
  mkdir -p "$HOME/bin"
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$HOME/bin" sh
  export PATH="$HOME/bin:$PATH"
fi

arduino-cli core update-index
arduino-cli core install "${ARDUINO_CORE}"

# ArduinoGraphics renders the scrolling text on the onboard LED matrix;
# unlike Arduino_LED_Matrix it isn't bundled with the core.
arduino-cli lib update-index
arduino-cli lib install "ArduinoGraphics"

mkdir -p build
arduino-cli compile --fqbn "${FQBN}" "${FIRMWARE_SKETCH}" --output-dir build
