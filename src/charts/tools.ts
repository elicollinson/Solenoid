/**
 * Chart Tool Definitions
 *
 * Defines the render_chart tool following the AG-UI protocol pattern.
 * The tool accepts structured chart configuration data that the frontend
 * can use to render charts inline using ink-chart components.
 *
 * AG-UI Protocol Compliance:
 * - Tool has name, description, and JSON Schema parameters
 * - Tool calls are streamed to the frontend with full arguments
 * - Frontend handles rendering based on the tool call data
 */

import type { ToolDefinition } from '../llm/types.js';

/**
 * The render_chart tool definition following AG-UI protocol.
 * This tool is called by the chart agent to render charts in the UI.
 */
export const renderChartToolDef: ToolDefinition = {
  type: 'function',
  function: {
    name: 'render_chart',
    description: `Render a chart in the terminal UI. Supports bar charts, stacked bar charts, line graphs, and sparklines. The chart will be displayed inline in the chat.

Choose the appropriate chart type:
- bar: For comparing values across categories
- stackedBar: For showing composition/distribution of a whole
- line: For showing trends over time with multiple series
- sparkline: For compact trend visualization in a single line`,
    parameters: {
      type: 'object',
      properties: {
        chartType: {
          type: 'string',
          description: 'The type of chart to render',
          enum: ['bar', 'stackedBar', 'line', 'sparkline'],
        },
        title: {
          type: 'string',
          description: 'Optional title to display above the chart',
        },
        // Bar chart properties
        barData: {
          type: 'string',
          description:
            'JSON array of bar chart data points. Each item should have: label (string), value (number), and optional color (string like "red", "blue", "green", "yellow", "cyan", "magenta"). Example: [{"label":"Q1","value":100},{"label":"Q2","value":150}]',
        },
        barSort: {
          type: 'string',
          description: 'Sort order for bar charts: "none", "asc", or "desc"',
          enum: ['none', 'asc', 'desc'],
        },
        barShowValue: {
          type: 'string',
          description: 'Where to show values on bar charts: "right", "inside", or "none"',
          enum: ['right', 'inside', 'none'],
        },
        // Stacked bar properties
        stackedData: {
          type: 'string',
          description:
            'JSON array of stacked bar segments. Each item should have: label (string), value (number), and optional color. Example: [{"label":"Product A","value":40,"color":"blue"},{"label":"Product B","value":30,"color":"green"}]',
        },
        stackedMode: {
          type: 'string',
          description: 'Display mode for stacked bar: "percentage" or "absolute"',
          enum: ['percentage', 'absolute'],
        },
        // Line graph properties
        lineSeries: {
          type: 'string',
          description:
            'JSON array of line series. Each series has: data (array of numbers), optional label (string), optional color. Example: [{"label":"Sales","data":[10,20,15,30,25],"color":"blue"}]',
        },
        lineHeight: {
          type: 'string',
          description: 'Height of line graph in rows (number as string, e.g., "10")',
        },
        lineXLabels: {
          type: 'string',
          description: 'JSON array of x-axis labels. Example: ["Jan","Feb","Mar","Apr","May"]',
        },
        // Sparkline properties
        sparklineData: {
          type: 'string',
          description: 'JSON array of numbers for sparkline. Example: [1,3,5,2,8,4,6]',
        },
        sparklineColor: {
          type: 'string',
          description: 'Color scheme for sparkline: "red", "blue", or "green"',
          enum: ['red', 'blue', 'green'],
        },
        sparklineMode: {
          type: 'string',
          description: 'Rendering mode for sparkline: "block" or "braille"',
          enum: ['block', 'braille'],
        },
        // General
        width: {
          type: 'string',
          description:
            'Width of the chart in characters (number as string, e.g., "60"). Defaults to 60.',
        },
      },
      required: ['chartType'],
    },
  },
};

/**
 * Parse chart tool arguments into a structured config object.
 * Handles JSON parsing of data arrays and converts string numbers.
 */
export function parseChartArgs(args: Record<string, unknown>): {
  success: boolean;
  config?: import('./types.js').ChartConfig;
  error?: string;
} {
  try {
    const chartType = args.chartType as string;
    const title = args.title as string | undefined;
    const width = args.width ? Number.parseInt(args.width as string, 10) : 60;

    switch (chartType) {
      case 'bar': {
        const dataStr = args.barData as string;
        if (!dataStr) {
          return { success: false, error: 'barData is required for bar charts' };
        }
        const data = JSON.parse(dataStr);
        return {
          success: true,
          config: {
            chartType: 'bar',
            title,
            data,
            sort: (args.barSort as 'none' | 'asc' | 'desc') || 'none',
            showValue: (args.barShowValue as 'right' | 'inside' | 'none') || 'right',
            width,
          },
        };
      }

      case 'stackedBar': {
        const dataStr = args.stackedData as string;
        if (!dataStr) {
          return { success: false, error: 'stackedData is required for stacked bar charts' };
        }
        const data = JSON.parse(dataStr);
        return {
          success: true,
          config: {
            chartType: 'stackedBar',
            title,
            data,
            mode: (args.stackedMode as 'percentage' | 'absolute') || 'percentage',
            showLabels: true,
            showValues: true,
            width,
          },
        };
      }

      case 'line': {
        const seriesStr = args.lineSeries as string;
        if (!seriesStr) {
          return { success: false, error: 'lineSeries is required for line graphs' };
        }
        const series = JSON.parse(seriesStr);
        const xLabelsStr = args.lineXLabels as string | undefined;
        const xLabels = xLabelsStr ? JSON.parse(xLabelsStr) : undefined;
        const height = args.lineHeight ? Number.parseInt(args.lineHeight as string, 10) : 10;
        return {
          success: true,
          config: {
            chartType: 'line',
            title,
            series,
            height,
            showYAxis: true,
            xLabels,
          },
        };
      }

      case 'sparkline': {
        const dataStr = args.sparklineData as string;
        if (!dataStr) {
          return { success: false, error: 'sparklineData is required for sparklines' };
        }
        const data = JSON.parse(dataStr);
        const threshold = args.sparklineThreshold
          ? Number.parseFloat(args.sparklineThreshold as string)
          : undefined;
        return {
          success: true,
          config: {
            chartType: 'sparkline',
            title,
            data,
            colorScheme: (args.sparklineColor as 'red' | 'blue' | 'green') || 'blue',
            mode: (args.sparklineMode as 'block' | 'braille') || 'block',
            threshold,
          },
        };
      }

      default:
        return { success: false, error: `Unknown chart type: ${chartType}` };
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return { success: false, error: `Failed to parse chart arguments: ${message}` };
  }
}
