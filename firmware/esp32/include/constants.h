#pragma once

#include <math.h>

// Physical constants
#ifndef PI
#define PI                  3.14159265358979323846f
#endif
#ifndef DEG_TO_RAD
#define DEG_TO_RAD          (PI / 180.0f)
#endif
#ifndef RAD_TO_DEG
#define RAD_TO_DEG          (180.0f / PI)
#endif

// Encoder resolutions
#ifndef ENCODER_14BIT
#define ENCODER_14BIT       16384
#endif
#ifndef ENCODER_17BIT
#define ENCODER_17BIT       131072
#endif
#ifndef ENCODER_18BIT
#define ENCODER_18BIT       262144
#endif

// Default PID gains
#define DEFAULT_KP          1.0f
#define DEFAULT_KI          0.1f
#define DEFAULT_KD          0.01f

// Default limits
#define DEFAULT_MAX_VELOCITY    1000.0f    // rpm
#define DEFAULT_MAX_TORQUE      1.0f       // Nm
