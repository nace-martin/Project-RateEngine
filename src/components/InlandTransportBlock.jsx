import React, { useState, useEffect } from 'react';

const TRANSPORT_TYPES = [
  'Port to Door',
  'Door to Port',
  'Port to CFS',
  'CFS to Door',
  'Empty Container Return',
  'Port to Port Shuttle',
];

const CONTAINER_TYPES = ['20GP', '40HC', '40RF', 'Other']; // Add more as needed
const TRUCK_TYPES = ['1-ton', '3-ton', '10-ton', 'Side Loader', 'Other']; // Add more as needed

function InlandTransportBlock({ onChange, locations = [] }) {
  const [formData, setFormData] = useState({
    transportType: TRANSPORT_TYPES[0],
    pickupLocation: '',
    dropOffLocation: '',
    containerType: CONTAINER_TYPES[0],
    truckType: TRUCK_TYPES[0],
    specialInstructions: '',
  });

  const [showContainerType, setShowContainerType] = useState(false);

  useEffect(() => {
    // Logic to determine if containerType should be shown
    // Example: Show if transportType involves a port or CFS, or implies container movement.
    const involvesContainer = formData.transportType.toLowerCase().includes('port') ||
                             formData.transportType.toLowerCase().includes('cfs') ||
                             formData.transportType.toLowerCase().includes('container');
    setShowContainerType(involvesContainer);
  }, [formData.transportType]);

  const handleChange = (field, value) => {
    const newData = { ...formData, [field]: value };
    setFormData(newData);
    if (onChange) {
      onChange(newData);
    }
  };

  return (
    <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-md text-gray-800">
      <h2 className="text-xl font-bold text-blue-600 mb-4 border-b border-gray-200 pb-2">INLAND TRANSPORT DETAILS</h2>

      {/* Transport Type */}
      <div className="mb-4">
        <label htmlFor="transportType" className="block mb-2 font-bold text-gray-800">Transport Type</label>
        <select
          id="transportType"
          name="transportType"
          value={formData.transportType}
          onChange={(e) => handleChange('transportType', e.target.value)}
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {TRANSPORT_TYPES.map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
      </div>

      {/* Pickup Location */}
      <div className="mb-4">
        <label htmlFor="pickupLocation" className="block mb-2 font-bold text-gray-800">Pickup Location</label>
        <select
          id="pickupLocation"
          name="pickupLocation"
          value={formData.pickupLocation}
          onChange={(e) => handleChange('pickupLocation', e.target.value)}
          disabled={!locations.length}
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Select Pickup Location</option>
          {locations.map((loc) => (
            <option key={`pickup-${loc}`} value={loc}>{loc}</option>
          ))}
        </select>
        {/* Fallback for text input if needed, or could be a separate component for combined input */}
      </div>

      {/* Drop-off Location */}
      <div className="mb-4">
        <label htmlFor="dropOffLocation" className="block mb-2 font-bold text-gray-800">Drop-off Location</label>
        <select
          id="dropOffLocation"
          name="dropOffLocation"
          value={formData.dropOffLocation}
          onChange={(e) => handleChange('dropOffLocation', e.target.value)}
          disabled={!locations.length}
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Select Drop-off Location</option>
          {locations.map((loc) => (
            <option key={`dropoff-${loc}`} value={loc}>{loc}</option>
          ))}
        </select>
        {/* Fallback for text input */}
      </div>
      
      {/* Container Type (Conditional) */}
      {showContainerType && (
        <div className="mb-4">
          <label htmlFor="containerType" className="block mb-2 font-bold text-gray-800">Container Type</label>
          <select
            id="containerType"
            name="containerType"
            value={formData.containerType}
            onChange={(e) => handleChange('containerType', e.target.value)}
            className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {CONTAINER_TYPES.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
      )}

      {/* Truck Type */}
      <div className="mb-4">
        <label htmlFor="truckType" className="block mb-2 font-bold text-gray-800">Truck Type</label>
        <select
          id="truckType"
          name="truckType"
          value={formData.truckType}
          onChange={(e) => handleChange('truckType', e.target.value)}
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {TRUCK_TYPES.map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
      </div>

      {/* Special Instructions */}
      <div className="mb-4">
        <label htmlFor="specialInstructions" className="block mb-2 font-bold text-gray-800">Special Instructions</label>
        <textarea
          id="specialInstructions"
          name="specialInstructions"
          value={formData.specialInstructions}
          onChange={(e) => handleChange('specialInstructions', e.target.value)}
          rows="4"
          className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
    </div>
  );
}

export default InlandTransportBlock;
