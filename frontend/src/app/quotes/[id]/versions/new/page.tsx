'use client';

import { useParams } from 'next/navigation';

export default function NewQuoteVersionPage() {
    const params = useParams();
    const { id } = params;

    return (
        <div className="container mx-auto p-4">
            <h1 className="text-2xl font-bold">Add New Version for Quotation #{id}</h1>
            <p>This is a placeholder for the new quote version page.</p>
        </div>
    );
}
