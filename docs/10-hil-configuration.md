# Configure HIL before uploading MCU firmware

The default pipeline is:

```text
Build → Reserve → Wait for active → Configure HIL → Upload → Test → Collect → Release
```

The Upload step contains two separate API operations: firmware upload to
storage, followed by explicit flashing of that stored MCU image. There is no
separate Flash job. A successful upload alone never permits CI tests to start.

## Repository variables and user data

| GitHub Actions variable | Meaning |
| --- | --- |
| `HIL_SENSOR_NAME` | Exact ECW inventory sensor name, such as `BME280`. Blank skips Configure HIL for workflows that do not use a HIL sensor. |
| `HIL_CSV_FILE` | Optional CSV path relative to `.github/user/hil/`. By default the sensor selects `bme280.csv`, `adxl345.csv`, `mcp3565r.csv`, or `pmod_mic3.csv`. |

Use a CSV exported from the frontend's sensor table. Values are in physical
units, not encoded device words. Column names, supported aliases, ranges,
channel order, signed conversion, rounding, two-word layout and full-scale
saturation follow the frontend sensor metadata. The supplied examples contain
100 samples; your CSV may contain another valid number of samples.

See [the user HIL directory](../.github/user/hil/README.md) for column examples.
All values are validated before selection or programming starts. Invalid data,
missing files, unsupported sensor encodings, ambiguous inventory names or an
overlong CSV fail without sending values or proceeding to MCU upload.

## Configure HIL sequence

1. Read `HIL_SENSOR_NAME` and load the corresponding physical-value CSV.
2. Find exactly one matching inventory sensor for the owned booking.
3. Save that single sensor, replacing another HIL selection if necessary.
   An existing single-sensor selection keeps its configuration ID.
4. Request preparation of the approved HIL image. A valid stored image can
   be reused; the client never selects an arbitrary local image to program.
5. Wait up to 180 seconds for the existing preparation API to return
   `status=okay`. Like the frontend, this uses successful programming and
   activation as readiness confirmation. CSV transmission starts only afterward.
6. Convert the CSV values exactly as the frontend does and send consecutive
   batches of up to 128 words. Every batch must return explicit success;
   the backend verifies readback. Stop on the first failure without retries.

The existing preparation API waits for programming and activation to succeed;
there is no separate activation-status polling request. The client requires
its explicit success response within one absolute three-minute deadline. This
is the same readiness confirmation the frontend uses, not an independent
sensor-health probe. A client timeout does not undo an already accepted server
operation, but it prevents CSV transmission and the following Upload step.

The step uploads `artifacts/hil-configuration.json` as `ecw-hil-<run-id>` even
on failure. The report includes the selected sensor, CSV name, sample/word
counts, configuration ID, readiness and sent-word count. It contains no API key.

## Existing frontend APIs

The integration reuses the frontend's existing routes. No backend change or
new route is required:

| Request | Purpose |
| --- | --- |
| `GET /v1/peripherals-list?booking_id=...` | Available HIL sensor names. |
| `GET /v1/peripherals?booking_id=...` | Saved sensor and configuration IDs. |
| `PUT /v1/peripherals` | Save one HIL sensor using the booking selection contract. |
| `POST /v1/peripheral-prepare` | Program or reuse and activate the approved HIL image; wait for success. |
| `POST /v1/peripheral-program-value` | Write converted CSV values with verified readback. |

The last two routes take `booking_id` and `configuration_id`. All requests
use the existing `ECW_API_KEY` secret; the runner never opens the board's
serial port directly. There is no extra status endpoint or new API naming.

## Trigger mode

The workflow files are on `delelop_2_stages`. Follow
[the two-stage setup guide](07-trigger-mode.md) to copy them into the default
branch of the repository that will run them.

Where the optional trigger workflows are present, Stage 1 still only builds,
reserves and registers the activation trigger. Stage 2 claims its unique run,
then runs Configure HIL before Upload. It reads the same repository variables
and the CSV at Stage 1's built commit. A duplicate dispatch that loses the
claim does not configure HIL, upload, flash, test or release the booking.

The claim winner retains its Release cleanup even when Configure HIL fails.
Start a new Stage 1 build after adopting these helpers; old queued builds do
not gain new scripts retroactively.
