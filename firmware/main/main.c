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
#include "driver/dac_oneshot.h"
#include "esp_log.h"
#include "esp_err.h"

#define TAG "DAC_STREAMER"

/* Configuracion de hardware */
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

void app_main(void)
{
    ESP_LOGI(TAG, "Iniciando Firmware PDS DAC Streamer...");
    init_dac();
}
