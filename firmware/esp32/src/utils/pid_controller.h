#pragma once

#include <Arduino.h>
#include <stdint.h>

class PIDController {
public:
    PIDController(float kp, float ki, float kd);
    ~PIDController() = default;

    void setGains(float kp, float ki, float kd);
    void setLimits(float minOutput, float maxOutput);
    void setSetpoint(float setpoint);

    float compute(float measurement);
    float compute(float measurement, float dt);

    void reset();
    bool hasError();

    float getProportional();
    float getIntegral();
    float getDerivative();

    float getOutput();

private:
    float _kp;
    float _ki;
    float _kd;

    float _setpoint;
    float _lastError;
    float _integral;
    float _output;

    float _minOutput;
    float _maxOutput;

    bool _initialized;
};
