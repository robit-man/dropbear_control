#pragma once

#include <Arduino.h>
#include <stdint.h>
#include <stdbool.h>

// Motor status
typedef enum {
    MOTOR_STATUS_IDLE = 0,
    MOTOR_STATUS_ENABLED,
    MOTOR_STATUS_RUNNING,
    MOTOR_STATUS_FAULT,
    MOTOR_STATUS_DISABLED
} MotorStatus;

// Motor config
typedef struct {
    uint8_t motorId;
    uint8_t protocol;  // PROTO_CAN, PROTO_RS485, PROTO_ETHERCAT
    float maxVelocity;
    float maxTorque;
    float kp;
    float ki;
    float kd;
} MotorConfig;

// Motor driver interface
class IMotorDriver {
public:
    virtual ~IMotorDriver() = default;

    virtual bool init() = 0;
    virtual void deinit() = 0;

    virtual MotorStatus getStatus() = 0;
    virtual float getTemperature() = 0;
    virtual int32_t getPosition() = 0;
    virtual float getVelocity() = 0;
    virtual float getCurrent() = 0;

    virtual void setPosition(float target) = 0;
    virtual void setVelocity(float target) = 0;
    virtual void setTorque(float target) = 0;
    virtual void enable() = 0;
    virtual void disable() = 0;
    virtual void faultReset() = 0;

    virtual void setLimits(float maxVelocity, float maxTorque) = 0;
    virtual void setGains(float kp, float ki, float kd) = 0;
};
