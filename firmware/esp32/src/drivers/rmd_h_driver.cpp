/**
 * MyActuator ESP32 Firmware - RMD-H Driver Implementation
 * 
 * RMD-H: Direct Drive Hollow Motor Series
 * Reference: MOTOR_RMD_H_CONTRACT.md
 */

#include "../../include/config.h"
#include "../../include/constants.h"
#include <Arduino.h>
#include "rmd_h_driver.h"
#include "../motor_driver.h"
#include "../../include/types.h"

RMDHDriver::RMDHDriver(uint8_t motorId, const MotorConfig& config)
    : _motorId(motorId), _config(config), _status(MOTOR_STATUS_IDLE),
      _temperature(0), _position(0), _velocity(0), _current(0),
      _inertiaCompensation(0.0f), _hollowBoreEnabled(false) {}

bool RMDHDriver::init() {
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

void RMDHDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus RMDHDriver::getStatus() { return _status; }

float RMDHDriver::getTemperature() {
    int raw = analogRead(PIN_TEMP_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _temperature = (voltage - 0.5f) * 100.0f;
    return _temperature;
}

int32_t RMDHDriver::getPosition() {
    _position = 0;
    return _position;
}

float RMDHDriver::getVelocity() {
    _velocity = 0.0f;
    return _velocity;
}

float RMDHDriver::getCurrent() {
    int raw = analogRead(PIN_CURRENT_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _current = (voltage - 1.65f) * 10.0f;
    return _current;
}

void RMDHDriver::setPosition(float target) {
    float adjustedTarget = target + _inertiaCompensation;
    (void)adjustedTarget;
}

void RMDHDriver::setVelocity(float target) {
    (void)target;
}

void RMDHDriver::setTorque(float target) {
    target = constrain(target, -_config.maxTorque, _config.maxTorque);
    (void)target;
}

void RMDHDriver::enable() {
    _status = MOTOR_STATUS_ENABLED;
}

void RMDHDriver::disable() {
    _status = MOTOR_STATUS_DISABLED;
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
}

void RMDHDriver::faultReset() {
    _status = MOTOR_STATUS_IDLE;
}

void RMDHDriver::setLimits(float maxVelocity, float maxTorque) {
    _config.maxVelocity = maxVelocity;
    _config.maxTorque = maxTorque;
}

void RMDHDriver::setGains(float kp, float ki, float kd) {
    _config.kp = kp;
    _config.ki = ki;
    _config.kd = kd;
}

void RMDHDriver::setInertiaCompensation(float inertia) {
    _inertiaCompensation = inertia;
}

void RMDHDriver::enableHollowBoreAccess(bool enable) {
    _hollowBoreEnabled = enable;
}


void RMDHDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus RMDHDriver::getStatus() {
    return _status;
}

float RMDHDriver::getTemperature() {
    return _temperature;
}

int32_t RMDHDriver::getPosition() {
    return _position;
}

float RMDHDriver::getVelocity() {
    return _velocity;
}

float RMDHDriver::getCurrent() {
    return _current;
}
