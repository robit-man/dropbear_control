#include "mcp2515_can.h"
#include "config.h"

MCP2515CAN::MCP2515CAN()
  : errorCount(0),
    status(0) {
}

bool MCP2515CAN::initialize(uint32_t bitrate) {
  // Initialize SPI
  SPI.begin();
  
  // Initialize MCP2515
  if (!can.begin(bitrate, PIN_MCP2515_CS)) {
    status = 0x01; // Initialization failed
    return false;
  }
  
  // Set normal mode
  can.setMode(MCP2515::NORMAL_MODE);
  
  // Configure filters
  if (!configureFilters()) {
    status = 0x02; // Filter configuration failed
    return false;
  }
  
  // Configure interrupts
  if (!configureInterrupts()) {
    status = 0x03; // Interrupt configuration failed
    return false;
  }
  
  status = 0x00; // Ready
  return true;
}

bool MCP2515CAN::sendCommand(uint8_t motorId, uint8_t command, const uint8_t* data, uint8_t length) {
  if (length > 8) {
    return false;
  }
  
  uint32_t canId = CAN_ID_RMD_X_BASE + motorId;
  
  // Create CAN message
  MCP2515::CAN_message_t msg;
  msg.id = canId;
  msg.len = length + 1; // Add command byte
  msg.buf[0] = command;
  memcpy(&msg.buf[1], data, length);
  
  // Send message
  if (can.sendMsgBuf(canId, msg.len, msg.buf) != CAN_OK) {
    errorCount++;
    return false;
  }
  
  return true;
}

bool MCP2515CAN::sendStatusRequest(uint8_t motorId) {
  uint32_t canId = CAN_ID_RMD_X_BASE + motorId;
  
  // Create status request message
  MCP2515::CAN_message_t msg;
  msg.id = canId;
  msg.len = 1;
  msg.buf[0] = CAN_MSG_TYPE_STATUS;
  
  // Send message
  if (can.sendMsgBuf(canId, msg.len, msg.buf) != CAN_OK) {
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
  
  // Create config message
  MCP2515::CAN_message_t msg;
  msg.id = canId;
  msg.len = length + 1; // Add config type byte
  msg.buf[0] = CAN_MSG_TYPE_CONFIG;
  memcpy(&msg.buf[1], configData, length);
  
  // Send message
  if (can.sendMsgBuf(canId, msg.len, msg.buf) != CAN_OK) {
    errorCount++;
    return false;
  }
  
  return true;
}

bool MCP2515CAN::receiveMessage(uint8_t* motorId, uint8_t* messageType, uint8_t* data, uint8_t* length) {
  if (!can.checkReceive()) {
    return false;
  }
  
  MCP2515::CAN_message_t msg;
  if (can.readMsgBuf(&msg) != CAN_OK) {
    errorCount++;
    return false;
  }
  
  // Extract motor ID from CAN ID
  if (msg.id >= CAN_ID_RMD_X_BASE && msg.id < CAN_ID_RMD_X_BASE + 255) {
    *motorId = msg.id - CAN_ID_RMD_X_BASE;
  } else {
    return false;
  }
  
  // Extract message type
  if (msg.len > 0) {
    *messageType = msg.buf[0];
    
    // Extract data
    uint8_t dataLen = msg.len - 1;
    if (dataLen > 8) {
      dataLen = 8;
    }
    memcpy(data, &msg.buf[1], dataLen);
    *length = dataLen;
    
    return true;
  }
  
  return false;
}

bool MCP2515CAN::hasPendingMessages() {
  return can.checkReceive();
}

void MCP2515CAN::setFilter(uint8_t motorId, uint8_t filterId) {
  uint32_t canId = CAN_ID_RMD_X_BASE + motorId;
  
  // Set individual filter
  can.setFilter(filterId, 0, canId);
}

void MCP2515CAN::clearFilters() {
  // Clear all filters
  for (int i = 0; i < 6; i++) {
    can.setFilter(i, 0, 0);
  }
}

uint32_t MCP2515CAN::getErrorCount() {
  return errorCount;
}

uint8_t MCP2515CAN::getStatus() {
  return status;
}

bool MCP2515CAN::configureFilters() {
  // Configure receive filters for all motor IDs
  for (int i = 0; i < 6; i++) {
    uint32_t canId = CAN_ID_RMD_X_BASE + i;
    can.setFilter(i, 0, canId);
  }
  
  return true;
}

bool MCP2515CAN::configureInterrupts() {
  // Configure interrupt pin
  pinMode(PIN_MCP2515_INT, INPUT);
  
  // Enable interrupts in MCP2515
  can.setInterrupt(MCP2515::INT_ENABLE);
  
  return true;
}
