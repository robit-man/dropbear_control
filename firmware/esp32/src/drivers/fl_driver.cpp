/**
 * MyActuator ESP32 Firmware - FL Driver Implementation
 * 
 * FL: Linear Motor Series
 * Reference: MOTOR_FL_CONTRACT.md
 */

#include "fl_driver.h"
#include "../../include/config.h"
#include "../../include/constants.h"
#include <Arduino.h>

FLDriver::FLDriver(uint8_t motorId, const MotorConfig& config)
    : _motorId(motorId), _config(config), _status(MOTOR_STATUS_IDLE),
      _temperature(0), _position(0), _velocity(0), _current(0),
      _strokeLength(100.0f), _forceFeedback(0.0f) {}

bool FLDriver::init() {
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

void FLDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus FLDriver::getStatus() { return _status; }

float FLDriver::getTemperature() {
    int raw = analogRead(PIN_TEMP_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _temperature = (voltage - 0.5f) * 100.0f;
    return _temperature;
}

int32_t FLDriver::getPosition() {
    _position = 0;
    return _position;
}

float FLDriver::getVelocity() {
    _velocity = 0.0f;
    return _velocity;
}

float FLDriver::getCurrent() {
    int raw = analogRead(PIN_CURRENT_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _current = (voltage - 1.65f) * 10.0f;
    return _current;
}

void FLDriver::setPosition(float target) {
    float adjustedTarget = target / _strokeLength;
    (void)adjustedTarget;
}

void FLDriver::setVelocity(float target) {
    float adjustedTarget = target / _strokeLength;
    (void)adjustedTarget;
}

void FLDriver::setTorque(float target) {
    target = constrain(target, -_config.maxTorque, _config.maxTorque);
    (void)target;
}

void FLDriver::enable() {
    _status = MOTOR_STATUS_ENABLED;
}

void FLDriver::disable() {
    _status = MOTOR_STATUS_DISABLED;
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
}

void FLDriver::faultReset() {
    _status = MOTOR_STATUS_IDLE;
}

void FLDriver::setLimits(float maxVelocity, float maxTorque) {
    _config.maxVelocity = maxVelocity;
    _config.maxTorque = maxTorque;
}

void FLDriver::setGains(float kp, float ki, float kd) {
    _config.kp = kp;
    _config.ki = ki;
    _config.kd = kd;
}

void FLDriver::setStrokeLength(float stroke) {
    _strokeLength = stroke;
}

void FLDriver::setForceFeedback(float force) {
    _forceFeedback = force;
}

