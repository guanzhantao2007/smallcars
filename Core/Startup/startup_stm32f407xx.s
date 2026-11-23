/**
  ******************************************************************************
  * @file      startup_stm32f407xx.s
  * @brief     STM32F407xx 向量表与启动代码 —— GNU as (arm-none-eabi-gcc) 语法
  *
  * 为什么需要这个文件：
  *   MDK-ARM/startup_stm32f407xx.s 是 ARMCC(armasm) 语法，GCC 编不了。
  *   两者做同一件事：定义中断向量表、给出栈顶、上电后跑 Reset_Handler。
  *   ARMCC 版保持原样不动（Keil 仍可用），本文件仅供 GCC 链路使用。
  *
  * 硬件事实：STM32F407VET6 / Flash 512K @0x08000000 / SRAM 128K @0x20000000
  * 向量个数：16 个系统异常 + 82 个外设中断 (IRQ0~IRQ81)
  ******************************************************************************
  */

  .syntax unified
  .cpu cortex-m4
  .fpu softvfp
  .thumb

.global g_pfnVectors
.global Default_Handler

/**
 * Reset 后第一段代码。
 * 不用 C 库的 .data 搬运机制，手工搬 + 手工清 bss，避免依赖链接脚本的 AT 语法行为。
 */
  .section .text.Reset_Handler
  .weak Reset_Handler
  .type Reset_Handler, %function
Reset_Handler:
  ldr   sp, =_estack            /* 设置栈顶 */

/* 把 .data 初值从 Flash 拷到 RAM */
  ldr   r0, =_sdata
  ldr   r1, =_edata
  ldr   r2, =_sidata
  movs  r3, #0
  b     LoopCopyDataInit

CopyDataInit:
  ldr   r4, [r2, r3]
  str   r4, [r0, r3]
  adds  r3, r3, #4

LoopCopyDataInit:
  adds  r4, r0, r3
  cmp   r4, r1
  bcc   CopyDataInit

/* .bss 清零 */
  ldr   r2, =_sbss
  ldr   r4, =_ebss
  movs  r3, #0
  b     LoopFillZerobss

FillZerobss:
  str   r3, [r2]
  adds  r2, r2, #4

LoopFillZerobss:
  cmp   r2, r4
  bcc   FillZerobss

/* SystemInit 在 Core/Src/system_stm32f4xx.c */
  bl    SystemInit
/* 执行 C 库的初始化函数表（.init_array），__attribute__((constructor)) 靠它 */
  bl    __libc_init_array
  bl    main

LoopForever:
  b     LoopForever
  .size Reset_Handler, .-Reset_Handler

/**
 * 未实现的中断统一停在这里。调试时若卡死在 Default_Handler，
 * 用调试器看 IPSR 寄存器或 LR 就能知道是哪个中断漏了实现。
 */
  .section .text.Default_Handler,"ax",%progbits
Default_Handler:
Infinite_Loop:
  b     Infinite_Loop
  .size Default_Handler, .-Default_Handler

/******************************************************************************
 * 向量表：必须放 Flash 最前面，地址 0x08000000
 ******************************************************************************/
  .section .isr_vector,"a",%progbits
  .type g_pfnVectors, %object

g_pfnVectors:
  .word _estack
  .word Reset_Handler
  .word NMI_Handler
  .word HardFault_Handler
  .word MemManage_Handler
  .word BusFault_Handler
  .word UsageFault_Handler
  .word 0
  .word 0
  .word 0
  .word 0
  .word SVC_Handler
  .word DebugMon_Handler
  .word 0
  .word PendSV_Handler
  .word SysTick_Handler

/* 外部中断 IRQ0 ~ IRQ81 */
  .word WWDG_IRQHandler
  .word PVD_IRQHandler
  .word TAMP_STAMP_IRQHandler
  .word RTC_WKUP_IRQHandler
  .word FLASH_IRQHandler
  .word RCC_IRQHandler
  .word EXTI0_IRQHandler
  .word EXTI1_IRQHandler
  .word EXTI2_IRQHandler
  .word EXTI3_IRQHandler
  .word EXTI4_IRQHandler
  .word DMA1_Stream0_IRQHandler
  .word DMA1_Stream1_IRQHandler
  .word DMA1_Stream2_IRQHandler
  .word DMA1_Stream3_IRQHandler
  .word DMA1_Stream4_IRQHandler
  .word DMA1_Stream5_IRQHandler
  .word DMA1_Stream6_IRQHandler
  .word ADC_IRQHandler
  .word CAN1_TX_IRQHandler
  .word CAN1_RX0_IRQHandler
  .word CAN1_RX1_IRQHandler
  .word CAN1_SCE_IRQHandler
  .word EXTI9_5_IRQHandler
  .word TIM1_BRK_TIM9_IRQHandler
  .word TIM1_UP_TIM10_IRQHandler
  .word TIM1_TRG_COM_TIM11_IRQHandler
  .word TIM1_CC_IRQHandler
  .word TIM2_IRQHandler
  .word TIM3_IRQHandler
  .word TIM4_IRQHandler
  .word I2C1_EV_IRQHandler
  .word I2C1_ER_IRQHandler
  .word I2C2_EV_IRQHandler
  .word I2C2_ER_IRQHandler
  .word SPI1_IRQHandler
  .word SPI2_IRQHandler
  .word USART1_IRQHandler
  .word USART2_IRQHandler
  .word USART3_IRQHandler
  .word EXTI15_10_IRQHandler
  .word RTC_Alarm_IRQHandler
  .word OTG_FS_WKUP_IRQHandler
  .word TIM8_BRK_TIM12_IRQHandler
  .word TIM8_UP_TIM13_IRQHandler
  .word TIM8_TRG_COM_TIM14_IRQHandler
  .word TIM8_CC_IRQHandler
  .word DMA1_Stream7_IRQHandler
  .word FSMC_IRQHandler
  .word SDIO_IRQHandler
  .word TIM5_IRQHandler
  .word SPI3_IRQHandler
  .word UART4_IRQHandler
  .word UART5_IRQHandler
  .word TIM6_DAC_IRQHandler
  .word TIM7_IRQHandler
  .word DMA2_Stream0_IRQHandler
  .word DMA2_Stream1_IRQHandler
  .word DMA2_Stream2_IRQHandler
  .word DMA2_Stream3_IRQHandler
  .word DMA2_Stream4_IRQHandler
  .word ETH_IRQHandler
  .word ETH_WKUP_IRQHandler
  .word CAN2_TX_IRQHandler
  .word CAN2_RX0_IRQHandler
  .word CAN2_RX1_IRQHandler
  .word CAN2_SCE_IRQHandler
  .word OTG_FS_IRQHandler
  .word DMA2_Stream5_IRQHandler
  .word DMA2_Stream6_IRQHandler
  .word DMA2_Stream7_IRQHandler
  .word USART6_IRQHandler
  .word I2C3_EV_IRQHandler
  .word I2C3_ER_IRQHandler
  .word OTG_HS_EP1_OUT_IRQHandler
  .word OTG_HS_EP1_IN_IRQHandler
  .word OTG_HS_WKUP_IRQHandler
  .word OTG_HS_IRQHandler
  .word DCMI_IRQHandler
  .word CRYP_IRQHandler
  .word HASH_RNG_IRQHandler
  .word FPU_IRQHandler

  .size g_pfnVectors, .-g_pfnVectors

/**
 * 所有中断/异常默认指向 Default_Handler（弱符号）。
 * 哪个中断在 stm32f4xx_it.c 里写了同名函数，就会覆盖这里的弱定义。
 */
  .macro IRQ handler
  .weak  \handler
  .thumb_set \handler,Default_Handler
  .endm

  IRQ NMI_Handler
  IRQ HardFault_Handler
  IRQ MemManage_Handler
  IRQ BusFault_Handler
  IRQ UsageFault_Handler
  IRQ SVC_Handler
  IRQ DebugMon_Handler
  IRQ PendSV_Handler
  IRQ SysTick_Handler

  IRQ WWDG_IRQHandler
  IRQ PVD_IRQHandler
  IRQ TAMP_STAMP_IRQHandler
  IRQ RTC_WKUP_IRQHandler
  IRQ FLASH_IRQHandler
  IRQ RCC_IRQHandler
  IRQ EXTI0_IRQHandler
  IRQ EXTI1_IRQHandler
  IRQ EXTI2_IRQHandler
  IRQ EXTI3_IRQHandler
  IRQ EXTI4_IRQHandler
  IRQ DMA1_Stream0_IRQHandler
  IRQ DMA1_Stream1_IRQHandler
  IRQ DMA1_Stream2_IRQHandler
  IRQ DMA1_Stream3_IRQHandler
  IRQ DMA1_Stream4_IRQHandler
  IRQ DMA1_Stream5_IRQHandler
  IRQ DMA1_Stream6_IRQHandler
  IRQ ADC_IRQHandler
  IRQ CAN1_TX_IRQHandler
  IRQ CAN1_RX0_IRQHandler
  IRQ CAN1_RX1_IRQHandler
  IRQ CAN1_SCE_IRQHandler
  IRQ EXTI9_5_IRQHandler
  IRQ TIM1_BRK_TIM9_IRQHandler
  IRQ TIM1_UP_TIM10_IRQHandler
  IRQ TIM1_TRG_COM_TIM11_IRQHandler
  IRQ TIM1_CC_IRQHandler
  IRQ TIM2_IRQHandler
  IRQ TIM3_IRQHandler
  IRQ TIM4_IRQHandler
  IRQ I2C1_EV_IRQHandler
  IRQ I2C1_ER_IRQHandler
  IRQ I2C2_EV_IRQHandler
  IRQ I2C2_ER_IRQHandler
  IRQ SPI1_IRQHandler
  IRQ SPI2_IRQHandler
  IRQ USART1_IRQHandler
  IRQ USART2_IRQHandler
  IRQ USART3_IRQHandler
  IRQ EXTI15_10_IRQHandler
  IRQ RTC_Alarm_IRQHandler
  IRQ OTG_FS_WKUP_IRQHandler
  IRQ TIM8_BRK_TIM12_IRQHandler
  IRQ TIM8_UP_TIM13_IRQHandler
  IRQ TIM8_TRG_COM_TIM14_IRQHandler
  IRQ TIM8_CC_IRQHandler
  IRQ DMA1_Stream7_IRQHandler
  IRQ FSMC_IRQHandler
  IRQ SDIO_IRQHandler
  IRQ TIM5_IRQHandler
  IRQ SPI3_IRQHandler
  IRQ UART4_IRQHandler
  IRQ UART5_IRQHandler
  IRQ TIM6_DAC_IRQHandler
  IRQ TIM7_IRQHandler
  IRQ DMA2_Stream0_IRQHandler
  IRQ DMA2_Stream1_IRQHandler
  IRQ DMA2_Stream2_IRQHandler
  IRQ DMA2_Stream3_IRQHandler
  IRQ DMA2_Stream4_IRQHandler
  IRQ ETH_IRQHandler
  IRQ ETH_WKUP_IRQHandler
  IRQ CAN2_TX_IRQHandler
  IRQ CAN2_RX0_IRQHandler
  IRQ CAN2_RX1_IRQHandler
  IRQ CAN2_SCE_IRQHandler
  IRQ OTG_FS_IRQHandler
  IRQ DMA2_Stream5_IRQHandler
  IRQ DMA2_Stream6_IRQHandler
  IRQ DMA2_Stream7_IRQHandler
  IRQ USART6_IRQHandler
  IRQ I2C3_EV_IRQHandler
  IRQ I2C3_ER_IRQHandler
  IRQ OTG_HS_EP1_OUT_IRQHandler
  IRQ OTG_HS_EP1_IN_IRQHandler
  IRQ OTG_HS_WKUP_IRQHandler
  IRQ OTG_HS_IRQHandler
  IRQ DCMI_IRQHandler
  IRQ CRYP_IRQHandler
  IRQ HASH_RNG_IRQHandler
  IRQ FPU_IRQHandler

  .end
