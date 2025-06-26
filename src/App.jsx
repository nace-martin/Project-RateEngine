import { useState } from 'react'; // 1. Import the useState hook from React
import './App.css';
import PieceRow from './components/PieceRow.jsx';

function App() {
  // 2. Initialize our component's state
  const [pieces, setPieces] = useState([
    // Start with one piece by default
    { id: 1 }
  ]);
// ... inside the App component function, before the return statement ...

function addPiece() {
  const newPiece = {
    // Create a unique ID using the current timestamp
    id: Date.now()
  };
  // Use the 'setPieces' function to update the state
  setPieces([...pieces, newPiece]);
}
function removePiece(idToRemove) {
  // Use the filter method to create a new array without the piece to be removed
  const updatedPieces = pieces.filter(piece => piece.id !== idToRemove);
  setPieces(updatedPieces);
}
  return (
    <div className="container">
      <h1>Project RateEngine</h1>
      <h2>Shipment Details</h2>

      <div className="pieces-container">
        {pieces.map(piece => (
          <PieceRow
            key={piece.id}
            id={piece.id}
            onRemove={removePiece}
          />
        ))}
      </div>

      <button type="button" className="btn-add" onClick={addPiece}>
        + Add Piece
      </button>
    </div>
  );
}

export default App;