import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Users, Car, Globe2, AlertTriangle, Activity, MapPin, Zap } from "lucide-react";

function getFlagEmoji(countryCode: string) {
  if (!countryCode || countryCode === "Unknown" || countryCode.length !== 2) return "🌍";
  const codePoints = countryCode
    .toUpperCase()
    .split('')
    .map(char => 127397 + char.charCodeAt(0));
  return String.fromCodePoint(...codePoints);
}

interface AdminStats {
  total_users: number;
  pending_invites: number;
  total_vehicles: number;
  vehicles_by_country: { name: string; value: number }[];
  sync_error_rate: number;
  connector_status: { name: string; value: number }[];
  total_trips: number;
  total_charging_sessions: number;
  vehicles_by_model: { name: string; value: number }[];
}

export function StatisticsDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.adminGetStatistics();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load stats");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="glass rounded-xl border border-iv-danger/20 bg-iv-danger/5 p-6 text-center text-iv-danger">
        <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">{error || "Failed to load statistics"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Level KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Users" value={stats.total_users} subtitle={`${stats.pending_invites} pending invites`} icon={Users} color="text-iv-cyan" />
        <StatCard title="Total Fleet" value={stats.total_vehicles} subtitle="Vehicles connected" icon={Car} color="text-iv-green" />
        <StatCard title="Global Reach" value={stats.vehicles_by_country.length} subtitle="Countries represented" icon={Globe2} color="text-iv-text" />
        <StatCard title="Sync Error Rate" value={`${stats.sync_error_rate}%`} subtitle="Auth/Token failures" icon={Activity} color={stats.sync_error_rate > 5 ? "text-iv-danger" : "text-iv-warning"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Vehicles by Country */}
        <div className="glass rounded-xl border border-iv-border p-6">
          <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2"><MapPin size={16} className="text-iv-muted" /> Fleet Distribution</h3>
          <div className="space-y-3">
            {stats.vehicles_by_country.map((item) => (
              <div key={item.name} className="flex items-center">
                <span className="w-16 text-sm font-medium text-iv-text flex items-center gap-1.5">
                  <span className="text-lg leading-none">{getFlagEmoji(item.name)}</span> {item.name}
                </span>
                <div className="flex-1 bg-iv-surface rounded-full h-2 overflow-hidden mx-3">
                  <div className="bg-iv-cyan h-full rounded-full" style={{ width: `${Math.max(2, (item.value / stats.total_vehicles) * 100)}%` }} />
                </div>
                <span className="w-8 text-right text-xs text-iv-muted">{item.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Sync Health & Telemetry */}
        <div className="space-y-6">
          <div className="glass rounded-xl border border-iv-border p-6">
            <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2"><Activity size={16} className="text-iv-muted" /> Connector Health</h3>
            <div className="space-y-3">
              {stats.connector_status.map((item) => (
                <div key={item.name} className="flex justify-between items-center border-b border-iv-border/50 pb-2 last:border-0 last:pb-0">
                  <span className={`text-sm ${item.name === "active" ? "text-iv-green" : "text-iv-danger"}`}>{item.name === "active" ? "Healthy (Active)" : item.name}</span>
                  <span className="text-sm font-medium">{item.value}</span>
                </div>
              ))}
            </div>
          </div>
          
          <div className="glass rounded-xl border border-iv-border p-6">
            <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2"><Zap size={16} className="text-iv-muted" /> Global Telemetry Tracked</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-iv-muted mb-1">Total Trips</p>
                <p className="text-2xl font-bold text-iv-text">{stats.total_trips.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs text-iv-muted mb-1">Charging Sessions</p>
                <p className="text-2xl font-bold text-iv-text">{stats.total_charging_sessions.toLocaleString()}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {/* Vehicle Models */}
      <div className="glass rounded-xl border border-iv-border p-6">
        <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2"><Car size={16} className="text-iv-muted" /> Models</h3>
        <div className="flex flex-wrap gap-2">
          {stats.vehicles_by_model.map((item) => (
            <span key={item.name} className="px-3 py-1.5 bg-iv-surface border border-iv-border rounded-lg text-sm text-iv-text">
              {item.name} <span className="text-iv-muted ml-2">{item.value}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, subtitle, icon: Icon, color }: any) {
  return (
    <div className="glass rounded-xl border border-iv-border p-5 flex flex-col justify-between">
      <div className="flex justify-between items-start mb-4">
        <p className="text-xs font-medium text-iv-muted">{title}</p>
        <Icon size={16} className={color} />
      </div>
      <div>
        <p className="text-3xl font-bold text-iv-text">{value}</p>
        <p className="text-[10px] text-iv-muted mt-1 opacity-70">{subtitle}</p>
      </div>
    </div>
  );
}
