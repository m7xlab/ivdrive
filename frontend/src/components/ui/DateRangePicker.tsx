"use client";

import { useState, useEffect, useCallback } from "react";
import { DayPicker, type DateRange } from "react-day-picker";
import * as Popover from "@radix-ui/react-popover";
import { format, subDays, startOfDay, endOfDay, startOfMonth, endOfMonth, startOfYear, endOfYear } from "date-fns";
import { Calendar } from "lucide-react";
import { cn } from "@/lib/cn";

export interface DateRangeValue {
  from: Date;
  to: Date;
}

export interface DateRangePickerProps {
  value: DateRangeValue;
  onChange: (range: DateRangeValue) => void;
  className?: string;
}

const PRESETS = [
  { label: "Today", getValue: () => ({ from: startOfDay(new Date()), to: endOfDay(new Date()) }) },
  { label: "Last 7 Days", getValue: () => ({ from: startOfDay(subDays(new Date(), 7)), to: endOfDay(new Date()) }) },
  { label: "Last 30 Days", getValue: () => ({ from: startOfDay(subDays(new Date(), 30)), to: endOfDay(new Date()) }) },
  { label: "This Month", getValue: () => ({ from: startOfMonth(new Date()), to: endOfMonth(new Date()) }) },
  { label: "This Year", getValue: () => ({ from: startOfYear(new Date()), to: endOfYear(new Date()) }) },
];

export function DateRangePicker({ value, onChange, className }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const [range, setRange] = useState<DateRange | undefined>({ from: value.from, to: value.to });
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 640);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  useEffect(() => {
    setRange({ from: value.from, to: value.to });
  }, [value.from, value.to]);

  const handleSelect = (selected: DateRange | undefined) => {
    setRange(selected);
    if (selected?.from && selected?.to) {
      onChange({ from: startOfDay(selected.from), to: endOfDay(selected.to) });
    }
  };

  const handlePreset = (preset: typeof PRESETS[number]) => {
    const v = preset.getValue();
    setRange({ from: v.from, to: v.to });
    onChange(v);
    setOpen(false);
  };

  const displayText = value.from && value.to
    ? `${format(value.from, "MMM d, yyyy")} – ${format(value.to, "MMM d, yyyy")}`
    : "Select date range";

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          className={cn(
            "flex items-center gap-2 rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm",
            "text-iv-text hover:border-iv-cyan/50 hover:bg-iv-charcoal transition-colors",
            "focus:outline-none focus:ring-2 focus:ring-iv-cyan/40",
            className
          )}
        >
          <Calendar className="h-4 w-4 text-iv-cyan" />
          <span className="whitespace-nowrap">{displayText}</span>
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          align={isMobile ? "center" : "end"}
          sideOffset={8}
          avoidCollisions
          collisionPadding={12}
          className={cn(
            "z-50 rounded-xl border border-iv-border bg-iv-charcoal p-4 shadow-xl shadow-black/20",
            "max-h-[90dvh] overflow-y-auto",
            "animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
            isMobile && "w-[calc(100vw-24px)] max-w-sm"
          )}
        >
          <div className={cn("flex gap-4", isMobile && "flex-col")}>
            {/* Presets — sidebar on desktop, scrollable row on mobile */}
            <div className={cn(
              isMobile
                ? "flex flex-row flex-wrap gap-1 pb-3 border-b border-iv-border"
                : "flex flex-col gap-1 border-r border-iv-border pr-4 min-w-[120px]"
            )}>
              {!isMobile && (
                <span className="text-xs font-semibold text-iv-muted uppercase tracking-wider mb-2">Quick Select</span>
              )}
              {PRESETS.map((p) => (
                <button
                  key={p.label}
                  onClick={() => handlePreset(p)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm text-left transition-colors",
                    "text-iv-text hover:bg-iv-surface hover:text-iv-cyan",
                    isMobile && "border border-iv-border/50 text-xs py-1"
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {/* Calendar — 1 month on mobile, 2 on desktop */}
            <DayPicker
              mode="range"
              selected={range}
              onSelect={handleSelect}
              numberOfMonths={isMobile ? 1 : 2}
              showOutsideDays
              classNames={{
                months: "flex gap-4",
                month_caption: "flex justify-center items-center h-10 text-sm font-semibold text-iv-text",
                nav: "flex items-center justify-between absolute inset-x-0 top-0 px-1 h-10",
                button_previous: "inline-flex items-center justify-center h-7 w-7 rounded-md text-iv-muted hover:text-iv-cyan hover:bg-iv-surface transition-colors",
                button_next: "inline-flex items-center justify-center h-7 w-7 rounded-md text-iv-muted hover:text-iv-cyan hover:bg-iv-surface transition-colors",
                weekday: "text-xs font-medium text-iv-muted w-9 text-center",
                day_button: "h-9 w-9 rounded-md text-sm text-iv-text hover:bg-iv-surface transition-colors inline-flex items-center justify-center",
                day: "p-0",
                selected: "bg-iv-cyan text-iv-black font-semibold",
                range_start: "bg-iv-cyan text-iv-black rounded-l-md font-semibold",
                range_end: "bg-iv-cyan text-iv-black rounded-r-md font-semibold",
                range_middle: "bg-iv-cyan/15 text-iv-cyan",
                today: "ring-1 ring-iv-cyan/50 font-semibold",
                outside: "text-iv-muted/40",
                disabled: "text-iv-muted/30",
                root: "relative",
              }}
            />
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
