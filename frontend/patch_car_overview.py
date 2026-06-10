import re

with open("src/components/statistics/CarOverviewDashboard.tsx", "r") as f:
    content = f.read()

# 1. Type for Climate Penalty
type_def = """interface ClimatePenaltyRow {
  temperature: number;
  states: Record<string, { avg_kwh_100km: number | null; trip_count: number }>;
}
interface ClimatePenaltyData {
  by_temperature: ClimatePenaltyRow[];
  summary: string;
}"""

content = re.sub(
    r"interface EfficiencyDataPoint \{[^}]+\}", 
    type_def, 
    content
)

# 2. State
content = content.replace(
    "const [winterEfficiency, setWinterEfficiency] = useState<EfficiencyDataPoint[]>([]);",
    "const [climatePenalty, setClimatePenalty] = useState<ClimatePenaltyData | null>(null);"
)

# 3. Fetch call
content = content.replace(
    "api.getAnalyticsEfficiency(vehicleId),",
    "api.getClimatePenalty(vehicleId, { fromDate: fromISO, toDate: toISOVal }),"
)

# 4. Result destructuring
content = content.replace(
    "const [b, r, c, bands, range100, wltp, eff, lStep, rStep, oTemp, bTemp, elecCons, vd, pulseData, winterEff] = results.map((res) => res.status === \"fulfilled\" ? res.value : null);",
    "const [b, r, c, bands, range100, wltp, eff, lStep, rStep, oTemp, bTemp, elecCons, vd, pulseData, climPen] = results.map((res) => res.status === \"fulfilled\" ? res.value : null);"
)

content = content.replace(
    "setWinterEfficiency(winterEff ?? []);",
    "setClimatePenalty(climPen ?? null);"
)

# 5. JSX
old_jsx = """      {/* ── Winter Penalty ── */}
      <SectionDivider label="Winter Penalty" />
      <div className="glass rounded-xl p-5">
        <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
          <ThermometerSnowflake size={14} /> Winter Penalty
        </h3>
        {winterEfficiency.length > 0 ? (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={winterEfficiency} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <defs>
                  <linearGradient id="winterGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00D4FF" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#00D4FF" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="temperature_celsius"
                  tickFormatter={(v) => `${v}°C`}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tickFormatter={(v) => `${v}`}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  domain={["auto", "auto"]}
                />
                <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" opacity={0.5} />
                <Tooltip
                  formatter={(value: number) => [`${value} kWh/100km`, "Consumption"]}
                  labelFormatter={(label) => `${label}°C`}
                  contentStyle={{ backgroundColor: "#1C1C2E", borderColor: "#2a2d42", borderRadius: "12px", color: "#fff" }}
                  itemStyle={{ color: "#00D4FF", fontWeight: "bold" }}
                />
                <Area
                  type="monotone"
                  dataKey="avg_consumption_kwh_100km"
                  stroke="#00D4FF"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#winterGradient)"
                  activeDot={{ r: 4, strokeWidth: 0, fill: "#00D4FF" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-sm text-iv-muted">No winter penalty data available.</div>
        )}
      </div>"""

new_jsx = """      {/* ── Climate Penalty ── */}
      <SectionDivider label="Climate Penalty" />
      <div className="glass rounded-xl p-5">
        <h3 className="text-sm font-medium text-iv-muted mb-2 flex items-center gap-2">
          <ThermometerSnowflake size={14} /> Climate Penalty
        </h3>
        <p className="text-xs text-iv-text-muted mb-4">{climatePenalty?.summary || "Analyzing climate data..."}</p>
        {climatePenalty?.by_temperature && climatePenalty.by_temperature.length > 0 ? (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart 
                data={climatePenalty.by_temperature.map(row => ({
                  temperature: row.temperature,
                  HEATING: row.states.HEATING?.avg_kwh_100km ?? null,
                  COOLING: row.states.COOLING?.avg_kwh_100km ?? null,
                  OFF: row.states.OFF?.avg_kwh_100km ?? null,
                }))} 
                margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
              >
                <XAxis
                  dataKey="temperature"
                  tickFormatter={(v) => `${v}°C`}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tickFormatter={(v) => `${v}`}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  domain={["auto", "auto"]}
                />
                <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" opacity={0.5} />
                <Tooltip
                  labelFormatter={(label) => `${label}°C`}
                  contentStyle={{ backgroundColor: "#1C1C2E", borderColor: "#2a2d42", borderRadius: "12px", color: "#fff" }}
                />
                <Legend wrapperStyle={{ fontSize: 10, paddingTop: 10 }} />
                <Line type="monotone" dataKey="HEATING" stroke="#00D4FF" strokeWidth={2} dot={{ r: 2 }} connectNulls name="Heating" />
                <Line type="monotone" dataKey="COOLING" stroke="#f59e0b" strokeWidth={2} dot={{ r: 2 }} connectNulls name="Cooling" />
                <Line type="monotone" dataKey="OFF" stroke="#10b981" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 1 }} connectNulls name="Climate Off" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-sm text-iv-muted">No climate penalty data available for this period.</div>
        )}
      </div>"""

content = content.replace(old_jsx, new_jsx)

with open("src/components/statistics/CarOverviewDashboard.tsx", "w") as f:
    f.write(content)

print("Patching complete.")
