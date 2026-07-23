#pragma once

#include <Arduino.h>
#include "serial_frame.h"
#include "motor_controller.h"

// SerialBridge: parses the 64-byte unified protocol frames
// (contracts/PROTOCOLS_CONTRACT.md section 3) arriving on a Stream — the ESP32
// USB CDC Serial port, which is the WebSerial endpoint the web dashboard uses —
// and dispatches them to a MotorController. It also emits STATUS_REPORT frames
// back so the dashboard can visualize live state.
//
// NOTE: Logger also writes human-readable text to the same Serial stream. The
// dashboard's WebSerial transport resyncs on 64-byte boundaries and ignores
// non-frame bytes, so interleaved log lines are tolerated (they just shift
// frame alignment). For a clean machine-only link, route frames to a separate
// UART (Serial1/Serial2) and point the dashboard there.
class SerialBridge {
public:
    SerialBridge(Stream& stream, MotorController& controller, uint8_t motorId);
    void begin();
    void update();            // call every loop: read + dispatch + periodic status
    void sendStatusReport();  // emit one STATUS_REPORT frame now
    void sendHeartbeat();

private:
    void _ingest(uint8_t b);
    void _dispatch(const serial_frame::Frame& f);
    void _emit(const serial_frame::Frame& f);

    Stream* _stream;
    MotorController* _controller;
    uint8_t _motorId;
    uint8_t _buf[serial_frame::FRAME_SIZE];
    uint8_t _idx;
    uint32_t _lastStatusMs;
    uint8_t _seq;
};
