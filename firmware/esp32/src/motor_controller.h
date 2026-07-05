#ifndef MOTOR_CONTROLLER_H
#define MOTOR_CONTROLLER_H

#include <Arduino.h>
#include "types.h"
#include "constants.h"

// Motor series support
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
#if defined(MOTOR_RMD_H)
  #include "drivers/rmd_h_driver.h"
#endif

#if defined(MOTOR_RMD_L)
  #include "drivers/rmd_l_driver.h"
#endif

#if defined(MOTOR_FL)
  #include "drivers/fl_driver.h"
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
#if defined(MOTOR_RMD_H)
  #include "drivers/rmd_h_driver.h"
#endif

#if defined(MOTOR_RMD_L)
  #include "drivers/rmd_l_driver.h"
#endif

#if defined(MOTOR_FL)
  #include "drivers/fl_driver.h"
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

#if defined(MOTOR_RMD_H)
  #include "drivers/rmd_h_driver.h"
#endif

#if defined(MOTOR_RMD_L)
  #include "drivers/rmd_l_driver.h"
#endif

#if defined(MOTOR_FL)
  #include "drivers/fl_driver.h"
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
  
private:
  MotorState currentState;
  MotorStatus currentStatus;
  FaultCode faultCode;
  
  // Motor driver instance (polymorphic)
  void* motorDriver;
  
  // Control parameters
  float targetPosition;
  float targetVelocity;
  float targetTorque;
  
  // PID controllers
  PIDController positionPID;
  PIDController velocityPID;
  PIDController torquePID;
  
  // Encoder interface
  EncoderInterface encoder;
  
  // Communication interface
  CommunicationInterface comm;

  // CAN bus interface
  MCP2515_CAN* canBus;

public:
  void setCanBus(MCP2515_CAN* bus) { canBus = bus; }
  void setCommunication(CommunicationInterface& comm) { this->comm = comm; }
  void setEncoder(Encoder& encoder) { this->encoder = encoder; }
  void setMotorDriver(MotorDriver& driver) { motorDriver = &driver; }
};

#endif // MOTOR_CONTROLLER_H
