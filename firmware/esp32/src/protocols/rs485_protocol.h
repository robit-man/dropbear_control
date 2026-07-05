#pragma once

#include "pal.h"

class RS485Protocol : public IProtocol {
public:
    RS485Protocol(uint8_t nodeId);
    ~RS485Protocol() override = default;
    
    bool init() override;
    void deinit() override;
    
    bool send(const Frame& frame) override;
    bool receive(Frame& frame, uint32_t timeout_ms = 100) override;
    
    ProtocolType getType() const override { return PROTOCOL_RS485; }
    uint8_t getNodeId() const override { return _nodeId; }
    void setNodeId(uint8_t id) override { _nodeId = id; }
    
    // RS485-specific
    void setBaudRate(uint32_t baud);
    void setParity(uint8_t parity);
    void setStopBits(uint8_t stopBits);
    
private:
    uint8_t _nodeId;
    uint32_t _baudRate;
    uint8_t _parity;
    uint8_t _stopBits;
};
