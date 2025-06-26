import { useState, useEffect } from 'react'; 
import './App.css';
import PieceRow from './components/PieceRow.jsx';
import { loadRateData } from './api.js';

function App() {
const [pieces, setPieces] = useState([
  { id: 1, weight: '', length: '', width: '', height: '' }
]);

const [freightRates, setFreightRates] = useState({});
const [locations, setLocations] = useState([]);
const [origin, setOrigin] = useState('');
const [destination, setDestination] = useState('');

  useEffect(() => {
    async function getRates() {
      console.log("Fetching rate data...");
      const { freightRates, locations } = await loadRateData();
      setFreightRates(freightRates);
      setLocations(locations);

      if (locations.length > 0) {
        setOrigin(locations[0]);
        setDestination(locations[1] || locations[0]);
      }

      console.log("Rate data loaded successfully!");
    }

    getRates();
  }, []);

  
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

    {/* --- ROUTING SECTION --- */}
    <div className="form-section">
      <h2>Routing</h2>
      <div className="form-group">
        <label htmlFor="origin">Origin</label>
        <select
          id="origin"
          name="origin"
          value={origin}
          onChange={e => setOrigin(e.target.value)}
        >
          {locations.map(loc => (
            <option key={loc} value={loc}>{loc}</option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="destination">Destination</label>
        <select
          id="destination"
          name="destination"
          value={destination}
          onChange={e => setDestination(e.target.value)}
        >
          {locations.map(loc => (
            <option key={loc} value={loc}>{loc}</option>
          ))}
        </select>
      </div>
    </div>

    {/* --- SHIPMENT DETAILS SECTION --- */}
    <div className="form-section">
      <h2>Shipment Details</h2>
      <div className="pieces-container">
        {pieces.map(piece => (
          <PieceRow
            key={piece.id}
            piece={piece}
            onRemove={removePiece}
            onChange={handlePieceChange}
          />
        ))}
      </div>

      <button type="button" className="btn-add" onClick={addPiece}>
        + Add Piece
      </button>
    </div>

    {/* --- DISPLAY THE CALCULATION --- */}
    <div className="chargeable-weight-display">
      <h2>Total Chargeable Weight</h2>
      <p><strong>{finalChargeableWeight}</strong> kg</p>
    </div>
  </div>
);
}

export default App;