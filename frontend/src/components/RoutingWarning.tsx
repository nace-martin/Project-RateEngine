"use client";

import React from 'react';
import { AlertCircle, Plane } from 'lucide-react';

interface RoutingViolation {
    piece_number: number;
    dimension: string;
    actual: string;
    limit: string;
    message: string;
}

interface RoutingInfo {
    service_level: string;
    routing_reason?: string;
    requires_via_routing: boolean;
    violations: RoutingViolation[];
}

interface RoutingWarningProps {
    routingInfo: RoutingInfo;
    className?: string;
}

export default function RoutingWarning({ routingInfo, className = '' }: RoutingWarningProps) {
    if (!routingInfo.requires_via_routing) {
        return null;
    }

    return (
        <div className={`rounded-lg border-l-4 border-amber-500 bg-amber-50 p-4 ${className}`}>
            <div className="flex items-start gap-3">
                <div className="flex-shrink-0">
                    <AlertCircle className="h-5 w-5 text-amber-600" />
                </div>
                <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                        <h3 className="text-sm font-semibold text-amber-900">
                            Routing via Brisbane Required
                        </h3>
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                            <Plane className="h-3 w-3" />
                            {routingInfo.service_level}
                        </span>
                    </div>

                    {routingInfo.routing_reason && (
                        <p className="text-sm text-amber-800 mb-3">
                            {routingInfo.routing_reason}
                        </p>
                    )}

                    {routingInfo.violations.length > 0 && (
                        <div className="mt-2 space-y-1">
                            <p className="text-xs font-medium text-amber-900">Constraint Violations:</p>
                            <ul className="space-y-1 text-xs text-amber-700">
                                {routingInfo.violations.map((violation, idx) => (
                                    <li key={idx} className="flex items-start gap-1">
                                        <span className="text-amber-500">•</span>
                                        <span>{violation.message}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="mt-3 pt-3 border-t border-amber-200">
                        <p className="text-xs text-amber-700">
                            This shipment will be routed <strong>SYD → BNE → POM</strong> via Air Niugini's wide-body B767 service.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
