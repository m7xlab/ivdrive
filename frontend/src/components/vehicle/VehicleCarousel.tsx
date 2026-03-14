
"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

interface Render {
  url: string;
  viewType: string;
}

interface VehicleCarouselProps {
  renders: Render[];
}

export function VehicleCarousel({ renders }: VehicleCarouselProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [isAutoPlaying, setIsAutoPlaying] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const extendedRenders = useMemo(() => {
    if (!renders || renders.length === 0) return [];
    return [...renders, ...renders, ...renders, ...renders, ...renders];
  }, [renders]);

  const originalLength = renders.length;
  const [internalIndex, setInternalIndex] = useState(originalLength * 2);

  useEffect(() => {
    if (!isAutoPlaying) return;
    const timer = setInterval(() => {
      setInternalIndex((prev) => prev + 1);
    }, 8000);
    return () => clearInterval(timer);
  }, [isAutoPlaying]);

  useEffect(() => {
    if (scrollRef.current) {
      const container = scrollRef.current;
      const activeThumb = container.children[internalIndex] as HTMLElement;
      if (activeThumb) {
        const scrollLeft = activeThumb.offsetLeft - (container.offsetWidth / 2) + (activeThumb.offsetWidth / 2);
        container.scrollTo({ left: scrollLeft, behavior: 'smooth' });
      }
    }
    setActiveIndex(internalIndex % originalLength);
  }, [internalIndex, originalLength]);

  const handleManualAction = (targetInternalIndex: number) => {
    setIsAutoPlaying(false);
    setInternalIndex(targetInternalIndex);
  };

  const handleNext = () => setInternalIndex((prev) => prev + 1);
  const handlePrev = () => setInternalIndex((prev) => prev - 1);

  if (!renders || renders.length === 0) return null;

  return (
    <div className="space-y-6">
      {/* Main Large View */}
      <div 
        className="relative group aspect-[16/9] md:aspect-[21/9] w-full rounded-3xl overflow-hidden bg-white/5 border border-iv-border/10 shadow-lg"
        onMouseEnter={() => setIsAutoPlaying(false)}
      >
        {renders.map((render, idx) => (
          <div
            key={idx}
            className={cn(
              "absolute inset-0 transition-all duration-1000 ease-in-out transform",
              idx === activeIndex ? "opacity-100 scale-100" : "opacity-0 scale-95 pointer-events-none"
            )}
          >
            {/* CLEAN REVERT: No vignette/smoke effects */}
            <div className="relative w-full h-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={render.url}
                alt={render.viewType}
                className="w-full h-full object-contain p-4 md:p-8"
              />
            </div>
          </div>
        ))}

        {/* Text area below image */}
        <div className="absolute inset-x-0 bottom-2 p-2 z-10">
          <p className="text-[9px] md:text-[10px] font-bold text-iv-text/40 uppercase tracking-[0.5em] text-center">
            {renders[activeIndex].viewType.replace(/_/g, ' ')}
          </p>
        </div>

        {/* Navigation Arrows */}
        <button
          onClick={(e) => { e.stopPropagation(); setIsAutoPlaying(false); handlePrev(); }}
          className="absolute left-6 top-1/2 -translate-y-1/2 p-3 rounded-full bg-iv-charcoal/20 text-white backdrop-blur-md opacity-0 group-hover:opacity-100 transition-all hover:bg-iv-cyan hover:text-iv-black shadow-lg z-40"
        >
          <ChevronLeft size={24} />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); setIsAutoPlaying(false); handleNext(); }}
          className="absolute right-6 top-1/2 -translate-y-1/2 p-3 rounded-full bg-iv-charcoal/20 text-white backdrop-blur-md opacity-0 group-hover:opacity-100 transition-all hover:bg-iv-cyan hover:text-iv-black shadow-lg z-40"
        >
          <ChevronRight size={24} />
        </button>
      </div>

      {/* Thumbnails Circular Strip */}
      <div className="relative h-32 md:h-40 flex items-center justify-center overflow-hidden">
        <div 
          ref={scrollRef}
          className="flex items-center gap-0 overflow-x-auto no-scrollbar h-full px-[50%]"
        >
          {extendedRenders.map((render, idx) => {
            const distance = Math.abs(idx - internalIndex);
            const isActive = idx === internalIndex;
            
            let widthClass = "w-20 md:w-28";
            let scale = 0.6;
            let opacity = 0.15;
            let zIndex = 0;

            if (distance === 0) {
                widthClass = "w-36 md:w-52";
                scale = 1.15;
                opacity = 1;
                zIndex = 30;
            } else if (distance === 1) {
                widthClass = "w-24 md:w-36";
                scale = 0.85;
                opacity = 0.5;
                zIndex = 20;
            } else if (distance === 2) {
                scale = 0.7;
                opacity = 0.3;
                zIndex = 10;
            }

            return (
              <div 
                key={idx} 
                className={cn("shrink-0 flex items-center justify-center transition-all duration-700 ease-in-out", widthClass)}
                style={{ zIndex }}
              >
                <button
                  onClick={() => handleManualAction(idx)}
                  style={{ 
                      transform: `scale(${scale})`,
                      opacity: opacity,
                  }}
                  className={cn(
                    "relative transition-all duration-700 ease-in-out rounded-2xl overflow-hidden border-2 aspect-[16/10] w-full bg-iv-surface/10",
                    isActive ? "border-iv-cyan shadow-[0_0_30px_rgba(0,243,255,0.4)]" : "border-transparent"
                  )}
                >
                  <div className="relative w-full h-full">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={render.url}
                      alt={render.viewType}
                      className="w-full h-full object-cover p-2"
                    />
                  </div>
                </button>
              </div>
            );
          })}
        </div>
        
        <div className="absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-iv-charcoal via-iv-charcoal/90 to-transparent pointer-events-none z-40" />
        <div className="absolute inset-y-0 right-0 w-1/3 bg-gradient-to-l from-iv-charcoal via-iv-charcoal/90 to-transparent pointer-events-none z-40" />
      </div>
    </div>
  );
}
