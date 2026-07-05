#pragma once

#include <Arduino.h>
#include <stdint.h>

class Encoder {
public:
    Encoder(uint8_t pinA, uint8_t pinB, uint8_t pinZ = 255);
    ~Encoder() = default;

    bool init();
    void deinit();

    int32_t getPosition();
    float getVelocity();
    bool getHome();

    void resetPosition();
    void setResolution(uint16_t resolution);

private:
    static void IRAM_ATTR onInterruptA();
    static void IRAM_ATTR onInterruptB();
    static void IRAM_ATTR onInterruptZ();

    uint8_t _pinA;
    uint8_t _pinB;
    uint8_t _pinZ;
    int32_t _position;
    uint32_t _lastTime;
    int32_t _lastPosition;
    uint16_t _resolution;
    bool _homeDetected;
    volatile uint8_t _state;

    static Encoder* _instance;
};
