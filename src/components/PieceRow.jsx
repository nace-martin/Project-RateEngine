import './PieceRow.css';

function PieceRow() {
  // For now, this component doesn't have any logic.
  // It just returns the visual structure (JSX).

  return (
    <div className="piece-row">
      <input type="number" className="piece-input" placeholder="Wt (kg)" />
      <input type="number" className="piece-input" placeholder="L (cm)" />
      <input type="number" className="piece-input" placeholder="W (cm)" />
      <input type="number" className="piece-input" placeholder="H (cm)" />
      <button type="button" className="btn-remove">
        X
      </button>
    </div>
  );
}

export default PieceRow;