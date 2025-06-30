import PieceRow from './PieceRow';

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
    <div className="bg-white p-4 rounded-2xl shadow-soft border border-cool-gray">
      <h2 className="text-efm-blue text-2xl font-semibold mb-4 pb-2 border-b border-cool-gray">Shipment Details</h2>
      <div className="grid grid-cols-5 gap-2 mb-2 text-mid-gray font-bold border-b border-cool-gray pb-2">
        <span>Weight (kg)</span>
        <span>Length (cm)</span>
        <span>Width (cm)</span>
        <span>Height (cm)</span>
        <span></span>
      </div>
      <div className="flex flex-col gap-2">
        {pieces.map(piece => (
          <PieceRow
            key={piece.id}
            piece={piece}
            onRemove={removePiece}
            onChange={handlePieceChange}
          />
        ))}
      </div>
      <div className="mt-4 text-center">
        <button type="button" className="bg-efm-blue text-white px-4 py-2 rounded-xl font-bold text-sm hover:bg-blue-700" onClick={addPiece}>
          + Add Another Piece
        </button>
      </div>
    </div>
  );
};

export default ShipmentDetails;
