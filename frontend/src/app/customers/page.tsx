'use client';

import { useState, useEffect } from 'react';
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface Address {
  country: string;
}

interface Customer {
  id: number;
  company_name: string;
  contact_person_name: string;
  primary_address: Address | null;
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);

  useEffect(() => {
    const getCustomers = async () => {
      const token = localStorage.getItem('authToken');
      const res = await fetch('http://127.0.0.1:8000/api/customers/', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Token ${token}`,
        },
      });
      if (!res.ok) {
        console.error('Failed to fetch customers');
        return;
      }
      const data = await res.json();
      setCustomers(data);
    };

    getCustomers();
  }, []);

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-center">
          <div>
            <CardTitle>Customers</CardTitle>
            <CardDescription>
              A list of all customers, agents, and partners in the system.
            </CardDescription>
          </div>
          <Link href="/customers/new">
            <Button>Add New Customer</Button>
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
          <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
              <th scope="col" className="px-6 py-3">
                Company Name
              </th>
              <th scope="col" className="px-6 py-3">
                Contact Person
              </th>
              <th scope="col" className="px-6 py-3">
                Country
              </th>
              <th scope="col" className="px-6 py-3">
                <span className="sr-only">Edit</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {customers.map((customer) => (
              <tr
                key={customer.id}
                className="bg-white border-b dark:bg-gray-800 dark:border-gray-700"
              >
                <th
                  scope="row"
                  className="px-6 py-4 font-medium text-gray-900 whitespace-nowrap dark:text-white"
                >
                  {customer.company_name}
                </th>
                <td className="px-6 py-4">{customer.contact_person_name}</td>
                <td className="px-6 py-4">{customer.primary_address?.country}</td>
                <td className="px-6 py-4 text-right">
                  <Link href={`/customers/${customer.id}/edit`}>
                    <Button variant="outline">Edit</Button>
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}