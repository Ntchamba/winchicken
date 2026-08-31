export const UNIT_PRESETS = ["kg", "L", "m", "V", "A", "W", "kcal"];

/**
 * Unit combo used everywhere `StockItem.unit` is set — a `<select>` of {@link UNIT_PRESETS}
 * plus "Autre (préciser)", which reveals a free-text input. `value` is the plain resolved
 * string (a preset, or whatever was typed); `onChange` receives that string. No schema
 * change — `unit` stays a free string; this is only the input control.
 *
 * @param {string} value
 * @param {(next: string) => void} onChange
 */
export default function UnitField({ value = "", onChange, className, style }) {
  const isPreset = UNIT_PRESETS.includes(value);

  return (
    <span style={{ display: "inline-flex", gap: 6, ...style }}>
      <select
        aria-label="Unité"
        className={className}
        value={isPreset ? value : "__other__"}
        onChange={(e) => onChange(e.target.value === "__other__" ? "" : e.target.value)}
      >
        {UNIT_PRESETS.map((u) => (
          <option key={u} value={u}>{u}</option>
        ))}
        <option value="__other__">Autre (préciser)</option>
      </select>
      {!isPreset && (
        <input
          type="text"
          aria-label="Unité personnalisée"
          placeholder="préciser"
          value={value}
          autoFocus={value === ""}
          onChange={(e) => onChange(e.target.value)}
          style={{ width: 96 }}
        />
      )}
    </span>
  );
}
