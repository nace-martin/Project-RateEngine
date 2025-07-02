import React from "react";

/**
 * A reusable button group for toggle/select scenarios.
 * @param {Array} items - Array of items to render as buttons. Each item should have at least a `value` and `label` property.
 * @param {string} selectedValue - The currently selected value.
 * @param {function} onValueChange - Callback when a button is clicked, receives the item's value.
 * @param {function} getItemClasses - Function (item, index, items) => string, returns className for each button.
 * @param {function} isDisabled - Optional function (item) => boolean, determines if a button is disabled.
 * @param {function} getButtonLabel - Optional function (item) => ReactNode, for custom label rendering.
 * @param {object} buttonStyle - Optional style object for each button.
 */
const ToggleButtonGroup = ({
  items = [],
  // selectedValue is intentionally not used here, but is passed for API consistency
  onValueChange,
  getItemClasses,
  isDisabled = () => false,
  getButtonLabel = (item) => item.label,
  buttonStyle = {},
}) => (
  <div className="flex flex-wrap rounded-lg overflow-hidden border border-gray-300">
    {items.map((item, index) => (
      <button
        key={item.value}
        type="button"
        onClick={() => !isDisabled(item) && onValueChange(item.value)}
        className={getItemClasses(item, index, items)}
        disabled={isDisabled(item)}
        style={buttonStyle}
      >
        {getButtonLabel(item)}
      </button>
    ))}
  </div>
);

export default ToggleButtonGroup;
