import React from 'react';

function QuoteOutput({ quote, onDownloadPdf, isDownloadingPdf }) { // Added onDownloadPdf and isDownloadingPdf props
  if (!quote) {
    return (
      <div className="quote-output">
        <h2>No quote data available yet.</h2>
      </div>
    );
  }

  return (
    <div className="bg-white p-4 rounded-2xl shadow-soft border border-cool-gray mt-5">
      <h2 className="text-efm-blue text-2xl font-semibold mb-4 pb-2 border-b border-cool-gray text-center">Quote Details</h2>
      <div className="mb-4 text-mid-gray">
        <p className="mb-2"><strong>Origin:</strong> {quote.origin}</p>
        <p className="mb-2"><strong>Destination:</strong> {quote.destination}</p>
        <p className="mb-2"><strong>Chargeable Weight:</strong> {quote.chargeableWeight} kg</p>
        <p className="mb-2"><strong>Generated At:</strong> {new Date(quote.generatedAt).toLocaleString()}</p>
      </div>
      <h3 className="text-efm-blue text-xl font-semibold mb-3 pb-2 border-b border-cool-gray">Line Items</h3>
      <table className="w-full border-collapse mb-4">
        <thead>
          <tr className="bg-cool-gray">
            <th className="border border-cool-gray p-2 text-left text-dark-charcoal">Description</th>
            <th className="border border-cool-gray p-2 text-left text-dark-charcoal">Cost</th>
          </tr>
        </thead>
        <tbody>
          {quote.lineItems && Array.isArray(quote.lineItems) && quote.lineItems.map((item, index) => (
            <tr key={index} className={`${index % 2 === 0 ? 'bg-light-gray' : 'bg-white'}`}>
              <td className="border border-cool-gray p-2 text-dark-charcoal">{item.name}</td>
              <td className="border border-cool-gray p-2 text-dark-charcoal">${(item.cost || 0).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="border-t border-cool-gray pt-4">
        <p className="text-lg font-bold flex justify-between mb-2"><strong>Subtotal:</strong> <span className="text-dark-charcoal">${(quote.subTotal || 0).toFixed(2)}</span></p>
        <p className="text-lg font-bold flex justify-between mb-2"><strong>GST:</strong> <span className="text-dark-charcoal">${(quote.gst || 0).toFixed(2)}</span></p>
        <p className="text-xl font-bold flex justify-between text-efm-blue"><strong>Grand Total:</strong> <span className="text-efm-blue">${(quote.grandTotal || 0).toFixed(2)}</span></p>
      </div>

      {onDownloadPdf && ( // Conditionally render the button if the handler is provided
        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={onDownloadPdf}
            disabled={isDownloadingPdf}
            className="bg-green-500 text-white font-bold py-3 px-6 rounded-xl hover:bg-green-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {isDownloadingPdf ? 'Downloading PDF...' : 'Download PDF'}
          </button>
        </div>
      )}
    </div>
  );
}

export default QuoteOutput;
