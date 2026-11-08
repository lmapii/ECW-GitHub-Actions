"""Run storage upload and explicit MCU flashing under the workflow's Upload step."""

import os

import flash_firmware
import upload_firmware


def main() -> None:
    code = upload_firmware.main()
    os.environ["ECW_FIRMWARE_CODE"] = code
    flash_firmware.main()


if __name__ == "__main__":
    main()
