#pragma once

// Portable, allocation-free MYACTUATOR classic-CAN V4.4 codec.
//
// Evidence: CAN BUS Motor Motion Protocol V4.4 260520.pdf
// SHA-256: 15731a29c60771f0066fa0b2c7a7609de76edc53fbc8757035d2389d7a5dc3d2
// Protocol layout is evidenced; applicability to any model/firmware is not.

#include <stddef.h>
#include <stdint.h>

namespace myactuator {
namespace rmd_v44 {

static const bool kApplicabilityVerified = false;
static const uint32_t kCanBitrate = 1000000UL;
static const uint16_t kRequestBaseId = 0x140;
static const uint16_t kResponseBaseId = 0x240;
static const uint8_t kMinMotorId = 1;
static const uint8_t kMaxMotorId = 32;
static const uint8_t kFrameDlc = 8;

static const uint16_t kKnownErrorMask =
    0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0040 | 0x0080 |
    0x0100 | 0x0800 | 0x1000 | 0x2000 | 0x4000;

enum class Command : uint8_t {
  kOperatingMode = 0x70,
  kBrakeRelease = 0x77,
  kBrakeLock = 0x78,
  kShutdown = 0x80,
  kStop = 0x81,
  kReadMultiTurnAngle = 0x92,
  kReadSingleTurnAngle = 0x94,
  kReadStatus1 = 0x9A,
  kReadStatus2 = 0x9C,
  kReadStatus3 = 0x9D,
  kIqControl = 0xA1,
  kSpeedControl = 0xA2,
  kAbsolutePosition = 0xA4,
};

enum class OperatingMode : uint8_t {
  kCurrent = 0x01,
  kSpeed = 0x02,
  kPosition = 0x03,
};

enum class Error : uint8_t {
  kOk = 0,
  kNullOutput,
  kInvalidMotorId,
  kInvalidCommand,
  kInvalidDlc,
  kExtendedFrame,
  kRemoteFrame,
  kInvalidArbitrationId,
  kUnexpectedMotorId,
  kUnexpectedCommand,
  kReservedNonzero,
  kInvalidValue,
};

enum class ResponseKind : uint8_t {
  kNone = 0,
  kEcho,
  kAngle,
  kStatus1,
  kMotionStatus,
  kPhaseStatus,
  kOperatingMode,
};

struct Frame {
  uint16_t arbitration_id;
  uint8_t dlc;
  bool is_extended;
  bool is_remote;
  uint8_t data[8];
};

struct DecodedRequest {
  uint8_t motor_id;
  Command command;
  int16_t iq_raw;
  uint8_t max_torque_percent_raw;
  int32_t speed_raw;
  uint16_t max_speed_raw;
  int32_t angle_raw;
};

// Fields not used by the selected ResponseKind remain zero.
struct DecodedResponse {
  ResponseKind kind;
  uint8_t motor_id;
  Command command;
  int8_t motor_temperature_c;
  uint8_t mos_temperature_raw;
  bool brake_command_released;
  uint16_t voltage_raw;       // 0.1 V/LSB for status 1.
  uint16_t error_mask;
  uint16_t unknown_error_bits;
  int32_t angle_i32_raw;      // 0.01 degree/LSB for 0x92/0x94.
  int16_t iq_raw;             // 0.01 A/LSB; this is not torque in N.m.
  int16_t output_speed_raw;   // 1 degree/s/LSB.
  int16_t output_angle_raw;   // 1 degree/LSB.
  int16_t phase_a_raw;        // 0.01 A/LSB.
  int16_t phase_b_raw;        // 0.01 A/LSB.
  int16_t phase_c_raw;        // 0.01 A/LSB.
  OperatingMode operating_mode;
};

bool IsValidMotorId(uint8_t motor_id);
uint16_t RequestArbitrationId(uint8_t motor_id);
uint16_t ResponseArbitrationId(uint8_t motor_id);
const char* ErrorName(Error error);

// Encodes only commands whose seven argument bytes are documented as zero.
Error EncodeZeroPayloadRequest(uint8_t motor_id, Command command, Frame* out);
Error EncodeIqControlRaw(uint8_t motor_id, int16_t iq_raw, Frame* out);
Error EncodeSpeedControlRaw(uint8_t motor_id, int32_t speed_raw,
                            uint8_t max_torque_percent_raw, Frame* out);
Error EncodeAbsolutePositionRaw(uint8_t motor_id, int32_t angle_raw,
                                uint16_t max_speed_raw, Frame* out);

// expected_motor_id == 0 and expected_command == 0 disable correlation checks.
Error DecodeRequest(const Frame& frame, DecodedRequest* out,
                    uint8_t expected_motor_id = 0,
                    uint8_t expected_command = 0);
Error DecodeResponse(const Frame& frame, DecodedResponse* out,
                     uint8_t expected_motor_id = 0,
                     uint8_t expected_command = 0);

}  // namespace rmd_v44
}  // namespace myactuator
