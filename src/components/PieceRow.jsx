import './PieceRow.css';

// 1. Receive the new props: `piece` and `onChange`
function PieceRow({ piece, onRemove, onChange }) {

  const handleInputChange = (e) => {
    // e.target.name will be "weight", "length", etc.
    // e.target.value will be the text the user typed
    onChange(piece.id, e.target.name, e.target.value);
  };

  return (
    <div className="piece-row">
      <input
        type="number"
        name="weight" // The 'name' attribute is crucial now
        className="piece-input"
        placeholder="Wt (kg)"
        value={piece.weight} // 2. Value is controlled by the prop
        onChange={handleInputChange} // 3. onChange calls our handler
      />
      <input
        type="number"
        name="length"
        className="piece-input"
        placeholder="L (cm)"
        value={piece.length}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="width"
        className="piece-input"
        placeholder="W (cm)"
        value={piece.width}
        onChange={handleInputChange}
      />
      <input
        type="number"
        name="height"
        className="piece-input"
        placeholder="H (cm)"
        value={piece.height}
        onChange={handleInputChange}
      />
      <button type="button" className="btn-remove" onClick={() => onRemove(piece.id)}>
        X
      </button>
    </div>
  );
}

export default PieceRow;