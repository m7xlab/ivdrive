"use client";



import { useState, useEffect, useCallback } from "react";

import { Bell, X, Info, CheckCircle, AlertTriangle, AlertCircle } from "lucide-react";

import { api } from "@/lib/api";



interface Announcement {

  id: string;

  title: string;

  message: string;

  type: "info" | "success" | "warning" | "critical";

  created_at: string;

}



export function NotificationCenter() {

  const [announcements, setAnnouncements] = useState<Announcement[]>([]);

  const [isOpen, setIsOpen] = useState(false);

  const [loading, setLoading] = useState(false);



  const fetchAnnouncements = useCallback(async () => {

    try {

      const data = await api.getUserAnnouncements();

      setAnnouncements(data);

    } catch (error) {

      console.error("Failed to fetch announcements", error);

    }

  }, []);



  useEffect(() => {

    fetchAnnouncements();

    // Poll every 5 minutes

    const interval = setInterval(fetchAnnouncements, 5 * 60 * 1000);

    return () => clearInterval(interval);

  }, [fetchAnnouncements]);



  const handleDismiss = async (id: string) => {

    try {

      await api.dismissAnnouncement(id);

      setAnnouncements((prev) => prev.filter((a) => a.id !== id));

      if (announcements.length <= 1) setIsOpen(false);

    } catch (error) {

      console.error("Failed to dismiss announcement", error);

    }

  };



  const getIcon = (type: string) => {

    switch (type) {

      case "success": return <CheckCircle className="w-4 h-4 text-iv-green" />;

      case "warning": return <AlertTriangle className="w-4 h-4 text-amber-400" />;

      case "critical": return <AlertCircle className="w-4 h-4 text-iv-danger" />;

      default: return <Info className="w-4 h-4 text-iv-cyan" />;

    }

  };



  const getTypeStyles = (type: string) => {

    switch (type) {

      case "success": return "bg-iv-green/10 border-iv-green/20";

      case "warning": return "bg-amber-500/10 border-amber-500/20";

      case "critical": return "bg-iv-danger/10 border-iv-danger/20";

      default: return "bg-iv-cyan/10 border-iv-cyan/20";

    }

  };



  const renderMessageWithLinks = (text: string) => {

    const urlRegex = /(https?:\/\/[^\s]+)/g;

    const parts = text.split(urlRegex);

    return parts.map((part, index) => {

      if (part.match(urlRegex)) {

        return (

          <a

            key={index}

            href={part}

            target="_blank"

            rel="noopener noreferrer"

            className="underline text-iv-accent hover:text-iv-primary break-all"

            onClick={(e) => e.stopPropagation()}

          >

            {part}

          </a>

        );

      }

      return part;

    });

  };



  return (

    <div className="relative">

      <button type="button"

        onClick={() => setIsOpen(!isOpen)}

        className={`relative p-2 rounded-lg transition-all ${

          isOpen ? "bg-iv-surface text-iv-text" : "text-iv-muted hover:text-iv-text hover:bg-iv-surface"

        }`}

      >

        <Bell size={20} className={announcements.length > 0 ? "animate-pulse-subtle" : ""} />

        {announcements.length > 0 && (

          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-iv-green rounded-full border-2 border-iv-charcoal" />

        )}

      </button>



      {isOpen && (

        <>

          <div 

            className="fixed inset-0 z-40" 

            onClick={() => setIsOpen(false)}

          />

          <div className="absolute left-full ml-4 bottom-0 w-80 glass border border-iv-border rounded-xl shadow-2xl z-50 overflow-hidden animate-in slide-in-from-left-2 duration-200">

            <div className="p-4 border-b border-iv-border flex items-center justify-between bg-iv-surface/50">

              <h3 className="text-sm font-bold text-iv-text">Notifications</h3>

              <span className="text-[10px] font-bold bg-iv-charcoal px-2 py-0.5 rounded-full text-iv-muted">

                {announcements.length} New

              </span>

            </div>

            

            <div className="max-h-[400px] overflow-y-auto p-3 space-y-3">

              {announcements.length === 0 ? (

                <div className="py-8 text-center">

                  <Bell className="w-8 h-8 text-iv-muted/20 mx-auto mb-2" />

                  <p className="text-xs text-iv-muted">All caught up!</p>

                </div>

              ) : (

                announcements.map((ann) => (

                  <div 

                    key={ann.id}

                    className={`relative p-3 rounded-lg border transition-all ${getTypeStyles(ann.type)}`}

                  >

                    <button type="button"

                      onClick={() => handleDismiss(ann.id)}

                      className="absolute top-2 right-2 text-iv-muted hover:text-iv-text transition-colors"

                    >

                      <X size={14} />

                    </button>

                    <div className="flex gap-3">

                      <div className="mt-0.5">{getIcon(ann.type)}</div>

                      <div className="flex-1 pr-4">

                        <p className="text-xs font-bold text-iv-text mb-0.5">{ann.title}</p>

                        <p className="text-[11px] text-iv-muted leading-relaxed">{renderMessageWithLinks(ann.message)}</p>

                        <p className="text-[9px] text-iv-muted/50 mt-1.5">

                          {new Date(ann.created_at).toLocaleDateString()}

                        </p>

                      </div>

                    </div>

                  </div>

                ))

              )}

            </div>

            

            {announcements.length > 0 && (

              <div className="p-2 border-t border-iv-border bg-iv-surface/30 text-center">

                <p className="text-[10px] text-iv-muted">Persists until dismissed</p>

              </div>

            )}

          </div>

        </>

      )}

    </div>

  );

}
