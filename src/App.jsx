import './App.css'
import PieceRow from './components/PieceRow.jsx'; // 1. Import your new component

function App() {
  return (
    <div className="container"> {/* Added a container for centering */}
      <h1>Project RateEngine</h1>
      <h2>Shipment Details</h2>

      {/* 2. Use your component like an HTML tag */}
      <PieceRow />
      <PieceRow />
      <PieceRow />

    </div>
  )
}

export default App