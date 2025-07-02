import React, { useState, useEffect } from 'react';

function CustomsClearanceBlock({ onChange, locations = [] }) { // Add locations prop with default value
  const [direction, setDirection] = useState('import');
  const [mode, setMode] = useState('air');
  const [originCountry, setOriginCountry] = useState('');
  const [destinationPort, setDestinationPort] = useState('');
  const [hsCodes, setHsCodes] = useState('');
  const [invoiceLines, setInvoiceLines] = useState('');
  const [naqiaOrExemption, setNaqiaOrExemption] = useState(false);

  // Function to consolidate form data and call onChange
  const handleChange = (field, value) => {
    const updatedData = {
      direction,
      mode,
      originCountry,
      destinationPort,
      hsCodes,
      invoiceLines,
      naqiaOrExemption,
      [field]: value, // Update the specific field that changed
    };

    // Update local state first
    if (field === 'direction') setDirection(value);
    else if (field === 'mode') setMode(value);
    else if (field === 'originCountry') setOriginCountry(value);
    else if (field === 'destinationPort') setDestinationPort(value);
    else if (field === 'hsCodes') setHsCodes(value);
    else if (field === 'invoiceLines') setInvoiceLines(value);
    else if (field === 'naqiaOrExemption') setNaqiaOrExemption(value);

    if (onChange) {
      onChange(updatedData);
    }
  };

  return (
    <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-md text-gray-800">
      <h2 className="text-xl font-bold text-blue-600 mb-4 border-b border-gray-200 pb-2">Customs Clearance Details</h2>
      
      {/* Direction */}
      <div className="mb-4">
        <label className="block mb-2 font-bold text-gray-800">Direction</label>
        <div>
          <label className="inline-flex items-center mr-6">
            <input
              type="radio"
              name="direction"
              value="import"
              checked={direction === 'import'}
              onChange={(e) => handleChange('direction', e.target.value)}
              className="form-radio text-blue-600"
            />
            <span className="ml-2">Import</span>
          </label>
          <label className="inline-flex items-center">
            <input
              type="radio"
              name="direction"
              value="export"
              checked={direction === 'export'}
              onChange={(e) => handleChange('direction', e.target.value)}
              className="form-radio text-blue-600"
            />
            <span className="ml-2">Export</span>
          </label>
        </div>
      </div>

      {/* Mode */}
      <div className="mb-4">
        <label className="block mb-2 font-bold text-gray-800">Mode</label>
        <div>
          <label className="inline-flex items-center mr-6">
            <input
              type="radio"
              name="mode"
              value="air"
              checked={mode === 'air'}
              onChange={(e) => handleChange('mode', e.target.value)}
              className="form-radio text-blue-600"
            />
            <span className="ml-2">Air</span>
          </label>
          <label className="inline-flex items-center">
            <input
              type="radio"
              name="mode"
              value="sea"
              checked={mode === 'sea'}
              onChange={(e) => handleChange('mode', e.target.value)}
              className="form-radio text-blue-600"
            />
            <span className="ml-2">Sea</span>
          </label>
        </div>
      </div>

      {/* Origin Country */}
      <div className="mb-4">
        <label htmlFor="originCountry" className="block mb-2 font-bold text-gray-800">Origin Country</label>
        <input
          type="text"
          id="originCountry"
          name="originCountry"
          value={originCountry}
          onChange={(e) => handleChange('originCountry', e.target.value)}
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Destination Port */}
      <div className="mb-4">
        <label htmlFor="destinationPort" className="block mb-2 font-bold text-gray-800">Destination Port</label>
        <select
          id="destinationPort"
          name="destinationPort"
          value={destinationPort}
          onChange={(e) => handleChange('destinationPort', e.target.value)}
          disabled={!locations.length}
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {locations.map((loc) => (
            <option key={loc} value={loc}>
              {loc}
            </option>
          ))}
        </select>
      </div>

      {/* HS Code(s) */}
      <div className="mb-4">
        <label htmlFor="hsCodes" className="block mb-2 font-bold text-gray-800">HS Code(s)</label>
        <input
          type="text"
          id="hsCodes"
          name="hsCodes"
          value={hsCodes}
          onChange={(e) => handleChange('hsCodes', e.target.value)}
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Invoice Lines / Item Description */}
      <div className="mb-4">
        <label htmlFor="invoiceLines" className="block mb-2 font-bold text-gray-800">Invoice Lines / Item Description</label>
        <textarea
          id="invoiceLines"
          name="invoiceLines"
          value={invoiceLines}
          onChange={(e) => handleChange('invoiceLines', e.target.value)}
          rows="4"
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* NAQIA or Exemption Toggle */}
      <div className="mb-4">
        <label className="inline-flex items-center">
          <input
            type="checkbox"
            name="naqiaOrExemption"
            checked={naqiaOrExemption}
            onChange={(e) => handleChange('naqiaOrExemption', e.target.checked)}
            className="form-checkbox text-blue-600 h-5 w-5"
          />
          <span className="ml-2 text-gray-800">NAQIA or Exemption</span>
        </label>
      </div>
    </div>
  );
}

export default CustomsClearanceBlock;
