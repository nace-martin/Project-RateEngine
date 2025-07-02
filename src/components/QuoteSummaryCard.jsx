import React from 'react';
import './QuoteSummaryCard.css'; // Import the CSS file

const QuoteSummaryCard = ({
  serviceType,
  freightMode,
  origin,
  destination,
  incoterm,
  pieces,
}) => {
  // Condition to render the card: origin, destination, and at least one piece with dimensions/weight
  const shouldRender =
    origin &&
    destination &&
    pieces &&
    pieces.some(
      (piece) => piece.length && piece.width && piece.height && piece.weight
    );

  if (!shouldRender) {
    return null; // Don't render the card if conditions aren't met
  }

  return (
    <div className="quote-summary-card">
      <h2>Quote Summary</h2>
      <p>Service Type: {serviceType}</p>
      <p>Freight Mode: {freightMode}</p>
      <p>Routing: {origin} to {destination}</p>
      <p>Incoterm: {incoterm}</p>
      <h3>Totals</h3>
      <p>Estimated Cost: [Placeholder]</p> {/* Static placeholder */}
      <p className={`status-line ${getStatusClass(serviceType, origin, destination, pieces, incoterm)}`}>
        {getStatusMessage(serviceType, origin, destination, pieces, incoterm)}
      </p>
    </div>
  );
};

// Helper functions to determine status
const getStatusMessage = (serviceType, origin, destination, pieces, incoterm) => {
  if (!origin || !destination) {
    return '❌ Invalid Quote Inputs'; // Should ideally not happen if card render logic is strict
  }
  const arePiecesValid = pieces && pieces.every(p => p.length && p.width && p.height && p.weight && p.quantity);
  if (!arePiecesValid) {
    return '⚠️ Waiting for Shipment Details';
  }
  if (!serviceType || !incoterm) { // Add other essential fields for a full quote if necessary
    return '⚠️ Waiting for Shipment Details'; // Or a more specific message
  }
  return '✅ Ready to Quote';
};

const getStatusClass = (serviceType, origin, destination, pieces, incoterm) => {
  const message = getStatusMessage(serviceType, origin, destination, pieces, incoterm);
  if (message.startsWith('✅')) return 'status-ready';
  if (message.startsWith('⚠️')) return 'status-waiting';
  if (message.startsWith('❌')) return 'status-invalid';
  return '';
};

export default QuoteSummaryCard;
