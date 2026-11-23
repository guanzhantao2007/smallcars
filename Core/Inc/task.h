#ifndef TASK_H
#define TASK_H

#include "main.h"
//创建任务状态枚举
typedef enum {
    TASK_BENGIN = 0U, //任务初始化状态
    TASK_RUNNING=1U,   //任务运行状态
    LINE_STATE =2U,     //循迹状态
    LINE_STOP=3U,      //循迹停止状态
    TASK_STOP=4U,      //任务停止状态
    TASK_ERROR=5U      //任务错误状态
} TaskState_t;


HAL_StatusTypeDef Task_Init(void);
TaskState_t Task1_Run(void);
void Task1_UartIdleCallback(void);
void Task1_UartError(void);
TaskState_t Task2_Run(void);
TaskState_t Task3_Run(void);
TaskState_t Task4_Run(void);
TaskState_t Task5_Run(void);
TaskState_t Task6_Run(void);

//-------------------------速度环调度接口（motor_id 用 1~4）-------------------
#define TASK_MOTOR_COUNT 4U

/* 主循环每轮调用，内部按 10 ms 节拍闭环四个轮子。不阻塞。 */
void Task_MotorControl_Update(void);
/* 使能速度环：目标为 0 的轮子会被填成 BASE_SPEED。 */
void Task_MotorControl_Start(void);
/* 停止：四轮目标清零并刹车（下一次 Update 生效）。 */
void Task_MotorControl_Stop(void);
/* 写一个轮子的目标速度，单位 mm/s，负数按 0 处理。 */
void Task_MotorControl_SetTarget(uint8_t motor_id, float target_mm_s);
/* 读回目标速度 / 实测速度，单位都是 mm/s；motor_id 越界返回 0。 */
float Task_MotorControl_GetTarget(uint8_t motor_id);
float Task_MotorControl_GetActual(uint8_t motor_id);

#endif
