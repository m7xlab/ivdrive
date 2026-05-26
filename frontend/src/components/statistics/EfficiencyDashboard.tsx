
"use client";

import { useState, useEffect } from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "@/lib/api";

interface EfficiencyData {
  temperature_celsius: number;
  consumption_kwh_100km: number;
  trips_recorded: number;
}

export function EfficiencyDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<EfficiencyData[]>([]);

  useEffect(() => {
    const fetchEfficiency = async () => {
      try {
        const res = await api.getAnalyticsEfficiency(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch efficiency", err);
      }
    };
    fetchEfficiency();
  }, [vehicleId]);

  return (
    <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
      <h3 className="text-lg font-bold text-iv-text">Winter Penalty Curve</h3>
      <p className="text-sm text-iv-text-muted mb-6">True Consumption (kWh/100km) mapped against Average Ambient Temperature (°C)</p>
      
      {data.length > 0 ? (
        <div className="h-72 w-full mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorConsumption" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00D4FF" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#00D4FF" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <XAxis 
                dataKey="temperature_celsius" 
                tickFormatter={(v) => `${v}°C`} 
                tick={{fill: '#8b8fa3', fontSize: 12}} 
                axisLine={false} 
                tickLine={false} 
              />
              <YAxis 
                tickFormatter={(v) => `${v}`} 
                tick={{fill: '#8b8fa3', fontSize: 12}} 
                axisLine={false} 
                tickLine={false} 
                domain={['auto', 'auto']}
              />
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#374151" opacity={0.2} />
              <Tooltip 
                formatter={(value: number) => [`${value} kWh / 100km`, 'Consumption']}
                labelFormatter={(label) => `Temp: ${label}°C`}
                contentStyle={{ backgroundColor: '#1C1C2E', borderColor: '#2a2d42', borderRadius: '12px', color: '#fff' }}
                itemStyle={{ color: '#00D4FF', fontWeight: 'bold' }}
              />
              <Area 
                type="monotone" 
                dataKey="consumption_kwh_100km" 
                stroke="#00D4FF" 
                strokeWidth={3}
                fillOpacity={1} 
                fill="url(#colorConsumption)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-72 flex items-center justify-center text-iv-text-muted">
          Collecting enough trip data to build the curve
        </div>
      )}
    </div>
  );
}
