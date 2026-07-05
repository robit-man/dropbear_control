/**
 * Configuration Utilities - Header
 * 
 * Motor configuration and parameter management
 */

#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>
#include <ArduinoJson.h>

class Config {
public:
    static bool loadConfig(const char* json);
    static bool saveConfig(const char* json);
    static uint8_t getMotorId();
    static void setMotorId(uint8_t motorId);
    static uint32_t getBaudRate();
    static void setBaudRate(uint32_t baudRate);
    static uint8_t getEncoderBits();
    static void setEncoderBits(uint8_t bits);
    static uint8_t getPowerClass();
    static void setPowerClass(uint8_t powerClass);

private:
    static uint8_t _motorId;
    static uint32_t _baudRate;
    static uint8_t _encoderBits;
    static uint8_t _powerClass;
};

#endif // CONFIG_H
