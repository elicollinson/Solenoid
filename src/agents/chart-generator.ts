/**
 * Chart Generator Agent (ADK)
 *
 * Data visualization specialist using ink-chart for terminal-based charts.
 * Creates inline charts for various data types including bar, line, pie,
 * and sparkline charts directly in the terminal UI.
 *
 * Supported chart types:
 * - Bar: Categories with values (horizontal bars)
 * - StackedBar: Parts of a whole or composition
 * - Line: Trends over time with multiple series
 * - Sparkline: Compact trend visualization
 *
 * AG-UI Protocol Compliance:
 * - Uses structured tool calls with JSON Schema parameters
 * - Tool call data is streamed to the frontend for rendering
 * - Charts are rendered inline in the chat using ink-chart components
 *
 * Google ADK Compatibility:
 * - Uses @google/adk LlmAgent for ADK-compatible agent
 * - Exports ADK-compatible FunctionTool for use with @google/adk
 */
import { LlmAgent, FunctionTool } from '@google/adk';
import { getAgentPrompt, loadSettings, getAdkModelName } from '../config/index.js';
import { parseChartArgs } from '../charts/index.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';
import { z } from 'zod';

const DEFAULT_INSTRUCTION = `You are a Chart Generator Agent specializing in terminal-based data visualizations.

### ROLE
You create charts that render directly in the terminal using the render_chart tool. Charts appear inline in the chat interface.

### HOW TO CREATE CHARTS
You MUST use the render_chart tool to create charts.
- Call the tool with the appropriate chartType and data
- Data must be provided as JSON strings
- DO NOT output raw data as text - use the tool

### CHART TYPE SELECTION GUIDE

| Data Type | Recommended Chart |
|-----------|-------------------|
| Categories with values | chartType: "bar" with barData |
| Parts of a whole / composition | chartType: "stackedBar" with stackedData |
| Trends over time | chartType: "line" with lineSeries |
| Compact trend / inline sparkline | chartType: "sparkline" with sparklineData |

### CHART PARAMETERS

**Bar Chart (chartType: "bar")**
- barData: JSON array of objects with label, value, and optional color
- barSort: "none", "asc", or "desc"
- barShowValue: "right", "inside", or "none"
- Example barData: '[{"label":"Q1","value":100,"color":"green"},{"label":"Q2","value":150,"color":"blue"}]'

**Stacked Bar Chart (chartType: "stackedBar")**
- stackedData: JSON array of segments with label, value, and optional color
- stackedMode: "percentage" or "absolute"
- Example stackedData: '[{"label":"Product A","value":40,"color":"blue"},{"label":"Product B","value":35,"color":"green"},{"label":"Other","value":25,"color":"yellow"}]'

**Line Graph (chartType: "line")**
- lineSeries: JSON array of series, each with data array, optional label and color
- lineHeight: Height in rows (e.g., "10")
- lineXLabels: JSON array of x-axis labels
- Example lineSeries: '[{"label":"Sales","data":[10,20,15,30,25],"color":"cyan"},{"label":"Costs","data":[8,12,14,18,20],"color":"magenta"}]'

**Sparkline (chartType: "sparkline")**
- sparklineData: JSON array of numbers
- sparklineColor: "red", "blue", or "green"
- sparklineMode: "block" or "braille"
- Example sparklineData: '[5,10,3,8,15,7,12,9,14,6]'

### COMMON PARAMETERS
- title: Optional title displayed above the chart
- width: Chart width in characters (default: 60)

### AVAILABLE COLORS
Use these color names: "red", "green", "blue", "yellow", "cyan", "magenta", "white", "gray"

### EXAMPLE TOOL CALLS

**Bar Chart Example:**
\`\`\`json
{
  "chartType": "bar",
  "title": "Quarterly Sales",
  "barData": "[{\\"label\\":\\"Q1\\",\\"value\\":150,\\"color\\":\\"cyan\\"},{\\"label\\":\\"Q2\\",\\"value\\":200,\\"color\\":\\"green\\"},{\\"label\\":\\"Q3\\",\\"value\\":180,\\"color\\":\\"yellow\\"},{\\"label\\":\\"Q4\\",\\"value\\":220,\\"color\\":\\"magenta\\"}]",
  "barSort": "none",
  "barShowValue": "right"
}
\`\`\`

**Line Graph Example:**
\`\`\`json
{
  "chartType": "line",
  "title": "Monthly Revenue",
  "lineSeries": "[{\\"label\\":\\"2023\\",\\"data\\":[100,120,115,140,160,155,180],\\"color\\":\\"cyan\\"},{\\"label\\":\\"2024\\",\\"data\\":[110,130,145,165,175,190,210],\\"color\\":\\"green\\"}]",
  "lineXLabels": "[\\"Jan\\",\\"Feb\\",\\"Mar\\",\\"Apr\\",\\"May\\",\\"Jun\\",\\"Jul\\"]",
  "lineHeight": "12"
}
\`\`\`

### CONSTRAINTS
- ALWAYS use the render_chart tool to create visualizations
- Choose the most appropriate chart type for the data
- Use descriptive titles that explain what the chart shows
- Use colors to distinguish different data series or categories
- Keep labels concise but meaningful`;

/**
 * Google ADK FunctionTool for chart rendering.
 *
 * This tool is compatible with @google/adk's LlmAgent and follows
 * the ADK pattern of using Zod schemas for parameter validation.
 *
 * AG-UI Protocol: The tool returns structured data that the frontend
 * can use to render charts inline using ink-chart components.
 */
export const renderChartAdkTool = new FunctionTool({
  name: 'render_chart',
  description: `Render a chart in the terminal UI. Supports bar charts, stacked bar charts, line graphs, and sparklines.

Choose the appropriate chart type:
- bar: For comparing values across categories
- stackedBar: For showing composition/distribution of a whole
- line: For showing trends over time with multiple series
- sparkline: For compact trend visualization in a single line`,
  parameters: z.object({
    chartType: z.enum(['bar', 'stackedBar', 'line', 'sparkline'])
      .describe('The type of chart to render'),
    title: z.string().optional()
      .describe('Optional title to display above the chart'),
    // Bar chart parameters
    barData: z.string().optional()
      .describe('JSON array of bar chart data points. Each item: {label, value, color?}'),
    barSort: z.enum(['none', 'asc', 'desc']).optional()
      .describe('Sort order for bar charts'),
    barShowValue: z.enum(['right', 'inside', 'none']).optional()
      .describe('Where to show values on bar charts'),
    // Stacked bar parameters
    stackedData: z.string().optional()
      .describe('JSON array of stacked bar segments. Each item: {label, value, color?}'),
    stackedMode: z.enum(['percentage', 'absolute']).optional()
      .describe('Display mode for stacked bar'),
    // Line graph parameters
    lineSeries: z.string().optional()
      .describe('JSON array of line series. Each: {data: number[], label?, color?}'),
    lineHeight: z.string().optional()
      .describe('Height of line graph in rows'),
    lineXLabels: z.string().optional()
      .describe('JSON array of x-axis labels'),
    // Sparkline parameters
    sparklineData: z.string().optional()
      .describe('JSON array of numbers for sparkline'),
    sparklineColor: z.enum(['red', 'blue', 'green']).optional()
      .describe('Color scheme for sparkline'),
    sparklineMode: z.enum(['block', 'braille']).optional()
      .describe('Rendering mode for sparkline'),
    // General
    width: z.string().optional()
      .describe('Width of the chart in characters'),
  }),
  execute: async (params) => {
    const result = parseChartArgs(params as Record<string, unknown>);
    if (!result.success) {
      return { status: 'error', error: result.error };
    }
    const config = result.config!;
    return {
      status: 'success',
      chartType: config.chartType,
      title: config.title,
      // Include the full config for AG-UI frontend rendering
      chartConfig: config,
    };
  },
});

// Load settings with fallback
let settings: ReturnType<typeof loadSettings> | null;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const adkModelName = settings
  ? getAdkModelName('chart_generator_agent', settings)
  : 'gemini-2.5-flash';

const customPrompt = settings
  ? getAgentPrompt('chart_generator_agent', settings)
  : undefined;

/**
 * Chart Generator LlmAgent - ink-chart visualization specialist (Google ADK)
 *
 * This is the primary ADK-compatible agent that uses the Google ADK LlmAgent
 * with the renderChartAdkTool for terminal-based chart rendering.
 */
export const chartGeneratorAgent = new LlmAgent({
  name: 'chart_generator_agent',
  model: adkModelName,
  description: 'Data visualization specialist that creates terminal charts using ink-chart.',
  instruction: customPrompt ?? DEFAULT_INSTRUCTION,
  tools: [renderChartAdkTool],
  afterModelCallback: saveMemoriesOnFinalResponse,
});

/**
 * Factory function for creating chart generator agent.
 * Returns the ADK LlmAgent for use in the agent hierarchy.
 */
export function createChartGeneratorAgent(): LlmAgent {
  return chartGeneratorAgent;
}

/**
 * Tool executors for the chart generator agent.
 * The render_chart tool parses the arguments and returns a success message.
 * The actual rendering happens on the frontend based on the tool call data.
 */
export const chartGeneratorToolExecutors: Record<
  string,
  (args: Record<string, unknown>) => Promise<string>
> = {
  render_chart: async (args) => {
    const result = parseChartArgs(args);
    if (!result.success) {
      return `Error: ${result.error}`;
    }
    const config = result.config!;
    return `Chart rendered successfully: ${config.chartType} chart${config.title ? ` - "${config.title}"` : ''}`;
  },
};
