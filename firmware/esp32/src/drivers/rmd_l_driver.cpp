/**
 * RMD-L Direct Drive Motor Driver - Implementation
 *
 * Implements control interface for RMD-L direct drive motor series
 */

#include "rmd_l_driver.h"
#include "../include/types.h"
#include "../include/config.h"
#include "../include/constants.h"
#include "motor_driver.h"
#include <Arduino.h>

RMDLDriver::RMDLDriver(uint8_t motorId, const MotorConfig& config)
    : _motorId(motorId),
      _config(config),
      _temperature(0),
      _position(0),
      _velocity(0),
      _current(0),
      _coggingCompensation(0) {
    _status = MOTOR_STATUS_IDLE;
}

bool RMDLDriver::init() {
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

void RMDLDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus RMDLDriver::getStatus() { return _status; }

float RMDLDriver::getTemperature() {
    int raw = analogRead(PIN_TEMP_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _temperature = (voltage - 0.5f) * 100.0f;
    return _temperature;
}

int32_t RMDLDriver::getPosition() {
    _position = 0;
    return _position;
}

float RMDLDriver::getVelocity() {
    _velocity = 0.0f;
    return _velocity;
}

float RMDLDriver::getCurrent() {
    int raw = analogRead(PIN_CURRENT_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _current = (voltage - 1.65f) * 10.0f;
    return _current;
}

void RMDLDriver::setPosition(float target) {
    float adjustedTarget = target + _coggingCompensation;
    (void)adjustedTarget;
}

void RMDLDriver::setVelocity(float target) {
    (void)target;
}

void RMDLDriver::setTorque(float target) {
    target = constrain(target, -_config.maxTorque, _config.maxTorque);
    (void)target;
}

void RMDLDriver::enable() {
    _status = MOTOR_STATUS_ENABLED;
}

void RMDLDriver::disable() {
    _status = MOTOR_STATUS_DISABLED;
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
}

void RMDLDriver::faultReset() {
    _status = MOTOR_STATUS_IDLE;
}

void RMDLDriver::setLimits(float maxVelocity, float maxTorque) {
    _config.maxVelocity = maxVelocity;
    _config.maxTorque = maxTorque;
}

void RMDLDriver::setGains(float kp, float ki, float kd) {
    _config.kp = kp;
    _config.ki = ki;
    _config.kd = kd;
}

void RMDLDriver::setCoggingCompensation(float compensation) {
    _coggingCompensation = compensation;
}
