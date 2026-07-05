/**
 * RS485 Driver - Header
 * 
 * Modbus RTU over RS485
 * 115200 baud, 8N1
 */

#ifndef RS485_H
#define RS485_H

#include <Arduino.h>

class RS485 {
public:
    static void init();
    static bool sendFrame(uint8_t address, const uint8_t* data, uint8_t length);
    static bool receiveFrame(uint8_t& address, uint8_t* data, uint8_t& length);
    static void setMotorId(uint8_t motorId);

private:
    static uint8_t _motorId;
};

#endif // RS485_H
