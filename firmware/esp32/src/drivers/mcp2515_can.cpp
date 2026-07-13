#include "mcp2515_can.h"
#include "config.h"

MCP2515CAN::MCP2515CAN()
  : errorCount(0),
    status(0) {
}

bool MCP2515CAN::initialize(uint32_t bitrate) {
  // Map bitrate to watterott MCP2515 baud constant
  int baudConst;
  switch (bitrate) {
    case 10000:   baudConst = CAN_BAUD_10K;  break;
    case 50000:   baudConst = CAN_BAUD_50K;  break;
    case 100000:  baudConst = CAN_BAUD_100K; break;
    case 125000:  baudConst = CAN_BAUD_125K; break;
    case 250000:  baudConst = CAN_BAUD_250K; break;
    case 500000:  baudConst = CAN_BAUD_500K; break;
    default:      baudConst = CAN_BAUD_500K; break;
  }

  SPI.begin();

  if (!MCP2515::initCAN(baudConst)) {
    status = 0x01; // Initialization failed
    return false;
  }

  if (!MCP2515::setCANNormalMode(false)) {
    status = 0x01;
    return false;
  }

  if (!configureFilters()) {
    status = 0x02; // Filter configuration failed
    return false;
  }

  if (!configureInterrupts()) {
    status = 0x03; // Interrupt configuration failed
    return false;
  }

  status = 0x00; // Ready
  return true;
}

bool MCP2515CAN::sendCommand(uint8_t motorId, uint8_t command, const uint8_t* data, uint8_t length) {
  if (length > 7) {
    return false;
  }

  uint32_t canId = CAN_ID_RMD_X_BASE + motorId;

  CANMSG msg;
  msg.isExtendedAdrs = false;
  msg.adrsValue = canId;
  msg.rtr = false;
  msg.dataLength = length + 1; // Add command byte
  msg.data[0] = command;
  memcpy(&msg.data[1], data, length);

  if (!MCP2515::transmitCANMessage(msg, 100)) {
    errorCount++;
    return false;
  }

  return true;
}

bool MCP2515CAN::sendStatusRequest(uint8_t motorId) {
  uint32_t canId = CAN_ID_RMD_X_BASE + motorId;

  CANMSG msg;
  msg.isExtendedAdrs = false;
  msg.adrsValue = canId;
  msg.rtr = false;
  msg.dataLength = 1;
  msg.data[0] = CAN_MSG_TYPE_STATUS;

  if (!MCP2515::transmitCANMessage(msg, 100)) {
    errorCount++;
    return false;
  }

  return true;
}

bool MCP2515CAN::sendConfig(uint8_t motorId, const uint8_t* configData, uint8_t length) {
  if (length > 7) { // 7 bytes for config data (8 total with type byte)
    return false;
  }

  uint32_t canId = CAN_ID_RMD_X_BASE + motorId;

  CANMSG msg;
  msg.isExtendedAdrs = false;
  msg.adrsValue = canId;
  msg.rtr = false;
  msg.dataLength = length + 1; // Add config type byte
  msg.data[0] = CAN_MSG_TYPE_CONFIG;
  memcpy(&msg.data[1], configData, length);

  if (!MCP2515::transmitCANMessage(msg, 100)) {
    errorCount++;
    return false;
  }

  return true;
}

bool MCP2515CAN::receiveMessage(uint8_t* motorId, uint8_t* messageType, uint8_t* data, uint8_t* length) {
  CANMSG msg;
  if (!MCP2515::receiveCANMessage(&msg, 0)) {
    return false;
  }

  // Extract motor ID from CAN ID
  if (msg.adrsValue >= CAN_ID_RMD_X_BASE && msg.adrsValue < CAN_ID_RMD_X_BASE + 255) {
    *motorId = msg.adrsValue - CAN_ID_RMD_X_BASE;
  } else {
    return false;
  }

  // Extract message type
  if (msg.dataLength > 0) {
    *messageType = msg.data[0];

    // Extract data
    uint8_t dataLen = msg.dataLength - 1;
    if (dataLen > 8) {
      dataLen = 8;
    }
    memcpy(data, &msg.data[1], dataLen);
    *length = dataLen;

    return true;
  }

  return false;
}

bool MCP2515CAN::hasPendingMessages() {
  // Poll-based: receiveMessage() performs the actual non-blocking check.
  return true;
}

void MCP2515CAN::setFilter(uint8_t motorId, uint8_t filterId) {
  // watterott MCP2515 library does not expose a filter API; accept and ignore.
  (void)motorId;
  (void)filterId;
}

void MCP2515CAN::clearFilters() {
  // watterott MCP2515 library does not expose a filter API; accept and ignore.
}

uint32_t MCP2515CAN::getErrorCount() {
  return errorCount;
}

uint8_t MCP2515CAN::getStatus() {
  return status;
}

bool MCP2515CAN::configureFilters() {
  // watterott MCP2515 library does not expose a filter API; accept and ignore.
  return true;
}

bool MCP2515CAN::configureInterrupts() {
  // Configure interrupt pin
  pinMode(PIN_MCP2515_INT, INPUT);

  // watterott MCP2515 library does not expose an interrupt-enable API; accept and ignore.
  return true;
}
