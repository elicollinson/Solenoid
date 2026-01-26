/**
 * Chart Renderer Component
 *
 * Renders charts inline in the chat using ink-chart components.
 * Supports bar charts, stacked bar charts, line graphs, and sparklines.
 *
 * AG-UI Protocol Compliance:
 * - Receives chart configuration from tool call arguments
 * - Renders charts based on the structured data
 * - Charts appear inline in the message flow
 */
import { Box, Text } from 'ink';
import { BarChart, StackedBarChart, LineGraph, Sparkline } from '@pppp606/ink-chart';
import { parseChartArgs } from '../../charts/index.js';
import type {
  BarChartConfig,
  StackedBarChartConfig,
  LineGraphConfig,
  SparklineConfig,
} from '../../charts/types.js';

interface ChartRendererProps {
  toolArgs: Record<string, unknown>;
}

/**
 * Map color names to ink-compatible color values
 */
function mapColor(color: string | undefined): string | undefined {
  if (!color) return undefined;
  // ink supports these color names directly
  const validColors = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white', 'gray', 'grey'];
  if (validColors.includes(color.toLowerCase())) {
    return color.toLowerCase();
  }
  return 'cyan'; // default fallback
}

/**
 * Render a bar chart
 */
function RenderBarChart({ config }: { config: BarChartConfig }) {
  const data = config.data.map((item) => ({
    label: item.label,
    value: item.value,
    color: mapColor(item.color),
  }));

  return (
    <Box flexDirection="column">
      {config.title && (
        <Text bold color="cyan">{config.title}</Text>
      )}
      <Box marginTop={config.title ? 1 : 0}>
        <BarChart
          data={data}
          sort={config.sort || 'none'}
          showValue={config.showValue || 'right'}
          width={config.width || 60}
        />
      </Box>
    </Box>
  );
}

/**
 * Render a stacked bar chart
 */
function RenderStackedBarChart({ config }: { config: StackedBarChartConfig }) {
  const data = config.data.map((item) => ({
    label: item.label,
    value: item.value,
    color: mapColor(item.color),
  }));

  return (
    <Box flexDirection="column">
      {config.title && (
        <Text bold color="cyan">{config.title}</Text>
      )}
      <Box marginTop={config.title ? 1 : 0}>
        <StackedBarChart
          data={data}
          mode={config.mode || 'percentage'}
          showLabels={config.showLabels !== false}
          showValues={config.showValues !== false}
          width={config.width || 60}
        />
      </Box>
    </Box>
  );
}

/**
 * Render a line graph
 */
function RenderLineGraph({ config }: { config: LineGraphConfig }) {
  // ink-chart LineGraph uses 'values' not 'data' for series data
  const data = config.series.map((series) => ({
    values: series.data,
    color: mapColor(series.color),
  }));

  // Build legend if series have labels
  const legendItems = config.series
    .filter((s) => s.label)
    .map((s) => ({ label: s.label!, color: mapColor(s.color) || 'cyan' }));

  return (
    <Box flexDirection="column">
      {config.title && (
        <Text bold color="cyan">{config.title}</Text>
      )}
      {legendItems.length > 0 && (
        <Box marginTop={config.title ? 1 : 0} gap={2}>
          {legendItems.map((item, i) => (
            <Text key={i} color={item.color}>● {item.label}</Text>
          ))}
        </Box>
      )}
      <Box marginTop={1}>
        <LineGraph
          data={data}
          height={config.height || 10}
          showYAxis={config.showYAxis !== false}
          xLabels={config.xLabels}
          yDomain={config.yDomain || 'auto'}
        />
      </Box>
    </Box>
  );
}

/**
 * Render a sparkline
 */
function RenderSparkline({ config }: { config: SparklineConfig }) {
  return (
    <Box flexDirection="column">
      {config.title && (
        <Text bold color="cyan">{config.title}: </Text>
      )}
      <Box>
        <Sparkline
          data={config.data}
          colorScheme={config.colorScheme || 'blue'}
          mode={config.mode || 'block'}
          threshold={config.threshold}
        />
      </Box>
    </Box>
  );
}

/**
 * Main chart renderer that dispatches to the appropriate chart component
 */
export function ChartRenderer({ toolArgs }: ChartRendererProps) {
  const result = parseChartArgs(toolArgs);

  if (!result.success || !result.config) {
    return (
      <Box borderStyle="single" borderColor="red" paddingX={1}>
        <Text color="red">Chart Error: {result.error || 'Unknown error'}</Text>
      </Box>
    );
  }

  const config = result.config;

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="cyan"
      paddingX={1}
      paddingY={0}
      marginY={1}
    >
      {config.chartType === 'bar' && <RenderBarChart config={config} />}
      {config.chartType === 'stackedBar' && <RenderStackedBarChart config={config} />}
      {config.chartType === 'line' && <RenderLineGraph config={config} />}
      {config.chartType === 'sparkline' && <RenderSparkline config={config} />}
    </Box>
  );
}

/**
 * Check if a tool call is a chart render call
 */
export function isChartToolCall(toolName: string): boolean {
  return toolName === 'render_chart';
}
