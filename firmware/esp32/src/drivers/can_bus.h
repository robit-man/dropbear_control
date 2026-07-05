/**
 * CAN Bus Driver - Header
 * 
 * ISO 11898-1 compliant CAN bus interface
 * 500kbps, 29-bit extended IDs
 */

#ifndef CAN_BUS_H
#define CAN_BUS_H

#include <Arduino.h>

class CANBus {
public:
    static void init();
    static bool sendFrame(uint32_t id, const uint8_t* data, uint8_t length);
    static bool receiveFrame(uint32_t& id, uint8_t* data, uint8_t& length);
    static void setMotorId(uint8_t motorId);

private:
    static uint8_t _motorId;
};

#endif // CAN_BUS_H
