#pragma once

#include <Arduino.h>
#include <SPI.h>
#include <mcp2515.h>

// MCP2515 CAN controller pin definitions for ESP32
#ifndef PIN_MCP2515_CS
#define PIN_MCP2515_CS 5
#endif

#ifndef PIN_MCP2515_INT
#define PIN_MCP2515_INT 4
#endif

// CAN bus configuration
#define CAN_BITRATE CAN_500KBPS
#define CAN_FILTER_MODE STANDARD_FILTER

// CAN message buffer size
#define CAN_RX_BUFFER_SIZE 16
#define CAN_TX_BUFFER_SIZE 16

// CAN message ID ranges for MyActuator motors
#define CAN_ID_RMD_X_BASE 0x100
#define CAN_ID_RH_BASE 0x200
#define CAN_ID_CEM_BASE 0x300
#define CAN_ID_RMD_H_BASE 0x400
#define CAN_ID_RMD_L_BASE 0x500
#define CAN_ID_FL_BASE 0x600

// CAN message types
#define CAN_MSG_TYPE_COMMAND 0x01
#define CAN_MSG_TYPE_STATUS 0x02
#define CAN_MSG_TYPE_CONFIG 0x03
#define CAN_MSG_TYPE_FEEDBACK 0x04

class MCP2515CAN {
public:
    MCP2515CAN();
    
    bool initialize(uint32_t bitrate = CAN_BITRATE);
    bool sendCommand(uint8_t motorId, uint8_t command, const uint8_t* data, uint8_t length);
    bool sendStatusRequest(uint8_t motorId);
    bool sendConfig(uint8_t motorId, const uint8_t* configData, uint8_t length);
    
    bool receiveMessage(uint8_t* motorId, uint8_t* messageType, uint8_t* data, uint8_t* length);
    bool hasPendingMessages();
    
    void setFilter(uint8_t motorId, uint8_t filterId);
    void clearFilters();
    
    uint32_t getErrorCount();
    uint8_t getStatus();
    
private:
    MCP2515_CAN can;
    uint32_t errorCount;
    uint8_t status;
    
    bool configureFilters();
    bool configureInterrupts();
};
