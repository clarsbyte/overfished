import { type HTMLAttributes, forwardRef } from "react";

type Props = HTMLAttributes<HTMLDivElement>;

/**
 * Glassmorphic surface used for every floating dashboard panel.
 * Consistent base so the cards feel like one design system.
 */
export const Card = forwardRef<HTMLDivElement, Props>(function Card(
  { className = "", children, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={[
        "liquid-glass-surface rounded-2xl",
        className,
      ].join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
});

interface SectionTitleProps {
  label: string;
  right?: React.ReactNode;
  className?: string;
}

export function SectionTitle({ label, right, className = "" }: SectionTitleProps) {
  return (
    <div className={`flex items-center justify-between mb-3 ${className}`}>
      <div className="text-[10px] font-mono tracking-[0.22em] text-cyan-300/70 uppercase">
        {label}
      </div>
      {right}
    </div>
  );
}
