import { useState } from 'react';
import './App.css';
import PieceRow from './components/PieceRow.jsx';

function App() {
  const [pieces, setPieces] = useState([
    // The first piece now has all the data fields
    { id: 1, weight: '', length: '', width: '', height: '' }
  ]);

  function addPiece() {
    // New pieces should also be created with the full structure
    const newPiece = {
      id: Date.now(), // Unique ID
      weight: '',
      length: '',
      width: '',
      height: ''
    };
    setPieces([...pieces, newPiece]);
  }

  function removePiece(idToRemove) {
    const updatedPieces = pieces.filter(piece => piece.id !== idToRemove);
    setPieces(updatedPieces);
  }

  function handlePieceChange(id, fieldName, value) {
  const nextPieces = pieces.map(p => {
    // If this is the piece that's being updated...
    if (p.id === id) {
      // ...return a new object with the changed field
      return { ...p, [fieldName]: value };
    }
    // Otherwise, return the piece unchanged
    return p;
  });
  // Update the state with the new array
  setPieces(nextPieces);
}

let totalChargeableWeight = 0;
pieces.forEach(p => {
  const weight = parseFloat(p.weight) || 0;
  const length = parseFloat(p.length) || 0;
  const width = parseFloat(p.width) || 0;
  const height = parseFloat(p.height) || 0;

  if (weight > 0 || length > 0) {
    // Using the standard 1:6000 ratio for air freight
    const volumetricWeight = (length * width * height) / 6000;
    totalChargeableWeight += Math.max(weight, volumetricWeight);
  }
});
// Round up to the nearest whole number
const finalChargeableWeight = Math.ceil(totalChargeableWeight);

  return (
    <div className="container">
      <h1>Project RateEngine</h1>
      <h2>Shipment Details</h2>

<div className="pieces-container">
  {pieces.map(piece => (
    <PieceRow
      key={piece.id}
      piece={piece} // Pass the entire piece object
      onRemove={removePiece}
      onChange={handlePieceChange} // Pass the change handler
    />
  ))}
</div>
      <button type="button" className="btn-add" onClick={addPiece}>
        + Add Piece
      </button>

    {/* --- DISPLAY THE CALCULATION --- */}
    <div className="chargeable-weight-display">
      <h2>Total Chargeable Weight</h2>
      <p>
        <strong>{finalChargeableWeight}</strong> kg
      </p>
    </div>
        
    </div>
  );
}

export default App;