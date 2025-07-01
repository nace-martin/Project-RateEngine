function PieceRow({ piece, onRemove, onChange }) {

  const handleInputChange = (e) => {
    onChange(piece.id, e.target.name, e.target.value);
  };

  return (
    <div className="grid grid-cols-5 gap-2 items-center">
      <input
        type="number"
        name="weight"
        className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="Wt (kg)"
        value={piece.weight}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="length"
        className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="L (cm)"
        value={piece.length}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="width"
        className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="W (cm)"
        value={piece.width}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="height"
        className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="H (cm)"
        value={piece.height}
        onChange={handleInputChange}
      />
      <button type="button" className="bg-orange-500 text-white font-bold py-2 px-4 rounded-xl hover:bg-orange-600 disabled:bg-gray-400 disabled:cursor-not-allowed" onClick={() => onRemove(piece.id)}>
        X
      </button>
    </div>
  );
}

export default PieceRow;