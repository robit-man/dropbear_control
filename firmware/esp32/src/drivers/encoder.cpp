#include "encoder.h"
#include <Arduino.h>

Encoder* Encoder::_instance = nullptr;

Encoder::Encoder(uint8_t pinA, uint8_t pinB, uint8_t pinZ)
    : _pinA(pinA), _pinB(pinB), _pinZ(pinZ),
      _position(0), _lastTime(0), _lastPosition(0),
      _resolution(16384), _homeDetected(false), _state(0) {
    _instance = this;
}

bool Encoder::init() {
    pinMode(_pinA, INPUT_PULLUP);
    pinMode(_pinB, INPUT_PULLUP);
    if (_pinZ != 255) {
        pinMode(_pinZ, INPUT_PULLUP);
    }

    attachInterrupt(digitalPinToInterrupt(_pinA), onInterruptA, CHANGE);
    attachInterrupt(digitalPinToInterrupt(_pinB), onInterruptB, CHANGE);
    if (_pinZ != 255) {
        attachInterrupt(digitalPinToInterrupt(_pinZ), onInterruptZ, FALLING);
    }

    _lastTime = micros();
    _lastPosition = 0;
    _position = 0;
    _homeDetected = false;

    return true;
}

void Encoder::deinit() {
    detachInterrupt(digitalPinToInterrupt(_pinA));
    detachInterrupt(digitalPinToInterrupt(_pinB));
    if (_pinZ != 255) {
        detachInterrupt(digitalPinToInterrupt(_pinZ));
    }
}

int32_t Encoder::getPosition() {
    return _position;
}

float Encoder::getVelocity() {
    uint32_t currentTime = micros();
    uint32_t deltaTime = currentTime - _lastTime;

    if (deltaTime == 0) return 0.0f;

    int32_t deltaPosition = _position - _lastPosition;
    float velocity = (float)deltaPosition / (float)deltaTime * 1000000.0f;

    _lastTime = currentTime;
    _lastPosition = _position;

    return velocity;
}

bool Encoder::getHome() {
    return _homeDetected;
}

void Encoder::resetPosition() {
    _position = 0;
    _lastPosition = 0;
}

void Encoder::setResolution(uint16_t resolution) {
    _resolution = resolution;
}

void IRAM_ATTR Encoder::onInterruptA() {
    if (_instance == nullptr) return;

    uint8_t currentState = (digitalRead(_instance->_pinA) << 1) | digitalRead(_instance->_pinB);
    uint8_t prevState = _instance->_state;

    _instance->_state = currentState;

    uint8_t stateChange = (prevState << 2) | currentState;

    switch (stateChange) {
        case 0b0111:
        case 0b1110:
        case 0b1000:
        case 0b0001:
            _instance->_position++;
            break;
        case 0b1011:
        case 0b1101:
        case 0b0100:
        case 0b0010:
            _instance->_position--;
            break;
        default:
            break;
    }
}

void IRAM_ATTR Encoder::onInterruptB() {
    onInterruptA();
}

void IRAM_ATTR Encoder::onInterruptZ() {
    if (_instance == nullptr) return;
    _instance->_homeDetected = true;
    _instance->_position = 0;
}
