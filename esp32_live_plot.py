#!/usr/bin/env python3
# ESP32 Live Plotter — USB + (ready for Wi‑Fi TCP)
# Funkcje:
#  - EMA (Exponential Moving Average) z regulowaną stałą czasową (--ema-tau)
#  - Rolling linear trend z nachyleniem [°C/min] i R²
#  - Median filter (5 próbek) i prosty outlier guard na skoki danych
#
# Przykład:
#   python esp32_live_plot.py --port COM3 --interval 5 --window 90 --ema-tau 45
#   python esp32_live_plot.py --list-ports
#   python esp32_live_plot.py --tcp 192.168.4.1:3333
#
# Wymagane:
#   pip install pyserial matplotlib numpy

import argparse, re, sys, time, threading, queue, socket
from datetime import datetime
from collections import deque

import numpy as np
import matplotlib.pyplot as plt

# pyserial (opcjonalnie)
try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None

FLOAT_RE = re.compile(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?')

def list_serial_ports():
    if list_ports is None:
        print("pyserial nie jest zainstalowany.")
        return
    for p in list_ports.comports():
        desc = f"{p.device} — {p.description}"
        if getattr(p, "vid", None) and getattr(p, "pid", None):
            desc += f" (VID:PID={p.vid:04X}:{p.pid:04X})"
        print(desc)

def parse_float_from_line(line: str):
    m = FLOAT_RE.search(line)
    return float(m.group(0)) if m else None

def serial_reader(port, baud, out_q, stop_event):
    if serial is None:
        print("Brak pyserial. Zainstaluj: pip install pyserial", file=sys.stderr)
        return
    try:
        with serial.Serial(port, baudrate=baud, timeout=1) as ser:
            ser.reset_input_buffer()
            while not stop_event.is_set():
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode(errors='replace').strip()
                val = parse_float_from_line(line)
                if val is not None:
                    out_q.put((time.time(), val, line))
    except Exception as e:
        print(f"Nie mogę otworzyć portu {port} @ {baud}: {e}", file=sys.stderr)

def tcp_reader(host, port, out_q, stop_event):
    addr = (host, port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect(addr)
        sock.settimeout(1)
        buf = b""
        while not stop_event.is_set():
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    time.sleep(0.1); continue
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    s = line.decode(errors='replace').strip()
                    val = parse_float_from_line(s)
                    if val is not None:
                        out_q.put((time.time(), val, s))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[tcp] błąd: {e}", file=sys.stderr); time.sleep(0.2)
    except Exception as e:
        print(f"Nie można połączyć z {addr}: {e}", file=sys.stderr)
    finally:
        try: sock.close()
        except: pass

def ema_series(t_list, y_list, tau=30.0):
    """
    EMA o stałej czasowej tau [s]. Zwraca listę y_ema o tej samej długości.
    Adaptacyjne alpha = 1 - exp(-dt/tau) dla nieregularnych odstępów.
    """
    if not t_list:
        return []
    y_ema = []
    prev = y_list[0]
    prev_t = t_list[0]
    y_ema.append(prev)
    for i in range(1, len(t_list)):
        dt = max(1e-9, t_list[i] - prev_t)
        alpha = 1.0 - np.exp(-dt / max(1e-9, tau))
        prev = prev + alpha * (y_list[i] - prev)
        y_ema.append(prev)
        prev_t = t_list[i]
    return y_ema

def compute_trend(xs_time, ys, seconds_window):
    """
    Rolling regresja liniowa na ostatnim oknie czasowym.
    Zwraca: (trend_x, trend_y, slope_per_sec, r2)
    slope_per_sec w [°C/s]; pomnóż *60 dla °C/min.
    """
    if len(xs_time) < 2:
        return [], [], None, None
    t_now = xs_time[-1]
    idx = [i for i, t in enumerate(xs_time) if (t_now - t) <= seconds_window]
    if len(idx) < 2:
        return [], [], None, None

    t_slice = np.array([xs_time[i] for i in idx])
    y_slice = np.array([ys[i] for i in idx])
    t0 = t_slice[0]
    X = t_slice - t0

    try:
        slope, intercept = np.polyfit(X, y_slice, 1)
        y_fit = slope * X + intercept
        # R^2
        ss_res = np.sum((y_slice - y_fit)**2)
        ss_tot = np.sum((y_slice - np.mean(y_slice))**2) + 1e-12
        r2 = 1.0 - ss_res / ss_tot

        x_line = np.array([X[0], X[-1]])
        y_line = slope * x_line + intercept
        return [t_slice[0], t_slice[-1]], [y_line[0], y_line[-1]], slope, r2
    except Exception:
        return [], [], None, None

def main():
    ap = argparse.ArgumentParser(description="ESP32 live temperature plotter with EMA, trend, median filter")
    ap.add_argument("--port", help="Port szeregowy, np. COM3/COM5 lub /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200, help="Baud (domyślnie 115200)")
    ap.add_argument("--interval", type=float, default=5.0, help="Interwał odświeżania wykresu [s]")
    ap.add_argument("--window", type=float, default=300.0, help="Okno trendu [s]")
    ap.add_argument("--max-points", type=int, default=5000, help="Maks. próbek w pamięci")
    ap.add_argument("--ema-tau", type=float, default=30.0, help="Stała czasowa EMA τ [s] (0 = wyłącz EMA)")
    ap.add_argument("--list-ports", action="store_true", help="Wypisz dostępne porty i wyjdź")
    ap.add_argument("--tcp", help="Tryb TCP host:port (Wi‑Fi). Jeśli podane, ignoruje --port")
    args = ap.parse_args()

    if args.list_ports:
        list_serial_ports()
        return

    if (args.port is None) and (args.tcp is None):
        print("Podaj --port (USB) albo --tcp host:port (Wi‑Fi).", file=sys.stderr)
        sys.exit(2)

    q = queue.Queue()
    stop_event = threading.Event()

    if args.tcp:
        try:
            host, port_str = args.tcp.split(":", 1)
            port_num = int(port_str)
        except Exception:
            print("Zły format --tcp. Użyj host:port, np. 192.168.4.1:3333", file=sys.stderr)
            sys.exit(2)
        reader_thr = threading.Thread(target=tcp_reader, args=(host, port_num, q, stop_event), daemon=True)
    else:
        reader_thr = threading.Thread(target=serial_reader, args=(args.port, args.baud, q, stop_event), daemon=True)
    reader_thr.start()

    xs = deque(maxlen=args.max_points)   # czasy (epoch)
    ys = deque(maxlen=args.max_points)   # temperatury (po medianie/outlier guard)
    med_buf = deque(maxlen=5)            # bufor do mediany 5-próbkowej
    lines_seen = 0

    plt.ion()
    fig = plt.figure("ESP32 Live Temperature")
    ax = plt.gca()
    temp_line, = ax.plot([], [], label="Temperature")
    trend_line, = ax.plot([], [], linestyle="--", label=f"Trend (last {int(args.window)} s)")
    if args.ema_tau > 0:
        ema_line, = ax.plot([], [], label=f"EMA (τ={int(args.ema_tau)} s)")
    else:
        ema_line = None
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature")
    ax.legend(loc="best")
    fig.show()
    ax.grid(True)

    try:
        last_draw = 0.0
        while True:
            # pobierz wszystkie dostępne próbki z kolejki
            try:
                while True:
                    t_epoch, temp_raw, raw_line = q.get_nowait()

                    # === MEDIAN FILTER (5 próbek) ===
                    med_buf.append(temp_raw)
                    filtered = float(np.median(med_buf))

                    # === OUTLIER GUARD ===
                    # odrzuć nagły skok >2°C w krótkim czasie (np. <2.5 s)
                    if len(xs) >= 1:
                        dt = max(1e-9, t_epoch - xs[-1])
                        jump = abs(filtered - ys[-1])
                        if dt < 2.5 and jump > 2.0:
                            # odrzucamy tę próbkę jako anomalię
                            continue

                    # zapisujemy próbkę (po medianie i guardzie)
                    xs.append(t_epoch)
                    ys.append(filtered)
                    lines_seen += 1
            except queue.Empty:
                pass

            # odświeżenie wykresu co args.interval
            now = time.time()
            if (now - last_draw) >= args.interval and len(xs) >= 1:
                last_draw = now
                x_np = np.array(xs); y_np = np.array(ys)
                temp_line.set_data(x_np, y_np)

                # Trend: nachylenie i R^2 (okno args.window)
                tx, ty, slope_sec, r2 = compute_trend(list(xs), list(ys), args.window)
                trend_line.set_data(tx, ty)
                slope_min = slope_sec * 60.0 if slope_sec is not None else None
                r2_txt = f"{r2:.2f}" if r2 is not None else "–"
                slope_txt = f"{slope_min:+.3f} °C/min" if slope_min is not None else "–"

                # EMA (na przefiltrowanych danych)
                if ema_line is not None and args.ema_tau > 0:
                    y_ema = ema_series(list(xs), list(ys), tau=args.ema_tau)
                    ema_line.set_data(np.array(xs), np.array(y_ema))

                # skale i podpisy
                ax.relim(); ax.autoscale_view()
                latest_iso = datetime.fromtimestamp(xs[-1]).strftime("%H:%M:%S")
                ax.set_title(
                    f"Samples: {lines_seen} | Latest: {ys[-1]:.2f} at {latest_iso} | "
                    f"Trend: {slope_txt}, R²={r2_txt}"
                )

                # format czasu na osi X
                ticks = ax.get_xticks()
                tick_labels = [datetime.fromtimestamp(t).strftime("%H:%M:%S") if t>0 else "" for t in ticks]
                ax.set_xticklabels(tick_labels, rotation=30, ha="right")

                fig.canvas.draw(); fig.canvas.flush_events()

            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStop.")
    finally:
        stop_event.set()
        try: reader_thr.join(timeout=1.0)
        except: pass

if __name__ == "__main__":
    main()
