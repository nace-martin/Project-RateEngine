// 1. Receive the new props: `piece` and `onChange`
function PieceRow({ piece, onRemove, onChange }) {

  const handleInputChange = (e) => {
    // e.target.name will be "weight", "length", etc.
    // e.target.value will be the text the user typed
    onChange(piece.id, e.target.name, e.target.value);
  };

  return (
    <div className="grid grid-cols-5 gap-2 items-center">
      <input
        type="number"
        name="weight"
        className="w-full p-2 border border-cool-gray rounded-md bg-light-gray text-dark-charcoal focus:outline-none focus:border-efm-blue"
        placeholder="Wt (kg)"
        value={piece.weight}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="length"
        className="w-full p-2 border border-cool-gray rounded-md bg-light-gray text-dark-charcoal focus:outline-none focus:border-efm-blue"
        placeholder="L (cm)"
        value={piece.length}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="width"
        className="w-full p-2 border border-cool-gray rounded-md bg-light-gray text-dark-charcoal focus:outline-none focus:border-efm-blue"
        placeholder="W (cm)"
        value={piece.width}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="height"
        className="w-full p-2 border border-cool-gray rounded-md bg-light-gray text-dark-charcoal focus:outline-none focus:border-efm-blue"
        placeholder="H (cm)"
        value={piece.height}
        onChange={handleInputChange}
      />
      <button type="button" className="bg-error text-white px-3 py-2 rounded-xl font-bold text-sm hover:bg-red-700" onClick={() => onRemove(piece.id)}>
        X
      </button>
    </div>
  );
}

export default PieceRow;