#include "serial_bridge.h"
#include <string.h>
#include "utils/logger.h"

SerialBridge::SerialBridge(Stream& stream, MotorController& controller, uint8_t motorId)
  : _stream(&stream), _controller(&controller), _motorId(motorId),
    _idx(0), _lastStatusMs(0), _seq(0) {
  memset(_buf, 0, sizeof(_buf));
}

void SerialBridge::begin() {
  Logger::info("SERIAL", "Serial bridge ready (motor %u)", _motorId);
}

void SerialBridge::update() {
  // 1) Drain incoming bytes and parse any complete 64-byte frames.
  while (_stream->available() > 0) {
    _ingest((uint8_t)_stream->read());
  }
  // 2) Run the control loop for the bound controller.
  _controller->update();
  // 3) Emit a status report at ~10 Hz.
  uint32_t now = millis();
  if (now - _lastStatusMs >= 100) {
    _lastStatusMs = now;
    sendStatusReport();
  }
}

void SerialBridge::_ingest(uint8_t b) {
  if (_idx < serial_frame::FRAME_SIZE) {
    _buf[_idx++] = b;
  }
  if (_idx == serial_frame::FRAME_SIZE) {
    serial_frame::Frame f;
    if (serial_frame::unpack(_buf, f)) {
      _dispatch(f);
    } else {
      // Bad sync/CRC: resync by dropping the oldest byte and shifting left.
      memmove(_buf, _buf + 1, serial_frame::FRAME_SIZE - 1);
      _idx = serial_frame::FRAME_SIZE - 1;
    }
  }
}

void SerialBridge::_dispatch(const serial_frame::Frame& f) {
  // Ignore frames not addressed to this motor (broadcast motor id = 0 accepted).
  if (f.motorId != _motorId && f.motorId != 0) return;

  switch (f.frameType) {
    case serial_frame::FRAME_TYPE_POSITION_CMD: {
      int32_t target; memcpy(&target, f.payload, 4);
      _controller->setTargetPosition((float)target / 1000.0f); // mrad -> rad
      break;
    }
    case serial_frame::FRAME_TYPE_VELOCITY_CMD: {
      int32_t target; memcpy(&target, f.payload, 4);
      _controller->setTargetVelocity((float)target / 1000.0f); // mrad/s -> rad/s
      break;
    }
    case serial_frame::FRAME_TYPE_TORQUE_CMD: {
      int16_t target; memcpy(&target, f.payload, 2);
      _controller->setTargetTorque((float)target / 100.0f);   // 0.01 N·m -> N·m
      break;
    }
    case serial_frame::FRAME_TYPE_DIAGNOSTIC:
    case serial_frame::FRAME_TYPE_HEARTBEAT:
      // Acknowledge with a fresh status report.
      sendStatusReport();
      break;
    default:
      // Unknown frame type: ignore.
      break;
  }
}

void SerialBridge::sendStatusReport() {
  serial_frame::Frame f;
  memset(&f, 0, sizeof(f));
  f.frameType   = serial_frame::FRAME_TYPE_STATUS_REPORT;
  f.motorId     = _motorId;
  f.commandType = 0x00;
  f.sequence    = _seq++;
  f.headerSeq   = 0;

  // Payload layout mirrors web/js/sim.js MotorSim.toStatusFrame so the
  // dashboard's onSerialFrame() can decode it directly. Position/velocity are
  // scaled to integer mrad / mrad-per-s to match the dashboard decoder
  // (which divides by 1000).
  int32_t pos  = (int32_t)(_controller->getPositionRadians() * 1000.0f);        // mrad
  int32_t vel  = (int32_t)(_controller->getVelocityRadiansPerSec() * 1000.0f);  // mrad/s
  int16_t torq = (int16_t)(_controller->getCurrent() * 100.0f); // 0.01 N·m
  memcpy(f.payload + 0,  &pos,  4);
  memcpy(f.payload + 4,  &vel,  4);
  memcpy(f.payload + 8,  &torq, 2);
  f.payload[10] = (uint8_t)constrain((int)_controller->getTemperature(), 0, 255);
  uint16_t st = (uint16_t)_controller->getState();
  memcpy(f.payload + 11, &st, 2);
  f.payload[13] = _controller->hasFault() ? (uint8_t)_controller->getFaultCode() : 0;

  _emit(f);
}

void SerialBridge::sendHeartbeat() {
  serial_frame::Frame f;
  memset(&f, 0, sizeof(f));
  f.frameType = serial_frame::FRAME_TYPE_HEARTBEAT;
  f.motorId   = _motorId;
  f.sequence  = _seq++;
  _emit(f);
}

void SerialBridge::_emit(const serial_frame::Frame& f) {
  uint8_t raw[serial_frame::FRAME_SIZE];
  serial_frame::pack(f, raw);
  _stream->write(raw, serial_frame::FRAME_SIZE);
}
