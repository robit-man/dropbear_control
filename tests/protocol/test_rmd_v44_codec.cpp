#include "rmd_v44_codec.h"

#include <stdint.h>

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace v44 = myactuator::rmd_v44;

namespace {

struct Vector {
  std::string direction;
  uint16_t arbitration_id;
  uint8_t data[8];
};

int checks = 0;
int failures = 0;

#define CHECK(condition)                                                        \
  do {                                                                          \
    ++checks;                                                                   \
    if (!(condition)) {                                                         \
      ++failures;                                                               \
      std::cerr << "FAIL " << __FILE__ << ":" << __LINE__ << ": "           \
                << #condition << "\n";                                          \
    }                                                                           \
  } while (0)

int HexDigit(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

bool ParseHexData(const std::string& text, uint8_t* data) {
  if (text.size() != 16) return false;
  for (size_t i = 0; i < 8; ++i) {
    const int high = HexDigit(text[i * 2]);
    const int low = HexDigit(text[i * 2 + 1]);
    if (high < 0 || low < 0) return false;
    data[i] = static_cast<uint8_t>((high << 4) | low);
  }
  return true;
}

std::vector<std::string> SplitTabs(const std::string& line) {
  std::vector<std::string> fields;
  std::stringstream stream(line);
  std::string field;
  while (std::getline(stream, field, '\t')) fields.push_back(field);
  return fields;
}

std::map<std::string, Vector> LoadVectors(const char* path) {
  std::ifstream stream(path);
  if (!stream) {
    std::cerr << "cannot open vector fixture: " << path << "\n";
    ++failures;
    return std::map<std::string, Vector>();
  }
  std::map<std::string, Vector> vectors;
  std::string line;
  std::getline(stream, line);  // header
  while (std::getline(stream, line)) {
    if (line.empty()) continue;
    const std::vector<std::string> fields = SplitTabs(line);
    if (fields.size() < 4) {
      std::cerr << "bad vector row: " << line << "\n";
      ++failures;
      continue;
    }
    Vector vector = {};
    vector.direction = fields[1];
    vector.arbitration_id =
        static_cast<uint16_t>(std::strtoul(fields[2].c_str(), NULL, 0));
    if (!ParseHexData(fields[3], vector.data)) {
      std::cerr << "bad vector data: " << fields[3] << "\n";
      ++failures;
      continue;
    }
    vectors[fields[0]] = vector;
  }
  return vectors;
}

v44::Frame MakeFrame(const Vector& vector) {
  v44::Frame frame = {};
  frame.arbitration_id = vector.arbitration_id;
  frame.dlc = 8;
  for (size_t i = 0; i < 8; ++i) frame.data[i] = vector.data[i];
  return frame;
}

bool FramesEqual(const v44::Frame& actual, const Vector& expected) {
  if (actual.arbitration_id != expected.arbitration_id || actual.dlc != 8 ||
      actual.is_extended || actual.is_remote) {
    return false;
  }
  for (size_t i = 0; i < 8; ++i) {
    if (actual.data[i] != expected.data[i]) return false;
  }
  return true;
}

const Vector& Get(const std::map<std::string, Vector>& vectors,
                  const std::string& name) {
  const std::map<std::string, Vector>::const_iterator found = vectors.find(name);
  if (found == vectors.end()) {
    std::cerr << "missing fixture vector: " << name << "\n";
    ++failures;
    static const Vector empty = {};
    return empty;
  }
  return found->second;
}

void TestSharedVectors(const std::map<std::string, Vector>& vectors) {
  for (std::map<std::string, Vector>::const_iterator it = vectors.begin();
       it != vectors.end(); ++it) {
    const v44::Frame frame = MakeFrame(it->second);
    if (it->second.direction == "request") {
      v44::DecodedRequest decoded = {};
      CHECK(v44::DecodeRequest(frame, &decoded) == v44::Error::kOk);
    } else if (it->second.direction == "response") {
      v44::DecodedResponse decoded = {};
      CHECK(v44::DecodeResponse(frame, &decoded) == v44::Error::kOk);
    } else {
      CHECK(false);
    }
  }
}

void TestEncoders(const std::map<std::string, Vector>& vectors) {
  struct ZeroCase {
    v44::Command command;
    const char* vector_name;
  };
  const ZeroCase zero_cases[] = {
      {v44::Command::kShutdown, "shutdown_request"},
      {v44::Command::kStop, "stop_request"},
      {v44::Command::kReadMultiTurnAngle, "read_multi_turn_request"},
      {v44::Command::kReadSingleTurnAngle, "read_single_turn_request"},
      {v44::Command::kReadStatus1, "status1_request"},
      {v44::Command::kReadStatus2, "status2_request"},
      {v44::Command::kReadStatus3, "status3_request"},
      {v44::Command::kOperatingMode, "operating_mode_request"},
      {v44::Command::kBrakeRelease, "brake_release_request"},
      {v44::Command::kBrakeLock, "brake_lock_request"},
  };
  for (size_t i = 0; i < sizeof(zero_cases) / sizeof(zero_cases[0]); ++i) {
    v44::Frame frame = {};
    CHECK(v44::EncodeZeroPayloadRequest(1, zero_cases[i].command, &frame) ==
          v44::Error::kOk);
    CHECK(FramesEqual(frame, Get(vectors, zero_cases[i].vector_name)));
  }

  v44::Frame frame = {};
  CHECK(v44::EncodeIqControlRaw(1, 100, &frame) == v44::Error::kOk);
  CHECK(FramesEqual(frame, Get(vectors, "iq_positive_request")));
  CHECK(v44::EncodeIqControlRaw(1, -100, &frame) == v44::Error::kOk);
  CHECK(FramesEqual(frame, Get(vectors, "iq_negative_request")));
  CHECK(v44::EncodeSpeedControlRaw(1, 10000, 0, &frame) == v44::Error::kOk);
  CHECK(FramesEqual(frame, Get(vectors, "speed_positive_request")));
  CHECK(v44::EncodeSpeedControlRaw(1, -10000, 0, &frame) == v44::Error::kOk);
  CHECK(FramesEqual(frame, Get(vectors, "speed_negative_request")));
  CHECK(v44::EncodeAbsolutePositionRaw(1, 36000, 500, &frame) == v44::Error::kOk);
  CHECK(FramesEqual(frame, Get(vectors, "absolute_positive_request")));
  CHECK(v44::EncodeAbsolutePositionRaw(1, -36000, 500, &frame) == v44::Error::kOk);
  CHECK(FramesEqual(frame, Get(vectors, "absolute_negative_request")));
  CHECK(v44::EncodeZeroPayloadRequest(32, v44::Command::kShutdown, &frame) ==
        v44::Error::kOk);
  CHECK(FramesEqual(frame, Get(vectors, "id32_shutdown_request")));
}

void TestDecodedValues(const std::map<std::string, Vector>& vectors) {
  v44::DecodedResponse response = {};
  CHECK(v44::DecodeResponse(MakeFrame(Get(vectors, "read_multi_turn_360_response")),
                            &response) == v44::Error::kOk);
  CHECK(response.kind == v44::ResponseKind::kAngle);
  CHECK(response.angle_i32_raw == 36000);

  CHECK(v44::DecodeResponse(MakeFrame(Get(vectors, "status1_response")), &response) ==
        v44::Error::kOk);
  CHECK(response.kind == v44::ResponseKind::kStatus1);
  CHECK(response.motor_temperature_c == 50);
  CHECK(response.mos_temperature_raw == 0);
  CHECK(response.brake_command_released);
  CHECK(response.voltage_raw == 485);
  CHECK(response.error_mask == 0x0004);
  CHECK(response.unknown_error_bits == 0);

  CHECK(v44::DecodeResponse(MakeFrame(Get(vectors, "status2_positive_response")),
                            &response) == v44::Error::kOk);
  CHECK(response.iq_raw == 100);
  CHECK(response.output_speed_raw == 500);
  CHECK(response.output_angle_raw == 45);

  CHECK(v44::DecodeResponse(MakeFrame(Get(vectors, "iq_negative_response")),
                            &response) == v44::Error::kOk);
  CHECK(response.iq_raw == -100);
  CHECK(response.output_speed_raw == -500);
  CHECK(response.output_angle_raw == -45);

  CHECK(v44::DecodeResponse(MakeFrame(Get(vectors, "status3_response")), &response) ==
        v44::Error::kOk);
  CHECK(response.phase_a_raw == 3010);
  CHECK(response.phase_b_raw == -1520);
  CHECK(response.phase_c_raw == -1600);

  CHECK(v44::DecodeResponse(
            MakeFrame(Get(vectors, "operating_mode_position_response")), &response) ==
        v44::Error::kOk);
  CHECK(response.operating_mode == v44::OperatingMode::kPosition);
}

void TestBoundaries() {
  CHECK(!v44::kApplicabilityVerified);
  CHECK(v44::kCanBitrate == 1000000UL);
  CHECK(!v44::IsValidMotorId(0));
  CHECK(v44::IsValidMotorId(1));
  CHECK(v44::IsValidMotorId(32));
  CHECK(!v44::IsValidMotorId(33));
  CHECK(v44::RequestArbitrationId(0) == 0);
  CHECK(v44::ResponseArbitrationId(33) == 0);
  CHECK(v44::RequestArbitrationId(1) == 0x141);
  CHECK(v44::RequestArbitrationId(32) == 0x160);
  CHECK(v44::ResponseArbitrationId(1) == 0x241);
  CHECK(v44::ResponseArbitrationId(32) == 0x260);

  const int16_t i16_values[] = {-32768, -1, 0, 1, 32767};
  for (size_t i = 0; i < sizeof(i16_values) / sizeof(i16_values[0]); ++i) {
    v44::Frame frame = {};
    v44::DecodedRequest decoded = {};
    CHECK(v44::EncodeIqControlRaw(1, i16_values[i], &frame) == v44::Error::kOk);
    CHECK(v44::DecodeRequest(frame, &decoded) == v44::Error::kOk);
    CHECK(decoded.iq_raw == i16_values[i]);
  }

  const int32_t i32_values[] = {INT32_MIN, -1, 0, 1, INT32_MAX};
  for (size_t i = 0; i < sizeof(i32_values) / sizeof(i32_values[0]); ++i) {
    v44::Frame frame = {};
    v44::DecodedRequest decoded = {};
    CHECK(v44::EncodeSpeedControlRaw(1, i32_values[i], 255, &frame) ==
          v44::Error::kOk);
    CHECK(v44::DecodeRequest(frame, &decoded) == v44::Error::kOk);
    CHECK(decoded.speed_raw == i32_values[i]);
    CHECK(decoded.max_torque_percent_raw == 255);
  }

  const uint16_t speed_limits[] = {0, 1, 65535};
  for (size_t i = 0; i < sizeof(speed_limits) / sizeof(speed_limits[0]); ++i) {
    v44::Frame frame = {};
    v44::DecodedRequest decoded = {};
    CHECK(v44::EncodeAbsolutePositionRaw(1, -1, speed_limits[i], &frame) ==
          v44::Error::kOk);
    CHECK(v44::DecodeRequest(frame, &decoded) == v44::Error::kOk);
    CHECK(decoded.angle_raw == -1);
    CHECK(decoded.max_speed_raw == speed_limits[i]);
  }
}

void TestMalformed(const std::map<std::string, Vector>& vectors) {
  v44::Frame frame = MakeFrame(Get(vectors, "status1_response"));
  v44::DecodedResponse response = {};
  v44::DecodedRequest request = {};

  frame.dlc = 7;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kInvalidDlc);
  frame = MakeFrame(Get(vectors, "status1_response"));
  frame.is_extended = true;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kExtendedFrame);
  frame = MakeFrame(Get(vectors, "status1_response"));
  frame.is_remote = true;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kRemoteFrame);
  frame = MakeFrame(Get(vectors, "status1_response"));
  frame.arbitration_id = 0x141;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kInvalidArbitrationId);
  frame = MakeFrame(Get(vectors, "status1_response"));
  frame.data[0] = 0xFF;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kInvalidCommand);

  frame = MakeFrame(Get(vectors, "shutdown_response"));
  frame.data[7] = 1;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kReservedNonzero);
  frame = MakeFrame(Get(vectors, "shutdown_request"));
  frame.data[1] = 1;
  CHECK(v44::DecodeRequest(frame, &request) == v44::Error::kReservedNonzero);
  frame = MakeFrame(Get(vectors, "iq_positive_request"));
  frame.data[2] = 1;
  CHECK(v44::DecodeRequest(frame, &request) == v44::Error::kReservedNonzero);

  frame = MakeFrame(Get(vectors, "status1_response"));
  CHECK(v44::DecodeResponse(frame, &response, 2) == v44::Error::kUnexpectedMotorId);
  CHECK(v44::DecodeResponse(frame, &response, 1, 0x9C) ==
        v44::Error::kUnexpectedCommand);

  frame = MakeFrame(Get(vectors, "read_single_turn_75_response"));
  frame.data[4] = 0x51;
  frame.data[5] = 0x46;  // 18001 raw = 180.01 degrees
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kInvalidValue);

  frame = MakeFrame(Get(vectors, "status1_response"));
  frame.data[3] = 2;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kInvalidValue);
  frame = MakeFrame(Get(vectors, "operating_mode_position_response"));
  frame.data[7] = 4;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kInvalidValue);

  frame = MakeFrame(Get(vectors, "status1_response"));
  frame.data[6] = 0x16;
  frame.data[7] = 0;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kOk);
  CHECK(response.error_mask == 0x0016);
  CHECK(response.unknown_error_bits == 0);
  frame.data[6] = 0x01;
  CHECK(v44::DecodeResponse(frame, &response) == v44::Error::kOk);
  CHECK(response.unknown_error_bits == 0x0001);

  v44::Frame output = {};
  CHECK(v44::EncodeZeroPayloadRequest(0, v44::Command::kShutdown, &output) ==
        v44::Error::kInvalidMotorId);
  CHECK(v44::EncodeZeroPayloadRequest(33, v44::Command::kShutdown, &output) ==
        v44::Error::kInvalidMotorId);
  CHECK(v44::EncodeZeroPayloadRequest(1, v44::Command::kIqControl, &output) ==
        v44::Error::kInvalidCommand);
  CHECK(v44::EncodeIqControlRaw(1, 0, NULL) == v44::Error::kNullOutput);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "usage: test_rmd_v44_codec GOLDEN_TSV\n";
    return 2;
  }
  const std::map<std::string, Vector> vectors = LoadVectors(argv[1]);
  CHECK(vectors.size() == 34);
  TestSharedVectors(vectors);
  TestEncoders(vectors);
  TestDecodedValues(vectors);
  TestBoundaries();
  TestMalformed(vectors);
  if (failures != 0) {
    std::cerr << "CPP_RMD_V44_FAILED checks=" << checks
              << " failures=" << failures << "\n";
    return 1;
  }
  std::cout << "CPP_RMD_V44_OK vectors=" << vectors.size()
            << " checks=" << checks << "\n";
  return 0;
}
