# FlagSense demo instructions

These instructions cover the offline dashboard demo, terminal replays, and the optional ESP32 display. Run Python commands from the repository root unless a step says to change directories.

## 1. Get the project

If the repository is not already on your computer:

```sh
git clone https://github.com/Ericdmch/formula_telemetry_display.git
cd formula_telemetry_display
```

If you already have the repository, open a terminal in its root folder. You can confirm you are in the right place with:

```sh
ls README.md app.py requirements.txt
```

## 2. Install the Python environment

Use Python 3.11 or newer. Create and activate a virtual environment, then install the project dependencies.

### macOS or Linux

```sh
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The dashboard, sample telemetry, track, and model are local. After the dependencies are installed, the standard demo runs without a network connection. No `.env` file or API key is needed; select an optional serial port in the dashboard itself.

## 3. Start the dashboard

With the virtual environment active and the terminal at the repository root:

```sh
streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`. The default **Synthetic Demo** is a 20-second prerecorded replay. Select **Start Demo**, then use **Pause**, **Reset**, and the speed selector to repeat it. It progresses from GREEN through YELLOW to a SAFETY CAR recommendation as the stopped car and approaching traffic appear.

Use the scenario selector to switch to one of the bundled historical replays:

- 2024 Azerbaijan — Pérez/Sainz
- 2021 Azerbaijan — Verstappen
- 2022 Canada — Tsunoda
- 2024 Qatar — mirror debris

The bundled historical scenarios work offline. They show documented race-control actions separately from FlagSense recommendations, and clearly label simulated fallback motion.

To stop Streamlit, press **Ctrl+C** in its terminal. To leave the virtual environment, run `deactivate` (macOS/Linux) or close the PowerShell window.

## 4. Run a replay in the terminal

For a text-only synthetic replay:

```sh
python -m scripts.run_demo
```

For a text timeline from a historical scenario:

```sh
python scripts/run_historical.py --scenario 2024_azerbaijan_perez_sainz
```

Other scenario IDs are `2021_azerbaijan_verstappen`, `2022_canada_tsunoda`, and `2024_qatar_mirror_debris`. Add `--write-derived` to save the pipeline output alongside the selected local scenario data.

## 5. Optional historical feed preparation

The dashboard does not fetch data. If you want to prepare measured FastF1 speed samples for the two Azerbaijan scenarios, install the optional dependency and run these commands while online:

```sh
python -m pip install -r requirements-historical.txt
python scripts/fetch_historical_scenarios.py --scenario 2024_azerbaijan_perez_sainz
python scripts/fetch_historical_scenarios.py --scenario 2021_azerbaijan_verstappen
```

This creates local cache files that Git ignores because redistribution rights are not established. It is optional; the bundled simulated replays remain available. To regenerate the bundled simulated fallback caches locally:

```sh
python scripts/build_scenario_cache.py --scenario all
```

## 6. Optional ESP32 display

The hardware display is optional. The app works without it. Firmware targets an ESP32-S3-DevKitC-1 N16R8 with an LCD1602A and a WS2812/NeoPixel ring. Check [firmware/README.md](firmware/README.md) for the wiring, supported board revisions, and display behavior before connecting hardware.

Install PlatformIO Core and connect the board by USB. From the repository root, build and upload the firmware:

```sh
cd firmware
pio device list
pio run
pio run -t upload
```

If more than one upload port is available, specify the board's port:

```sh
pio run -t upload --upload-port /dev/cu.usbmodemXXXX
```

Use the appropriate port shown by `pio device list` (for example, `COM3` on Windows). To inspect firmware messages manually:

```sh
pio device monitor -b 115200 --port /dev/cu.usbmodemXXXX
```

In a second terminal, return to the repository root, activate `.venv`, and start the dashboard with `streamlit run app.py`. Expand **Driver display (ESP32)**, scan for devices, select the serial port, and choose **Connect**. The panel shows connection state and device messages. Close the PlatformIO serial monitor before connecting from the dashboard because only one program can own the USB serial port at a time.

To build and run the hardware-independent firmware parser/framer test from the repository root:

```sh
c++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include \
  firmware/src/SerialProtocol.cpp firmware/src/StateMachine.cpp \
  firmware/test/native/test_parser.cpp -o /tmp/flagsense_parser_test
/tmp/flagsense_parser_test
```

## 7. Optional developer commands

Run the Python test suite:

```sh
python -m pytest
```

Rebuild the generated training set, model, and synthetic demo telemetry in order:

```sh
python -m scripts.generate_training_data
python -m scripts.train_model
python -m scripts.generate_demo_race
```

The generated artifacts replace the corresponding local model and demo inputs.
