"use client";

import { useEffect, useState } from "react";
import ProtectedRoute from "@/components/protected-route";
import { useAuth } from "@/context/auth-context";
import type { Customer } from "@/lib/types";

export default function HomePage() {
  const { user } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const staticCustomers: Customer[] = [
      {
        id: 1,
        company_name: "Test Customer 1",
        audience_type: "LOCAL_PNG_CUSTOMER",
        primary_address: null,
        contact_person_name: "Jane Doe",
        contact_person_email: "jane@example.com",
        contact_person_phone: "123-456-7890",
        name: "Test Customer 1",
        email: "jane@example.com",
        phone: "123-456-7890",
      },
      {
        id: 2,
        company_name: "Test Customer 2",
        audience_type: "OVERSEAS_PARTNER_AU",
        primary_address: null,
        contact_person_name: "John Smith",
        contact_person_email: "john@example.com",
        contact_person_phone: "555-0100",
        name: "Test Customer 2",
        email: "john@example.com",
        phone: "555-0100",
      },
    ];
    setCustomers(staticCustomers);
    setLoading(false);
  }, [user]);

  return (
    <ProtectedRoute>
      <main className="container mx-auto p-8">
        <h1 className="text-4xl font-bold">Customers</h1>
        <p className="mt-2 text-lg text-gray-600">
          A list of customers from the database.
        </p>

        {loading && <div className="mt-6">Loading customers…</div>}

        {!loading && (
          <div className="mt-8">
            <ul className="divide-y divide-gray-200">
              {customers.map((customer) => (
                <li key={customer.id} className="py-4">
                  <p className="text-xl font-semibold text-gray-800">
                    {customer.company_name || customer.name}
                  </p>
                  <p className="text-sm text-gray-500">
                    {customer.contact_person_email || customer.email}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </ProtectedRoute>
  );
}
