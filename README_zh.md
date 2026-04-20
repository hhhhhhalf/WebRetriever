<h1 align="center">🌐 WebRetriever: 用于高效网络智能体评估的大规模综合基准</h1>
<p align="center">
<a href="https://github.com/hhhhhhalf/WebRetriever">📃 论文</a>
•
<a href="https://github.com/hhhhhhalf/WebRetriever">🏆 排行榜</a>
•
<a href="https://github.com/hhhhhhalf/WebRetriever">🤗 数据 (即将发布)</a>
•
🔤中文|<a href="https://github.com/hhhhhhalf/WebRetriever/blob/main/README.md">English</a>
</p>

## :bulb: 动机

<p align="center">
  <img src="figure1.png" alt="WebRetriever 基准测试的动机。" width="80%">
</p>
<p align="center"><em>图 1. WebRetriever 基准测试的动机。WebRetriever 从三个方面解决了先前工作的关键局限性：数据集规模和多样性、自动化评估的可靠性，以及面向部署的评估协议。</em>
</p>

## :page_facing_up: 摘要

<div style="max-width:900px; margin:auto; text-align: justify;">
随着网络智能体在自动化任务执行方面日益展现出强大能力，开发稳健的评估框架以衡量其导航与任务完成性能已成为关键的研究重点。然而，现有基准测试存在若干根本性局限。首先，它们规模不足且领域多样性有限，从而制约了对跨领域泛化能力的全面评估。其次，主流的 LLM-as-Judge 评估方法未能充分捕捉细粒度的交互语义，特别是在精确查询构建和筛选操作方面。第三，当前的基准测试主要强调导航成功率指标，而忽视了现实世界部署场景中的关键需求。为应对这些局限，我们推出了 WebRetriever，这是一个大规模基准测试，涵盖 800 个网站和 1,500 项任务，横跨消费、专业和企业等多个领域，全面覆盖了用户意图模式。我们提出了 NavEval（导航评估），这是一个新颖的 LLM-as-Judge 框架，它利用了超越视觉截图的丰富交互上下文，在多个评估数据集上实现了与人类判断最先进的对齐。此外，我们建立了三种互补的评估协议，共同对网络智能体能力进行整体评估：导航熟练度、知识辅助交互以及包含信息提取的端到端任务完成。广泛的实验分析揭示了不同评估协议之间存在显著的性能差异，表明仅凭导航成功率不足以预测实际应用的有效性。WebRetriever 为智能体能力提供了细粒度的诊断洞察，并为推进网络智能体的研发奠定了严谨的基础。
</div>

## :star: 主要贡献

> 1. **一个用于现实网络智能体评估的大规模、综合性基准：**
> 我们精心策划了涵盖 800 个真实网站、横跨不同领域和用户意图的 1,500 项任务。与现有基准相比，WebRetriever 提供了前所未有的规模、多样性和覆盖范围，能够在真实的在线环境中对网络智能体进行更全面、更具代表性的评估。
>
> 2. **一种通用且高精度的自动化评估方法：**
> 我们提出了 NavEval，这是一种自动化评估方法，在大规模实验中达到了约 90% 的人类水平一致性，从而能够大规模、实时地对网络智能体性能进行实用且可靠的评估。
>
> 3. **综合性评估框架：**
> 我们提出了三种互补的评估方案来系统性地评估网络智能体，明确地将导航成功与答案正确性区分开来，并描述了在注入操作知识下的行为可靠性，从而提供了现有基准中缺失的诊断信号。

## :bar_chart: 数据集构建

<p align="center"><em>表 1. WebRetriever 与相关基准测试的对比。<strong>意图类型</strong>: 任务意图类型 (<strong>G</strong>: 通用, <strong>P</strong>: 专业, <strong>G</strong>&<strong>P</strong>: 两者兼具); <strong>设置</strong>: 评估环境配置; <strong>在线</strong>: 是否支持在真实环境中进行在线实时连接评估; <strong>交互性</strong>: 环境是否允许交互; <strong>网站数量</strong>: 网站数量; <strong>评估任务数</strong>: 评估任务数量。</em>
</p>
<p align="center">
  <img src="table1.png" width="70%">
</p>

## :brain: NavEval

<p align="center">
  <img src="figure2.png" alt="" width="70%">
</p>
<p align="center"><em>图 2. NavEval 的工作流程。与现有方法相比，NavEval 应用基于规则的过滤来提取细粒度的中间信号，然后由大语言模型将这些信号与任务描述、动作轨迹和最终截图进行联合推理，以确定任务是否成功，从而实现更稳健的评估，并获得更高的人类一致性评分。</em>
</p>

## :clipboard: 评估协议

<p align="center">
  <img src="figure3.png" alt="" width="70%">
</p>
<p align="center"><em>图 3. 协议 II 中构建操作文档的半自动化流程工作流。该流程集成了自动探索、评估、人工精炼和基于 LLM 的生成，以产出高质量的操作文档。</em></p>
<br>

我们设计了三种互补的评估协议，以进行全面评估：

> 1.  **协议 I** 评估到达目标页面的基本导航能力。
>
> 2.  **协议 II** 评估在提供操作知识时的导航性能。
>
> 3.  **协议 III** 通过联合评估导航和信息提取来衡量端到端任务完成情况，避免了将到达页面等同于任务成功的局限性。

## :chart_with_upwards_trend: 实验结果

<p align="center"><em>表 2. 在 WebRetriever 数据集上，网络智能体轨迹在三种提出的评估协议下的任务成功率 (SR)，分别使用 NavEval 和人工标注进行评估。所有数值均以百分比 (%) 报告。</em>
</p>
<p align="center">
  <img src="table2.png" width="60%">
</p>
<br>
<p align="center"><em>表 3. 在 WebRetriever 数据集上，使用不同 LLM-as-a-Judge 模型的自动化评估方法对网络智能体轨迹的人类一致性评分 (AR)。Avg AR 表示平均人类一致性评分。所有数值均以百分比 (%) 报告。</em>
</p>
<p align="center">
  <img src="table3.png" width="80%">
</p>
<br>
<p align="center"><em>表 4. 在 Online-Mind2Web 数据集上，使用不同 LLM-as-a-Judge 模型的自动化评估方法对网络智能体轨迹的人类一致性评分 (AR)。Avg AR 表示平均人类一致性评分。所有数值均以百分比 (%) 报告。</em>
</p>
<p align="center">
  <img src="table4.png" width="60%">
</p>
