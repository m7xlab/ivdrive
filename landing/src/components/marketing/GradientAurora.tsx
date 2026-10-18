export function GradientAurora() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="aurora"
        style={{
          width: "55vw",
          height: "55vw",
          top: "-18%",
          left: "50%",
          transform: "translateX(-50%)",
          background:
            "radial-gradient(circle, rgba(75,168,46,0.28) 0%, rgba(0,212,255,0.12) 42%, transparent 70%)",
        }}
      />
      <div
        className="aurora"
        style={{
          width: "38vw",
          height: "38vw",
          top: "8%",
          right: "-8%",
          background:
            "radial-gradient(circle, rgba(0,212,255,0.18) 0%, transparent 68%)",
        }}
      />
      <div
        className="aurora"
        style={{
          width: "32vw",
          height: "32vw",
          top: "18%",
          left: "-10%",
          background:
            "radial-gradient(circle, rgba(75,168,46,0.16) 0%, transparent 70%)",
        }}
      />
    </div>
  );
}
