/**
 * Chart Type Definitions
 *
 * Defines the data structures for ink-chart based visualizations.
 * These types are used by both the chart agent tool definitions and
 * the UI rendering components, following the AG-UI protocol pattern
 * where tool calls contain structured data for frontend rendering.
 */

/**
 * Bar chart data point with label, value, and optional color
 */
export interface BarChartDataPoint {
  label: string;
  value: number;
  color?: string;
}

/**
 * Configuration for bar charts
 */
export interface BarChartConfig {
  chartType: 'bar';
  title?: string;
  data: BarChartDataPoint[];
  sort?: 'none' | 'asc' | 'desc';
  showValue?: 'right' | 'inside' | 'none';
  width?: number;
}

/**
 * Stacked bar chart segment
 */
export interface StackedBarSegment {
  label: string;
  value: number;
  color?: string;
}

/**
 * Configuration for stacked bar charts
 */
export interface StackedBarChartConfig {
  chartType: 'stackedBar';
  title?: string;
  data: StackedBarSegment[];
  mode?: 'percentage' | 'absolute';
  showLabels?: boolean;
  showValues?: boolean;
  width?: number;
}

/**
 * Line graph data series
 */
export interface LineGraphSeries {
  label?: string;
  data: number[];
  color?: string;
}

/**
 * Configuration for line graphs
 */
export interface LineGraphConfig {
  chartType: 'line';
  title?: string;
  series: LineGraphSeries[];
  height?: number;
  showYAxis?: boolean;
  xLabels?: string[];
  yDomain?: [number, number];
}

/**
 * Configuration for sparklines
 */
export interface SparklineConfig {
  chartType: 'sparkline';
  title?: string;
  data: number[];
  colorScheme?: 'red' | 'blue' | 'green';
  mode?: 'block' | 'braille';
  threshold?: number;
}

/**
 * Union type for all chart configurations
 */
export type ChartConfig =
  | BarChartConfig
  | StackedBarChartConfig
  | LineGraphConfig
  | SparklineConfig;

/**
 * Chart render result from the tool
 */
export interface ChartRenderResult {
  success: boolean;
  chartType: ChartConfig['chartType'];
  title?: string;
  error?: string;
}
