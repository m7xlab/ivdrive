
"use client";

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, BarChart3 } from "lucide-react";
import { StatisticsShell } from "@/components/statistics/StatisticsShell";

export default function StatisticsPage() {
  const params = useParams();
  const router = useRouter();
  const vehicleId = params.id as string;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-full p-2 text-iv-text-muted hover:bg-iv-surface hover:text-iv-text transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-iv-text flex items-center gap-2">
              <BarChart3 className="h-6 w-6 text-iv-cyan" />
              Advanced Statistics
            </h1>
            <p className="text-sm text-iv-text-muted">Analytics and Economics</p>
          </div>
        </div>
      </div>

      <StatisticsShell vehicleId={vehicleId} />
    </div>
  );
}
