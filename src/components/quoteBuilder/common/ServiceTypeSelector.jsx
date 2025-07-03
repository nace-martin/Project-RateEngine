
import ToggleButtonGroup from '@/components/ui/ToggleButtonGroup';

const ServiceTypeSelector = ({ selectedServiceType, onServiceTypeChange }) => {
  const baseClasses = "flex-1 py-3 px-4 text-center font-semibold cursor-pointer transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500";
  const activeClasses = "bg-blue-600 text-white";
  const inactiveClasses = "bg-gray-200 text-gray-700 hover:bg-gray-300";
  const disabledClasses = "bg-gray-100 text-gray-400 cursor-not-allowed";

  const serviceTypes = [
    { value: 'airFreight', label: 'Air Freight', enabled: true },
    { value: 'seaFreight', label: 'Sea Freight', enabled: true },
    { value: 'customsClearance', label: 'Customs Clearance Only', enabled: true },
    { value: 'inlandTransport', label: 'Inland Transport / Cartage', enabled: true },
    { value: 'projectCargo', label: 'Breakbulk or Project Cargo', enabled: false },
  ];

  const getItemClasses = (service, index, items) => [
    baseClasses,
    index === 0 ? 'rounded-l-lg' : '',
    index === items.length - 1 ? 'rounded-r-lg' : '',
    selectedServiceType === service.value
      ? activeClasses
      : (service.enabled ? inactiveClasses : disabledClasses),
    'mb-1 md:mb-0 md:mr-0.5 last:mr-0 w-full sm:w-auto',
  ].filter(Boolean).join(' ');

  const isDisabled = (service) => !service.enabled;

  const getButtonLabel = (service) => (
    <>
      {service.label}
      {!service.enabled ? ' (Coming Soon)' : ''}
    </>
  );

  return (
    <div className="mb-6">
      <label className="block text-xl font-bold text-gray-800 mb-3 text-center">
        What kind of logistics service are you quoting?
      </label>
      <ToggleButtonGroup
        items={serviceTypes}
        selectedValue={selectedServiceType}
        onValueChange={onServiceTypeChange}
        getItemClasses={getItemClasses}
        isDisabled={isDisabled}
        getButtonLabel={getButtonLabel}
        buttonStyle={{ minWidth: '160px' }}
      />
    </div>
  );
};

export default ServiceTypeSelector;
