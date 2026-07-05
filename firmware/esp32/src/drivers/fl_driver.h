#pragma once

#include "motor_driver.h"

class FLDriver : public IMotorDriver {
public:
    FLDriver(uint8_t motorId, const MotorConfig& config);
    ~FLDriver() override = default;
    
    bool init() override;
    void deinit() override;
    
    MotorStatus getStatus() override;
    float getTemperature() override;
    int32_t getPosition() override;
    float getVelocity() override;
    float getCurrent() override;
    
    void setPosition(float target) override;
    void setVelocity(float target) override;
    void setTorque(float target) override;
    void enable() override;
    void disable() override;
    void faultReset() override;
    
    void setLimits(float maxVelocity, float maxTorque) override;
    void setGains(float kp, float ki, float kd) override;
    
    // FL specific
    void setStrokeLength(float stroke);
    void setForceFeedback(float force);
    
private:
    uint8_t _motorId;
    MotorConfig _config;
    MotorStatus _status;
    float _temperature;
    int32_t _position;
    float _velocity;
    float _current;
    float _strokeLength;
    float _forceFeedback;
};
