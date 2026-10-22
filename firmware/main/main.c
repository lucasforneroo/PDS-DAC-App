/**
 * @file main.c
 * @brief Firmware de recepción de muestras serie y reproducción DAC en tiempo real.
 *        Cátedra de Procesamiento Digital de Señales (PDS) - UNRaf.
 *
 * @details
 * - DAC One-Shot: Canal 0 mapeado en GPIO 25 (8 bits, 0-255 -> 0V - ~3.3V).
 * - Pin testigo (Trigger / Jitter analysis): GPIO 2 conmutado (toggled) en cada muestra.
 * - UART0 (Consola / USB-Serie): 115200 baud, 8N1, sin flow control.
 * - Latencia ultrabaja: Umbrales FIFO configurados a 1 byte y timeout mínimo de 1 símbolo.
 * - Tarea FreeRTOS fija en Core 1 con prioridad alta para aislar el streaming del Core 0 (WiFi/BT/Sys).
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "driver/dac_oneshot.h"
#include "esp_log.h"
#include "esp_err.h"

#define TAG "DAC_STREAMER"

/* Configuraciones de hardware y comunicación */
#define UART_PORT_NUM         UART_NUM_0
#define UART_BAUD_RATE        115200
#define UART_RX_BUF_SIZE      1024
#define UART_TX_BUF_SIZE      0

#define PROBE_GPIO_PIN        GPIO_NUM_2
#define DAC_OUTPUT_CHAN       DAC_CHAN_0  /* GPIO 25 en ESP32 */

/* Prioridad y afinidad de la tarea de streaming */
#define STREAM_TASK_PRIORITY  (configMAX_PRIORITIES - 2)
#define STREAM_TASK_CORE_ID   1

static dac_oneshot_handle_t s_dac_handle = NULL;

/**
 * @brief Inicializa el canal 0 del DAC en modo One-Shot.
 */
static void init_dac(void)
{
    dac_oneshot_config_t dac_cfg = {
        .chan_id = DAC_OUTPUT_CHAN,
    };
    ESP_ERROR_CHECK(dac_oneshot_new_channel(&dac_cfg, &s_dac_handle));
    /* Inicializar en punto medio de escala (offset DC Vref/2 aprox 1.65V) */
    ESP_ERROR_CHECK(dac_oneshot_output_voltage(s_dac_handle, 128));
    ESP_LOGI(TAG, "DAC inicializado en GPIO 25 (DAC_CHAN_0) - Modo One-Shot.");
}

/**
 * @brief Configura el GPIO 2 como pin de prueba/trigger para osciloscopio o analizador lógico.
 */
static void init_probe_gpio(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << PROBE_GPIO_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));
    gpio_set_level(PROBE_GPIO_PIN, 0);
    ESP_LOGI(TAG, "Pin testigo de muestreo configurado en GPIO %d.", PROBE_GPIO_PIN);
}

/**
 * @brief Configura UART0 optimizado para recepción streaming de baja latencia.
 */
static void init_uart(void)
{
    uart_config_t uart_config = {
        .baud_rate = UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(uart_param_config(UART_PORT_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_PORT_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    /* Instalar driver UART con buffer circular en RAM */
    ESP_ERROR_CHECK(uart_driver_install(UART_PORT_NUM, UART_RX_BUF_SIZE, UART_TX_BUF_SIZE, 0, NULL, 0));

    /*
     * Optimización de latencia y jitter:
     * - Threshold de FIFO lleno a 1 byte: genera interrupción tan pronto entra un dato.
     * - Timeout threshold a 1 tiempo de símbolo: si no se llena la FIFO, expira al toque.
     */
    ESP_ERROR_CHECK(uart_set_rx_full_threshold(UART_PORT_NUM, 1));
    ESP_ERROR_CHECK(uart_set_rx_timeout(UART_PORT_NUM, 1));

    ESP_LOGI(TAG, "UART0 configurada a %d bps, 8N1, umbrales de minima latencia activos.", UART_BAUD_RATE);
}

/**
 * @brief Tarea de alta prioridad dedicada a procesar el stream serie y enviarlo al DAC.
 */
static void dac_stream_task(void *pvParameters)
{
    uint8_t rx_byte = 0;
    uint32_t pin_state = 0;

    ESP_LOGI(TAG, "Tarea de streaming DAC iniciada en Core %d con prioridad %d.",
             xPortGetCoreID(), uxTaskPriorityGet(NULL));

    while (1) {
        /*
         * Lectura bloqueante por interrupción:
         * Espera hasta 10 ticks si no hay datos entrantes.
         * Al usar bloqueo de FreeRTOS, el CPU cede tiempo si no hay tráfico,
         * evitando starvation y garantizando que el Task Watchdog Timer (TWDT)
         * del IDLE task no salte jamás.
         */
        int len = uart_read_bytes(UART_PORT_NUM, &rx_byte, 1, 10 / portTICK_PERIOD_MS);

        if (len > 0) {
            /* 1) Escribir muestra al DAC inmediatamente */
            dac_oneshot_output_voltage(s_dac_handle, rx_byte);

            /* 2) Toggle del pin testigo GPIO 2 */
            pin_state ^= 1;
            gpio_set_level(PROBE_GPIO_PIN, pin_state);
        }
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "=== Inicializando Sistema de Streaming DAC PDS ===");

    init_probe_gpio();
    init_dac();
    init_uart();

    /*
     * Crear la tarea fijada al Core 1 (Application CPU), dejando el Core 0 (Protocol CPU)
     * libre para tareas del sistema o red, eliminando contención y reduciendo jitter.
     */
    xTaskCreatePinnedToCore(
        dac_stream_task,
        "dac_stream_task",
        4096,
        NULL,
        STREAM_TASK_PRIORITY,
        NULL,
        STREAM_TASK_CORE_ID
    );

    ESP_LOGI(TAG, "Sistema listo para recibir muestras serie desde app_generator.py.");
}
