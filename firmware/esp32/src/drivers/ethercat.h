/**
 * EtherCAT Driver - Header
 * 
 * EtherCAT with CoE (CANopen over EtherCAT)
 * 1ms cycle time, DC sync
 */

#ifndef ETHERCAT_H
#define ETHERCAT_H

#include <Arduino.h>

class EtherCAT {
public:
    static void init();
    static bool sendFrame(uint8_t motorId, const uint8_t* data, uint8_t length);
    static bool receiveFrame(uint8_t& motorId, uint8_t* data, uint8_t& length);
    static void setMotorId(uint8_t motorId);
    static void setCycleTime(uint16_t cycleTimeMs);

private:
    static uint8_t _motorId;
    static uint16_t _cycleTimeMs;
};

#endif // ETHERCAT_H
