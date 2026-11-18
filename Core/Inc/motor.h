#ifndef __MOTOR_H
#define __MOTOR_H

#include "stm32f4xx_hal.h"

//创建电机结构体
typedef struct {
    const int motor_id; // 电机编号
    double speed; // 目标线速度（毫米/秒，100毫米/秒映射为满量程）
    int dir;     // 电机方向：1前进，0后退
    float p;
    float i;
    float d;
} Motor;
//目前电机支持的最大速度是 100毫米/秒，超过这个速度会被限制为满量程。

void motor_init(void);
uint16_t speed2pluse(float speed);
void motor_run(Motor motor);
/* Call periodically; sampling and PID calculations are handled in motor.c. */
void motor_pid_run(Motor motor);

#endif
