/**
 * @file main.c
 * @brief Firmware de recepcion de muestras serie y reproduccion DAC en tiempo real.
 *        Catedra de Procesamiento Digital de Senales (PDS) - UNRaf.
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

/* Configuraciones de hardware y comunicacion */
#define UART_PORT_NUM         UART_NUM_0
#define UART_BAUD_RATE        115200
#define UART_RX_BUF_SIZE      1024
#define UART_TX_BUF_SIZE      0

#define PROBE_GPIO_PIN        GPIO_NUM_2
#define DAC_OUTPUT_CHAN       DAC_CHAN_0  /* GPIO 25 en ESP32 */

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
 * @brief Configura el GPIO 2 como pin de prueba/trigger para osciloscopio o analizador logico.
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
    ESP_ERROR_CHECK(gpio_set_level(PROBE_GPIO_PIN, 0));
    ESP_LOGI(TAG, "Pin testigo configurado en GPIO %d.", PROBE_GPIO_PIN);
}

/**
 * @brief Inicializa el puerto UART0 para recepcion en streaming de ultra baja latencia.
 */
static void init_uart(void)
{
    const uart_config_t uart_config = {
        .baud_rate = UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .rx_flow_ctrl_thresh = 0,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(uart_driver_install(UART_PORT_NUM, UART_RX_BUF_SIZE, UART_TX_BUF_SIZE, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_PORT_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_PORT_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    /*
     * Reduccion critica de umbrales para eliminar latencia y jitter de recepcion:
     * - Threshold de FIFO llena a 1 byte (aviso inmediato por muestra).
     * - Timeout minimo de 1 tiempo de simbolo antes de descartar/entregar.
     */
    ESP_ERROR_CHECK(uart_set_rx_full_threshold(UART_PORT_NUM, 1));
    ESP_ERROR_CHECK(uart_set_rx_timeout(UART_PORT_NUM, 1));

    ESP_LOGI(TAG, "UART0 configurado a %d baudios (8N1, FIFO thresh = 1 byte).", UART_BAUD_RATE);
}

void app_main(void)
{
    ESP_LOGI(TAG, "Iniciando Firmware PDS DAC Streamer...");
    init_probe_gpio();
    init_dac();
    init_uart();
}
