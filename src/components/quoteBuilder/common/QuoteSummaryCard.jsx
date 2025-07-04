import React from 'react';

const QuoteSummaryCard = ({ quoteData, onSaveQuote, saving, saveSuccess, saveError, onDownloadPdf, isDownloadingPdf }) => {
  if (!quoteData) {
    return null;
  }

  const {
    pieces = [],
    totalChargeableWeight,
    origin,
    destination,
    incoterm,
    isDangerousGoods,
    notes,
    createdBy,
    transportMode,
    fxQuoteData, // Destructure fxQuoteData
  } = quoteData;

  const { quoteAmount, adjustedRate } = fxQuoteData || {}; // Provide default empty object

  const totalQuantity = pieces.reduce((sum, piece) => sum + (parseInt(piece.quantity, 10) || 0), 0);
  const totalWeight = pieces.reduce((sum, piece) => sum + ((parseInt(piece.quantity, 10) || 0) * (parseFloat(piece.weightKg, 10) || 0)), 0);

  const formatDimensions = (piece) => {
    if (!piece || !piece.lengthCm || !piece.widthCm || !piece.heightCm) return 'N/A';
    return `${piece.lengthCm}L x ${piece.widthCm}W x ${piece.heightCm}H cm`;
  };

  const piecesSummary = () => {
    if (pieces.length === 0) return 'No pieces';
    if (pieces.length === 1) {
      const piece = pieces[0];
      return `${piece.quantity || 0} pc / ${formatDimensions(piece)} / ${((parseInt(piece.quantity, 10) || 0) * (parseFloat(piece.weightKg, 10) || 0)).toFixed(2)} kg`;
    }
    return `${totalQuantity} pcs / Multiple dimensions / ${totalWeight.toFixed(2)} kg`;
  };

  return (
    <div className="bg-white shadow-md rounded-lg p-6 space-y-4">
      <h3 className="text-xl font-semibold text-gray-800 border-b pb-2 mb-4">Quote Summary</h3>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
        <div>
          <p className="text-sm font-medium text-gray-500">Transport Mode</p>
          <p className="text-md text-gray-800">{transportMode || 'N/A'}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Route</p>
          <p className="text-md text-gray-800">{origin || 'N/A'} → {destination || 'N/A'}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Incoterm</p>
          <p className="text-md text-gray-800">{incoterm || 'N/A'}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Pieces</p>
          <p className="text-md text-gray-800">{piecesSummary()}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Chargeable Weight (RT)</p>
          <p className="text-md text-gray-800">{totalChargeableWeight ? `${totalChargeableWeight} RT` : 'N/A'}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Dangerous Goods</p>
          <p className="text-md text-gray-800">{isDangerousGoods ? 'Yes' : 'No'}</p>
        </div>
        {notes && (
          <div className="md:col-span-2">
            <p className="text-sm font-medium text-gray-500">Additional Notes</p>
            <p className="text-md text-gray-800 whitespace-pre-wrap">{notes}</p>
          </div>
        )}
        <div className="md:col-span-2">
          <p className="text-sm font-medium text-gray-500">Created By</p>
          <p className="text-md text-gray-800">{createdBy || 'N/A'}</p>
        </div>
        
        {/* Display FX Quote Information if available */}
        {quoteAmount && adjustedRate && (
          <div className="md:col-span-2 pt-4 mt-4 border-t">
            <p className="text-sm font-medium text-gray-500">Quoted Amount (USD)</p>
            <p className="text-md text-gray-800">
              ${quoteAmount} @ FX rate: {adjustedRate}
            </p>
          </div>
        )}
      </div>

      {(onSaveQuote || onDownloadPdf) && (
        <div className="mt-6 pt-4 border-t">
          <div className="flex items-center space-x-4">
            {onSaveQuote && (
              <button
                onClick={onSaveQuote}
                disabled={saving || isDownloadingPdf}
                className="w-full bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Quote'}
              </button>
            )}
            {onDownloadPdf && (
              <button
                onClick={onDownloadPdf}
                disabled={saving || isDownloadingPdf}
                className="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline disabled:opacity-50"
              >
                {isDownloadingPdf ? 'Downloading...' : 'Download PDF'}
              </button>
            )}
          </div>
          {saveSuccess && (
            <p className="text-green-500 mt-2 text-sm text-center">Quote saved successfully!</p>
          )}
          {saveError && (
            <p className="text-red-500 mt-2 text-sm text-center">Error: {saveError}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default QuoteSummaryCard;
