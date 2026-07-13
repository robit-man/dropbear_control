#pragma once

#include <stdint.h>
#include <stdbool.h>

// Motor status (defined in motor_driver.h)
// MOTOR_STATUS_IDLE = 0
// MOTOR_STATUS_ENABLED
// MOTOR_STATUS_RUNNING
// MOTOR_STATUS_FAULT
// MOTOR_STATUS_DISABLED

// Protocol types (use PROTO_ prefix to avoid macro conflicts)
typedef enum {
    PROTO_CAN = 0,
    PROTO_RS485,
    PROTO_ETHERCAT,
    PROTO_COUNT
} ProtocolType;

// Motor series
typedef enum {
    MOTOR_SERIES_RMD_X = 0,
    MOTOR_SERIES_RH,
    MOTOR_SERIES_CEM,
    MOTOR_SERIES_RMD_H,
    MOTOR_SERIES_RMD_L,
    MOTOR_SERIES_FL,
    MOTOR_SERIES_COUNT
} MotorSeries;

// Gearbox type
typedef enum {
    GEARBOX_PLANETARY = 0,
    GEARBOX_HARMONIC,
    GEARBOX_DIRECT,
    GEARBOX_CYCLOID,
    GEARBOX_LINEAR,
    GEARBOX_COUNT
} GearboxType;

// Drive type
typedef enum {
    DRIVE_STANDARD = 0,
    DRIVE_BRAKE,
    DRIVE_COUNT
} DriveType;

// Communication type (use COMM_ prefix to avoid macro conflicts)
typedef enum {
    COMM_CAN = 0,
    COMM_RS485,
    COMM_ETHERCAT,
    COMM_COUNT
} Communication;

// Frame types
typedef enum {
    FRAME_TYPE_STATUS_REPORT = 0x01,
    FRAME_TYPE_POSITION_CMD = 0x02,
    FRAME_TYPE_VELOCITY_CMD = 0x03,
    FRAME_TYPE_TORQUE_CMD = 0x04,
    FRAME_TYPE_PARAM_READ = 0x05,
    FRAME_TYPE_PARAM_WRITE = 0x06,
    FRAME_TYPE_HEARTBEAT = 0x07,
    FRAME_TYPE_FIRMWARE_UPDATE = 0x08
} FrameType;

// Unified frame structure (64 bytes)
typedef struct {
    uint8_t header[2]; // 0xAA 0x55
    uint8_t frame_type;
    uint8_t node_id;
    uint8_t reserved[2];
    uint32_t timestamp;
    uint8_t payload[56];
    uint16_t crc16;
} Frame;

// Motor configuration
typedef struct {
    ProtocolType protocol;
    MotorSeries motorSeries;
    uint8_t motorId;
    uint32_t baudRate;
    float maxTorque;
    float maxVelocity;
    float kp;
    float ki;
    float kd;
} MotorConfig;
typedef struct {
    uint8_t motor_id;
    uint8_t status;
    int32_t position;
    int32_t velocity;
    int16_t torque;
    float temperature;
    uint32_t uptime;
    bool hasFault;
} StatusReport;

// Command structure
typedef struct {
    uint8_t motor_id;
    uint8_t command_type;
    int32_t value;
    uint8_t data[32];
    uint8_t data_length;
} Command;

// Motor state
typedef enum {
    MOTOR_STATE_IDLE = 0,
    MOTOR_STATE_READY,
    MOTOR_STATE_ENABLED,
    MOTOR_STATE_RUNNING,
    MOTOR_STATE_FAULT,
    MOTOR_STATE_DISABLED,
    MOTOR_STATE_POSITION_CONTROL,
    MOTOR_STATE_VELOCITY_CONTROL,
    MOTOR_STATE_TORQUE_CONTROL
} MotorState;

// Fault codes
typedef enum {
    FAULT_NONE = 0,
    FAULT_ENCODER,
    FAULT_COMMUNICATION,
    FAULT_MOTOR_DRIVER,
    FAULT_HARDWARE,
    FAULT_COUNT
} FaultCode;

// PID Controller
typedef struct {
    float kp, ki, kd;
    float integral;
    float derivative;
    float output;
    float setpoint;
    float error;
    float prev_error;
    
    void reset() {
        integral = 0;
        derivative = 0;
        output = 0;
        prev_error = 0;
    }
    
    float compute(float setpoint, float measurement) {
        error = setpoint - measurement;
        integral += error;
        derivative = error - prev_error;
        output = kp * error + ki * integral + kd * derivative;
        prev_error = error;
        return output;
    }
} PIDController;

class CommunicationInterface {
public:
    virtual bool initialize() = 0;
    virtual bool send(const uint8_t* data, uint8_t length) = 0;
    virtual uint8_t receive(uint8_t* buffer, uint8_t max_length) = 0;
    virtual void process() = 0;
    virtual ~CommunicationInterface() {}
};

// Constants
#define MAX_MOTORS 8
#define MAX_FRAME_SIZE 64
#define DEFAULT_BITRATE 500000
#define DEFAULT_BAUDRATE 115200
#define DEFAULT_CYCLE_TIME_US 1000
#define CONTROL_LOOP_PERIOD_US 1000
