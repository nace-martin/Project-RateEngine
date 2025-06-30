import QuoteBuilder from './pages/QuoteBuilder.jsx';

function App() {
  // The App component's only job now is to render our page.
  // In the future, this is where you would add a Navbar, Footer, or Routing.
  return (
    <div className="min-h-screen bg-white text-dark-charcoal">
      <QuoteBuilder />
    </div>
  );
}

export default App;