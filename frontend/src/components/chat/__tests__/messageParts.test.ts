import { describe, it, expect } from 'vitest';
import { parseMessageContent, followupsOf, isValidSeries, chartToMetrics } from '../messageParts';

// Verbatim from a production answer: four unrelated figures in one bar chart.
const PROD_MIXED_CHART =
  '```json_chart\n{"title":"BlackMagic — Last 30 Days Overview","type":"bar","data":[{"name":"Distance","km":565},{"name":"Energy","kWh":159.4},{"name":"Charged","kWh":218.9},{"name":"Cost","EUR":79.86}],"categories":["km","kWh","EUR"]}\n```';

const SERIES_CHART =
  '```json_chart\n{"title":"Consumption vs Temperature","type":"bar","data":[{"name":"Below 0°C","kWh/100km":21.2},{"name":"0–5°C","kWh/100km":31.2},{"name":"5–10°C","kWh/100km":29.1}],"categories":["kWh/100km"]}\n```';

describe('parseMessageContent', () => {
  it('returns plain prose as one text part', () => {
    expect(parseMessageContent('In May, 80 trips.')).toEqual([{ type: 'text', content: 'In May, 80 trips.' }]);
  });

  it('turns a mixed-unit chart into metric tiles, one per value', () => {
    const parts = parseMessageContent('Quick picture.\n\n' + PROD_MIXED_CHART);
    expect(parts.map((p) => p.type)).toEqual(['text', 'metrics']);
    const metrics = parts[1];
    if (metrics.type !== 'metrics') throw new Error('expected metrics');
    expect(metrics.items).toEqual([
      { label: 'Distance', value: '565', unit: 'km' },
      { label: 'Energy', value: '159.4', unit: 'kWh' },
      { label: 'Charged', value: '218.9', unit: 'kWh' },
      { label: 'Cost', value: '79.9', unit: 'EUR' },
    ]);
  });

  it('keeps a genuine series as a chart, and only the first one', () => {
    const parts = parseMessageContent('A.\n' + SERIES_CHART + '\nB.\n' + SERIES_CHART);
    expect(parts.map((p) => p.type)).toEqual(['text', 'chart', 'text', 'metrics']);
  });

  it('renders a json_metrics block and drops junk items', () => {
    const block = '```json_metrics\n{"items":[{"label":"Distance","value":565,"unit":"km","note":"100 trips"},{"label":"","value":1},{"value":2}]}\n```';
    const parts = parseMessageContent('Prose.\n' + block);
    expect(parts[1]).toEqual({ type: 'metrics', items: [{ label: 'Distance', value: '565', unit: 'km', note: '100 trips' }] });
  });

  it('extracts at most three distinct follow-up questions', () => {
    const block = '```json_followups\n{"questions":["How does that compare with October?","how does that compare with october?","What did charging cost?","Is my data up to date?","Another?"]}\n```';
    const content = 'Answer.\n' + block;
    expect(followupsOf(content)).toEqual(['How does that compare with October?', 'What did charging cost?', 'Is my data up to date?']);
    // The block never shows as text.
    expect(parseMessageContent(content).some((p) => p.type === 'text' && p.content.includes('json_followups'))).toBe(false);
  });

  it('ignores a block with broken JSON and keeps the prose', () => {
    const parts = parseMessageContent('Numbers.\n```json_chart\n{not json\n```\nDone.');
    expect(parts).toEqual([
      { type: 'text', content: 'Numbers.\n' },
      { type: 'text', content: '\nDone.' },
    ]);
  });

  it('tolerates a chart tag with no newline after it', () => {
    const parts = parseMessageContent('X ```json_chart{"type":"line","data":[{"name":"a","v":1},{"name":"b","v":2},{"name":"c","v":3}],"categories":["v"]}```');
    expect(parts.map((p) => p.type)).toEqual(['text', 'chart']);
  });
});

describe('isValidSeries / chartToMetrics', () => {
  it('rejects fewer than three points and per-row keys', () => {
    expect(isValidSeries({ type: 'bar', data: [{ name: 'SOH', '%': 95 }, { name: 'Deg', '%': 5 }], categories: ['%'] })).toBe(false);
    expect(isValidSeries({ type: 'bar', data: [{ name: 'a', km: 1 }, { name: 'b', kWh: 2 }, { name: 'c', EUR: 3 }], categories: ['km', 'kWh', 'EUR'] })).toBe(false);
  });

  it('a donut needs two non-zero slices', () => {
    expect(isValidSeries({ type: 'donut', data: [{ name: 'AC', value: 408.9 }, { name: 'DC', value: 0 }, { name: 'x', value: 0 }], categories: ['value'] })).toBe(false);
    expect(chartToMetrics({ type: 'donut', data: [{ name: 'AC', value: 408.9 }, { name: 'DC', value: 0 }], categories: ['value'] })).toEqual([
      { label: 'AC', value: '408.9', unit: '' },
      { label: 'DC', value: '0', unit: '' },
    ]);
  });
});
