# HIL values used before MCU firmware upload

Set the repository variable `HIL_SENSOR_NAME` to the exact sensor name from
ECW, for example `BME280`, `ADXL345`, `MCP3565R`, or `Pmod MIC3` (use `MIC3`
if that is its inventory name). Leave it blank to skip HIL configuration.

CSV files use the same physical-value format as the frontend's table export.
The provided examples each contain 100 samples. Replace the values or export
your own table from the frontend; the sample count comes from the CSV rows.

| Sensor | Default CSV | Columns after optional `sample` |
| --- | --- | --- |
| BME280 | `bme280.csv` | `temperature_c,humidity_pct,pressure_hpa` |
| ADXL345 | `adxl345.csv` | `x_g,y_g,z_g` |
| MCP3565R | `mcp3565r.csv` | `voltage_v` |
| Pmod MIC3 / MIC3 | `pmod_mic3.csv` | `voltage_v` |

For another filename, set `HIL_CSV_FILE` to a path relative to this directory,
for example `scenarios/warm_room.csv`. Files outside this directory are rejected.

Example BME280 CSV, directly compatible with the frontend:

```csv
sample,temperature_c,humidity_pct,pressure_hpa
0,25,50,1013.25
1,26,55,1010
```

The importer accepts reordered named columns, frontend column aliases,
comma/semicolon/tab delimiters, quoted decimal commas and an optional sample
column. Sample labels do not choose device addresses: row order determines
consecutive sample positions, just as in the frontend. Empty channel cells
become zero words on send; values outside the sensor's frontend range fail.
Overlong files fail rather than silently dropping samples.

The Configure HIL step validates the entire CSV before changing the selected
sensor. It then saves one sensor, programs or reuses its approved image, waits
for programming and activation to succeed within three minutes, and sends the converted values
with readback verification. A failure prevents the Upload step from running.

The following Upload step performs two explicit MCU operations in order:
upload the built firmware to storage, then flash that stored firmware. HIL
configuration and CSV sending finish before either operation starts.
