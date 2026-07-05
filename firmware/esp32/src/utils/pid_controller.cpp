#include "pid_controller.h"
#include <Arduino.h>

PIDController::PIDController(float kp, float ki, float kd)
    : _kp(kp), _ki(ki), _kd(kd),
      _setpoint(0), _lastError(0), _integral(0), _output(0),
      _minOutput(-100.0f), _maxOutput(100.0f), _initialized(false) {}

void PIDController::setGains(float kp, float ki, float kd) {
    _kp = kp;
    _ki = ki;
    _kd = kd;
}

void PIDController::setLimits(float minOutput, float maxOutput) {
    _minOutput = minOutput;
    _maxOutput = maxOutput;
}

void PIDController::setSetpoint(float setpoint) {
    _setpoint = setpoint;
}

float PIDController::compute(float measurement) {
    return compute(measurement, 0.01f);  // Default 10ms timestep
}

float PIDController::compute(float measurement, float dt) {
    if (dt <= 0) dt = 0.01f;

    float error = _setpoint - measurement;

    // Proportional
    float proportional = _kp * error;

    // Integral
    _integral += error * dt;
    // Anti-windup
    if (_integral > _maxOutput / _ki) _integral = _maxOutput / _ki;
    if (_integral < _minOutput / _ki) _integral = _minOutput / _ki;
    float integral = _ki * _integral;

    // Derivative
    float derivative = (error - _lastError) / dt;
    _lastError = error;

    // Compute output
    _output = proportional + integral + (_kd * derivative);

    // Clamp output
    if (_output > _maxOutput) _output = _maxOutput;
    if (_output < _minOutput) _output = _minOutput;

    _initialized = true;

    return _output;
}

void PIDController::reset() {
    _setpoint = 0;
    _lastError = 0;
    _integral = 0;
    _output = 0;
    _initialized = false;
}

bool PIDController::hasError() {
    return _initialized;
}

float PIDController::getProportional() {
    return _kp;
}

float PIDController::getIntegral() {
    return _ki;
}

float PIDController::getDerivative() {
    return _kd;
}

float PIDController::getOutput() {
    return _output;
}
