interface Props {
  on: boolean;
  onChange: (v: boolean) => void;
  ariaLabel?: string;
}

/**
 * Pill toggle: emerald when active, slate when off.
 * Sized to read well at small layer-row scale.
 */
export function Toggle({ on, onChange, ariaLabel }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={ariaLabel}
      onClick={() => onChange(!on)}
      className={[
        "relative inline-flex h-[18px] w-[32px] flex-shrink-0 items-center rounded-full transition-colors duration-200",
        on
          ? "bg-emerald-500/90 shadow-[0_0_10px_rgba(16,185,129,0.4)]"
          : "bg-slate-700/70",
      ].join(" ")}
    >
      <span
        className={[
          "inline-block h-[14px] w-[14px] rounded-full bg-white shadow-md transition-transform duration-200",
          on ? "translate-x-[16px]" : "translate-x-[2px]",
        ].join(" ")}
      />
    </button>
  );
}
