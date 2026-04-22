# ESP32 Live Temperature Monitor

Real-time temperature measurement with a **DS18B20** sensor on the **Adafruit HUZZAH32 (ESP32 Feather)**. Readings are displayed on a 16x2 LCD and streamed over Wi-Fi (TCP) to a Python plotter with EMA smoothing, linear trend and outlier filtering.

---

## Features

- Wi-Fi TCP stream — sends `T=xx.xx\n` every second
- 16x2 LCD display — current temperature and device IP
- Python live plotter — EMA, rolling trend, R2
- Signal processing — 5-sample median filter + outlier guard
- Auto-reconnect — ESP32 restarts on Wi-Fi timeout
- USB or Wi-Fi — Python script supports both Serial and TCP

---

## Hardware

- Adafruit HUZZAH32 (ESP32 Feather)
- DS18B20 1-Wire temperature sensor
- 16x2 LCD with I2C backpack (address 0x27 or 0x3F)
- 4.7 kOhm resistor (pull-up for 1-Wire bus)

---

## Wiring

```
DS18B20
  VCC  -------- 3V3
  GND  -------- GND
  DQ   --+----- GPIO 21
         +---- [4.7kOhm] -- 3V3

LCD (I2C)
  VCC  -------- 5V
  GND  -------- GND
  SDA  -------- GPIO 23
  SCL  -------- GPIO 22
```

> If your LCD shows nothing, change `LCD_ADDR` from `0x27` to `0x3F`.

---

## Getting Started

### 1. Clone
```bash
git clone https://github.com/your-username/esp32-ds18b20-live-monitor.git
cd esp32-ds18b20-live-monitor
```

### 2. Wi-Fi credentials
```bash
cp src/secrets.h.example src/secrets.h
```
Edit `src/secrets.h`:
```cpp
#define WIFI_SSID "your_network"
#define WIFI_PASS "your_password"
```
> `secrets.h` is in `.gitignore` and will never be committed.

### 3. Flash (PlatformIO)
```bash
pio run --target upload
```

### 4. Python dependencies
```bash
pip install pyserial matplotlib numpy
```

### 5. Run the plotter
```bash
# Wi-Fi (recommended)
python esp32_live_plot.py --tcp 192.168.1.42:3333

# USB serial
python esp32_live_plot.py --port COM3
python esp32_live_plot.py --port /dev/ttyUSB0

# List ports
python esp32_live_plot.py --list-ports
```

---

## Plotter Options

| Argument | Default | Description |
|---|---|---|
| `--tcp HOST:PORT` | - | Wi-Fi TCP mode |
| `--port PORT` | - | USB serial mode |
| `--baud BAUD` | 115200 | Serial baud rate |
| `--interval SEC` | 5 | Chart refresh interval |
| `--window SEC` | 300 | Trend window |
| `--ema-tau SEC` | 30 | EMA time constant (0 = off) |
| `--max-points N` | 5000 | Max samples in memory |

---

## TCP Protocol

```
T=23.56
T=23.57
T=nan        <- sensor error
```

---

## License

MIT
