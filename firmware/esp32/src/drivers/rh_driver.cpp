/**
 * MyActuator ESP32 Firmware - RH Driver Implementation
 * 
 * RH: Harmonic Gearbox Motor Series
 * Reference: MOTOR_RH_CONTRACT.md
 */

#include "rh_driver.h"
#include "../../include/config.h"
#include "../../include/constants.h"
#include <Arduino.h>

RHDriver::RHDriver(uint8_t motorId, const MotorConfig& config)
    : _motorId(motorId), _config(config), _status(MOTOR_STATUS_IDLE),
      _temperature(0), _position(0), _velocity(0), _current(0),
      _harmonicRatio(100.0f) {}

bool RHDriver::init() {
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

void RHDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus RHDriver::getStatus() { return _status; }
float RHDriver::getTemperature() {
    int raw = analogRead(PIN_TEMP_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _temperature = (voltage - 0.5f) * 100.0f;
    return _temperature;
}
int32_t RHDriver::getPosition() { _position = 0; return _position; }
float RHDriver::getVelocity() { _velocity = 0.0f; return _velocity; }
float RHDriver::getCurrent() {
    int raw = analogRead(PIN_CURRENT_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _current = (voltage - 1.65f) * 10.0f;
    return _current;
}

void RHDriver::setPosition(float target) {
    float adjustedTarget = target * _harmonicRatio;
    (void)adjustedTarget;
}

void RHDriver::setVelocity(float target) {
    float adjustedTarget = target * _harmonicRatio;
    (void)adjustedTarget;
}

void RHDriver::setTorque(float target) {
    target = constrain(target, -_config.maxTorque, _config.maxTorque);
    (void)target;
}

void RHDriver::enable() { _status = MOTOR_STATUS_ENABLED; }
void RHDriver::disable() {
    _status = MOTOR_STATUS_DISABLED;
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
}
void RHDriver::faultReset() { _status = MOTOR_STATUS_IDLE; }

void RHDriver::setLimits(float maxVelocity, float maxTorque) {
    _config.maxVelocity = maxVelocity;
    _config.maxTorque = maxTorque;
}

void RHDriver::setGains(float kp, float ki, float kd) {
    _config.kp = kp;
    _config.ki = ki;
    _config.kd = kd;
}

void RHDriver::setHarmonicRatio(float ratio) { _harmonicRatio = ratio; }
void RHDriver::zeroCalibrate() { _position = 0; }

