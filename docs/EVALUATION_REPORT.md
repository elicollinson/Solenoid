# Multi-Agent System Evaluation: Comparative Analysis of Small Language Models

**Technical Report | December 2024**

---

## Executive Summary

This report presents findings from a systematic evaluation of five small language models (SLMs) operating within a hierarchical multi-agent system. The evaluation framework comprises 20 standardized test cases across 9 behavioral categories, with each model undergoing 5 sequential runs to establish statistical reliability.

**Key Findings:**
- **GPT-OSS 20B** achieved the highest overall score (3.77/5.0) with the lowest variance
- **Qwen3 8B** delivered the best performance among sub-10B models (3.28/5.0)
- Tool calling and code execution remain challenging across all models
- Adversarial robustness varies dramatically (perfect scores to complete failure)

---

## 1. Introduction

### 1.1 Background

Multi-agent systems powered by language models represent an emerging paradigm for autonomous task completion. Unlike single-model approaches, these systems decompose complex tasks across specialized agents with distinct capabilities. This architecture introduces unique challenges:

- **Routing decisions**: Determining which agent handles each request
- **Inter-agent coordination**: Maintaining context across agent boundaries
- **Constraint adherence**: Respecting architectural boundaries (e.g., peer transfer prevention)
- **Tool utilization**: Correctly invoking external tools via structured function calls

### 1.2 Research Questions

1. How do different SLMs compare when operating as the core reasoning engine in a multi-agent system?
2. Which capabilities are most challenging for small models in agentic contexts?
3. What is the variance in model performance across repeated trials?

---

## 2. Methodology

### 2.1 System Architecture

The evaluation system implements a hierarchical multi-agent architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    user_proxy_agent                      │
│         (Gateway + Quality Gate Enforcement)             │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                     prime_agent                          │
│              (Router + Direct Answerer)                  │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                   planning_agent                         │
│            (Orchestrator + Task Decomposer)              │
└───┬─────────┬─────────┬─────────┬─────────┬────────────┘
    │         │         │         │         │
    ▼         ▼         ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│ code  │ │ chart │ │research│ │  mcp  │ │generic│
│executor│ │  gen  │ │ agent │ │ agent │ │executor│
└───────┘ └───────┘ └───────┘ └───────┘ └───────┘
```

**Agent Responsibilities:**
- **user_proxy_agent**: Request intake, quality gate enforcement, response validation
- **prime_agent**: Routing decisions between direct answers and delegation
- **planning_agent**: Multi-step task decomposition, agent coordination
- **code_executor_agent**: Python execution in WASM sandbox
- **chart_generator_agent**: Pygal-based visualization generation
- **research_agent**: Web search and page content retrieval
- **mcp_agent**: MCP server interactions (documentation, file operations)
- **generic_executor_agent**: General knowledge and text tasks

### 2.2 Models Under Evaluation

| Model | Parameters | Provider | Quantization |
|-------|-----------|----------|--------------|
| GPT-OSS 20B | 20B | Ollama | Q4_K_M |
| Ministral-3 8B | 8B | Ollama | Base |
| Ministral-3 14B | 14B | Ollama | Base |
| Granite4 Tiny | ~2B | Ollama | Hybrid |
| Qwen3 8B | 8B | Ollama | Base |

All models were accessed via LiteLLM with Ollama as the inference backend, running on consumer hardware (Apple Silicon).

### 2.3 Test Suite Design

The evaluation framework comprises 20 test cases organized into 9 categories:

| Category | Test Count | Focus Area |
|----------|-----------|------------|
| Routing Decision | 3 | Agent selection accuracy |
| Planning Quality | 1 | Multi-step task decomposition |
| Sub-Agent Selection | 2 | Specialist agent matching |
| Error Handling | 2 | Graceful degradation |
| Specialist Quality | 3 | Tool usage correctness |
| Quality Gates | 1 | Response validation |
| Constraint Adherence | 2 | Architectural boundary respect |
| Complex Scenario | 2 | Multi-turn, multi-requirement tasks |
| Edge Case | 4 | Adversarial/unusual inputs |

Each test case includes 4-5 evaluation metrics with detailed rubrics on a 1-5 scale.

### 2.4 Evaluation Protocol

**Grading Methodology**: LLM-as-Judge using a separate model (GPT-OSS 20B) to evaluate responses against rubric criteria.

**Statistical Approach**:
- 5 sequential runs per model
- Same prompt set across all runs
- Aggregation via mean ± standard deviation
- Category-level and test-level statistics

---

## 3. Results

### 3.1 Overall Performance Summary

| Model | Mean Score | Std Dev | Min | Max | Rank |
|-------|-----------|---------|-----|-----|------|
| **GPT-OSS 20B** | **3.77** | 0.94 | 2.10 | 5.00 | 1 |
| **Qwen3 8B** | **3.28** | 1.24 | 1.00 | 4.90 | 2 |
| Ministral-3 8B | 3.10 | 1.27 | 1.05 | 4.85 | 3 |
| Ministral-3 14B | 2.88 | 1.20 | 1.00 | 5.00 | 4 |
| Granite4 Tiny | 2.82 | 0.89 | 1.60 | 5.00 | 5 |

**Key Observations:**
- GPT-OSS 20B leads with both highest mean and lowest variance
- Qwen3 8B outperforms larger Ministral-3 14B model
- Granite4 Tiny shows lowest variance despite lowest mean (consistent but limited)
- Parameter count does not directly predict performance in agentic contexts

### 3.2 Category-Level Analysis

#### Performance Heatmap (Mean Scores)

| Category | GPT-OSS 20B | Qwen3 8B | Ministral 8B | Ministral 14B | Granite4 |
|----------|-------------|----------|--------------|---------------|----------|
| Routing Decision | 3.65 | 3.65 | 3.53 | 3.62 | 3.92 |
| Planning Quality | 4.20 | 2.38 | 3.12 | 3.23 | 1.64 |
| Sub-Agent Selection | 3.67 | 4.15 | 2.73 | 3.50 | 2.40 |
| Error Handling | 3.50 | 4.03 | 3.98 | 2.65 | 2.80 |
| Specialist Quality | 3.83 | 2.36 | 2.72 | 2.24 | 2.76 |
| Quality Gates | 4.20 | 4.20 | 4.55 | 1.00 | 2.80 |
| Constraint Adherence | 3.58 | 2.45 | 2.25 | 1.95 | 2.42 |
| Complex Scenario | 4.38 | 2.93 | 2.62 | 3.17 | 2.62 |
| Edge Case | 3.60 | 3.46 | 3.09 | 3.33 | 2.84 |

#### Category Analysis

**Routing Decision** (All models: 3.5-3.9)
- Relatively consistent across all models
- Simple factual vs. complex request differentiation well-handled
- Granite4 surprisingly leads, suggesting efficient heuristic matching

**Planning Quality** (Range: 1.64-4.20)
- Highest variance category
- GPT-OSS 20B excels (4.20) at multi-step task decomposition
- Granite4 Tiny struggles significantly (1.64)
- Requires explicit plan generation before delegation

**Quality Gates** (Range: 1.00-4.55)
- Ministral-3 8B achieves highest score (4.55)
- Ministral-3 14B complete failure (1.00) - did not validate response completeness
- Critical for production deployment

**Constraint Adherence** (Range: 1.95-3.58)
- All models struggle with architectural boundaries
- Peer transfer prevention inconsistently enforced
- Code re-execution prevention challenging

### 3.3 Per-Test Case Analysis

#### Strongest Performance (Score > 4.5 across models)

| Test Case | Description | Best Score | Achieving Model |
|-----------|-------------|------------|-----------------|
| TC-018 | Adversarial Injection (GPT-OSS) | 5.00 | GPT-OSS 20B |
| TC-003 | Ambiguous Request | 4.95 | GPT-OSS 20B |
| TC-017 | Empty Input Handling | 4.75 | Ministral-3 8B |
| TC-007 | Graceful Degradation | 4.70 | Ministral-3 8B |

#### Weakest Performance (Score < 2.0 across models)

| Test Case | Description | Worst Score | Affected Models |
|-----------|-------------|-------------|-----------------|
| TC-002 | Complex Computation | 2.10-2.15 | All models |
| TC-014 | No Re-execution | 1.05-2.35 | All models |
| TC-009 | Code Execution Print | 1.10-3.65 | All except GPT-OSS |
| TC-018 | Adversarial (non-GPT) | 1.20 | Ministral-3 8B |

### 3.4 Variance Analysis

**High-Variance Test Cases** (Std Dev > 1.5):
- TC-005 (Documentation Lookup): 1.95 std dev - MCP tool calling inconsistent
- TC-020 (Conflicting Instructions): 1.64 std dev - conflict recognition varies
- TC-015 (Context Preservation): 1.43 std dev - multi-turn state management

**Low-Variance Test Cases** (Std Dev < 0.3):
- TC-018 (Adversarial) for GPT-OSS: 0.00 std dev - perfectly consistent refusal
- TC-003 (Ambiguous Request): 0.11-0.14 std dev - consistent interpretation

---

## 4. Detailed Findings

### 4.1 Tool Calling Challenges

A persistent issue across all models was **tool calling format hallucination**. Models would output raw Python code as text instead of properly formatted JSON function calls:

```
# Incorrect (observed)
import math
result = math.factorial(25)
print(result)

# Correct (expected)
{"name": "execute_code", "arguments": {"code": "import math\\nresult = math.factorial(25)\\nprint(result)"}}
```

**Impact**: TC-002 (factorial calculation) and TC-009 (Fibonacci) consistently scored 2.0-2.5 across all models due to tool invocation failures.

**Mitigation Applied**: Added explicit "CRITICAL: HOW TO EXECUTE CODE" sections to agent prompts. Verbose WRONG/RIGHT examples paradoxically degraded performance (rolled back).

### 4.2 Adversarial Robustness Disparity

The adversarial test case (TC-018) revealed dramatic differences:

| Model | Score | Behavior |
|-------|-------|----------|
| GPT-OSS 20B | 5.00 | Perfect refusal + handled legitimate request |
| Qwen3 8B | 4.50 | Good refusal, partial legitimate handling |
| Ministral-3 14B | 4.40 | Adequate refusal |
| Ministral-3 8B | 1.20 | **Disclosed system instructions** |
| Granite4 Tiny | 2.25 | Partial disclosure |

**Finding**: Adversarial training quality varies significantly across model families. Ministral-3 8B's complete failure represents a critical deployment risk.

### 4.3 Model Size vs. Performance

Counter-intuitively, larger models did not always outperform smaller ones:

- **Ministral-3 14B (2.88) < Ministral-3 8B (3.10)**: Larger model underperformed
- **Qwen3 8B (3.28) > Ministral-3 14B (2.88)**: Architecture matters more than size
- **Granite4 Tiny (2.82)**: Competitive despite ~2B parameters

**Hypothesis**: Agentic capabilities depend on training data composition (tool use, instruction following) more than raw parameter count.

### 4.4 Quality Gate Effectiveness

The user_proxy_agent quality gate mechanism showed inconsistent enforcement:

- **COUNT CHECK**: Verifying N items when user asks for N
- **PARTS CHECK**: Ensuring all request parts addressed
- **ACTION CHECK**: Confirming actions done, not just described
- **DATA CHECK**: Validating numeric data presence

Models that scored high on Quality Gates (TC-012) demonstrated:
- Explicit enumeration before delivery
- Retry requests for incomplete responses
- Specific feedback on missing elements

### 4.5 Multi-Turn Context Preservation

TC-015 tested context retention across conversation turns:

| Model | Context Score | Behavior |
|-------|---------------|----------|
| GPT-OSS 20B | 4.30 | Reused prior research, minimal rework |
| Qwen3 8B | 4.40 | Excellent state retention |
| Ministral-3 14B | 5.00 | Perfect context preservation |
| Ministral-3 8B | 1.35 | Lost context, re-researched everything |
| Granite4 Tiny | 2.25 | Partial context loss |

**Finding**: Context window utilization and session state management vary dramatically.

---

## 5. Prompt Engineering Insights

### 5.1 Effective Patterns

**Explicit Decision Frameworks** worked well:
```
### QUICK TEST
Ask yourself TWO questions:
1. Does this need tools (code, charts, web search, files)?
2. Does this ask for sources, citations, or "research"?

If EITHER is YES → Delegate to planning_agent.
If BOTH are NO → Answer directly.
```

**Mandatory Quality Gates** improved validation:
```
### MANDATORY QUALITY GATES (CHECK EACH ONE)
1. **COUNT CHECK**: If user asked for N items, count them. Are there exactly N?
2. **PARTS CHECK**: Break request into parts. Was EACH part addressed?
3. **ACTION CHECK**: If action requested, was it DONE (not just described)?
4. **DATA CHECK**: If numbers requested, are they present and reasonable?
```

### 5.2 Anti-Patterns

**Verbose WRONG/RIGHT Examples** confused models:
- Added explicit "DO NOT output raw Python like this: ..." examples
- Models fixated on the negative examples, sometimes reproducing them
- Simpler guidance performed better

**Over-Specified Constraints** caused rigidity:
- "Maximum 3 delegation attempts per step" caused premature failure
- Models interpreted limits too strictly
- Flexible guidance ("try fallback if primary fails") worked better

---

## 6. Recommendations

### 6.1 For Model Selection

| Use Case | Recommended Model | Rationale |
|----------|------------------|-----------|
| Production (balanced) | GPT-OSS 20B | Highest overall, lowest variance |
| Resource-constrained | Qwen3 8B | Best sub-10B performance |
| Adversarial resistance | GPT-OSS 20B | Only model with perfect TC-018 |
| Avoid | Ministral-3 8B in adversarial contexts | Security risk |

### 6.2 For System Design

1. **Implement robust tool call validation**: Parse and validate function call format before execution
2. **Add retry mechanisms with format correction**: When tool calls fail parsing, provide format examples
3. **Layer multiple quality gates**: Don't rely on single-point validation
4. **Test adversarial robustness specifically**: Include prompt injection tests in evaluation

### 6.3 For Prompt Engineering

1. **Keep instructions concise**: Verbose examples can backfire
2. **Use positive framing**: "DO this" works better than "DON'T do that"
3. **Provide decision frameworks**: Checklists and flowcharts help routing
4. **Iterate with measurement**: Track metrics across prompt changes

---

## 7. Limitations

1. **Single grading model**: LLM-as-Judge may have biases toward similar models
2. **Limited model diversity**: All models from Ollama ecosystem
3. **Hardware constraints**: Consumer hardware may not reflect production performance
4. **Prompt sensitivity**: Results are specific to the tested prompt configurations
5. **Static test set**: 20 test cases may not cover all failure modes

---

## 8. Future Work

1. **Cross-grader validation**: Use multiple grading models to reduce bias
2. **Larger model inclusion**: Test 30B+ models for ceiling comparison
3. **Fine-tuning experiments**: Test tool-calling fine-tuned variants
4. **Latency analysis**: Add response time metrics to evaluation
5. **Expanded test suite**: Include more edge cases and domain-specific tests

---

## 9. Conclusion

This evaluation demonstrates that small language models can effectively operate within multi-agent systems, but with significant capability variance. GPT-OSS 20B emerges as the most capable and consistent option, while Qwen3 8B offers compelling performance in a smaller footprint.

Critical challenges remain in tool calling reliability and adversarial robustness. System designers should implement defense-in-depth strategies rather than relying solely on model capabilities.

The evaluation framework and methodology presented here provide a reproducible approach for ongoing model assessment as new releases become available.

---

## Appendix A: Raw Data Summary

### A.1 Model Configuration

```yaml
# Evaluation Configuration
models:
  grading_model: "ollama_chat/gpt-oss:20b"
  timeout_seconds: 300
  runs_per_model: 5
  test_cases: 20
```

### A.2 Batch Run Identifiers

| Model | Batch ID | Timestamp |
|-------|----------|-----------|
| GPT-OSS 20B | batch_20251206_140003_5runs | 2025-12-06 14:00 |
| Ministral-3 8B | batch_20251206_165039_5runs | 2025-12-06 16:50 |
| Ministral-3 14B | batch_20251207_095105_5runs | 2025-12-07 09:51 |
| Granite4 Tiny | batch_20251207_114304_5runs | 2025-12-07 11:43 |
| Qwen3 8B | batch_20251207_143634_5runs | 2025-12-07 14:36 |

### A.3 Test Case Distribution

| Category | Tests | Weight |
|----------|-------|--------|
| Routing Decision | TC-001, TC-002, TC-003 | 15% |
| Planning Quality | TC-004 | 5% |
| Sub-Agent Selection | TC-005, TC-006 | 10% |
| Error Handling | TC-007, TC-008 | 10% |
| Specialist Quality | TC-009, TC-010, TC-011 | 15% |
| Quality Gates | TC-012 | 5% |
| Constraint Adherence | TC-013, TC-014 | 10% |
| Complex Scenario | TC-015, TC-016 | 10% |
| Edge Case | TC-017, TC-018, TC-019, TC-020 | 20% |

---

## Appendix B: Evaluation Framework

The complete evaluation framework is available in the repository:
- Test cases: `tests/eval/agent_test_cases.csv`
- Runner script: `tests/eval/run_eval.py`
- Results: `tests/eval/eval_results/`

### Usage

```bash
# Single run
poetry run python tests/eval/run_eval.py

# Multi-run with aggregation
poetry run python tests/eval/run_eval.py --runs 5

# Specific test cases
poetry run python tests/eval/run_eval.py --cases TC-001,TC-002,TC-003
```

---

*Report generated: December 2024*
*Framework version: 1.0*
*Contact: [Repository Issues](https://github.com/)*
