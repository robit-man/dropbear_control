/**
 * RMD-L Direct Drive Motor Driver - Implementation
 * 
 * Implements control interface for RMD-L direct drive motor series
 */


/**
 * MyActuator ESP32 Firmware - RMD-L Driver Implementation
 * 
 * RMD-L: Direct Drive Motor Series
 * Reference: MOTOR_RMD_L_CONTRACT.md
 */

#include "rmd_l_driver.h"
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
#include "../utils/logger.h"
#include "motor_driver.h"

RMDLDriver::RMDLDriver(uint8_t motorId, const MotorConfig& config)
    : _motorId(motorId),
      _config(config),
      _temperature(0),
      _position(0),
      _velocity(0),
      _current(0),
      _coggingCompensation(0) {
    memset(&_status, 0, sizeof(MotorStatus));
}

RMDLDriver::~RMDLDriver() = default;

bool RMDLDriver::init() {
    // Initialize CAN bus if configured
    if (_config.communication == COMM_CAN) {
        if (!CANBus::getInstance().begin(_config.canBusSpeed)) {
            Logger::error("RMD-L: Failed to initialize CAN bus");
            return false;
        }
    }
    
    // Initialize RS485 if configured
    if (_config.communication == COMM_RS485) {
        if (!RS485::getInstance().begin(_config.rs485BaudRate)) {
            Logger::error("RMD-L: Failed to initialize RS485");
            return false;
        }
    }
    
    // Initialize encoder
    if (!Encoder::getInstance().begin(_config.encoderPinA, _config.encoderPinB, _config.encoderPinZ)) {
        Logger::error("RMD-L: Failed to initialize encoder");
        return false;
    }
    
    // Initialize motor driver
    if (!MotorDriver::getInstance().begin(_config.motorPinPWM, _config.motorPinDir)) {
        Logger::error("RMD-L: Failed to initialize motor driver");
        return false;
    }
    
    // Set initial limits
    setLimits(_config.maxVelocity, _config.maxTorque);
    
    // Set initial gains
    setGains(_config.kp, _config.ki, _config.kd);
    
    Logger::info("RMD-L: Driver initialized for motor ID " + String(_motorId));
    return true;
}

void RMDLDriver::deinit() {
    MotorDriver::getInstance().end();
    Encoder::getInstance().end();
    Logger::info("RMD-L: Driver deinitialized");
}

MotorStatus RMDLDriver::getStatus() {
    // Read encoder
    _position = Encoder::getInstance().getPosition();
    _velocity = Encoder::getInstance().getVelocity();
    
    // Read current
    _current = MotorDriver::getInstance().getCurrent();
    
    // Read temperature (if available)
    _temperature = MotorDriver::getInstance().getTemperature();
    
    // Update status
    _status.position = _position;
    _status.velocity = _velocity;
    _status.current = _current;
    _status.temperature = _temperature;
    _status.enabled = IMotorDriver::getInstance().isEnabled();
    
    return _status;
}

float RMDLDriver::getTemperature() {
    return _temperature;
}

int32_t RMDLDriver::getPosition() {
    return _position;
}

float RMDLDriver::getVelocity() {
    return _velocity;
}

float RMDLDriver::getCurrent() {
    return _current;
}

void RMDLDriver::setPosition(float target) {
    // Apply cogging compensation
    target += _coggingCompensation;
    
    // Clamp to limits
    if (target > _config.maxPosition) {
        target = _config.maxPosition;
    } else if (target < -_config.maxPosition) {
        target = -_config.maxPosition;
    }
    
    MotorDriver::getInstance().setPosition(target);
}

void RMDLDriver::setVelocity(float target) {
    // Clamp to limits
    if (target > _config.maxVelocity) {
        target = _config.maxVelocity;
    } else if (target < -_config.maxVelocity) {
        target = -_config.maxVelocity;
    }
    
    MotorDriver::getInstance().setVelocity(target);
}

void RMDLDriver::setTorque(float target) {
    // Clamp to limits
    if (target > _config.maxTorque) {
        target = _config.maxTorque;
    } else if (target < -_config.maxTorque) {
        target = -_config.maxTorque;
    }
    
    MotorDriver::getInstance().setTorque(target);
}

void RMDLDriver::enable() {
    MotorDriver::getInstance().enable();
    Logger::info("RMD-L: Motor enabled");
}

void RMDLDriver::disable() {
    MotorDriver::getInstance().disable();
    Logger::info("RMD-L: Motor disabled");
}

void RMDLDriver::faultReset() {
    MotorDriver::getInstance().faultReset();
    Logger::info("RMD-L: Fault reset");
}

void RMDLDriver::setLimits(float maxVelocity, float maxTorque) {
    _config.maxVelocity = maxVelocity;
    _config.maxTorque = maxTorque;
    MotorDriver::getInstance().setLimits(maxVelocity, maxTorque);
}

void RMDLDriver::setGains(float kp, float ki, float kd) {
    _config.kp = kp;
    _config.ki = ki;
    _config.kd = kd;
    MotorDriver::getInstance().setGains(kp, ki, kd);
}

void RMDLDriver::setCoggingCompensation(float compensation) {
    _coggingCompensation = compensation;
}


void RMDLDriver::deinit() {
    digitalWrite(PIN_MOTOR_PWM_A, LOW);
    digitalWrite(PIN_MOTOR_PWM_B, LOW);
    _status = MOTOR_STATUS_DISABLED;
}

MotorStatus RMDLDriver::getStatus() {
    return _status;
}

float RMDLDriver::getTemperature() {
    return _temperature;
}

int32_t RMDLDriver::getPosition() {
    return _position;
}

float RMDLDriver::getVelocity() {
    return _velocity;
}

float RMDLDriver::getCurrent() {
    return _current;
}
