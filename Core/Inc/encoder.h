#ifndef ENCODER_H
#define ENCODER_H

#include "stm32f4xx_hal.h"

#define ENCODER_TIMEBASE_HZ 100U

void encoder_init(void);
void encoder_timebase_tick(void);
/* 返回该 motor_id 的线速度（mm/s），正值表示前进。 */
float encoder_get_speed(int motor_id);

#endif
