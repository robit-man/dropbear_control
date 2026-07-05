/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */


/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

/**
 * MyActuator ESP32 Firmware - CEM Driver Implementation
 * 
 * CEM: Cycloidal Gearbox Motor Series
 * Reference: MOTOR_CEM_CONTRACT.md
 */

#include "cem_driver.h"
#include "../include/types.h"
#include "../../include/config.h"
#include "../../include/constants.h"
#include <Arduino.h>

CEMDriver::CEMDriver(uint8_t motorId, const MotorConfig& config)
    : _motorId(motorId), _config(config), _status(MOTOR_STATUS_IDLE),
      _temperature(0), _position(0), _velocity(0), _current(0),
      _strokeLength(50.0f), _cycloidPhaseOffset(0.0f) {}

bool CEMDriver::init() {
    pinMode(PIN_MOTOR_PWM_A, OUTPUT);
    pinMode(PIN_MOTOR_PWM_B, OUTPUT);
    pinMode(PIN_ENCODER_A, INPUT_PULLUP);
    pinMode(PIN_ENCODER_B, INPUT_PULLUP);
    pinMode(PIN_ENCODER_Z, INPUT_PULLUP);
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);
    _status = MOTOR_STATUS_IDLE;
    return true;
}

void CEMDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus CEMDriver::getStatus() { return _status; }

float CEMDriver::getTemperature() {
    int raw = analogRead(PIN_TEMP_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _temperature = (voltage - 0.5f) * 100.0f;
    return _temperature;
}

int32_t CEMDriver::getPosition() {
    _position = 0;
    return _position;
}

float CEMDriver::getVelocity() {
    _velocity = 0.0f;
    return _velocity;
}

float CEMDriver::getCurrent() {
    int raw = analogRead(PIN_CURRENT_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _current = (voltage - 1.65f) * 10.0f;
    return _current;
}

void CEMDriver::setPosition(float target) {
    float adjustedTarget = target + _cycloidPhaseOffset;
    (void)adjustedTarget;
}

void CEMDriver::setVelocity(float target) {
    (void)target;
}

void CEMDriver::setTorque(float target) {
    target = constrain(target, -_config.maxTorque, _config.maxTorque);
    (void)target;
}

void CEMDriver::enable() {
    _status = MOTOR_STATUS_ENABLED;
}

void CEMDriver::disable() {
    _status = MOTOR_STATUS_DISABLED;
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
}

void CEMDriver::faultReset() {
    _status = MOTOR_STATUS_IDLE;
}

void CEMDriver::setLimits(float maxVelocity, float maxTorque) {
    _config.maxVelocity = maxVelocity;
    _config.maxTorque = maxTorque;
}

void CEMDriver::setGains(float kp, float ki, float kd) {
    _config.kp = kp;
    _config.ki = ki;
    _config.kd = kd;
}

void CEMDriver::setStrokeLength(float stroke) {
    _strokeLength = stroke;
}

void CEMDriver::setCycloidPhaseOffset(float offset) {
    _cycloidPhaseOffset = offset;
}

