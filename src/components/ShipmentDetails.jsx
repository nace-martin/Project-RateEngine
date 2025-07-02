import PieceRow from './PieceRow';
import './ShipmentDetails.css';

const ShipmentDetails = ({
  pieces,
  setPieces,
  freightMode,
  incoterm,
  onIncotermChange,
  warehouseCutoffDate,
  onWarehouseCutoffDateChange,
  displayCBM,
  displayRT
}) => {
  const incotermOptions = ['EXW', 'FOB', 'CIF', 'DAP', 'DDP'];

  const showIncoterms = freightMode === 'air-international' || freightMode === 'sea-lcl' || freightMode === 'sea-fcl';
  const showLCLFields = freightMode === 'sea-lcl';

  const handlePieceChange = (id, name, value) => {
    const updatedPieces = pieces.map(p => (p.id === id ? { ...p, [name]: value } : p));
    setPieces(updatedPieces);
  };

  const addPiece = () => {
    const newId = pieces.length > 0 ? Math.max(...pieces.map(p => p.id)) + 1 : 1;
    setPieces([...pieces, { id: newId, weight: '', length: '', width: '', height: '' }]);
  };

  const removePiece = (id) => {
    if (pieces.length <= 1) return;
    setPieces(pieces.filter(p => p.id !== id));
  };

  return (
    <div className="form-section shipment-details-section bg-white p-6 rounded-2xl border border-gray-200 shadow-md text-gray-800">
      <div className="flex justify-between items-center mb-6"> {/* Increased bottom margin */}
        <h2 className="text-xl font-bold text-blue-600">Shipment Details</h2>
        {/* Container for Incoterms and Warehouse Cut-off Date */}
        <div className="flex gap-x-4 items-end">
          {showIncoterms && (
            <div className="flex-1 min-w-[180px]"> {/* Adjusted min-width */}
              <label htmlFor="incoterm" className="block text-sm font-medium text-gray-700 mb-1">Incoterm</label>
              <select
                id="incoterm"
                name="incoterm"
                value={incoterm}
                onChange={(e) => onIncotermChange(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {incotermOptions.map(option => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>
          )}
          {showLCLFields && (
            <div className="flex-1 min-w-[180px]"> {/* Adjusted min-width */}
              <label htmlFor="warehouseCutoffDate" className="block text-sm font-medium text-gray-700 mb-1">Warehouse Cut-off</label>
              <input
                type="date"
                id="warehouseCutoffDate"
                name="warehouseCutoffDate"
                value={warehouseCutoffDate || ''}
                onChange={(e) => onWarehouseCutoffDateChange(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}
        </div>
      </div>

      {showLCLFields && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2 mb-6 p-4 bg-indigo-50 border border-indigo-200 rounded-lg shadow">
          <div>
            <span className="block text-sm font-medium text-gray-500">Total Volume (CBM):</span>
            <span className="block text-xl font-semibold text-indigo-700 data-testid-total-cbm">{displayCBM.toFixed(3)} m³</span>
          </div>
          <div>
            <span className="block text-sm font-medium text-gray-500">Revenue Tons (RT):</span>
            <span className="block text-xl font-semibold text-indigo-700 data-testid-revenue-tons">{displayRT.toFixed(3)}</span>
          </div>
        </div>
      )}

      <div className="piece-header mb-2"> {/* Added margin to piece-header */}
        <span className="font-medium text-gray-600">Weight (kg)</span>
        <span className="font-medium text-gray-600">Length (cm)</span>
        <span className="font-medium text-gray-600">Width (cm)</span>
        <span className="font-medium text-gray-600">Height (cm)</span>
        <span></span> {/* For remove button column */}
      </div>
      <div className="pieces-container space-y-3"> {/* Added space-y for spacing between piece rows */}
        {pieces.map(piece => (
          <PieceRow
            key={piece.id}
            piece={piece}
            onChange={handlePieceChange}
            onRemove={removePiece}
          />
        ))}
      </div>
      <div className="add-piece-container mt-4"> {/* Added margin top */}
        <button type="button" onClick={addPiece} className="bg-green-500 hover:bg-green-600 text-white font-semibold py-2 px-4 rounded-md shadow focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2">
          Add Piece
        </button>
      </div>
    </div>
  );
};

export default ShipmentDetails;