const ModeSelector = ({ selectedMode, onModeChange }) => {
  const baseClasses = "flex-1 py-3 px-4 text-center font-semibold cursor-pointer transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500";
  const activeClasses = "bg-blue-600 text-white";
  const inactiveClasses = "bg-gray-200 text-gray-700 hover:bg-gray-300";

  return (
    <div className="flex rounded-lg overflow-hidden border border-gray-300">
      <button
        type="button"
        onClick={() => onModeChange('domesticAir')}
        className={`${baseClasses} rounded-l-lg ${selectedMode === 'domesticAir' ? activeClasses : inactiveClasses}`}
      >
        Domestic Air
      </button>
      <button
        type="button"
        onClick={() => onModeChange('lclSea')}
        className={`${baseClasses} rounded-r-lg ${selectedMode === 'lclSea' ? activeClasses : inactiveClasses}`}
      >
        LCL Sea
      </button>
    </div>
  );
};

export default ModeSelector;
