import React from 'react';
import './QuoteOutput.css';

function QuoteOutput({ quote }) {
  if (!quote) {
    return (
      <div className="quote-output">
        <h2>No quote data available yet.</h2>
      </div>
    );
  }

  return (
    <div className="quote-output">
      <h2>Quote Details</h2>
      <div className="quote-summary">
        <p><strong>Origin:</strong> {quote.origin}</p>
        <p><strong>Destination:</strong> {quote.destination}</p>
        <p><strong>Chargeable Weight:</strong> {quote.chargeableWeight} kg</p>
        <p><strong>Generated At:</strong> {new Date(quote.generatedAt).toLocaleString()}</p>
      </div>
      <h3>Line Items</h3>
      <table>
        <thead>
          <tr>
            <th>Description</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {quote.lineItems.map((item, index) => (
            <tr key={index}>
              <td>{item.name}</td>
              <td>${(item.cost || 0).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="quote-totals">
        <p><strong>Subtotal:</strong> ${(quote.subTotal || 0).toFixed(2)}</p>
        <p><strong>GST:</strong> ${(quote.gst || 0).toFixed(2)}</p>
        <p><strong>Grand Total:</strong> ${(quote.grandTotal || 0).toFixed(2)}</p>
      </div>
    </div>
  );
}

export default QuoteOutput;
