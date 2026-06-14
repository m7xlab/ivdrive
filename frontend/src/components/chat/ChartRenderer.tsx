"use client";

import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  Legend
} from "recharts";

interface ChartData {
  title?: string;
  type: "bar" | "line" | "pie" | "donut";
  data: any[];
  categories: string[];
  xDataKey?: string;
}

const COLORS = ["#007AFF", "#34C759", "#FF9500", "#FF3B30", "#5856D6", "#AF52DE"];

export function ChartRenderer({ chartJson }: { chartJson: string }) {
  let chartData: ChartData | null = null;
  try {
    chartData = JSON.parse(chartJson);
  } catch (e) {
    return null;
  }

  if (!chartData || !chartData.data || chartData.data.length === 0) return null;

  const { title, type, data, categories, xDataKey = "name" } = chartData;

  const renderChart = () => {
    switch (type) {
      case "bar":
        return (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--iv-border)" />
              <XAxis dataKey={xDataKey} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "var(--iv-text-muted)" }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "var(--iv-text-muted)" }} />
              <Tooltip
                contentStyle={{ borderRadius: '12px', border: '1px solid var(--iv-border)', boxShadow: '0 4px 12px rgba(0,0,0,0.2)', backgroundColor: 'var(--iv-surface)' }}
                labelStyle={{ color: 'var(--iv-text)' }}
                itemStyle={{ color: 'var(--iv-text)' }}
                cursor={{ fill: 'var(--iv-border)' }}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12, color: 'var(--iv-text-muted)' }} />
              {categories.map((cat, i) => (
                <Bar key={cat} dataKey={cat} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      case "line":
        return (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--iv-border)" />
              <XAxis dataKey={xDataKey} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "var(--iv-text-muted)" }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "var(--iv-text-muted)" }} />
              <Tooltip
                contentStyle={{ borderRadius: '12px', border: '1px solid var(--iv-border)', boxShadow: '0 4px 12px rgba(0,0,0,0.2)', backgroundColor: 'var(--iv-surface)' }}
                labelStyle={{ color: 'var(--iv-text)' }}
                itemStyle={{ color: 'var(--iv-text)' }}
                cursor={{ stroke: 'var(--iv-border)' }}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12, color: 'var(--iv-text-muted)' }} />
              {categories.map((cat, i) => (
                <Line key={cat} type="monotone" dataKey={cat} stroke={COLORS[i % COLORS.length]} strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );
      case "pie":
      case "donut":
        const isDonut = type === "donut";
        return (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip
                contentStyle={{ borderRadius: '12px', border: '1px solid var(--iv-border)', boxShadow: '0 4px 12px rgba(0,0,0,0.2)', backgroundColor: 'var(--iv-surface)' }}
                labelStyle={{ color: 'var(--iv-text)' }}
                itemStyle={{ color: 'var(--iv-text)' }}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12, color: 'var(--iv-text-muted)' }} />
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={isDonut ? 60 : 0}
                outerRadius={80}
                paddingAngle={isDonut ? 5 : 0}
                dataKey={categories[0]}
                nameKey={xDataKey}
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        );
      default:
        return null;
    }
  };

  return (
    <div className="w-full h-64 mt-3 bg-iv-surface rounded-2xl p-4 shadow-sm border border-iv-border flex flex-col">
      {title && <h4 className="text-sm font-semibold mb-3 text-iv-text">{title}</h4>}
      <div className="flex-1 w-full min-h-0">
        {renderChart()}
      </div>
    </div>
  );
}
