import re

with open("src/components/statistics/CarOverviewDashboard.tsx", "r") as f:
    content = f.read()

# Replace the entire JSX block for Winter Penalty
pattern = r"\{/\*\s*──\s*Winter Penalty\s*──\s*\*/\}.*?(?=\{/\*\s*──\s*Trips & Geography\s*──\s*\*/\}|</div>\s*</div>\s*$|{/\* ── )"

new_jsx = """{/* ── Climate Penalty ── */}
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
      </div>

      """

# Find the start of the Winter Penalty section
start_idx = content.find("{/* ── Winter Penalty ── */}")
if start_idx != -1:
    # Find the next section to know where to stop replacing
    end_idx = content.find("{/* ──", start_idx + 10)
    if end_idx == -1:
        end_idx = len(content) # End of file? Probably not, there is more.
    
    # Let's see what comes after Winter Penalty
    print("Next section starts at:", content[end_idx:end_idx+50])
    
    # We will replace from start_idx to end_idx
    content = content[:start_idx] + new_jsx + content[end_idx:]
    
    with open("src/components/statistics/CarOverviewDashboard.tsx", "w") as f:
        f.write(content)
    print("Replaced Winter Penalty JSX successfully.")
else:
    print("Could not find {/* ── Winter Penalty ── */}")

