const ModeSelector = ({ selectedMode, onModeChange }) => {
  const baseClasses = "flex-1 py-3 px-4 text-center font-semibold cursor-pointer transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500";
  const activeClasses = "bg-blue-600 text-white";
  const inactiveClasses = "bg-gray-200 text-gray-700 hover:bg-gray-300";

  const modes = [
    { value: 'air-domestic', label: 'Domestic Air' },
    { value: 'air-international', label: 'Int\'l Air' },
    { value: 'sea-lcl', label: 'Sea LCL' },
    { value: 'sea-fcl', label: 'Sea FCL' },
    { value: 'inland-domestic', label: 'Inland Domestic' },
  ];

  return (
    <div className="flex flex-wrap rounded-lg overflow-hidden border border-gray-300">
      {modes.map((mode, index) => (
        <button
          key={mode.value}
          type="button"
          onClick={() => onModeChange(mode.value)}
          className={[
            baseClasses,
            index === 0 && 'rounded-l-lg',
            index === modes.length - 1 && 'rounded-r-lg',
            selectedMode === mode.value ? activeClasses : inactiveClasses,
            'mb-2 md:mb-0 md:mr-1 last:mr-0'
          ].filter(Boolean).join(' ')}
          style={{ minWidth: '120px' }} // Ensure buttons have some minimum width
        >
          {mode.label}
        </button>
      ))}
    </div>
  );
};

export default ModeSelector;
