#include "rmd_x_driver.h"
#include "../include/types.h"
#include "../include/config.h"
#include "../include/constants.h"
#include "motor_driver.h"
#include "encoder.h"
#include "can_bus.h"
#include "rs485.h"
#include "ethercat.h"
#include "motor_controller.h"
#include "protocols/pal.h"
#include "../../include/config.h"
#include "../../include/constants.h"
#include <Arduino.h>

RMDXDriver::RMDXDriver(uint8_t motorId, const MotorConfig& config)
    : _motorId(motorId), _config(config), _status(MOTOR_STATUS_IDLE),
      _temperature(0), _position(0), _velocity(0), _current(0),
      _gearboxRatio(1.0f), _backlashCompensation(0.0f) {}

bool RMDXDriver::init() {
    // Initialize motor PWM pins
    pinMode(PIN_MOTOR_PWM_A, OUTPUT);
    pinMode(PIN_MOTOR_PWM_B, OUTPUT);
    
    // Initialize encoder pins
    pinMode(PIN_ENCODER_A, INPUT_PULLUP);
    pinMode(PIN_ENCODER_B, INPUT_PULLUP);
    pinMode(PIN_ENCODER_Z, INPUT_PULLUP);
    
    // Initialize ADC pins
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);
    
    _status = MOTOR_STATUS_IDLE;
    return true;
}

void RMDXDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus RMDXDriver::getStatus() {
    return _status;
}

float RMDXDriver::getTemperature() {
    int raw = analogRead(PIN_TEMP_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    // NTC thermistor calculation (simplified)
    _temperature = (voltage - 0.5f) * 100.0f;
    return _temperature;
}

int32_t RMDXDriver::getPosition() {
    // Read encoder position (simplified)
    _position = 0;
    return _position;
}

float RMDXDriver::getVelocity() {
    // Calculate velocity from encoder (simplified)
    _velocity = 0.0f;
    return _velocity;
}

float RMDXDriver::getCurrent() {
    int raw = analogRead(PIN_CURRENT_SENSE);
    float voltage = raw * (3.3f / 4095.0f);
    _current = (voltage - 1.65f) * 10.0f; // Simplified conversion
    return _current;
}

void RMDXDriver::setPosition(float target) {
    // Apply gearbox ratio and backlash compensation
    float adjustedTarget = target * _gearboxRatio + _backlashCompensation;
    // Send command to motor driver (simplified)
    (void)adjustedTarget;
}

void RMDXDriver::setVelocity(float target) {
    // Apply gearbox ratio
    float adjustedTarget = target * _gearboxRatio;
    (void)adjustedTarget;
}

void RMDXDriver::setTorque(float target) {
    // Limit torque to max
    target = constrain(target, -_config.maxTorque, _config.maxTorque);
    (void)target;
}

void RMDXDriver::enable() {
    _status = MOTOR_STATUS_ENABLED;
}

void RMDXDriver::disable() {
    _status = MOTOR_STATUS_DISABLED;
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
}

void RMDXDriver::faultReset() {
    _status = MOTOR_STATUS_IDLE;
}

void RMDXDriver::setLimits(float maxVelocity, float maxTorque) {
    _config.maxVelocity = maxVelocity;
    _config.maxTorque = maxTorque;
}

void RMDXDriver::setGains(float kp, float ki, float kd) {
    _config.kp = kp;
    _config.ki = ki;
    _config.kd = kd;
}

void RMDXDriver::setGearboxRatio(float ratio) {
    _gearboxRatio = ratio;
}

void RMDXDriver::setBacklashCompensation(float compensation) {
    _backlashCompensation = compensation;
}


void RMDXDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus RMDXDriver::getStatus() {
    return _status;
}

float RMDXDriver::getTemperature() {
    return _temperature;
}

int32_t RMDXDriver::getPosition() {
    return _position;
}

float RMDXDriver::getVelocity() {
    return _velocity;
}

float RMDXDriver::getCurrent() {
    return _current;
}
