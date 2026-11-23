# PROJECT.md — 单协小车（STM32F407）项目事实清单

> **这份文件是唯一真值来源。** 代码与本文冲突时，以代码为准，并立刻修正本文。
> AI 协作前必须先读完本文；改任何引脚、时钟、定时器、参数，**先改本文，再改代码**。
>
> 最后核对：2026-11-23 21:40（依据 `smart_cars.ioc`、`Core/Inc/main.h`、`Core/Src/tim.c`、`Core/Src/task.c`、`Core/Src/motor.c`、原理图 `原理图(1).pdf`、MG310 官方规格图）

> ## 代码基线（2026-11-23 车主决定：以最新提交为准）
>
> **当前工作分支：`imu-dlpf-20hz`，HEAD = `2a5afd2 视觉`（2026-11-20）。** 跟踪 `origin/imu-dlpf-20hz`。
>
> - `main`（`19a734b Initial project upload`）**保留不动**，作为干净回退点。切回命令：`git checkout main`
> - 历史链：`Initial project upload` → `imu增加硬件滤波` → `实现通信` → `111111` → `修改一些电机错误` → `去哈尔滨前的一版` → `视觉`
> - 本文档 §2 / §3 / §7.1 / §7.2（硬件事实）在新旧两条分支上都成立；§5 / §6 / §10（代码现状）**只描述 `imu-dlpf-20hz`**。
> - **`main` 分支的描述一律不要再引用**，一切以当前分支为准。
>
> 相对 `main`，本分支带来的实质变化：
>
> | 内容 | 文件 | 影响本文档 |
> |---|---|---|
> | `task.c`(432) + `task.h`，状态机 / Task1~6 / 串口帧解析 / 循迹 | 新增 | §4、§5、§10 |
> | 电机量程**从 mm/s 改为百分比**，`MOTOR_SPEED_FULL_SCALE_MM_S` 已删除 | `motor.c` | §6、§7.3（旧文档的"差 12 倍"**已不适用**） |
> | 串口 DMA + 空闲中断 + 环形 FIFO | `dma.c/h`、`usart.c` | §2.3、§4 |
> | `main.c` 瘦身到 248 行，业务全进 `task.c` | `main.c` | §5（正好是 AGENTS.md R14 想要的结构） |
> | 编码器**计数符号翻了两路**（motor1、motor3 由 +1 变 -1） | `encoder.c` | §2.2（已更新） |
> | 视觉上位机 Python（循迹/车位识别） | `camera/` | §10 |
> | `main.h` 加 `all_task_state_t` 枚举；`.ioc` 加 DMA 与 USART1 接收 | 配置 | §2.3 |

---

## 0. 一句话

四驱（4 轮独立驱动 + 4 路编码器）STM32 小车，当前目标：**速度环（每轮独立闭环）+ 角度环（yaw 定向闭环）**。

当前代码状态：**速度环、循迹、串口收发、视觉接口的代码都已存在，但 `main.c` 里 `Task1_Run()` 与 4 个 `motor_pid_run()` 全被注释掉 —— 电机当前完全不受控，主循环只剩每 1 秒打印 motor1 转速。** 角度环尚不存在。
构建链路：**正从 Keil(MDK-ARM) 迁往 VSCode + CMake + GCC（待打通）**，详见 §8。

---

## 1. 硬件与工具链【核实】

| 项 | 值 | 来源 |
|---|---|---|
| MCU | STM32F407VET6，LQFP100 | `.ioc` `Mcu.CPN` |
| 外部晶振 | HSE 8 MHz（另有 LSE 32.768 kHz） | `.ioc` `RCC.HSE_VALUE` |
| 系统时钟 | SYSCLK 168 MHz（PLL M=8 N=336 P=2） | `.ioc` + `main.c SystemClock_Config` |
| APB1 / APB2 | 42 MHz / 84 MHz；对应定时器时钟 **84 / 168 MHz** | `.ioc` `APB1TimFreq_Value` |
| HAL 库 | STM32Cube FW_F4 V1.28.3 | `.ioc` `FirmwarePackage` |
| CubeMX | 6.14.1 | `.ioc` `MxCube.Version` |
| **构建链路（现行）** | **VSCode + CMake + Ninja + arm-none-eabi-gcc + OpenOCD + Cortex-Debug** | 2026-11-23 车主确定，见 `AGENTS.md` §2 |
| 烧录器 | ST-Link **与** CMSIS-DAP（DAP-Link）都要支持 | 2026-11-23 确认 |
| 遗留 Keil 工程 | MDK-ARM（ARMCC V5.06u5，`uAC6=0`，-O3），**仅作参照，不再维护** | `MDK-ARM/smart_cars.uvprojx` |
| 旧产物 | `MDK-ARM/smart_cars/smart_cars.axf` / `.hex` | `<OutputName>` |
| 堆 / 栈 | Heap 0x200 / Stack 0x400 | `.ioc` `ProjectManager` |
| 电源 | 12 V DC → SS34 防反 → F3（1 A 自恢复保险）→ 开关 → MSMP2307 降压 5 V | 原理图 |
| 驱动供电 | 电机驱动 VM = 12V_MAIN | 原理图 |

**⚠ 工具链不一致（真实风险）**：`.ioc` 里 `ProjectManager.CompilerLinker=GCC`，但 Keil 工程实际用 ARMCC。**用 CubeMX 重新生成代码可能覆盖/改坏 Keil 工程结构。** 除非任务明确要求，不要打开 CubeMX 重新生成。

---

## 2. 引脚表【核实】

### 2.1 电机 PWM（四路双通道正反转）

| 代码 motor_id | 物理位置 | 网络名 | MCU 引脚 | 定时器通道 |
|---|---|---|---|---|
| 1 | 左后 | AIN1 / AIN2 | **PE9 / PE11** | TIM1_CH1 / CH2 |
| 2 | 右后 | BIN1 / BIN2 | **PE13 / PE14** | TIM1_CH3 / CH4 |
| 3 | 左前 | CIN1 / CIN2 | **PE5 / PE6** | TIM9_CH1 / CH2 |
| 4 | 右前 | DIN1 / DIN2 | **PB14 / PB15** | TIM12_CH1 / CH2 |

**⚠ 这一处最容易被"顺手统一"改坏**：原理图上 `PE5` 的网标是 **AIN2_2**、`PE6` 是 **AIN1_2**，与驱动 1 的命名顺序相反。`motor.c` 里 motor3 把 `TIM9_CH1`(=PE5) 当作 in1 是**故意的硬件匹配**，不是笔误。**不要把它改成 AIN1 优先**，否则左前轮会反向。

### 2.2 编码器（4 路，编码器接口模式 TI12）

| motor_id | 位置 | 定时器 | CH1 引脚 | CH2 引脚 | 计数符号 |
|---|---|---|---|---|---|
| 1 | 左后 | TIM5（32 位） | PA0 `ENC_L_A` | PA1 `ENC_L_B` | **-1** |
| 2 | 右后 | TIM3 | PA6 `ENC_R_A` | PA7 `ENC_R_B` | **+1** |
| 3 | 左前 | TIM8 | PC6 `ENC_L2_A` | PC7 `ENC_L2_B` | **-1** |
| 4 | 右前 | TIM4 | PD12 `ENC_R2_B` | PD13 `ENC_R2_A` | **-1** |

- **符号在 `2a5afd2 视觉` 里被改过**：旧版是 `{+1, -1, +1, -1}`，现在 motor1 / motor3 翻成了 `-1`。**这是实测调出来的，不是笔误，不要"统一成 +1"。**
- `PA6` 在 `.ioc` 里**没有** GPIO_Label（只有 `ENC_R_B` 标了 PA7），`ENC_R_A = PA6` 由 `tim.c` 的 `GPIO_PIN_6|ENC_R_B_Pin` 与原理图网标双向确认。
- motor4 的 CH1 接的是 **B 相**（PD12）、CH2 接 A 相（PD13），顺序与 motor1/3 相反 —— 这是符号取 -1 的原因之一。
- **符号 ±1 跟物理安装方向绑定，属于调出来的经验值，不是算出来的。** 速度环正反馈跑飞时，第一个要查的就是这里。
- 方向还有**第二层**在 `motor.c`：`motor_run()` 里对 motor2/3/4 做了 `motor_direction = 1 - motor_direction` 的极性翻转（注释写着"Motor 1 is correctly oriented"）。**两层符号叠加，改任一层都要四轮一起验，不要单改一个。**

### 2.3 其他外设

| 功能 | 引脚 | 说明 |
|---|---|---|
| MPU6050 | I2C1：PB6(SCL) / PB7(SDA)，AD0 接 GND | 7 位地址 **0x68** |
| OLED | I2C2：PB10(SCL) / PB11(SDA) | `OLED_Init(&hi2c2)` |
| 蜂鸣器 | PC1 `FENGMING` | S8050 NPN 驱动，**高电平响** |
| LED1（红） | PB0 | 高电平亮 |
| LED2（绿） | PB1 | 高电平亮 |
| 按键 | key1=PE2 / key2=PE3 / key3=PE4 | 原理图 SW 编号与 key 编号**错位**：SW1=按键1、SW3=按键2、SW2=按键3。以 `main.h` 的 key 编号为准 |
| 串口 | USART1 PA9(PA10)；**USART2 PA2/PA3（`printf` 走这里）**；UART5 PC12/PD2；USART3 PC10/PC11（原理图有，CubeMX 未配置） | 全部 115200-8-N-1 |
| 电源指示灯 | VCC → R1 390Ω → LED1(XL-2012SURC) | **注意：原理图里有两个 "LED1"**，这个是电源灯，不受 MCU 控制 |

**【未知】舵机信号脚、电位器 ADC 引脚、视觉模块接口信号脚** —— 原理图文本里能读到接口存在，但读不到确定映射。需要看板子实物确认，不要猜。

### 2.4 编码器接线（MG310 GMR，PH2.0 六线）【核实】

| 线号 | 定义 | 接到 |
|---|---|---|
| 1 | 电机线 + | 驱动模块输出 |
| 2 | 编码器地线 | GND |
| 3 | 编码器输出 **B 相** | TIMx_CH2 |
| 4 | 编码器输出 **A 相** | TIMx_CH1 |
| 5 | 编码器电源 | 3.3 ~ 5 V |
| 6 | 电机线 − | 驱动模块输出 |

**注意：3 号是 B、4 号是 A，顺序与常见模块相反。** 按线号接，不要按"A 先 B 后"的直觉。编码器输出带上拉，无需外部上拉电阻。

参数与派生量见 `docs/MG310_电机参数速查.md`。

---

## 3. 定时器分配

| 定时器 | 用途 | PSC | ARR | 频率 | 类别 |
|---|---|---|---|---|---|
| TIM1 | 电机 1/2 PWM（4 通道） | 0 | 8399 | **20 kHz** | 【推得】168 MHz / 8400 |
| TIM9 | 电机 3 PWM（2 通道） | 0 | 8399 | **20 kHz** | 【推得】168 MHz / 8400 |
| TIM12 | 电机 4 PWM（2 通道） | 0 | 8399 | **10 kHz** | 【推得】84 MHz / 8400 |
| TIM3 / TIM4 / TIM8 | 编码器接口（16 位，ARR 65535） | 0 | 65535 | — | 【核实】 |
| TIM5 | 编码器接口（**32 位**，ARR 4294967295） | 0 | 2³²-1 | — | 【核实】 |
| TIM6 | 周期中断 → `IMU_Tick1ms()` | 8933 | 9 | **940 Hz** | 【推得】84 MHz/8934/10 |
| TIM7 | 周期中断 → `encoder_timebase_tick()` | 83 | 9999 | **100 Hz** | 【推得】84 MHz/84/10000 |

**⚠ 命名与事实不符**：`IMU_Tick1ms()` 名字说 1 ms，TIM6 实际是 **940 Hz（≈1.064 ms）**，与 `IMU_SAMPLE_HZ 940` 一致。**名字是历史遗留，不要按名字推周期。**

---

## 4. 数据链路（2026-11-23 起速度环已改为定时驱动）

```
USART1 (DMA + IDLE) ──► Task1_UartIdleCallback() ──► FIFO ──┐
                                                             ├─ 0xAA err 0x5A ──► line_error ──► LineTracking_Apply()
                                                             └─ 0xCC status slot 0x5A ──► garage_status[]
                                                                        │（只写目标，不调 PID）
TIM7 (100Hz 中断) ──► encoder_timebase_ticks++                           ▼
                                                        motor_target_mm_s[4]  ◄── 串口命令 / VOFA 滑块（待做）
                                                                        │
主循环 Task_MotorControl_Update()  ──10ms 节拍──► motor_pid_run(id 1..4) ──► speed2pluse() ──► PWM
TIM6 (940Hz 中断) ──► IMU_Tick1ms() ──► IMU_Update() 在主循环消费 ──► yaw/roll/pitch
```

- **速度环现在由主循环按 10 ms 节拍驱动**（`task.c` 的 `Task_MotorControl_Update()`），不再由视觉帧触发。视觉帧只写目标值 —— 帧停了速度环照样闭环，这正是验收标准 D2 要的行为。
- `motor_pid_run()` 内部只保留 **5 ms 下限保护**（`MOTOR_MIN_SAMPLE_PERIOD_MS`），不再自己管 10 ms 周期；节拍唯一归 `task.c`。`dt` 由函数内部实测，周期在 5 ms 以上波动都算得对。
- `LineTracking_Apply()` 现在只做一件事：`Task_MotorControl_SetTarget(1/3, left)` + `SetTarget(2/4, right)`。
- 四轮目标用 `motor_target_mm_s[]` 存（下标 0~3 = `motor_id` 1~4），`Motor.speed` 每拍被目标值覆盖，PID 输出回写不到目标上。
- 测速公式：`count_delta × (π × 48 mm) × 100 Hz ÷ (500 × 4 × 20) ÷ elapsed_ticks`，再乘 `forward_count_sign`。
- **`main.c` 的 `while(1)` 现在：`Task_MotorControl_Update()` + 每 1000 ms 打印 `encoder_get_speed(1)`。`Task1_Run()` 仍然是注释状态**（视觉没接，暂时不启用循迹）。
- `Task_Init()` 末尾调 `Task_MotorControl_Start()` → **上电即闭环，目标 `BASE_SPEED`(150 mm/s)。验收时轮子必须架空。**
- 量纲链（重要）：`Motor.speed` 进入 `motor_pid_run()` 时是 **mm/s**，出来后变成 **百分比 0~100**，再进 `motor_run()`。**同一个字段两种单位，见 §6.3。**

---

## 5. 代码模块地图

| 文件 | 行数 | 职责 | 改动权限 |
|---|---|---|---|
| `Core/Src/main.c` | 246 | 只有初始化 + 主循环空壳（业务全在 `task.c`） | 可改，**只做调度，不塞业务**（AGENTS.md R14） |
| `Core/Src/task.c` / `task.h` | **536 / 41** | Task1_Run 状态机、串口帧解析、FIFO、循迹调速、**四轮速度环调度**、OLED 车位显示 | **本项目当前主战场**，可改；改动必须说清动了哪个 Task |
| `Core/Src/motor.c` / `motor.h` | 271 / 22 | PWM 输出 + 单轮速度环 PID | **核心，慎改**，改动必须整轮验证 |
| `Core/Src/encoder.c` / `encoder.h` | 126 / 13 | 4 路编码器测速，溢出回绕处理 | **核心，慎改** |
| `Core/Src/imu.c` / `imu.h` | 410 / 56 | MPU6050 读取、零偏学习、姿态解算、硬件低通 | **优先当只读**，解算逻辑不要动 |
| `Core/Src/usart.c` | 334 | 五路串口初始化 + `printf` 重定向（ARMCC 专有） | 只改 `USER CODE` 区 |
| `Core/Src/stm32f4xx_it.c` | 290 | TIM6/TIM7 中断 + UART IDLE 回调分发 | **只改 `USER CODE BEGIN/END` 之间** |
| `Core/Src/dma.c` / `dma.h` | 55 / 52 | USART1 接收 DMA 通道 | CubeMX 生成，只改 USER CODE 区 |
| `Core/Src/oled.c` / `oled.h` | 367 / 31 | I2C OLED 显示 | 可改 |
| `Core/Src/tim.c` `gpio.c` `i2c.c` | CubeMX 生成 | 外设初始化 | **只改 `USER CODE BEGIN/END` 之间** |
| `camera/*.py` | 1504 | PC 端视觉：循迹 + 车位识别，串口发帧给 STM32 | 可改，**接口协议见 §4** |
| `Drivers/` | 3 万+ 行 | HAL 与 CMSIS | **绝对不动** |

> **⚠ 技术债（已知，未修）**：`task.c` 现在 **536 行，已超 AGENTS.md R13 的 500 行上限**。之所以现在不拆，是因为新增 `.c` 文件必须同步改 `MDK-ARM/smart_cars.uvprojx`，而 Keil 目前是**唯一能编译的链路** —— 拆错就等于把他唯一的构建方式搞坏。**触发条件：CMake 链路打通当天，把速度环调度整块搬到 `control.c`/`control.h`**（约 130 行，边界已经在代码里标出来了）。

### 5.1 文档与协作文档

| 文件 | 作用 | 维护者 |
|---|---|---|
| `PROJECT.md` | 事实清单（本文件） | 每次改事实必须同步 |
| `AGENTS.md` | AI 协作纪律（0~12 章） | 规则变化时改 |
| `STATE.md` | 进度、已知 bug、**试过没用的方案** | 每轮工作结束必须追加 |
| `docs/MG310_电机参数速查.md` | 电机/编码器/轮胎参数与派生量 | 参数或选型变化时改 |
| `docs/验收标准_电机动起来.md` | 「电机动起来」这一阶段的决策记录（D1~D4）+ 5 条验收标准（R1~R5） | 车主拍板后改 |
| `docs/VOFA调试链路_设计草案.md` | VOFA+ 上行/下行协议、串口选型、实施步骤（**草案，待确认**） | 方案定稿后改 |
| `reports/YYYY-MM-DD_*.html` | 每次对话的工作汇报（单文件 HTML） | 每次对话生成 |

---

## 6. 已知问题与坑（白纸黑字，别踩）

1. ~~**`main.c` 里电机完全没被驱动。**~~ **已修（2026-11-23，提交 `914e8cc`）**：主循环现在调 `Task_MotorControl_Update()`，`Task_Init()` 末尾 `Task_MotorControl_Start()` 上电即闭环。**副作用：上电轮子就转（目标 150 mm/s），验收时轮子必须架空。**
2. ~~**速度环被视觉帧驱动，不是定时驱动。**~~ **已修（2026-11-23，提交 `914e8cc`）**：帧只写目标值，闭环由 10 ms 节拍跑，帧停不冻结（对应验收 D2）。
3. **`Motor.speed` 一个字段两种单位。** 进 `motor_pid_run()` 是 **mm/s**，函数内部把它改写成 **百分比 0~100** 再交给 `motor_run()`。今天因为全程走 PID 所以没错；但**谁要是直接写 `motorFL.speed = 300; motor_run(motorFL);`，300 会被 clamp 成 100% 满占空比**，看起来"正常"其实是满油门。
4. **`LINE_STEERING_GAIN = 0.0f`。** 左右目标速度恒等于 `base_speed`，`line_error` 对它完全没影响 → **现在这版不会转向，只会直行**。要真循迹必须先把它调成非零。
5. **`BASE_SPEED 150` 的量纲没有书面定义。** 按 PID 的用法它是 **mm/s**（150 mm/s ≈ 0.15 m/s，约为空载速度的 12%）。但 `LineTracking_Apply()` 里的限幅写的是 `0 ~ 1000`，看着更像"0~1000 的速度档位"。**改它之前先按 §7.4 实测一次实际速度。**
6. **最大占空比 100%，未设上限 —— 车主已明确决定保持（2026-11-23，决策 D3）。** 驱动供电 12 V、电机额定 7.4 V、厂家标注**不可堵转**。风险已知并接受。**这是决策不是遗漏，不要再建议加 60% 上限，也不要"顺手"加限制。** 操作约束靠人工：调试时禁止长时间满油门。
7. **`yaw` 是纯陀螺仪积分，无磁力计校正，长时间必然漂移。** 而且零偏学习的现状是：初始化时做一次静态标定（`imu_sensor_init` 里采 `IMU_CALIB_SAMPLES` 个样本平均成 `s_bias[3]`），**但运行期学习被关掉了**（`s_learn_en = 0U`，且全工程没有任何地方调 `IMU_SetBiasLearn(1)`）。所以温漂无法被跟踪。**角度环必须容忍这一点**：用短周期闭环 + 出发前 `IMU_ZeroYaw()`，不要指望 yaw 绝对准。
8. `.ioc` 的 `CompilerLinker=GCC`，与遗留 Keil 工程的 ARMCC 不一致（见 §1）。**不要用 CubeMX 重新生成代码。**
9. CubeMX 生成的 `USER CODE` 区外代码，重新生成会被覆盖。改之前先确认改的位置在哪个区。
10. **`motor1_start` / `motor1_stop` 宏引用的 `EN1_Pin` / `EN1_GPIO_Port` 在 `motor.h` 里已不存在**（该版 `motor.h` 只剩 22 行，宏已被删干净）。若在旧笔记里看到这两个名字，那是 `main` 分支的遗留，**不要照抄**。
11. **`task.c` 里 `motorRL/motorRR/motorFL/motorFR` 的命名与 `motor_id` 交叉**：`{1,...}` 叫 RL、`{3,...}` 叫 FL，而 `main.c` 打印 motor1 时标签写的是 `motorRL`。**以 `motor_id` 为准，不要以变量名为准。**
12. **视觉端还会发 `TT + 0x00 + Z`（倒T 确认帧），`task.c` 的状态机不解析这种帧。** 目前它是被静默丢掉的（4 个字节都不在 `0xCC/0xAA` 分支里），但如果它插在别的帧中间会打断那一帧。循迹阶段接视觉时再处理，**不是当前的阻塞项**。

---

## 7. 真值清单（分四类，禁止混用）

### 7.1 已核实（文件/图纸里写死的）

| 参数 | 现值 | 依据 |
|---|---|---|
| 芯片 / 封装 | STM32F407VET6 / LQFP100 | `.ioc` |
| 系统时钟 | 168 MHz | `.ioc` + `main.c` |
| 全部引脚映射 | 见 §2 | `.ioc` + 原理图 + `tim.c` 三方交叉 |
| 定时器 PSC/ARR | 见 §3 | `.ioc` + `tim.c` |
| 编码器接口模式 | TI12（4 倍频） | `.ioc` `EncoderMode` |
| MPU6050 地址 | 0x68 | `imu.c` + 原理图 AD0=GND |
| 串口波特率 | 115200 | `usart.c` |
| 编译器（遗留 Keil 工程） | ARMCC AC5 V5.06u5，-O3 | `uvprojx`；**目标链路改用 arm-none-eabi-gcc**，见 §8 |
| 编码器线数 | **500 ppr** | MG310 官方规格图（2026-11-23 核对） |
| 减速比 | **1:20** | MG310 官方规格图 |
| 轮径 | **48 mm** | MG310 配件规格图 |
| 电机额定电压 | **7.4 V**（可用 7~13 V） | MG310 官方规格图 |
| 电机空载/额定转速 | **500 / 400 RPM**（输出轴） | MG310 官方规格图 |

### 7.2 推得（按公式算出来的，不是测的）

| 参数 | 值 | 算法 |
|---|---|---|
| TIM1/TIM9 PWM 频率 | 20 kHz | 168 MHz ÷ 8400 |
| TIM12 PWM 频率 | 10 kHz | 84 MHz ÷ 8400 |
| TIM6 中断频率 | 940 Hz | 84 MHz ÷ 8934 ÷ 10 |
| TIM7 中断频率 | 100 Hz | 84 MHz ÷ 84 ÷ 10000 |
| 输出轴一圈计数值 | **40000** | 500 × 4 × 20 |
| 每个计数的位移 | **0.00377 mm** | 150.8 mm ÷ 40000 |
| 空载线速度（7.4 V） | **1256 mm/s** | 500 RPM ÷ 60 × π×48 |
| 额定线速度 | **1005 mm/s** | 400 RPM ÷ 60 × π×48 |
| 四轮额定总推力 | **≈ 6.5 N** | 0.0392 N·m ÷ 0.024 m × 4 |
| 12 V 满占空线速度 | **≈ 2040 mm/s**（未实测） | 按电压线性外推 |

### 7.3 设定值（代码里写死、未经实测的值）

> **旧文档里"满量程差 12 倍"那条已经不成立。** `2a5afd2` 把 `MOTOR_SPEED_FULL_SCALE_MM_S` 整个删掉了，`speed2pluse()` 改为吃 **百分比 0~100**，`speed2pluse()` 的 ARR 也改成从**传入的定时器**读（旧版写死 `htim1`）。**这两个 bug 在本分支上确实已经修好。**

| 参数 | 现值 | 位置 | 状态 |
|---|---|---|---|
| 目标基础速度 | **150 mm/s** | `task.c` `BASE_SPEED` | **量纲已由车主确认（决策 D1）= mm/s**。数值未实测，限幅 0~1000 的语义暂不统一 |
| 循迹转向增益 | **0.0** | `task.c` `LINE_STEERING_GAIN` | **等于关掉转向**（§6.4），循迹阶段再定 |
| 四轮 P / I | 0.13~0.15 / 0.04~0.06 | `task.c` 四个 `Motor` 初值 | **未实测**，量纲是 "%占空比 / (mm/s)" |
| 四轮 D | 全 0 | 同上 | 未整定 |
| 最大占空比 | **100%（无上限）** | `motor.c` `MOTOR_PWM_FULL_SCALE_PERCENT` | **车主决定保持 100%（决策 D3）**，不是遗漏 |
| 速度环周期 | **10 ms，由 `task.c` 调度** | `task.c` `MOTOR_CONTROL_PERIOD_MS` | 已实现，**实际间隔未实测**（`HAL_GetTick` 分辨率 1 ms） |
| 帧格式 | `0xAA <err> 0x5A` / `0xCC <status> <slot> 0x5A` | `task.c` 顶部宏 | 与 `camera/task1.py` 已对拍一致 |

### 7.4 未知（必须实测，不许猜）

| 问题 | 怎么测 | 优先级 |
|---|---|---|
| 编码器**接线与计数方向**是否正确（PPR 已由官方图纸确认，不必再验数值） | 手转车轮整一圈，读 TIMx->CNT 变化量应 ≈ 40000；四轮同向转动时符号应同号 | **最高**，符号错会让速度环正反馈跑飞 |
| 电机在 12 V 下的实际最高速度 | 限占空比逐级加，串口打速度 | 高 |
| 按键有效电平（上拉还是下拉） | 万用表量空闲电平 / 串口打印 `key1_read` | 中 |
| 电机驱动模块型号（原理图只有接口，没写型号） | 看板子丝印 | 中 |
| 舵机、电位器、视觉接口的信号脚 | 看板子 / 原理图原图 | 低（本项目暂不用） |

---

## 8. 构建与烧录（VSCode 链路，**待打通**）

### 8.1 目标链路

```
VSCode  ──► CMake + Ninja ──► arm-none-eabi-gcc ──► build/smart_cars.elf
   │                                                    │
   └──► Cortex-Debug ──► OpenOCD ──► ST-Link / CMSIS-DAP ──► 烧录 + GDB 调试
```

VSCode 本身不编译也不烧录，只负责"转发命令"和"显示调试界面"。每一层都能单独用命令行验证。

### 8.2 需要新建的文件（**尚未创建**）

| 文件 | 作用 | 来源 |
|---|---|---|
| `CMakeLists.txt` | 源文件清单 + 编译参数 + 链接参数 | 手写（不重新生成 CubeMX） |
| `cmake/gcc-arm-none-eabi.cmake` | 工具链文件（必须写在 `project()` 之前） | 手写 |
| `STM32F407VETx_FLASH.ld` | GCC 链接脚本（替代 `.sct`） | ST 官方 CubeF4 仓库 |
| `startup_stm32f407xx.s`（GCC 版） | 向量表与复位入口（替代 ARMCC 版） | CMSIS / ST 官方仓库 |
| `.vscode/tasks.json` | 编译任务 | 手写 |
| `.vscode/launch.json` | 调试配置（ST-Link / DAP 两套） | 手写 |
| `.vscode/c_cpp_properties.json` | 补全路径，指向 `build/compile_commands.json` | 改写现有 |

### 8.3 三处必须改的代码（GCC 兼容）

| 位置 | 现状（ARMCC） | 改成（GCC） |
|---|---|---|
| `Core/Src/usart.c` L26-32 | `struct __FILE{}` + `FILE __stdout` + `#pragma import(__use_no_semihosting)` + `fputc` | `int _write(int fd, char *ptr, int len)` 包一层 `HAL_UART_Transmit` |
| `MDK-ARM/startup_stm32f407xx.s` | ARMCC 汇编语法 | 换 GCC 版（**不要改原文件，新增一份**） |
| `MDK-ARM/smart_cars/smart_cars.sct` | ARMCC 分散加载 | 换 `.ld`（新增，不动原文件） |

### 8.4 关键编译参数（照这个配，别自己发明）

```
-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
-Og -g3            (Debug；别用 -O2/-O3，否则变量被优化掉，断点看不到值)
--specs=nano.specs (否则 printf 一进来 Flash 涨几十 KB)
-ffunction-sections -Wl,--gc-sections
-u _printf_float   (要打印浮点必须加)
```

### 8.5 打通顺序（三步各自独立验证，不要跳）

1. **命令行编译**：`cmake -B build -G Ninja && cmake --build build -j` → 产出 `.elf`，`arm-none-eabi-size build/smart_cars.elf` 能看出 Flash/RAM 占用
2. **命令行烧录**：`openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c "program build/smart_cars.elf verify reset exit"` → 看到 `Verified OK`
3. **F5 调试**：能停在 `main()`、能看变量、能设断点

> 报错时按 1→2→3 倒查，立刻能分清是构建问题、连接问题还是调试适配器问题。
> **每打通一步，把实测过的命令写回本节并标注【已实测】。**

### 8.6 OpenOCD 两套配置

| 烧录器 | interface 配置 | 说明 |
|---|---|---|
| ST-Link | `interface/stlink.cfg` | Windows 下若报找不到适配器，用 Zadig 把接口改成 WinUSB |
| CMSIS-DAP / DAP-Link | `interface/cmsis-dap.cfg` | 核心板板载 DAP 通常免驱 |

target 都是 `target/stm32f4x.cfg`。

### 8.7 观察输出

USART2 @ 115200（`printf` 重定向到 USART2，见 `usart.c`）。

---

## 9. 目标架构（计划，非现状）

```
main loop (无阻塞)
  └─ 每 10 ms
       ├─ 读 yaw ──► 角度环 PID ──► 转向修正量 (差速)
       ├─ 四个轮目标 = 基础速度 ± 转向修正
       ├─ motor_pid_run(轮1..4)        ← 速度环
       └─ 每 500 ms: OLED / 串口刷新
```

- 角度环输出的是**差速量**，不是直接给电机 PWM。
- 外环（角度）周期应慢于内环（速度）：角度环 20~50 ms，速度环 10 ms。
- **`task.c` 已存在（432 行）**，速度环调度就落在这里；角度环另开 `control.c/h`，**不要再往 `task.c` 里堆**（已接近 500 行上限）。

---

## 10. 进度与下一步（基线：`imu-dlpf-20hz` @ `2a5afd2`）

- [x] 四轮 PWM 输出
- [x] 四路编码器测速
- [x] MPU6050 姿态解算 + 硬件低通
- [x] 规范落地：`PROJECT.md` / `AGENTS.md` / `STATE.md`
- [x] 电机参数核实（MG310 官方图纸）：500 ppr / 1:20 / 48 mm **全部正确**
- [x] 业务从 `main.c` 拆到 `task.c`（AGENTS.md R14 已满足）
- [x] 串口 DMA + 空闲中断 + FIFO 帧解析
- [x] 视觉上位机 `camera/`（循迹误差 + 车位识别）
- [x] **把电机重新接回主循环**（`914e8cc`）
- [x] **速度环改定时驱动**（10 ms 节拍，`914e8cc`）
- [x] 决策：`BASE_SPEED 150` 量纲 = **mm/s**（D1）
- [x] 决策：最大占空比 **保持 100% 不设上限**（D3）
- [x] 决策：帧停后**保持最后目标继续闭环**（D2）
- [ ] **烧一版验证电机动起来 + 方向正确**（验收标准见 `docs/验收标准_电机动起来.md`）
- [ ] **打通 VSCode 编译链路**（CMake + GCC + OpenOCD，见 §8.2）
- [ ] 决策：`LINE_STEERING_GAIN` 设为多少（现在是 0，等于不转向）
- [ ] 单轮速度环整定（先 1 个轮子跑通，再复制到 4 个）
- [ ] **VOFA+ 上位机**：四路目标/实际速度曲线 + 滑块调 kp/ki/目标 + 启停命令（**架构草案见 `docs/VOFA调试链路_设计草案.md`**，端口/协议/波特率三项待定）
- [ ] 角度环（yaw 闭环 → 差速），新增 `control.c`
- [ ] 拆 `control.c`（`task.c` 已 536 行，见 §5 技术债）
