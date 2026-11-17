#include "motor.h"
#include "encoder.h"
#include "tim.h"

#define MOTOR_SPEED_FULL_SCALE_MM_S 100.0f
#define MOTOR_SPEED_SAMPLE_PERIOD_MS 10U
#define MOTOR_COUNT 4U

typedef struct {
    float integral;
    float previous_measurement;
    uint32_t previous_tick;
    uint8_t initialized;
} MotorPidState;

static MotorPidState motor_pid_states[MOTOR_COUNT];

void motor_init(void)
{
    uint32_t index;

    if (HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1) != HAL_OK ||
        HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2) != HAL_OK ||
        HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_3) != HAL_OK ||
        HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_4) != HAL_OK ||
        HAL_TIM_PWM_Start(&htim9, TIM_CHANNEL_1) != HAL_OK ||
        HAL_TIM_PWM_Start(&htim9, TIM_CHANNEL_2) != HAL_OK ||
        HAL_TIM_PWM_Start(&htim12, TIM_CHANNEL_1) != HAL_OK ||
        HAL_TIM_PWM_Start(&htim12, TIM_CHANNEL_2) != HAL_OK) {
        Error_Handler();
    }

    for (index = 0U; index < MOTOR_COUNT; ++index) {
        motor_pid_states[index].integral = 0.0f;
        motor_pid_states[index].previous_measurement = 0.0f;
        motor_pid_states[index].previous_tick = HAL_GetTick();
        motor_pid_states[index].initialized = 0U;
    }
}

uint16_t speed2pluse(float speed)
{
    uint32_t period = __HAL_TIM_GET_AUTORELOAD(&htim1);

    if (speed < 0.0f) {
        speed = -speed;
    }
    if (!(speed > 0.0f) || period == 0U) {
        return 0U;
    }
    if (speed >= MOTOR_SPEED_FULL_SCALE_MM_S) {
        return (period > UINT16_MAX) ? UINT16_MAX : (uint16_t)period;
    }

    return (uint16_t)((speed * (float)period / MOTOR_SPEED_FULL_SCALE_MM_S) + 0.5f);//为什么要加0.5f？因为这是四舍五入的技巧，将浮点数转换为整数时，直接截断会导致精度损失，而加上0.5f后再取整，可以实现四舍五入的效果，从而得到更准确的脉冲值。
}


void motor_run(Motor motor)
{
    TIM_HandleTypeDef *timer;
    uint32_t in1_channel;
    uint32_t in2_channel;
    uint16_t pulse;

    if (motor.dir != 0 && motor.dir != 1) {
        Error_Handler();
        return;
    }

    switch (motor.motor_id) {
    case 1:
        timer = &htim1;
        in1_channel = TIM_CHANNEL_1;
        in2_channel = TIM_CHANNEL_2;
        break;
    case 2:
        timer = &htim1;
        in1_channel = TIM_CHANNEL_3;
        in2_channel = TIM_CHANNEL_4;
        break;
    case 3:
        timer = &htim9;
        in1_channel = TIM_CHANNEL_1;
        in2_channel = TIM_CHANNEL_2;
        break;
    case 4:
        timer = &htim12;
        in1_channel = TIM_CHANNEL_1;
        in2_channel = TIM_CHANNEL_2;
        break;
    default:
        Error_Handler();
        return;
    }

    pulse = speed2pluse((float)motor.speed);
    __HAL_TIM_SET_COMPARE(timer, in1_channel, (motor.dir == 1) ? pulse : 0U);
    __HAL_TIM_SET_COMPARE(timer, in2_channel, (motor.dir == 0) ? pulse : 0U);
}

void motor_pid_run(Motor motor)
{
    uint32_t index;
    uint32_t current_tick;
    uint32_t elapsed_ms;
    float target_speed;
    float dt_seconds;
    float measured_speed;
    float error;
    float derivative;
    float candidate_integral;
    float output;
    float raw_output;
    MotorPidState *state;

    if (motor.motor_id < 1 || motor.motor_id > (int)MOTOR_COUNT ||
        (motor.dir != 0 && motor.dir != 1) ||
        !(motor.speed >= 0.0) ||
        !(motor.p >= 0.0f) ||
        !(motor.i >= 0.0f) ||
        !(motor.d >= 0.0f)) {
        Error_Handler();
        return;
    }

    index = (uint32_t)(motor.motor_id - 1);
    state = &motor_pid_states[index];
    current_tick = HAL_GetTick();
    elapsed_ms = (uint32_t)(current_tick - state->previous_tick);
    if (elapsed_ms < MOTOR_SPEED_SAMPLE_PERIOD_MS) {
        return;
    }

    dt_seconds = (float)elapsed_ms / 1000.0f;
    state->previous_tick = current_tick;

    target_speed = (motor.speed >= MOTOR_SPEED_FULL_SCALE_MM_S)
                       ? MOTOR_SPEED_FULL_SCALE_MM_S
                       : (float)motor.speed;
    measured_speed = encoder_get_speed(motor.motor_id);
    if (motor.dir == 0) {
        measured_speed = -measured_speed;
    }

    if (state->initialized == 0U) {
        state->previous_measurement = measured_speed;
        state->initialized = 1U;
    }

    if (target_speed == 0.0f) {
        state->integral = 0.0f;
        state->previous_measurement = measured_speed;
        motor.speed = 0.0;
        motor_run(motor);
        return;
    }

    error = target_speed - measured_speed;
    derivative = -(measured_speed - state->previous_measurement) / dt_seconds;
    candidate_integral = state->integral + error * dt_seconds;
    raw_output = motor.p * error +
                 motor.i * candidate_integral +
                 motor.d * derivative;

    if ((raw_output >= 0.0f && raw_output <= MOTOR_SPEED_FULL_SCALE_MM_S) ||
        (raw_output > MOTOR_SPEED_FULL_SCALE_MM_S && error < 0.0f) ||
        (raw_output < 0.0f && error > 0.0f)) {
        state->integral = candidate_integral;
    }

    output = motor.p * error +
             motor.i * state->integral +
             motor.d * derivative;
    if (output < 0.0f) {
        output = 0.0f;
    } else if (output > MOTOR_SPEED_FULL_SCALE_MM_S) {
        output = MOTOR_SPEED_FULL_SCALE_MM_S;
    }

    state->previous_measurement = measured_speed;
    motor.speed = output;
    motor_run(motor);
}

