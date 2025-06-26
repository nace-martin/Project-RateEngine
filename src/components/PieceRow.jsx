import './PieceRow.css';

function PieceRow({ id, onRemove }) {
  return (
    <div className="piece-row">
      <input type="number" className="piece-input" placeholder="Wt (kg)" />
      <input type="number" className="piece-input" placeholder="L (cm)" />
      <input type="number" className="piece-input" placeholder="W (cm)" />
      <input type="number" className="piece-input" placeholder="H (cm)" />
      <button type="button" className="btn-remove" onClick={() => onRemove(id)}>        X
      </button>
    </div>
  );
}

export default PieceRow;