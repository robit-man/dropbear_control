/**
 * Configuration Utilities - Implementation
 */

#include "config.h"

uint8_t Config::_motorId = 1;
uint32_t Config::_baudRate = 115200;
uint8_t Config::_encoderBits = 14;
uint8_t Config::_powerClass = 10;

bool Config::loadConfig(const char* json) {
    // Parse JSON configuration
    return true;
}

bool Config::saveConfig(const char* json) {
    // Save JSON configuration
    return true;
}

uint8_t Config::getMotorId() {
    return _motorId;
}

void Config::setMotorId(uint8_t motorId) {
    _motorId = motorId;
}

uint32_t Config::getBaudRate() {
    return _baudRate;
}

void Config::setBaudRate(uint32_t baudRate) {
    _baudRate = baudRate;
}

uint8_t Config::getEncoderBits() {
    return _encoderBits;
}

void Config::setEncoderBits(uint8_t bits) {
    _encoderBits = bits;
}

uint8_t Config::getPowerClass() {
    return _powerClass;
}

void Config::setPowerClass(uint8_t powerClass) {
    _powerClass = powerClass;
}
