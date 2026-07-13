#pragma once
#include "motor_driver.h"
#include "types.h"

class RMDXDriver : public IMotorDriver {
public:
    RMDXDriver(uint8_t motorId, const MotorConfig& config);
    ~RMDXDriver() override = default;
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
    void setBacklashCompensation(float compensation);

private:
    uint8_t _motorId;
    MotorConfig _config;
    float _backlashCompensation = 0.0f;
    MotorStatus _status = MOTOR_STATUS_IDLE;
    float _temperature = 0.0f;
    int32_t _position = 0;
    float _velocity = 0.0f;
    float _current = 0.0f;
    float _gearboxRatio = 1.0f;
};
