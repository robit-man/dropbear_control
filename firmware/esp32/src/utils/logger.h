/**
 * Logger Utilities - Header
 *
 * Serial logging with levels
 */

#ifndef LOGGER_H
#define LOGGER_H

#include <Arduino.h>
#include <stdarg.h>

// Log levels
#define LOG_LEVEL_VERBOSE 0
#define LOG_LEVEL_DEBUG   1
#define LOG_LEVEL_INFO    2
#define LOG_LEVEL_WARN    3
#define LOG_LEVEL_ERROR   4

class Logger {
public:
    static void init(Stream& stream);
    static void info(const char* module, const char* fmt, ...);
    static void warn(const char* module, const char* fmt, ...);
    static void error(const char* module, const char* fmt, ...);
    static void debug(const char* module, const char* fmt, ...);
    static void verbose(const char* module, const char* fmt, ...);
    
    static void setLevel(uint8_t level);
    static uint8_t getLevel();

private:
    static Stream* _stream;
    static bool _initialized;
    static uint8_t _level;
    static uint32_t _timestamp;
    
    static void log(uint8_t level, const char* module, const char* fmt, ...);
};

#endif // LOGGER_H
