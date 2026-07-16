import React from "react";
import { ExceptionWorkspace } from "../../../../components/spot/ExceptionWorkspace";
import { hardCaseAirImportData } from "../../../../data/hardCaseAirImport";

export const metadata = {
    title: "SPOT Exception Workspace Demo",
    description: "Phase 8D.1 - Exception Workspace Prototype",
};

export default function ExceptionWorkspaceDemoPage() {
    return (
        <div className="w-full min-h-screen bg-slate-900">
            <ExceptionWorkspace initialData={hardCaseAirImportData} />
        </div>
    );
}
