#include "rmd_v44_codec.h"

#include <string.h>

namespace myactuator {
namespace rmd_v44 {
namespace {

bool IsSupportedCommand(uint8_t value) {
  switch (static_cast<Command>(value)) {
    case Command::kOperatingMode:
    case Command::kBrakeRelease:
    case Command::kBrakeLock:
    case Command::kShutdown:
    case Command::kStop:
    case Command::kReadMultiTurnAngle:
    case Command::kReadSingleTurnAngle:
    case Command::kReadStatus1:
    case Command::kReadStatus2:
    case Command::kReadStatus3:
    case Command::kIqControl:
    case Command::kSpeedControl:
    case Command::kAbsolutePosition:
      return true;
  }
  return false;
}

bool IsZeroPayloadCommand(Command command) {
  switch (command) {
    case Command::kOperatingMode:
    case Command::kBrakeRelease:
    case Command::kBrakeLock:
    case Command::kShutdown:
    case Command::kStop:
    case Command::kReadMultiTurnAngle:
    case Command::kReadSingleTurnAngle:
    case Command::kReadStatus1:
    case Command::kReadStatus2:
    case Command::kReadStatus3:
      return true;
    case Command::kIqControl:
    case Command::kSpeedControl:
    case Command::kAbsolutePosition:
      return false;
  }
  return false;
}

bool IsEchoCommand(Command command) {
  return command == Command::kBrakeRelease || command == Command::kBrakeLock ||
         command == Command::kShutdown || command == Command::kStop;
}

bool IsMotionStatusCommand(Command command) {
  return command == Command::kReadStatus2 || command == Command::kIqControl ||
         command == Command::kSpeedControl ||
         command == Command::kAbsolutePosition;
}

bool AllZero(const uint8_t* data, size_t begin, size_t end) {
  for (size_t i = begin; i < end; ++i) {
    if (data[i] != 0) return false;
  }
  return true;
}

uint16_t ReadU16(const uint8_t* data, size_t offset) {
  return static_cast<uint16_t>(data[offset]) |
         (static_cast<uint16_t>(data[offset + 1]) << 8);
}

int16_t ReadI16(const uint8_t* data, size_t offset) {
  const uint16_t value = ReadU16(data, offset);
  if (value <= 0x7FFFu) return static_cast<int16_t>(value);
  return static_cast<int16_t>(-static_cast<int32_t>(0x10000u - value));
}

int32_t ReadI32(const uint8_t* data, size_t offset) {
  const uint32_t value = static_cast<uint32_t>(data[offset]) |
                         (static_cast<uint32_t>(data[offset + 1]) << 8) |
                         (static_cast<uint32_t>(data[offset + 2]) << 16) |
                         (static_cast<uint32_t>(data[offset + 3]) << 24);
  if (value <= 0x7FFFFFFFUL) return static_cast<int32_t>(value);
  return static_cast<int32_t>(-static_cast<int64_t>(0x100000000ULL - value));
}

int8_t ReadI8(uint8_t value) {
  if (value <= 0x7Fu) return static_cast<int8_t>(value);
  return static_cast<int8_t>(-static_cast<int16_t>(0x100u - value));
}

void WriteU16(uint16_t value, uint8_t* data, size_t offset) {
  data[offset] = static_cast<uint8_t>(value & 0xFFu);
  data[offset + 1] = static_cast<uint8_t>((value >> 8) & 0xFFu);
}

void WriteI16(int16_t value, uint8_t* data, size_t offset) {
  WriteU16(static_cast<uint16_t>(value), data, offset);
}

void WriteI32(int32_t value, uint8_t* data, size_t offset) {
  const uint32_t raw = static_cast<uint32_t>(value);
  data[offset] = static_cast<uint8_t>(raw & 0xFFu);
  data[offset + 1] = static_cast<uint8_t>((raw >> 8) & 0xFFu);
  data[offset + 2] = static_cast<uint8_t>((raw >> 16) & 0xFFu);
  data[offset + 3] = static_cast<uint8_t>((raw >> 24) & 0xFFu);
}

void InitializeFrame(uint8_t motor_id, Command command, Frame* out) {
  memset(out, 0, sizeof(*out));
  out->arbitration_id = RequestArbitrationId(motor_id);
  out->dlc = kFrameDlc;
  out->data[0] = static_cast<uint8_t>(command);
}

Error ValidateWire(const Frame& frame) {
  if (frame.is_extended) return Error::kExtendedFrame;
  if (frame.is_remote) return Error::kRemoteFrame;
  if (frame.arbitration_id > 0x7FFu) return Error::kInvalidArbitrationId;
  if (frame.dlc != kFrameDlc) return Error::kInvalidDlc;
  return Error::kOk;
}

Error DecodeMotorId(uint16_t arbitration_id, uint16_t base,
                    uint8_t expected_motor_id, uint8_t* motor_id) {
  if (expected_motor_id != 0 && !IsValidMotorId(expected_motor_id)) {
    return Error::kInvalidMotorId;
  }
  if (arbitration_id <= base) return Error::kInvalidArbitrationId;
  const uint16_t candidate = arbitration_id - base;
  if (candidate < kMinMotorId || candidate > kMaxMotorId) {
    return Error::kInvalidArbitrationId;
  }
  *motor_id = static_cast<uint8_t>(candidate);
  if (expected_motor_id != 0 && *motor_id != expected_motor_id) {
    return Error::kUnexpectedMotorId;
  }
  return Error::kOk;
}

Error DecodeCommand(uint8_t value, uint8_t expected_command, Command* command) {
  if (!IsSupportedCommand(value)) return Error::kInvalidCommand;
  if (expected_command != 0 && !IsSupportedCommand(expected_command)) {
    return Error::kInvalidCommand;
  }
  if (expected_command != 0 && value != expected_command) {
    return Error::kUnexpectedCommand;
  }
  *command = static_cast<Command>(value);
  return Error::kOk;
}

}  // namespace

bool IsValidMotorId(uint8_t motor_id) {
  return motor_id >= kMinMotorId && motor_id <= kMaxMotorId;
}

uint16_t RequestArbitrationId(uint8_t motor_id) {
  if (!IsValidMotorId(motor_id)) return 0;
  return static_cast<uint16_t>(kRequestBaseId + motor_id);
}

uint16_t ResponseArbitrationId(uint8_t motor_id) {
  if (!IsValidMotorId(motor_id)) return 0;
  return static_cast<uint16_t>(kResponseBaseId + motor_id);
}

const char* ErrorName(Error error) {
  switch (error) {
    case Error::kOk: return "ok";
    case Error::kNullOutput: return "null_output";
    case Error::kInvalidMotorId: return "invalid_motor_id";
    case Error::kInvalidCommand: return "invalid_command";
    case Error::kInvalidDlc: return "invalid_dlc";
    case Error::kExtendedFrame: return "extended_frame";
    case Error::kRemoteFrame: return "remote_frame";
    case Error::kInvalidArbitrationId: return "invalid_arbitration_id";
    case Error::kUnexpectedMotorId: return "unexpected_motor_id";
    case Error::kUnexpectedCommand: return "unexpected_command";
    case Error::kReservedNonzero: return "reserved_nonzero";
    case Error::kInvalidValue: return "invalid_value";
  }
  return "unknown_error";
}

Error EncodeZeroPayloadRequest(uint8_t motor_id, Command command, Frame* out) {
  if (out == NULL) return Error::kNullOutput;
  if (!IsValidMotorId(motor_id)) return Error::kInvalidMotorId;
  if (!IsSupportedCommand(static_cast<uint8_t>(command)) ||
      !IsZeroPayloadCommand(command)) {
    return Error::kInvalidCommand;
  }
  InitializeFrame(motor_id, command, out);
  return Error::kOk;
}

Error EncodeIqControlRaw(uint8_t motor_id, int16_t iq_raw, Frame* out) {
  if (out == NULL) return Error::kNullOutput;
  if (!IsValidMotorId(motor_id)) return Error::kInvalidMotorId;
  InitializeFrame(motor_id, Command::kIqControl, out);
  WriteI16(iq_raw, out->data, 4);
  return Error::kOk;
}

Error EncodeSpeedControlRaw(uint8_t motor_id, int32_t speed_raw,
                            uint8_t max_torque_percent_raw, Frame* out) {
  if (out == NULL) return Error::kNullOutput;
  if (!IsValidMotorId(motor_id)) return Error::kInvalidMotorId;
  InitializeFrame(motor_id, Command::kSpeedControl, out);
  out->data[1] = max_torque_percent_raw;
  WriteI32(speed_raw, out->data, 4);
  return Error::kOk;
}

Error EncodeAbsolutePositionRaw(uint8_t motor_id, int32_t angle_raw,
                                uint16_t max_speed_raw, Frame* out) {
  if (out == NULL) return Error::kNullOutput;
  if (!IsValidMotorId(motor_id)) return Error::kInvalidMotorId;
  InitializeFrame(motor_id, Command::kAbsolutePosition, out);
  WriteU16(max_speed_raw, out->data, 2);
  WriteI32(angle_raw, out->data, 4);
  return Error::kOk;
}

Error DecodeRequest(const Frame& frame, DecodedRequest* out,
                    uint8_t expected_motor_id, uint8_t expected_command) {
  if (out == NULL) return Error::kNullOutput;
  Error error = ValidateWire(frame);
  if (error != Error::kOk) return error;
  memset(out, 0, sizeof(*out));
  error = DecodeMotorId(frame.arbitration_id, kRequestBaseId,
                        expected_motor_id, &out->motor_id);
  if (error != Error::kOk) return error;
  error = DecodeCommand(frame.data[0], expected_command, &out->command);
  if (error != Error::kOk) return error;

  if (IsZeroPayloadCommand(out->command)) {
    if (!AllZero(frame.data, 1, 8)) return Error::kReservedNonzero;
    return Error::kOk;
  }
  if (out->command == Command::kIqControl) {
    if (!AllZero(frame.data, 1, 4) || !AllZero(frame.data, 6, 8)) {
      return Error::kReservedNonzero;
    }
    out->iq_raw = ReadI16(frame.data, 4);
    return Error::kOk;
  }
  if (out->command == Command::kSpeedControl) {
    if (!AllZero(frame.data, 2, 4)) return Error::kReservedNonzero;
    out->max_torque_percent_raw = frame.data[1];
    out->speed_raw = ReadI32(frame.data, 4);
    return Error::kOk;
  }
  if (out->command == Command::kAbsolutePosition) {
    if (frame.data[1] != 0) return Error::kReservedNonzero;
    out->max_speed_raw = ReadU16(frame.data, 2);
    out->angle_raw = ReadI32(frame.data, 4);
    return Error::kOk;
  }
  return Error::kInvalidCommand;
}

Error DecodeResponse(const Frame& frame, DecodedResponse* out,
                     uint8_t expected_motor_id, uint8_t expected_command) {
  if (out == NULL) return Error::kNullOutput;
  Error error = ValidateWire(frame);
  if (error != Error::kOk) return error;
  memset(out, 0, sizeof(*out));
  error = DecodeMotorId(frame.arbitration_id, kResponseBaseId,
                        expected_motor_id, &out->motor_id);
  if (error != Error::kOk) return error;
  error = DecodeCommand(frame.data[0], expected_command, &out->command);
  if (error != Error::kOk) return error;

  if (IsEchoCommand(out->command)) {
    if (!AllZero(frame.data, 1, 8)) return Error::kReservedNonzero;
    out->kind = ResponseKind::kEcho;
    return Error::kOk;
  }
  if (out->command == Command::kReadMultiTurnAngle ||
      out->command == Command::kReadSingleTurnAngle) {
    if (!AllZero(frame.data, 1, 4)) return Error::kReservedNonzero;
    out->angle_i32_raw = ReadI32(frame.data, 4);
    if (out->command == Command::kReadSingleTurnAngle &&
        (out->angle_i32_raw < -18000 || out->angle_i32_raw > 18000)) {
      return Error::kInvalidValue;
    }
    out->kind = ResponseKind::kAngle;
    return Error::kOk;
  }
  if (out->command == Command::kReadStatus1) {
    if (frame.data[3] > 1) return Error::kInvalidValue;
    out->motor_temperature_c = ReadI8(frame.data[1]);
    out->mos_temperature_raw = frame.data[2];
    out->brake_command_released = frame.data[3] == 1;
    out->voltage_raw = ReadU16(frame.data, 4);
    out->error_mask = ReadU16(frame.data, 6);
    out->unknown_error_bits =
        static_cast<uint16_t>(out->error_mask & static_cast<uint16_t>(~kKnownErrorMask));
    out->kind = ResponseKind::kStatus1;
    return Error::kOk;
  }
  if (IsMotionStatusCommand(out->command)) {
    out->motor_temperature_c = ReadI8(frame.data[1]);
    out->iq_raw = ReadI16(frame.data, 2);
    out->output_speed_raw = ReadI16(frame.data, 4);
    out->output_angle_raw = ReadI16(frame.data, 6);
    out->kind = ResponseKind::kMotionStatus;
    return Error::kOk;
  }
  if (out->command == Command::kReadStatus3) {
    out->motor_temperature_c = ReadI8(frame.data[1]);
    out->phase_a_raw = ReadI16(frame.data, 2);
    out->phase_b_raw = ReadI16(frame.data, 4);
    out->phase_c_raw = ReadI16(frame.data, 6);
    out->kind = ResponseKind::kPhaseStatus;
    return Error::kOk;
  }
  if (out->command == Command::kOperatingMode) {
    if (!AllZero(frame.data, 1, 7)) return Error::kReservedNonzero;
    if (frame.data[7] < static_cast<uint8_t>(OperatingMode::kCurrent) ||
        frame.data[7] > static_cast<uint8_t>(OperatingMode::kPosition)) {
      return Error::kInvalidValue;
    }
    out->operating_mode = static_cast<OperatingMode>(frame.data[7]);
    out->kind = ResponseKind::kOperatingMode;
    return Error::kOk;
  }
  return Error::kInvalidCommand;
}

}  // namespace rmd_v44
}  // namespace myactuator
