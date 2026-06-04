"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Sidebar, BottomNav } from "@/components/sidebar";
import { IVDriveAIWidget } from "@/components/chat/IVDriveAIWidget";

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-iv-black">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-iv-border border-t-iv-green" />
        <p className="text-sm text-iv-muted">Loading...</p>
      </div>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [mounted, loading, user, router]);

  if (!mounted) {
    return <div className="flex min-h-screen bg-iv-black" />;
  }

  if (loading) return <LoadingScreen />;

  if (!user) return null;

  return (
    <div className="flex min-h-screen bg-iv-black">
      <Sidebar />
      <main className="min-h-screen flex-1 overflow-x-hidden p-4 pb-24 md:ml-[240px] md:p-6 md:pb-6">
        {children}
      </main>
      <BottomNav />
      <IVDriveAIWidget />
    </div>
  );
}
