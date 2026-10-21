"use client";

import { useState, type InputHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  /** Start visible (rare — usually leave false). */
  defaultVisible?: boolean;
  /** Class for the outer wrapper (flex-1 in form rows). */
  wrapperClassName?: string;
};

/** Password field with show/hide toggle (standard UX). */
export function PasswordInput({
  defaultVisible = false,
  className = "",
  wrapperClassName = "",
  ...rest
}: Props) {
  const [visible, setVisible] = useState(defaultVisible);
  return (
    <div className={`relative ${wrapperClassName}`.trim()}>
      <input
        {...rest}
        type={visible ? "text" : "password"}
        className={`${className} pr-10`.trim()}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        tabIndex={-1}
        aria-label={visible ? "Hide password" : "Show password"}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors p-1"
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
