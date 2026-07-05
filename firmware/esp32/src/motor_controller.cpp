#include "motor_controller.h"
#include "protocols/pal.h"
#include "drivers/mcp2515_can.h"

MotorController::MotorController(uint8_t motorId, const MotorConfig& config) 
  : currentState(MOTOR_STATE_IDLE),
    faultCode(FAULT_NONE),
    targetPosition(0.0f),
    targetVelocity(0.0f),
    canBus(nullptr),
    targetTorque(0.0f) {
  motorDriver = nullptr;
}

bool MotorController::initialize() {
  // Initialize encoder
  if (!encoder.initialize()) {
    faultCode = FAULT_ENCODER;
    return false;
  }
  
  // Initialize communication
  if (!comm.initialize()) {
    faultCode = FAULT_COMMUNICATION;
    return false;
  // Initialize motor driver based on configured motor series
  #if defined(MOTOR_RMD_X)
    if (!rmd_x_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;

  // Initialize safety monitoring
  safetyMonitoring = true;
  lastHeartbeat = millis();
  #elif defined(MOTOR_RH)
    if (!rh_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_CEM)
    if (!cem_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_RMD_H)
    if (!rmd_h_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_RMD_L)
    if (!rmd_l_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_FL)
    if (!fl_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #endif

  
  // Initialize motor driver based on configured motor series
  #if defined(MOTOR_RMD_X)
    if (!rmd_x_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_RH)
    if (!rh_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_CEM)
    if (!cem_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_RMD_H)
    if (!rmd_h_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_RMD_L)
    if (!rmd_l_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #elif defined(MOTOR_FL)
    if (!fl_driver.initialize()) {
      faultCode = FAULT_MOTOR_DRIVER;
      return false;
    }
  #endif
  
  currentState = MOTOR_STATE_READY;
  return true;
}

void MotorController::update() {
  if (currentState == MOTOR_STATE_FAULT) {
    return;
  }
  
  // Read encoder
  encoder.read();
  
  // Execute control loop
  switch (currentState) {
    case MOTOR_STATE_READY:
      // Wait for commands
      break;
      
    case MOTOR_STATE_POSITION_CONTROL:
      // Position control loop
      break;
      
    case MOTOR_STATE_VELOCITY_CONTROL:
      // Velocity control loop
      break;
      
    case MOTOR_STATE_TORQUE_CONTROL:
      // Torque control loop
      break;
      
    default:
      break;
  }
  
  // Check for faults
  if (encoder.hasFault() || comm.hasFault()) {
    currentState = MOTOR_STATE_FAULT;
    faultCode = FAULT_HARDWARE;
  }
}

void MotorController::setTargetPosition(float position) {
  targetPosition = position;
  currentState = MOTOR_STATE_POSITION_CONTROL;
}

void MotorController::setTargetVelocity(float velocity) {
  targetVelocity = velocity;
  currentState = MOTOR_STATE_VELOCITY_CONTROL;
}

void MotorController::setTargetTorque(float torque) {
  targetTorque = torque;
  currentState = MOTOR_STATE_TORQUE_CONTROL;
}

MotorStatus MotorController::getStatus() const {
  return currentStatus;
}

MotorState MotorController::getState() const {
  return currentState;
}

bool MotorController::hasFault() const {
  return currentState == MOTOR_STATE_FAULT;
}

FaultCode MotorController::getFaultCode() const {
  return faultCode;
}

void MotorController::clearFault() {
  faultCode = FAULT_NONE;
  currentState = MOTOR_STATE_READY;
}
