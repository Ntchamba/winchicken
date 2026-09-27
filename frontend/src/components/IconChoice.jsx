import "./icon-choice.css";

/**
 * A row of icon + label cards standing in for a plain <select> on a short, fixed list of
 * options (product type, expense category, …) — a bare <select> is pure text, which shuts
 * out anyone who can't read the option names. Behaves like a radio group: one value selected
 * at a time, native keyboard/focus support via real <button> elements (no custom ARIA needed).
 *
 * @param {string} value - the selected option's value.
 * @param {(value: string) => void} onChange
 * @param {{value: string, label: string, Icon: import("react").ComponentType}[]} options
 * @param {string} [ariaLabel] - defaults to grouping by the surrounding <fieldset>/<label> if omitted.
 */
export default function IconChoice({ value, onChange, options, ariaLabel }) {
  return (
    <div className="icon-choice" role="radiogroup" aria-label={ariaLabel}>
      {options.map((opt) => {
        const selected = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            className={`icon-choice-option ${selected ? "selected" : ""}`}
            onClick={() => onChange(opt.value)}
          >
            <opt.Icon size={20} strokeWidth={1.8} aria-hidden="true" />
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
