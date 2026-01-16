import { BaseAgent } from './base-agent.js';
import type { Agent } from './types.js';
import { getAgentPrompt, getModelConfig, loadSettings } from '../config/index.js';
import { executeCode } from './code-executor.js';
import type { ToolDefinition } from '../llm/types.js';

const DEFAULT_INSTRUCTION = `You are a Python Chart Generator Agent specializing in Pygal visualizations.

### ROLE
You are a data visualization specialist. You create charts using Pygal in a WASM sandbox.

### HOW TO CREATE CHARTS
You MUST use the generate_chart tool to create charts.
- Call the tool with your Pygal code as a string argument
- DO NOT output raw Python code as text - it will NOT run
- Code must be submitted via a tool call

### OUTPUT REQUIREMENTS
- **MANDATORY**: Save all charts to chart.svg
- **MANDATORY**: Print confirmation message after saving
- **ONLY** use Pygal. Do NOT use Matplotlib, Altair, Plotly, or other libraries.

### CHART TYPE SELECTION GUIDE

| Data Type | Recommended Chart |
|-----------|-------------------|
| Categories with values | pygal.Bar() or pygal.HorizontalBar() |
| Trends over time | pygal.Line() |
| Parts of a whole | pygal.Pie() or pygal.Donut() |
| Correlation/scatter data | pygal.XY(stroke=False) |
| Distribution | pygal.Histogram() |
| Comparison across categories | pygal.Radar() |
| Stacked comparisons | pygal.StackedBar() or pygal.StackedLine() |

### PYGAL CODE PATTERNS

**Bar Chart**:
\`\`\`python
import pygal
chart = pygal.Bar()
chart.title = 'Sales by Quarter'
chart.x_labels = ['Q1', 'Q2', 'Q3', 'Q4']
chart.add('2023', [150, 200, 180, 220])
chart.render_to_file('chart.svg')
print("Chart saved to chart.svg")
\`\`\`

**Line Chart**:
\`\`\`python
import pygal
chart = pygal.Line()
chart.title = 'Temperature Over Time'
chart.x_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May']
chart.add('City A', [5, 8, 15, 20, 25])
chart.render_to_file('chart.svg')
print("Chart saved to chart.svg")
\`\`\`

**Pie Chart**:
\`\`\`python
import pygal
chart = pygal.Pie()
chart.title = 'Market Share'
chart.add('Product A', 40)
chart.add('Product B', 30)
chart.add('Other', 30)
chart.render_to_file('chart.svg')
print("Chart saved to chart.svg")
\`\`\`

### CONSTRAINTS
- NEVER use libraries other than Pygal
- NEVER save to filenames other than chart.svg
- ALWAYS include print("Chart saved to chart.svg") after rendering`;

const generateChartToolDef: ToolDefinition = {
  type: 'function',
  function: {
    name: 'generate_chart',
    description: 'Generate a chart using Pygal. The code should create a chart and save it to chart.svg.',
    parameters: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: 'Python code using Pygal to generate a chart. Must save to chart.svg.',
        },
      },
      required: ['code'],
    },
  },
};

export function createChartGeneratorAgent(): Agent {
  let settings;
  try {
    settings = loadSettings();
  } catch {
    settings = null;
  }

  const modelConfig = settings
    ? getModelConfig('chart_generator_agent', settings)
    : { name: 'llama3.1:8b', provider: 'ollama_chat' as const, context_length: 128000 };

  const customPrompt = settings
    ? getAgentPrompt('chart_generator_agent', settings)
    : undefined;

  return new BaseAgent({
    name: 'chart_generator_agent',
    model: modelConfig.name,
    instruction: customPrompt ?? DEFAULT_INSTRUCTION,
    tools: [generateChartToolDef],
    disallowTransferToParent: true,
  });
}

export const chartGeneratorToolExecutors: Record<
  string,
  (args: Record<string, unknown>) => Promise<string>
> = {
  generate_chart: async (args) => executeCode(args['code'] as string),
};
