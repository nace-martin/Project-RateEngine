import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import QuoteBuilder from './pages/QuoteBuilder.jsx';
import AirQuoteBuilder from './pages/AirQuoteBuilder.jsx'; // Import the new component

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-white text-dark-charcoal">
        <Routes>
          <Route path="/" element={<QuoteBuilder />} />
          <Route path="/air-quote" element={<AirQuoteBuilder />} /> {/* Add the new route */}
        </Routes>
      </div>
    </Router>
  );
}

export default App;