import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import math

class SignalStreamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDS UNRaf - TP2: Recreación de Señales por Streaming")
        self.root.geometry("980x760")
        self.root.resizable(True, True)

        # Estado de conexión y streaming
        self.ser = None
        self.is_streaming = False
        self.stream_thread = None

        # Variables de configuración de señal
        self.waveform = tk.StringVar(value="Senoidal")
        self.freq = tk.DoubleVar(value=10.0)          # Frecuencia de la señal (Hz)
        self.fs = tk.DoubleVar(value=1000.0)          # Tasa de envío de muestras (muestras/seg)
        self.amplitude = tk.DoubleVar(value=100.0)    # Amplitud digital (%)
        self.dac_bits = tk.IntVar(value=8)            # 8 bits (1 byte) o 12 bits (2 bytes)
        self.v_ref = tk.DoubleVar(value=3.3)          # Tensión de referencia del DAC (V)
        self.baudrate = tk.IntVar(value=115200)

        # Métricas en vivo
        self.samples_sent = 0

        self._build_ui()
        self._update_metrics()
        self._draw_preview()

    def _build_ui(self):
        # --- 1. PANEL DE CONEXIÓN SERIE (Consigna 1b y 3) ---
        conn_frame = ttk.LabelFrame(self.root, text=" 1. Configuración de Puerto COM y DAC ", padding=10)
        conn_frame.pack(fill="x", padx=12, pady=6)

        ttk.Label(conn_frame, text="Puerto COM:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.port_combo = ttk.Combobox(conn_frame, width=15, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=5, pady=2)
        self._refresh_ports()

        ttk.Button(conn_frame, text="↻", width=3, command=self._refresh_ports).grid(row=0, column=2, padx=2)

        ttk.Label(conn_frame, text="Baudrate:").grid(row=0, column=3, padx=5, pady=2, sticky="w")
        baud_combo = ttk.Combobox(conn_frame, textvariable=self.baudrate, values=[9600, 57600, 115200, 230400, 460800, 921600], width=10, state="readonly")
        baud_combo.grid(row=0, column=4, padx=5, pady=2)
        baud_combo.bind("<<ComboboxSelected>>", lambda e: self._update_metrics())

        ttk.Label(conn_frame, text="Resolución DAC:").grid(row=0, column=5, padx=5, pady=2, sticky="w")
        bits_combo = ttk.Combobox(conn_frame, textvariable=self.dac_bits, values=[8, 12], width=5, state="readonly")
        bits_combo.grid(row=0, column=6, padx=5, pady=2)
        bits_combo.bind("<<ComboboxSelected>>", lambda e: [self._update_metrics(), self._draw_preview()])

        ttk.Label(conn_frame, text="Vref (V):").grid(row=0, column=7, padx=5, pady=2, sticky="w")
        vref_entry = ttk.Entry(conn_frame, textvariable=self.v_ref, width=6)
        vref_entry.grid(row=0, column=8, padx=5, pady=2)
        vref_entry.bind("<KeyRelease>", lambda e: self._update_metrics())

        self.btn_connect = ttk.Button(conn_frame, text="Iniciar Streaming", command=self.toggle_streaming)
        self.btn_connect.grid(row=0, column=9, padx=10, pady=2)

        # --- 2. PANEL DE PARÁMETROS DE SEÑAL (Consigna 4) ---
        ctrl_frame = ttk.LabelFrame(self.root, text=" 2. Control de Señal en Tiempo Real (Consigna 4) ", padding=10)
        ctrl_frame.pack(fill="x", padx=12, pady=6)

        # Forma de onda
        ttk.Label(ctrl_frame, text="Forma de Onda:").grid(row=0, column=0, sticky="w", pady=4)
        wave_frame = ttk.Frame(ctrl_frame)
        wave_frame.grid(row=0, column=1, columnspan=2, sticky="w")
        for w in ["Senoidal", "Triangular", "Cuadrada"]:
            ttk.Radiobutton(wave_frame, text=w, variable=self.waveform, value=w, command=self._draw_preview).pack(side="left", padx=8)

        # Frecuencia de muestreo (fs)
        ttk.Label(ctrl_frame, text="Tasa de envío fs (muestras/s):").grid(row=1, column=0, sticky="w", pady=4)
        self.fs_scale = ttk.Scale(ctrl_frame, from_=50, to=5000, variable=self.fs, orient="horizontal", length=360, command=lambda e: self._on_param_change())
        self.fs_scale.grid(row=1, column=1, padx=8)
        self.lbl_fs = ttk.Label(ctrl_frame, text="1000.0 Hz", width=14)
        self.lbl_fs.grid(row=1, column=2, sticky="w")

        # Frecuencia de la señal (f0)
        ttk.Label(ctrl_frame, text="Frecuencia de Señal f0 (Hz):").grid(row=2, column=0, sticky="w", pady=4)
        self.f_scale = ttk.Scale(ctrl_frame, from_=0.5, to=250.0, variable=self.freq, orient="horizontal", length=360, command=lambda e: self._on_param_change())
        self.f_scale.grid(row=2, column=1, padx=8)
        self.lbl_f = ttk.Label(ctrl_frame, text="10.00 Hz", width=14)
        self.lbl_f.grid(row=2, column=2, sticky="w")

        # Amplitud (Consigna 4c)
        ttk.Label(ctrl_frame, text="Amplitud Digital (Consigna 4c):").grid(row=3, column=0, sticky="w", pady=4)
        self.amp_scale = ttk.Scale(ctrl_frame, from_=5.0, to=100.0, variable=self.amplitude, orient="horizontal", length=360, command=lambda e: self._on_param_change())
        self.amp_scale.grid(row=3, column=1, padx=8)
        self.lbl_amp = ttk.Label(ctrl_frame, text="100.0 %", width=14)
        self.lbl_amp.grid(row=3, column=2, sticky="w")

        # --- 3. PANEL DE MÉTRICAS Y CÁLCULOS PARA EL INFORME ---
        metrics_frame = ttk.LabelFrame(self.root, text=" 3. Cálculos del Sistema en Vivo (Para responder Consignas 2, 3, 4 y 5) ", padding=10)
        metrics_frame.pack(fill="x", padx=12, pady=6)

        self.lbl_metrics_left = ttk.Label(metrics_frame, text="", justify="left", font=("Consolas", 9))
        self.lbl_metrics_left.grid(row=0, column=0, sticky="nw", padx=10)

        self.lbl_metrics_right = ttk.Label(metrics_frame, text="", justify="left", font=("Consolas", 9))
        self.lbl_metrics_right.grid(row=0, column=1, sticky="nw", padx=20)

        # --- 4. PREVISUALIZACIÓN DE CUANTIZACIÓN Y ESCALONES (Consigna 5b) ---
        preview_frame = ttk.LabelFrame(self.root, text=" 4. Previsualización de 1 Período (Escalones de Cuantización y Retención ZOH) ", padding=8)
        preview_frame.pack(fill="both", expand=True, padx=12, pady=6)

        self.canvas = tk.Canvas(preview_frame, bg="#1e1e1e", height=180)
        self.canvas.pack(fill="both", expand=True)

        # --- 5. BARRA DE ESTADO Y PRUEBA DE INTEGRIDAD (Consigna 5c) ---
        status_frame = ttk.Frame(self.root, padding=6)
        status_frame.pack(fill="x", padx=12)

        self.lbl_status = ttk.Label(status_frame, text="Estado: Detenido | Muestras enviadas: 0", font=("Arial", 9, "bold"))
        self.lbl_status.pack(side="left")

        ttk.Button(status_frame, text="Enviar 1 Período Exacto (Prueba 5c)", command=self.send_single_period_test).pack(side="right", padx=5)

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports:
            self.port_combo.current(0)

    def _on_param_change(self):
        self._update_metrics()
        self._draw_preview()

    def _calculate_sample(self, phase, wave_type, amp_factor, max_dac_val):
        """Calcula una muestra normalizada [-1, 1] y la escala al rango del DAC."""
        if wave_type == "Senoidal":
            raw = math.sin(phase)
        elif wave_type == "Cuadrada":
            raw = 1.0 if (phase % (2 * math.pi)) < math.pi else -1.0
        elif wave_type == "Triangular":
            norm_p = (phase % (2 * math.pi)) / (2 * math.pi)
            raw = 4.0 * norm_p - 1.0 if norm_p < 0.5 else 3.0 - 4.0 * norm_p
        else:
            raw = 0.0

        # Escalar por amplitud centrada en Vref/2 (mitad del rango del DAC)
        mid = max_dac_val / 2.0
        val = int(round(mid + (raw * mid * amp_factor)))
        return max(0, min(max_dac_val, val))

    def _update_metrics(self):
        bits = self.dac_bits.get()
        levels = (2 ** bits)
        max_val = levels - 1
        try:
            vref = float(self.v_ref.get())
        except ValueError:
            vref = 3.3

        lsb_mv = (vref / max_val) * 1000.0
        baud = self.baudrate.get()
        bytes_per_sample = 1 if bits == 8 else 2
        # 10 bits de trama UART (1 start + 8 datos + 1 stop) por cada byte enviado
        max_uart_fs = baud / (10.0 * bytes_per_sample)

        fs_val = round(self.fs.get(), 1)
        f0_val = round(self.freq.get(), 2)
        amp_pct = round(self.amplitude.get(), 1)

        self.lbl_fs.config(text=f"{fs_val} m/s")
        self.lbl_f.config(text=f"{f0_val} Hz (Paso: 0.1 Hz)")
        self.lbl_amp.config(text=f"{amp_pct} %")

        samples_per_period = fs_val / f0_val if f0_val > 0 else 0
        ts_ms = (1000.0 / fs_val) if fs_val > 0 else 0

        # Consigna 4c: Resolución efectiva al escalar digitalmente
        used_levels = max(1, int(round(max_val * (amp_pct / 100.0))))
        effective_bits = math.log2(used_levels + 1)
        vpp_expected = vref * (amp_pct / 100.0)

        left_text = (
            f"• Resolución DAC (2b): {bits} bits ({levels} niveles) | 1 LSB = {lsb_mv:.2f} mV\n"
            f"• Límite teórico UART (3a): {max_uart_fs:.0f} muestras/s (@ {baud} bps)\n"
            f"• Frec. máx Nyquist (f < fs/2): {fs_val/2:.1f} Hz | Práctica (>=10 m/per): {fs_val/10:.1f} Hz\n"
            f"• Muestras por período (5b/5d): {samples_per_period:.1f} muestras/ciclo (Ts = {ts_ms:.2f} ms)"
        )
        right_text = (
            f"• Escalado de Amplitud (4c): Usa {used_levels + 1} de {levels} niveles\n"
            f"• Resolución Efectiva (4c): {effective_bits:.2f} bits efectivos\n"
            f"• Salida esperada (5a): Vpp ≈ {vpp_expected:.2f} V | Vdc ≈ {vref/2:.2f} V\n"
            f"• Rango Frecuencia (4b): 0.5 Hz a {min(250.0, fs_val/4):.1f} Hz"
        )
        self.lbl_metrics_left.config(text=left_text)
        self.lbl_metrics_right.config(text=right_text)

    def _draw_preview(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 760
        h = self.canvas.winfo_height() or 180
        pad = 20

        bits = self.dac_bits.get()
        max_val = (2 ** bits) - 1
        amp_factor = self.amplitude.get() / 100.0
        wave = self.waveform.get()
        n_samples = max(2, min(200, int(round(self.fs.get() / max(0.5, self.freq.get())))))

        # Línea central (Nivel de continua Vref/2)
        mid_y = h / 2
        self.canvas.create_line(pad, mid_y, w - pad, mid_y, fill="#444444", dash=(4, 2))

        # Dibujar escalones ZOH (Zero-Order Hold) como se verá en el osciloscopio
        dx = (w - 2 * pad) / n_samples
        prev_x, prev_y = None, None

        for i in range(n_samples + 1):
            phase = (2 * math.pi * i) / n_samples
            dac_val = self._calculate_sample(phase, wave, amp_factor, max_val)
            norm_y = dac_val / max_val
            x = pad + i * dx
            y = (h - pad) - norm_y * (h - 2 * pad)

            if prev_x is not None:
                # Escalón horizontal (retención de muestra) y vertical (cambio de muestra)
                self.canvas.create_line(prev_x, prev_y, x, prev_y, fill="#00e676", width=2)
                self.canvas.create_line(x, prev_y, x, y, fill="#00e676", width=2)
            prev_x, prev_y = x, y

    def _pack_sample(self, dac_val, bits):
        """Empaqueta la muestra: 1 byte para 8 bits, 2 bytes sincronizados para 12 bits."""
        if bits == 8:
            return bytes([dac_val & 0xFF])
        else:
            # Protocolo de 2 bytes con bit de sincronismo para 12 bits:
            # Byte alto: 0b10dddddd (bit 7 = 1 indica primer byte, contiene bits 11..6)
            # Byte bajo: 0b00dddddd (bit 7 = 0 indica segundo byte, contiene bits 5..0)
            b_high = 0x80 | ((dac_val >> 6) & 0x3F)
            b_low = dac_val & 0x3F
            return bytes([b_high, b_low])

    def _stream_worker(self):
        phase = 0.0
        next_call = time.perf_counter()

        while self.is_streaming and self.ser and self.ser.is_open:
            fs_curr = self.fs.get()
            f0_curr = self.freq.get()
            amp_factor = self.amplitude.get() / 100.0
            bits = self.dac_bits.get()
            max_val = (2 ** bits) - 1
            wave = self.waveform.get()

            dt = 1.0 / fs_curr
            d_phase = 2.0 * math.pi * f0_curr * dt

            sample = self._calculate_sample(phase, wave, amp_factor, max_val)
            phase = (phase + d_phase) % (2.0 * math.pi)

            try:
                self.ser.write(self._pack_sample(sample, bits))
                self.samples_sent += 1
            except Exception as e:
                print(f"Error en puerto serie: {e}")
                break

            # Control de tiempo de alta precisión para minimizar el jitter en PC
            next_call += dt
            sleep_time = next_call - time.perf_counter()
            if sleep_time > 0.002:
                time.sleep(sleep_time - 0.001)
            while time.perf_counter() < next_call:
                pass

    def toggle_streaming(self):
        if not self.is_streaming:
            port = self.port_combo.get()
            if not port:
                messagebox.showwarning("Puerto faltante", "Seleccioná un puerto COM válido.")
                return
            try:
                self.ser = serial.Serial(port, self.baudrate.get(), timeout=0)
                self.is_streaming = True
                self.samples_sent = 0
                self.btn_connect.config(text="Detener Streaming")
                self.stream_thread = threading.Thread(target=self._stream_worker, daemon=True)
                self.stream_thread.start()
                self._update_status_loop()
            except Exception as e:
                messagebox.showerror("Error al abrir puerto COM", str(e))
        else:
            self.is_streaming = False
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.btn_connect.config(text="Iniciar Streaming")
            self.lbl_status.config(text=f"Estado: Detenido | Total muestras enviadas: {self.samples_sent}")

    def send_single_period_test(self):
        """Consigna 5c: Envía exactamente 1 período de muestras y vuelve a cero para contar escalones en el osciloscopio."""
        if self.is_streaming:
            messagebox.showinfo("Streaming activo", "Detené el streaming continuo antes de enviar la ráfaga de prueba.")
            return
        port = self.port_combo.get()
        if not port:
            messagebox.showwarning("Puerto faltante", "Seleccioná un puerto COM válido.")
            return
        try:
            with serial.Serial(port, self.baudrate.get(), timeout=0) as ser:
                time.sleep(0.1)
                n_samples = int(round(self.fs.get() / self.freq.get()))
                dt = 1.0 / self.fs.get()
                bits = self.dac_bits.get()
                max_val = (2 ** bits) - 1
                amp = self.amplitude.get() / 100.0
                wave = self.waveform.get()

                for i in range(n_samples):
                    phase = (2.0 * math.pi * i) / n_samples
                    val = self._calculate_sample(phase, wave, amp, max_val)
                    ser.write(self._pack_sample(val, bits))
                    time.sleep(dt)

                # Muestra final en 0 para marcar fin de ráfaga
                ser.write(self._pack_sample(0, bits))
                messagebox.showinfo(
                    "Prueba 5c Completada",
                    f"Se enviaron exactamente {n_samples} muestras (1 período completo).\n"
                    f"Configurá el osciloscopio en modo 'Single Trigger' para contar los {n_samples} escalones."
                )
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _update_status_loop(self):
        if self.is_streaming:
            self.lbl_status.config(text=f"Estado: TRANSMITIENDO EN VIVO | Muestras enviadas: {self.samples_sent}")
            self.root.after(200, self._update_status_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = SignalStreamerApp(root)
    root.mainloop()
