#ifndef OLED_H
#define OLED_H

#include "stm32f4xx_hal.h"
#include <stdint.h>

#define OLED_I2C_ADDR_7BIT 0x3CU
#define OLED_COLUMN_OFFSET 0U
#define OLED_6X8 6U
#define OLED_8X16 8U

/* 初始化 OLED；本工程 PB10/PB11 对应 I2C2，传入 &hi2c2。 */
HAL_StatusTypeDef OLED_Init(I2C_HandleTypeDef *hi2c);

/* 将显存中的图像刷新到屏幕，并返回 HAL 传输状态。 */
HAL_StatusTypeDef OLED_Update(void);

/* 清空显存；需要调用 OLED_Update 才会更新屏幕。 */
void OLED_Clear(void);

/* 在指定像素坐标绘制 ASCII 字符，支持 OLED_6X8 和 OLED_8X16。 */
void OLED_ShowChar(int16_t x, int16_t y, char ch, uint8_t font);

/* 在指定像素坐标绘制 ASCII 字符串，换行符会移动到下一行。 */
void OLED_ShowString(int16_t x, int16_t y, const char *str, uint8_t font);

/* 按指定位数显示无符号整数，不足位数时在左侧补零。 */
void OLED_ShowNum(int16_t x, int16_t y, uint32_t number,
                  uint8_t length, uint8_t font);

#endif
