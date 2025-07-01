import PieceRow from './PieceRow';
import './ShipmentDetails.css';

const ShipmentDetails = ({ pieces, setPieces }) => {

  const handlePieceChange = (id, name, value) => {
    const updatedPieces = pieces.map(p => (p.id === id ? { ...p, [name]: value } : p));
    setPieces(updatedPieces);
  };

  const addPiece = () => {
    const newId = pieces.length > 0 ? Math.max(...pieces.map(p => p.id)) + 1 : 1;
    setPieces([...pieces, { id: newId, weight: '', length: '', width: '', height: '' }]);
  };

  const removePiece = (id) => {
    // Prevent removing the last piece
    if (pieces.length <= 1) return;
    setPieces(pieces.filter(p => p.id !== id));
  };

  return (
    <div className="form-section shipment-details-section">
      <h2>Shipment Details</h2>
      <div className="piece-header">
        <span>Weight (kg)</span>
        <span>Length (cm)</span>
        <span>Width (cm)</span>
        <span>Height (cm)</span>
        <span></span>
      </div>
      <div className="pieces-container">
        {pieces.map(piece => (
          <PieceRow
            key={piece.id}
            piece={piece}
            // Corrected prop name from onPieceChange to onChange
            onChange={handlePieceChange}
            onRemove={removePiece}
          />
        ))}
      </div>
      <div className="add-piece-container">
        {/* User's version of button text, kept from their provided code */}
        <button type="button" onClick={addPiece} className="btn-add-piece">
          Add Piece
        </button>
      </div>
    </div>
  );
};

export default ShipmentDetails;