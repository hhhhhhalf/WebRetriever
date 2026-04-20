<h1 align="center">🌐 WebRetriever: A Large-Scale Comprehensive Benchmark for Efficient Web Agent Evaluation</h1>
<p align="center">
<a href="https://github.com/hhhhhhalf/WebRetriever">📃 Paper</a>
•
<a href="https://github.com/hhhhhhalf/WebRetriever">🏆 Leaderboard</a>
•
<a href="https://github.com/hhhhhhalf/WebRetriever">🤗 Data (Release Soon)</a>
•
🔤English|<a href="https://github.com/hhhhhhalf/WebRetriever/blob/main/README_zh.md">中文</a>
</p>


## :bulb: Motivation
<p align="center">
  <img src="figure1.png" alt="Motivation for the WebRetriever benchmark." width="80%">
</p>
<p align="center"><em>Figure 1. Motivation for the WebRetriever benchmark. WebRetriever addresses key limitations of prior work from three aspects: dataset scale and diversity, automated evaluation reliability, and deployment-oriented evaluation protocols.</em>
</p>


## :page_facing_up: Abstract
<div style="max-width:900px; margin:auto; text-align: justify;">
As web agents increasingly demonstrate capabilities in automated task execution, the development of robust evaluation frameworks for assessing their navigation and task completion performance has emerged as a critical research priority. However, existing benchmarks exhibit several fundamental limitations. First, they suffer from insufficient scale and limited domain diversity, thereby constraining comprehensive evaluation of cross-domain generalization. Second, prevailing LLM-as-Judge evaluation methodologies inadequately capture fine-grained interaction semantics, particularly regarding precise query formulation and filtering operations. Third, current benchmarks predominantly emphasize navigation success metrics while neglecting critical requirements for real-world deployment scenarios. To address these limitations, we introduce WebRetriever, a large-scale benchmark encompassing 800 websites and 1,500 tasks across diverse domains, including consumer, professional, and enterprise sectors, with comprehensive coverage of user intent patterns. We propose NavEval (Navigation Evaluation), a novel LLM-as-Judge framework that leverages rich interaction context beyond visual screenshots, achieving state-of-the-art alignment with human judgment across multiple evaluation datasets. Furthermore, we establish three complementary evaluation protocols that collectively provide holistic assessment of web agent capabilities: navigation proficiency, knowledge-assisted interaction, and end-to-end task completion with information extraction. Extensive experimental analysis reveals substantial performance disparities across evaluation protocols, demonstrating that navigation success alone serves as an insufficient predictor of real-world application effectiveness. WebRetriever delivers fine-grained diagnostic insights into agent capabilities and establishes a rigorous foundation for advancing web agent research and development.
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
<p align="center"><em>Table 1. Comparison between WebRetriever and related benchmarks. <strong>Intent-Type</strong>: task intent type (<strong>G</strong>: general, <strong>P</strong>: professional, <strong>G</strong>&<strong>P</strong>: both); <strong>Setting</strong>: the evaluation environment configuration; <strong>Online</strong>: whether online live connection evaluation is supported in real-world environments; <strong>Interactive</strong>: whether the environment allows interaction; <strong>Websites</strong>: number of websites; <strong>Eval-Tasks</strong>: number of evaluation tasks.</em>
</p>
<p align="center">
  <img src="table1.png" width="70%">
</p>

## :brain: NavEval
<p align="center">
  <img src="figure2.png" alt="" width="70%">
</p>
<p align="center"><em>Figure 2. Workflow of NavEval. Compared to existing methods, NavEval applies rule-based filtering to extract fine-grained intermediate signals, which are then jointly reasoned with the task description, action trajectory, and final screenshot by an LLM to determine task success, enabling robust evaluation with higher human agreement rates.</em>
</p>

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
<p align="center"><em>Table 2. Task Success Rate (SR) of web agent trajectories on WebRetriever across the three proposed evaluation protocols, assessed using NavEval and human annotation, respectively. All values are reported as percentages (%).</em>
</p>
<p align="center">
  <img src="table2.png" width="60%">
</p>
<br>
<p align="center"><em>Table 3. Human Agreement Rate (AR) of web agent trajectories on WebRetriever across automated evaluation methods with different LLM-as-a-Judge models. Avg AR denotes the average human agreement rate. All values are reported as percentages (%).</em>
</p>
<p align="center">
  <img src="table3.png" width="80%">
</p>
<br>
<p align="center"><em>Table 4. Human Agreement Rate (AR) of web agent trajectories on Online-Mind2Web across automated evaluation methods with different LLM-as-a-Judge models. Avg AR denotes the average human agreement rate. All values are reported as percentages (%).</em>
</p>
<p align="center">
  <img src="table4.png" width="60%">
</p>
