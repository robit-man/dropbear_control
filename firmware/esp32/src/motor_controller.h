#ifndef MOTOR_CONTROLLER_H
#define MOTOR_CONTROLLER_H

#include <Arduino.h>
#include "types.h"
#include "constants.h"
#include "drivers/motor_driver.h"
#include "drivers/encoder.h"
#include "drivers/mcp2515_can.h"

// Per-product driver selection based on build flags
#if defined(MOTOR_RMD_X)
  #include "drivers/rmd_x_driver.h"
#endif
#if defined(MOTOR_RH)
  #include "drivers/rh_driver.h"
#endif
#if defined(MOTOR_CEM)
  #include "drivers/cem_driver.h"
#endif
#if defined(MOTOR_RMD_H)
  #include "drivers/rmd_h_driver.h"
#endif
#if defined(MOTOR_RMD_L)
  #include "drivers/rmd_l_driver.h"
#endif
#if defined(MOTOR_FL)
  #include "drivers/fl_driver.h"
#endif

class MotorController {
public:
  MotorController(uint8_t motorId, const MotorConfig& config);
  ~MotorController();

  bool initialize();
  void update();

  // Control interface
  void setTargetPosition(float position);
  void setTargetVelocity(float velocity);
  void setTargetTorque(float torque);

  // Status
  MotorStatus getStatus() const;
  MotorState getState() const;

  // Fault handling
  bool hasFault() const;
  FaultCode getFaultCode() const;
  void clearFault();

  // Accessors
  uint8_t getMotorId() const { return motorId; }
  MotorSeries getMotorSeries() const { return motorSeries; }
  float getGearboxRatio() const { return gearboxRatio; }
  float getBacklashCompensation() const { return backlashCompensation; }
  float getKp() const { return kp; }
  float getKi() const { return ki; }
  float getKd() const { return kd; }
  void getLimits(float& maxVelocity, float& maxTorque) const {
    maxVelocity = maxVelocityLimit;
    maxTorque = maxTorqueLimit;
  }
  float getTargetPosition() const { return targetPosition; }
  float getTargetVelocity() const { return targetVelocity; }
  float getTargetTorque() const { return targetTorque; }
  bool isSafetyMonitoring() const { return safetyMonitoring; }
  uint32_t getHeartbeat() const { return lastHeartbeat; }

  float getTemperature() const { return temperature; }
  int32_t getPosition() const { return position; }
  float getVelocity() const { return velocity; }
  float getCurrent() const { return current; }

  // Dependency injection
  void setCanBus(MCP2515CAN* bus) { canBus = bus; }
  void setCommunication(CommunicationInterface* c) { comm = c; }
  void setEncoder(Encoder* e) { encoder = e; }
  void setMotorDriver(IMotorDriver* driver) { motorDriver = driver; }

private:
  uint8_t motorId;
  MotorSeries motorSeries;
  float gearboxRatio;
  float backlashCompensation;
  float kp;
  float ki;
  float kd;
  float maxVelocityLimit;
  float maxTorqueLimit;

  MotorState currentState;
  MotorStatus currentStatus;
  FaultCode faultCode;

  IMotorDriver* motorDriver;

  float targetPosition;
  float targetVelocity;
  float targetTorque;

  PIDController positionPID;
  PIDController velocityPID;
  PIDController torquePID;

  Encoder* encoder;
  CommunicationInterface* comm;
  MCP2515CAN* canBus;

  bool safetyMonitoring;
  uint32_t lastHeartbeat;

  float temperature;
  int32_t position;
  float velocity;
  float current;
};

#endif // MOTOR_CONTROLLER_H
