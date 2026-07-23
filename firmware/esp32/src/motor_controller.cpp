#include "motor_controller.h"
#include "protocols/pal.h"
#include "drivers/mcp2515_can.h"

MotorController::MotorController(uint8_t motorId, const MotorConfig& config)
  : motorId(motorId),
    motorSeries(config.motorSeries),
    gearboxRatio(1.0f),
    backlashCompensation(0.0f),
    kp(config.kp),
    ki(config.ki),
    kd(config.kd),
    maxVelocityLimit(config.maxVelocity),
    maxTorqueLimit(config.maxTorque),
    currentState(MOTOR_STATE_IDLE),
    currentStatus(MOTOR_STATUS_IDLE),
    faultCode(FAULT_NONE),
    motorDriver(nullptr),
    targetPosition(0.0f),
    targetVelocity(0.0f),
    targetTorque(0.0f),
    encoder(nullptr),
    comm(nullptr),
    canBus(nullptr),
    safetyMonitoring(true),
    lastHeartbeat(0),
    temperature(0.0f),
    position(0),
    velocity(0.0f),
    current(0.0f) {
  positionPID.reset();
  velocityPID.reset();
  torquePID.reset();
}

MotorController::~MotorController() = default;

bool MotorController::initialize() {
  if (encoder && !encoder->init()) {
    faultCode = FAULT_ENCODER;
    return false;
  }

  if (comm && !comm->initialize()) {
    faultCode = FAULT_COMMUNICATION;
    return false;
  }

  if (motorDriver && !motorDriver->init()) {
    faultCode = FAULT_MOTOR_DRIVER;
    return false;
  }

  safetyMonitoring = true;
  lastHeartbeat = millis();
  currentState = MOTOR_STATE_READY;
  return true;
}

void MotorController::update() {
  if (currentState == MOTOR_STATE_FAULT) {
    return;
  }

  if (encoder) {
    position = encoder->getPosition();
    velocity = encoder->getVelocity();
  }

  if (motorDriver) {
    temperature = motorDriver->getTemperature();
    current = motorDriver->getCurrent();

    switch (currentState) {
      case MOTOR_STATE_POSITION_CONTROL:
        motorDriver->setPosition(targetPosition);
        break;
      case MOTOR_STATE_VELOCITY_CONTROL:
        motorDriver->setVelocity(targetVelocity);
        break;
      case MOTOR_STATE_TORQUE_CONTROL:
        motorDriver->setTorque(targetTorque);
        break;
      default:
        break;
    }
  }
}

void MotorController::setTargetPosition(float target) {
  targetPosition = target;
  currentState = MOTOR_STATE_POSITION_CONTROL;
}

void MotorController::setTargetVelocity(float target) {
  targetVelocity = target;
  currentState = MOTOR_STATE_VELOCITY_CONTROL;
}

void MotorController::setTargetTorque(float target) {
  targetTorque = target;
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

float MotorController::getPositionRadians() const {
  if (encoder && encoder->getResolution() > 0) {
    return (float)position / (float)encoder->getResolution() * 2.0f * PI;
  }
  return 0.0f;
}

float MotorController::getVelocityRadiansPerSec() const {
  if (encoder && encoder->getResolution() > 0) {
    return velocity / (float)encoder->getResolution() * 2.0f * PI;
  }
  return 0.0f;
}
