# Runtime observations / 运行时观察

[English](#english) · [简体中文](#简体中文)

## English

Each observer decodes two archived input populations on one machine. These are post-incident observations, not historical actions executed on two machines. The original [numerical comparison](NUMERICAL_REPRODUCIBILITY.md) also records steps decoded on its comparison machine. Frozen 54's strict default failure remains a failure. 58 checks recorded observation consistency conditionally on the numerical library's binary64 and faithful elementary-function assumptions; it proves neither future bitwise identity nor trajectory identity.

| observer | cases | test arrays | original 54 exit | max logits | max T | max q | max step | CP options | test options |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original_comparison_machine | 96 | 48 | 0 | 2.6645352591003757e-15 | 8.882432167567345e-08 | 6.7894915245503284e-09 | 1.0269195577228274e-08 | 0 | 0 |
| default_hosted_observer | 96 | 48 | 1 | 2.6645352591003757e-15 | 8.882432167567345e-08 | 6.7894915245503284e-09 | 1.026919541069482e-08 | 0 | 0 |

## 简体中文

每个观察端在同一台机器上解码两份归档输入。这是故障后的新观察，不是两台机器历史上实际执行的动作。原数值比较页的步长同样由其比较机解码。冻结54的默认严格复算失败仍是失败。58在数值库明确的binary64及基本函数faithful舍入假设下核验记录观察的一致性，不证明未来逐位一致或闭环轨迹一致。表中数字逐项读取机器结果。

| observer | cases | test arrays | original 54 exit | max logits | max T | max q | max step | CP options | test options |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original_comparison_machine | 96 | 48 | 0 | 2.6645352591003757e-15 | 8.882432167567345e-08 | 6.7894915245503284e-09 | 1.0269195577228274e-08 | 0 | 0 |
| default_hosted_observer | 96 | 48 | 1 | 2.6645352591003757e-15 | 8.882432167567345e-08 | 6.7894915245503284e-09 | 1.026919541069482e-08 | 0 | 0 |
