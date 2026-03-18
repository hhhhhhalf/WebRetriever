<h1 align="center">🌐 WebRetriever: A Large-Scale Comprehensive Benchmark for Efficient Web Agent Evaluation</h1>
<p align="center">
<a href="https://github.com/hhhhhhalf/WebRetriever">📃 Paper</a>
•
<a href="https://github.com/hhhhhhalf/WebRetriever">🏆 Leaderboard</a>
•
<a href="https://github.com/hhhhhhalf/WebRetriever">🤗 Data</a>
</p>


## :bulb: Motivation
<p align="center">
  <img src="figure1.png" alt="Motivation for the WebRetriever benchmark." width="80%">
</p>
<p align="center"><em>Figure 1. Motivation for the WebRetriever benchmark. WebRetriever addresses key limitations of prior work from three aspects: dataset scale and diversity, automated evaluation reliability, and deployment-oriented evaluation protocols.</em></p>


## :page_facing_up: Abstract
<div style="max-width:900px; margin:auto; text-align: justify;">
As web agents increasingly demonstrate capabilities in automated task execution, the development of robust evaluation frameworks for assessing their navigation and task completion performance has emerged as a critical research priority. However, existing benchmarks exhibit several fundamental limitations. First, they suffer from insufficient scale and limited domain diversity, thereby constraining comprehensive evaluation of cross-domain generalization. Second, prevailing LLM-as-Judge evaluation methodologies inadequately capture fine-grained interaction semantics, particularly regarding precise query formulation and filtering operations. Third, current benchmarks predominantly emphasize navigation success metrics while neglecting critical requirements for real-world deployment scenarios. To address these limitations, we introduce WebRetriever, a large-scale benchmark encompassing 800 websites and 1,500 tasks across diverse domains, including consumer, professional, and enterprise sectors, with comprehensive coverage of user intent patterns. We propose NavEval (Navigation Evaluation), a novel LLM-as-Judge framework that leverages rich interaction context beyond visual screenshots, achieving state-of-the-art alignment with human judgment across multiple evaluation datasets. Furthermore, we establish three complementary evaluation protocols that collectively provide holistic assessment of web agent capabilities: navigation proficiency, knowledge-assisted interaction, and end-to-end task completion with information extraction. Extensive experimental analysis reveals substantial performance disparities across evaluation protocols, demonstrating that navigation success alone serves as an insufficient predictor of real-world application effectiveness. WebRetriever delivers fine-grained diagnostic insights into agent capabilities and establishes a rigorous foundation for advancing web agent research and development.
</div>
<br>
<div style="max-width:900px; margin:auto; text-align: justify;">
随着网络智能体在自动化任务执行方面的能力日益增强，开发用于评估其导航和任务完成性能的稳健评估框架已成为一项重要的研究重点。然而，现有的基准测试存在一些根本性的局限性。首先，它们规模不足且领域多样性有限，从而限制了对跨领域泛化能力的全面评估。其次，目前主流的 LLM-as-Judge 的评估方法未能充分捕捉细粒度的交互语义，尤其是在精确的查询构建和过滤操作方面。第三，当前的基准测试主要侧重于导航成功指标，而忽略了实际部署场景的关键需求。为了解决这些局限性，我们推出了 WebRetriever，这是一个涵盖 800 个网站和 1500 个任务的大规模基准测试，涉及消费者、专业人士和企业等多个领域，并全面覆盖了用户意图模式。我们提出了 NavEval（导航评估），这是一个新型的 LLM-as-Judge 的框架，它利用了除视觉截图之外的丰富交互上下文，在多个评估数据集上实现了与人类判断结果的最佳一致性。此外，我们建立了三种互补的评估协议，共同对网络代理的能力进行全面评估：导航能力、知识辅助交互以及包含信息提取的端到端任务完成情况。大量的实验分析揭示了不同评估协议之间存在显著的性能差异，表明仅凭导航成功不足以预测实际应用的效果。 WebRetriever 提供了对代理能力的细粒度诊断洞察，并为推进网络智能体的研究和开发奠定了坚实的基础。
</div>

## :star: Main Contributions
> 1. **A large-scale, comprehensive benchmark for realistic web agent evaluation:**  
We curate 1,500 tasks across 800 real websites spanning diverse domains and user intents. Compared with prior benchmarks, WebRetriever provides unprecedented scale, diversity, and coverage, enabling more comprehensive and representative evaluation of web agents in realistic online environments.
>
> 2. **A general and high-precision automated evaluation method:**  
We propose NavEval, an automated evaluation method that attains approximately 90% human-level agreement in large-scale experiments, thereby enabling practical and reliable assessment of web agent performance at scale and in real-time.
>
> 3. **Comprehensive evaluation framework:**  
We propose three complementary evaluation protocols to systematically assess web agents, explicitly disentangling navigation success from answer correctness and characterizing behavioral reliability under injected operational knowledge, thereby providing diagnostic signals missing from prior benchmarks.


## :bar_chart: Dataset Construction
<p align="center">
  <img src="table1.png" width="70%">
</p>

## :brain: NavEval
<p align="center">
  <img src="figure2.png" alt="" width="70%">
</p>
<p align="center"><em>Figure 2. Workflow of NavEval. Compared to existing methods, NavEval applies rule-based filtering to extract fine-grained intermediate signals, which are then jointly reasoned with the task description, action trajectory, and final screenshot by an LLM to determine task success, enabling robust evaluation with higher human agreement rates.</em></p>

## :clipboard: Evaluation Protocols
<p align="center">
  <img src="figure3.png" alt="" width="70%">
</p>
<p align="center"><em>Figure 3. Workflow of the semi-automated pipeline for constructing operational documentation in Protocol II. The process integrates automated exploration, evaluation, manual refinement, and LLM-based generation to produce high-quality operational documentation.</em></p>
<br>

We design three complementary evaluation protocols for comprehensive assessment:
> 1. **Protocol I** evaluates basic navigation ability to reach target pages.
>  
> 2. **Protocol II** assesses navigation performance when provided with operational knowledge.
> 
> 3. **Protocol III** measures end-to-end task completion by jointly evaluating navigation and information extraction, avoiding the limitation of equating page arrival with task success.


## :chart_with_upwards_trend: Experiment Results
<p align="center">
  <img src="table2.png" width="80%">
</p>
<br>
<p align="center">
  <img src="table3.png" width="80%">
</p>
<br>
<p align="center">
  <img src="table4.png" width="80%">
</p>
