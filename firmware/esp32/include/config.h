#pragma once

// Pin mappings for ESP32 DevKitC
#define PIN_MOTOR_PWM_A     18
#define PIN_MOTOR_PWM_B     19
#define PIN_ENCODER_A       4
#define PIN_ENCODER_B       5
#define PIN_ENCODER_Z       16
#define PIN_CURRENT_SENSE   34
#define PIN_TEMP_SENSE      35
#define PIN_CAN_TX          22
#define PIN_CAN_RX          23
#define PIN_RS485_TX        17
#define PIN_RS485_RX        15
#define PIN_RS485_DE_RE     21
#define PIN_ETHERCAT_TX     22
#define PIN_ETHERCAT_RX     23
#define PIN_STATUS_LED      2
#define PIN_FAULT_LED       25
#define PIN_ENABLE_BTN      32
#define PIN_FAULT_RESET_BTN 33

// Control loop timing
#define CURRENT_LOOP_HZ     10000
#define VELOCITY_LOOP_HZ    1000
#define POSITION_LOOP_HZ    100
#define COMM_LOOP_HZ        100

// Safety limits
#define TEMP_FAULT_C        85.0f
#define CURRENT_FAULT_PCT   150.0f
#define COMM_TIMEOUT_MS     500
#define VOLTAGE_MIN_V       10.0f

// Memory targets
#define FLASH_BOOTLOADER_KB 16
#define FLASH_APP_KB        256
#define FLASH_NVS_KB        32
#define FLASH_UPDATE_BUF_KB 64

#define RAM_LOOP_STACK_B    2048
#define RAM_PROTO_BUF_B     4096
#define RAM_MOTOR_STATE_B   2048
#define RAM_LOG_BUF_B       1024
