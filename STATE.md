# STATE.md — 项目进度状态

> **这是给"下一个会话的 Agent"看的文件。** 新会话没有上下文，靠这份文件接手。
> 每轮工作结束必须追加一节「会话记录」。不要删历史，过时的划掉即可。
> 事实去 `PROJECT.md`，纪律去 `AGENTS.md`，**这里只记"做到哪了、卡在哪、试过什么"**。

**最后更新：2026-11-23 23:30**

---

## 1. 当前阶段（一句话）

**构建链已换成 CMake + arm-none-eabi-gcc + OpenOCD，编译实测通过（提交 `20b94fb`），VSCode 里「构建」和「构建并烧录」两个任务已配好；固件 `build/smart_cars.elf` 已生成，但还没烧进芯片。下一步：架空车 → 烧第一版 → 验电机方向与编码器计数。**

进度：`[######----] 6/10`（PWM、编码器、IMU、task 拆分、串口收发、视觉接口、电机调度、**构建链**；烧录实测、VOFA、角度环未开始）

**当前分支**：`imu-dlpf-20hz` @ `20b94fb`（比远程多 2 个本地提交）
**回退点**：`914e8cc`（速度环定时驱动，构建链之前的稳定点）｜`main` = `19a734b`（初始上传，`git checkout main` 可回）

> ⚠ **上电即闭环，目标 150 mm/s —— 烧录前把车架空。**

---

## 1.1 阻塞项：无

上一轮的"本地代码不是最新版"已解决 —— 车主 2026-11-23 决定「按最新的」，已切分支。

> 注意：**`main` 分支的描述已过期，不要引用。** `PROJECT.md` 里所有"代码现状"章节现在只描述 `imu-dlpf-20hz`。

---

## 2. 已完成

| 事项 | 完成时间 | 备注 |
|---|---|---|
| 四轮 PWM 输出 | 接手前已有 | `motor.c`，TIM1/TIM9/TIM12 |
| 四路编码器测速 | 接手前已有 | `encoder.c`，TIM3/4/5/8 |
| MPU6050 姿态解算 | 接手前已有 | `imu.c`，含硬件低通 |
| `task.c` 业务拆分（432 行） | `2a5afd2` 之前已有 | 状态机 + Task1~6 + 帧解析 + 循迹 |
| 串口 DMA + IDLE + FIFO | `2a5afd2` 之前已有 | `dma.c` + `task.c` |
| 视觉上位机 `camera/` | `2a5afd2` 之前已有 | Python，循迹误差 + 车位识别 |
| 建立 `PROJECT.md`（事实清单） | 2026-11-23 | 引脚/定时器/模块/已知坑/真值四分类 |
| 建立 `AGENTS.md`（协作纪律） | 2026-11-23 | 0~12 章 + 验收分级 + 输出格式 |
| 核实 MG310 参数 | 2026-11-23 | **500 ppr / 1:20 / 48 mm 全部正确**，见 `docs/MG310_电机参数速查.md` |
| 技术栈选定 | 2026-11-23 | CMake + arm-none-eabi-gcc + OpenOCD + Cortex-Debug |
| 切到最新分支并重写代码现状章节 | 2026-11-23 | `git checkout -b imu-dlpf-20hz origin/imu-dlpf-20hz` |
| **速度环改 10 ms 定时驱动** | 2026-11-23 | 提交 `914e8cc`：目标数组 `motor_target_mm_s[]` + `Task_MotorControl_Update()` |
| **电机接回主循环** | 2026-11-23 | 提交 `914e8cc`：`main.c` 调 `Task_MotorControl_Update()`，`Task_Init()` 末尾 Start |
| GCC 语法/类型检查通过 | 2026-11-23 | `-Wall -Wextra` 零警告；**未链接、未烧录** |
| **CMake + GCC 构建链打通** | 2026-11-23 | 提交 `20b94fb`：`CMakeLists.txt`、工具链文件、GCC 启动文件、`.ld`、5 个 VSCode 任务 |
| **编译实测通过** | 2026-11-23 | 退出码 0；Flash 30332 B / 512 KB (5.79%)，RAM 7968 B / 128 KB (6.08%) |
| **烧录链路实测到 probe** | 2026-11-23 | OpenOCD 0.12.0 + CMSIS-DAP(FW 2.0.0) 连通；`flash probe` 返回 **512 KiB** |
| 调试器类型确认 | 2026-11-23 | **CMSIS-DAP，不是 ST-Link**；设备名带 `ATK_`，虚拟串口 COM11 |
| VOFA 需求草案 | 2026-11-23 | `docs/VOFA调试链路_设计草案.md`；**已定 USART2 + FireWater + 115200** |

---

## 3. 进行中

| 事项 | 进度 | 卡在哪 |
|---|---|---|
| 烧录验收（R1 / R5） | 0% | 固件已编好，只差 `program` 一步；**轮子必须架空**（上电即 150 mm/s） |
| `.vscode/launch.json`（F5 断点调试） | 0% | 需要装 Cortex-Debug 扩展；烧录验证通过后再做 |
| VOFA+ 调试链路 | 5%（草案 + 三项决定已定） | 下一步写 `vofa.c`；**先修 printf 逐字节阻塞发送**（已知问题 12） |

---

## 4. 已知问题 / 待决策（**动代码前先看这节**）

| # | 问题 | 影响 | 状态 |
|---|---|---|---|
| 1 | ~~电机没被接回主循环~~ | — | **已修 `914e8cc`**（副作用：上电即转） |
| 2 | ~~速度环由视觉帧驱动~~ | — | **已修 `914e8cc`**（帧只写目标，闭环 10 ms） |
| 3 | `Motor.speed` 一字段两量纲（mm/s → %） | 直接调 `motor_run()` 会被 clamp 成满油门 | 已知，**改结构前先读 `PROJECT.md` §6.3** |
| 4 | `LINE_STEERING_GAIN = 0.0f` | 左右目标恒等 → **不会转向** | 循迹阶段再定，不阻塞当前 |
| 5 | `BASE_SPEED 150` 的 mm/s 已确认，但限幅仍写 0~1000 | 语义不统一，容易误判 | 已知，暂不统一 |
| 6 | 最大占空比 100%（车主已决定 D3） | 超压发热、**不可堵转** | **决策项，不要再动** |
| 7 | yaw 纯陀螺仪积分，无磁力计；运行期零偏学习关闭 | 长时间必漂移 | 角度环设计时需容忍 |
| 8 | 角度环完全不存在 | — | 未开始 |
| 9 | `IMU_Tick1ms()` 名字说 1 ms，实际 940 Hz | 容易误算周期 | 已知，不改名 |
| 10 | **`task.c` 已 536 行，超 500 行上限** | 再堆不可维护 | **技术债**：CMake 打通当天拆 `control.c`（新文件要同步改 `uvprojx`，现在不能拆） |
| 11 | 编码器计数符号 `{−1,+1,−1,−1}`，叠 `motor_run()` 里 2/3/4 号极性翻转 | 若被"统一"，速度环正反馈跑飞 | 已知，**不许动** |
| 12 | `printf` 的 `fputc` 逐字节阻塞发送 | VOFA 高频推帧会把主循环卡死 | **VOFA 开工前必须先修** |
| 13 | USART2 没有 RX 中断/DMA | VOFA 的命令收不进来 | VOFA 开工前补（照抄 USART1 的做法） |
| 14 | PID 增益 `p/i/d` 没有运行时修改入口 | 滑块调 kp/ki 做不到 | 需新增 `Task_MotorControl_SetGain()` |

---

## 5. 试过但没有采用的方案（**最重要的一节，避免后来者重走**）

| 方案 | 结论 | 原因 |
|---|---|---|
| 把 `MOTOR_SPEED_FULL_SCALE_MM_S` 改成 ≈1300 | **不需要了** | `2a5afd2` 已把该常量删除，改为百分比量纲，ARR 也从传入定时器读。旧"差 12 倍"问题**不存在** |
| VSCode 调 `UV4.exe -b` 命令行编译（仍是 ARMCC） | **放弃** | 车主明确要求不走 Keil 编译；且报错无法映射回编辑器 |
| EIDE 插件导入 `.uvprojx` | **否决** | 配置是私有格式（`.eide/eide.yml`），对 AI Agent 是黑盒，无法命令行自动化。多 Agent 并行会把 Agent 的手绑住 |
| 用 CubeMX 重新生成 CMake 工程 | **否决** | `.ioc` 里 `CompilerLinker=GCC` 与现有 ARMCC 工程结构不一致；重新生成会覆盖 `USER CODE` 区外代码。**改为手写 `CMakeLists.txt`** |
| 手转车轮验证编码器 40000 计数 | **降级为可选** | 官方图纸已确认 500×4×20=40000，不必再验数值；**但仍需验证方向**（符号错会让速度环正反馈跑飞） |
| 以 `main` 分支为基础重写 | **否决** | 车主 2026-11-23 决定按最新提交；`main` 缺 `task.c`/DMA/视觉，重写等于白干 |
| 加 60% 最大占空比上限 | **否决** | 车主 2026-11-23 明确决定保持 100%（D3），风险已知并接受。**不要再提** |
| 用 `Motor motor = *motor_table[i];` 做局部副本 | **放弃** | `Motor.motor_id` 是 `const` 成员 → 结构体不可赋值，编译报 `assignment of read-only variable`。改走指针 `motor->speed = ...` |
| 本轮就把速度环调度拆进 `control.c` | **暂缓** | 新增 `.c` 必须同步手改 `MDK-ARM/smart_cars.uvprojx`；Keil 是当前唯一能编译的链路，拆错等于把唯一构建方式搞坏。**CMake 打通当天再拆**（触发条件已写进 `PROJECT.md` §5） |
| `printf` 直接拿来推 VOFA 数据 | **不可行** | `fputc` 逐字节 `HAL_UART_Transmit(..., HAL_MAX_DELAY)`，8 通道 100 Hz 会把主循环拖死。必须先改环形缓冲 + DMA |

---

## 6. 下一步（按顺序）

1. **架空车 → 烧第一版**：VSCode 里 `Ctrl+Shift+P` → `Tasks: Run Task` → 「构建并烧录」。按 `docs/验收标准_电机动起来.md` 的 R1/R5 验：四轮都转？方向对？`TIMx->CNT` 一圈 ≈ 40000？
2. **验串口**：USART2 @115200 能否打出 `Task_Init` 的初始化日志 —— 这是"烧进去的到底是不是新代码"的唯一硬证据
3. **`.vscode/launch.json`**（Cortex-Debug）：能停在 `main()`、能看变量、能设断点
4. **VOFA+ 链路**（**USART2 + FireWater + 115200 已定**）：先修 `printf` 逐字节阻塞 → 8 通道上行 → 收命令 → 在线改增益
5. **角度环**（yaw → 差速），新增 `control.c`，顺手把速度环调度搬过去（构建链已通，加 `.c` 不再需要手改 `uvprojx`）

---

## 7. 会话记录（追加，不删）

### 2026-11-23 第一次会话
**做了什么**
- 通读工程：`.ioc` / `main.h` / `tim.c` / `motor.c` / `encoder.c` / `imu.c` / `usart.c` / `.uvprojx`
- 用 PDF 工具提取原理图网标，与代码交叉核对引脚
- 建立 `PROJECT.md`、`AGENTS.md`、`STATE.md`
- 提取 MG310 参数到 `docs/MG310_电机参数速查.md`，核对出满量程差 12 倍的问题
- 技术栈调研（CMake/GCC vs EIDE vs UV4 命令行）并选定 CMake + GCC 路线
- 按车主 11 条修改意见重写 `AGENTS.md`（0~12 章）
- 生成 HTML 工作汇报：`reports/2026-11-23_规范落地与电机参数核实.html`
- 体检 git：发现本地落后分支 6 个提交

**发现的坑**
- 速度环代码写了但没接
- 满量程参数错一个数量级（**仅在 `main` 分支成立**，新分支已修）
- 驱动 12 V 超电机额定 7.4 V
- `motor3` 的 PE5 网标是 AIN2_2，与驱动 1 命名相反，是故意的（不许"修正"）
- `.ioc` 的编译器字段与实际 Keil 工程不一致

**留给下一轮**
- 没有任何 C 代码被修改，全部是文档
- VSCode 链路一个文件都还没建

### 2026-11-23 第二次会话（切分支 + 核实量程问题）
**做了什么**
- 车主决定「按最新的」→ `git checkout -b imu-dlpf-20hz origin/imu-dlpf-20hz`，HEAD = `2a5afd2 视觉`
- `main` 保持不动，作为回退点
- 逐行核实新分支的电机/编码器/任务调度链路（`motor.c` 268 行、`task.c` 432 行、`main.c` 248 行）
- 重写 `PROJECT.md` 的 §0 / §2.2 / §4 / §5 / §6 / §7.1 / §7.3 / §9 / §10
- 重写 `STATE.md`（本节所在文件）
- **未修改任何 C 代码**

**核实结论：旧的"差 12 倍"问题已不存在**
- `MOTOR_SPEED_FULL_SCALE_MM_S` 常量已被删除
- `speed2pluse()` 现在吃百分比 0~100，且 ARR 从**传入的定时器**读（旧版写死 `htim1`）
- `motor_pid_run()` 输出百分比交给 `motor_run()`，量纲自洽
- 但**新的隐患是"一字段两量纲"**：`Motor.speed` 进 PID 是 mm/s、进 `motor_run` 是 %。直接手写 `motor_run()` 会踩

**这一轮查出的"真·卡点"（比参数问题更硬）**
- `main.c` 的 `Task1_Run()` 与 4 个 `motor_pid_run()` **被注释掉了** → 电机根本没在跑
- 速度环由 `0xAA` 循迹帧触发（`LineTracking_Apply`），**帧停 → PID 冻结 → 车盲跑**
- `LINE_STEERING_GAIN = 0.0f` → 不会转向
- 编码器符号在本分支被翻过：`{-1, +1, -1, -1}`，配 `motor_run()` 内部的 2/3/4 号极性翻转，是两层叠加

**留给下一轮**
- 未改任何 C 代码
- 待车主决定：`BASE_SPEED` 量纲、`LINE_STEERING_GAIN` 取值、是否加 60% 占空比上限
- 然后才动手：接回电机 → 速度环改定时驱动

### 2026-11-23 第三次会话（接回电机 + 速度环定时驱动，提交 914e8cc）
**车主决定**
- D3 不加占空比上限（保持 100%）
- D1 `BASE_SPEED = 150` 就是 mm/s，限幅同步语义暂不管
- 本轮只做「接回电机」+「速度环改定时驱动」，每步提交 git

**做了什么（只动 4 个文件）**
- `task.h`：新增 `TASK_MOTOR_COUNT` + 6 个接口（Update/Start/Stop/SetTarget/GetTarget/GetActual）
- `task.c`：`motor_target_mm_s[4]` 目标数组 + `motor_table[]` 指针表 + 10 ms 调度器；`LineTracking_Apply()` 改成只写目标；`LineTracking_Stop()` 改调 `Task_MotorControl_Stop()`；`Task_Init()` 末尾 `Start()`；补 `<stdio.h>`
- `motor.c`：`MOTOR_SPEED_SAMPLE_PERIOD_MS 10U` → `MOTOR_MIN_SAMPLE_PERIOD_MS 5U`（只做下限保护，节拍归调度器）
- `main.c`：4 行注释掉的 `motor_pid_run` → 1 行 `Task_MotorControl_Update()`

**验证**
- `arm-none-eabi-gcc -fsyntax-only -Wall -Wextra`（task/motor/main/encoder）零警告；逐文件扫 `Core/Src/*.c` 仅 `oled.c` 有**原有的** `OLED_H` 宏重定义警告，未改
- **未链接、未烧录、未实测转速**

**踩到的坑**
- `Motor.motor_id` 是 `const int` → 结构体整体赋值编译报错，只能走指针
- `task.c` 用了 `printf` 却没 `#include <stdio.h>`：ARMCC 能过，GCC 直接报错
- 拆 `control.c` 的念头被否：新 `.c` 要同步改 `uvprojx`，Keil 是唯一能编译的链路

**留给下一轮**
- 烧录验收 R1/R5（**轮子架空**，上电即 150 mm/s）
- 若某轮反转：先查 `encoder.c` 的符号，再查 `motor_run()` 里的极性翻转，**别只改一处**
- VOFA 草案已写好，卡 3 个决定（串口 / 协议 / 波特率）

### 2026-11-23 第四次会话（构建链切 CMake+GCC+OpenOCD，提交 20b94fb）
**车主决定**
- VOFA：**USART2 + FireWater + 115200**（三项全定）
- 编译路：**GCC + CMake**（不装 EIDE、不调 UV4）
- 首烧版本：**直接烧现在这版**（上电轮子就转，必须架空）

**做了什么（新增 5 个文件，改 2 个）**
- `CMakeLists.txt`：GLOB 收集 `Core/Src/*.c` 与 HAL `Src/*.c`，加 `.c` 不用改脚本；Debug `-Og -g3`；产物 `.elf/.hex/.bin/.map`
- `cmake/gcc-arm-none-eabi.cmake`：工具链文件，`CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY`
- `Core/Startup/startup_stm32f407xx.s`：GCC 语法向量表，16 系统异常 + 82 外设中断
- `STM32F407VETX_FLASH.ld`：Flash 512K / RAM 128K / CCM 64K
- `.vscode/tasks.json`：构建 / 配置 / 烧录 / 构建并烧录 / 擦除；**删掉了原来误配的 MinGW gcc 任务**
- `Core/Src/usart.c`：printf 重定向改条件编译（GCC 走 `_write`，ARMCC 原代码一字未改）
- `.gitignore`：加 `/build/`

**实测证据**
- `cmake --build build` 退出码 0，无 error
- 向量表首字 `0x20020000`（RAM 末尾），次字 `0x08005D95`（`Reset_Handler`+1）
- `.data` VMA=`0x20000000` / LMA=`0x08007590`（Flash 加载、RAM 运行）
- OpenOCD `flash probe` → **512 KiB**，与 `.ld` 一致
- Flash 30332 B / 512 KB (5.79%)，RAM 7968 B / 128 KB (6.08%)
- **未烧录、未上电实测**

**踩到的坑（两个都不报错在源码行，很难查）**
- `-lc -lm` 放进 `target_link_options` → 排到 `.obj` 之前 → `undefined reference to atan2f/sqrtf`。改用 `target_link_libraries(m)`
- 工程路径含中文，`objcopy` 经 `cmd.exe` 传绝对路径被转 GBK 乱码 → 后处理改相对文件名 + `WORKING_DIRECTORY`
- 顺带确认：调试器是 **CMSIS-DAP（FW 2.0.0）**，不是 ST-Link；cmake/ninja 原先没装，已 pip 装到 WorkBuddy 的 Python 环境

**留给下一轮**
- 烧录 + 串口验证（USART2 / PA2-PA3 / 115200）
- **注意**：`-u _printf_float` 目前没加，因为全工程没有 `%f`；VOFA 打印速度值时必须加
- `build/` 已被 git 忽略，产物不进版本库
