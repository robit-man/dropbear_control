#include "logger.h"
#include <Arduino.h>
#include <stdarg.h>

Stream* Logger::_stream = nullptr;
bool Logger::_initialized = false;
uint8_t Logger::_level = LOG_LEVEL_INFO;
uint32_t Logger::_timestamp = 0;

void Logger::init(Stream& stream) {
    _stream = &stream;
    _initialized = true;
    _timestamp = millis();
}

void Logger::setLevel(uint8_t level) {
    _level = level;
}

uint8_t Logger::getLevel() {
    return _level;
}

void Logger::log(uint8_t level, const char* module, const char* fmt, ...) {
    if (level > _level) return;

    uint32_t timestamp = millis() - _timestamp;
    char prefix[32];
    snprintf(prefix, sizeof(prefix), "[%07lu]", timestamp);

    const char* levelStr;
    switch (level) {
        case LOG_LEVEL_ERROR: levelStr = "ERROR"; break;
        case LOG_LEVEL_WARN:  levelStr = "WARN";  break;
        case LOG_LEVEL_INFO:  levelStr = "INFO";  break;
        case LOG_LEVEL_DEBUG: levelStr = "DEBUG"; break;
        case LOG_LEVEL_VERBOSE: levelStr = "VERB";  break;
        default: levelStr = "????"; break;
    }

    char header[64];
    snprintf(header, sizeof(header), "%s [%s] [%s] ", prefix, levelStr, module);
    Serial.print(header);

    va_list args;
    va_start(args, fmt);
    vsnprintf((char*)NULL, 0, fmt, args);
    va_end(args);

    char buffer[256];
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);

    Serial.println(buffer);
}

void Logger::error(const char* module, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    log(LOG_LEVEL_ERROR, module, fmt, args);
    va_end(args);
}

void Logger::warn(const char* module, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    log(LOG_LEVEL_WARN, module, fmt, args);
    va_end(args);
}

void Logger::info(const char* module, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    log(LOG_LEVEL_INFO, module, fmt, args);
    va_end(args);
}

void Logger::debug(const char* module, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    log(LOG_LEVEL_DEBUG, module, fmt, args);
    va_end(args);
}

void Logger::verbose(const char* module, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    log(LOG_LEVEL_VERBOSE, module, fmt, args);
    va_end(args);
}
