# PDS UNRaf - TP2: Recreación de Señales por Streaming DAC en ESP32

Sistema de instrumentación y procesamiento digital de señales para la recreación analógica de señales arbitrarias (senoidal, triangular, cuadrada) en tiempo real mediante streaming serie desde PC hacia un microcontrolador ESP32.

Desarrollado para la cátedra de **Procesamiento Digital de Señales (PDS)** - Universidad Nacional de Rafaela (UNRaf).

---

## 🏛️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│ 1. PC: app_generator.py (Tkinter + PySerial)                │
│    - Cálculo matemático de muestras discretizadas x[n]      │
│    - Cuantización a 8 bits: sample in [0, 255]              │
│    - Cadencia temporal de streaming: Ts = 1 / Fs            │
└──────────────────────────────┬──────────────────────────────┘
                               │ UART0 (115200 bps, 8N1)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. ESP32 UART RX FIFO (Hardware)                            │
│    - Interrupción inmediata (rxfifo_full_thresh = 1)        │
│    - Latencia de entrega mínima (rx_timeout_thresh = 1)     │
└──────────────────────────────┬──────────────────────────────┘
                               │ FreeRTOS Core 1 (dac_stream_task)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Firmware ESP-IDF v5/v6 (main.c)                          │
│    - dac_oneshot_output_voltage(handle, sample_byte)        │
│    - Toggle testigo en GPIO 2 para análisis de jitter       │
└──────────────────────────────┬──────────────────────────────┘
                               │ R-2R Ladder interno
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Salidas Analógica y Digital (Osciloscopio)               │
│    - Canal 1 (DAC): GPIO 25 -> Retenedor ZOH (0 V a ~3.3 V) │
│    - Canal 2 (Testigo): GPIO 2 -> Señal cuadrada a fs / 2   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Características Principales

- **DAC One-Shot determinístico:** Conversión analógica muestra a muestra en **GPIO 25 (`DAC_CHAN_0`)** sin intermediación de PWM ni generador por coseno de hardware. Tiempo de respuesta de silicio: 7 a 11 µs.
- **Minimización de Latencia y Jitter Serie:** Reducción de los umbrales de interrupción de UART0 (`rxfifo_full_thresh = 1` y `rx_timeout_thresh = 1`) para evitar acumulación de bytes en buffers y asegurar entrega instantánea a la CPU.
- **Aislamiento en Core 1:** Tarea FreeRTOS dedicada fijada al núcleo 1 con prioridad máxima de aplicación, aislando el pipeline analógico de las tareas del sistema del Core 0.
- **Pin Testigo para Instrumentación (GPIO 2):** Conmutación (*toggle*) por cada byte recibido y convertido. Permite verificar en el osciloscopio:
  1. Que el 100% de las muestras enviadas por la PC se convierten en escalones ZOH.
  2. La frecuencia de muestreo efectiva ($f_{\text{GPIO2}} = f_s / 2$).
  3. El jitter temporal introducido por el sistema operativo emisor mediante persistencia infinita o histograma de flanco.
- **Aplicación de Escritorio con Análisis en Vivo:**
  - Formas de onda: Senoidal, Triangular y Cuadrada con control de offset y amplitud digital.
  - Cálculo en tiempo real de LSB ($V_{\text{ref}}/256$), bits efectivos (ENOB), límite de Nyquist y tasa máxima teórica UART.
  - Modo ráfaga (Prueba 5c): Envío de exactamente 1 período cerrado para conteo de escalones en osciloscopio vía *Single Trigger*.

---

## 📂 Estructura del Repositorio

```
PDS-DAC-App/
├── app_generator.py          # Aplicación GUI de escritorio (Python / Tkinter)
├── .gitignore                # Reglas de exclusión para Python y builds de ESP-IDF
├── README.md                 # Documentación técnica integral
└── firmware/                 # Proyecto de firmware ESP-IDF
    ├── CMakeLists.txt        # Configuración raíz de CMake
    ├── sdkconfig             # Parámetros del BSP para ESP32
    └── main/
        ├── CMakeLists.txt    # Registro de componentes y dependencias
        └── main.c            # Implementación en C de ultra-baja latencia
```

---

## 🛠️ Requisitos Previos

### Software
1. **Python 3.10+** con dependencias:
   ```bash
   pip install pyserial
   ```
2. **ESP-IDF v5.x / v6.x** configurado en el entorno de desarrollo (`idf.py`).

### Hardware
- Placa de desarrollo **ESP32 DevKit v1 / NodeMCU-32S** (chip ESP32-D0WDQ6 o equivalente).
- Cable Micro-USB o USB-C con soporte de datos.
- Osciloscopio digital o analizador lógico de al menos 2 canales.

---

## 🔌 Conexiones de Hardware

| Señal / Función | Pin ESP32 | Conexión en Osciloscopio |
|---|---|---|
| **Salida Analógica DAC** | **GPIO 25** | **Canal 1 (Sonda 1X)** |
| **Pin Testigo de Muestras** | **GPIO 2** | **Canal 2 (Trigger digital)** |
| **Referencia de Masa** | **GND** | **Pinzas de masa (GND)** |
| **Puerto Serie UART0** | **GPIO 3 (RX0)** | Conexión interna USB-Serie CP2102/CH340 |

---

## ⚡ Guía de Instalación y Puesta en Marcha

### 1. Compilación y Flasheo del Firmware

Abrir una consola con el entorno ESP-IDF activado:

```powershell
# Acceder a la carpeta del firmware
cd firmware

# (Opcional si es primera vez) Configurar target
idf.py set-target esp32

# Compilar y flashear al puerto COM de tu placa
idf.py -p COM8 flash monitor
```

> [!NOTE]
> Para salir del monitor serie de ESP-IDF presionar `Ctrl + ]`. Recuerda cerrar el monitor antes de abrir la aplicación Python para que el puerto no quede ocupado (`PermissionError`).

### 2. Ejecución de la Aplicación en PC

```powershell
# En la raíz del proyecto
python app_generator.py
```

1. Seleccionar el puerto COM correspondiente (ej. `COM8`) y verificar la velocidad (`115200` bps).
2. Seleccionar la forma de onda deseada y ajustar la frecuencia $f_0$ (ej. $10\text{ Hz}$) y la tasa de muestreo $f_s$ (ej. $1000\text{ muestras/s}$).
3. Hacer clic en **Iniciar Streaming** para transmisión continua.
4. Para realizar la **Prueba de Verificación 5c**, detener el streaming continuo y hacer clic en **Enviar 1 Período Exacto**. Configurar el osciloscopio en *Single Trigger* sobre el flanco de GPIO 2 para contar los escalones ZOH correspondientes a $N = f_s / f_0$.

---

## 📊 Especificaciones Técnicas y Ecuaciones

### Límite de Transferencia UART (Consigna 3a)
Para una trama UART estándar 8N1 (1 start + 8 datos + 1 stop = 10 bits por byte):
$$f_{s,\max} = \frac{\text{Baudrate}}{10 \times \text{Bytes por muestra}} = \frac{115200}{10 \times 1} = 11520\text{ muestras/seg}$$
A $f_s = 1000\text{ Hz}$, la utilización del canal serie es de apenas el **8.68%**, garantizando que el streaming no se degrade por saturación del enlace serie.

### Resolución de Tensión LSB (Consigna 2b)
$$V_{\text{LSB}} = \frac{V_{\text{ref}}}{2^n} = \frac{3.3\,\text{V}}{256} \approx 12.89\,\text{mV}$$

### Salida Analógica del DAC
$$V_{\text{out}}[n] = V_{\text{ref}} \cdot \frac{\text{muestra}[n]}{255}$$

---

## 📄 Licencia

Proyecto desarrollado bajo propósitos académicos para la cátedra de PDS - UNRaf. Libre uso para fines educativos.
