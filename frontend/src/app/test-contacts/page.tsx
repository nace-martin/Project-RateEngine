"use client";

import { useState } from "react";
import { useAuth } from "@/context/auth-context";
import { getContactsForCompany, searchCompanies } from "@/lib/api";
import { CompanySearchResult, Contact } from "@/lib/types";
import { Button } from "@/components/ui/button";

export default function TestContactsPage() {
  const { user, token } = useAuth();
  const [companies, setCompanies] = useState<CompanySearchResult[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [log, setLog] = useState<string[]>([]);

  const addLog = (msg: string) => setLog(prev => [...prev, msg]);

  const handleSearch = async () => {
    addLog("Searching companies...");
    try {
      const res = await searchCompanies("Test"); // Search for "Test" or similar
      addLog(`Found ${res.length} companies.`);
      setCompanies(res);
    } catch (e: any) {
      addLog(`Error searching: ${e.message}`);
    }
  };

  const handleFetchContacts = async (id: string) => {
    setSelectedCompanyId(id);
    addLog(`Fetching contacts for company ${id}...`);
    try {
        const res = await getContactsForCompany(id);
        addLog(`Fetched ${res.length} contacts.`);
        addLog(JSON.stringify(res, null, 2));
        setContacts(res);
    } catch (e: any) {
        addLog(`Error fetching contacts: ${e.message}`);
    }
  };

  if (!user) return <div>Please login first</div>;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Contact Debugger</h1>
      <div className="mb-4">
        <Button onClick={handleSearch}>Search Companies</Button>
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        <div>
            <h2 className="font-bold">Companies</h2>
            <ul>
                {companies.map(c => (
                    <li key={c.id} className="mb-2">
                        <Button variant="outline" onClick={() => handleFetchContacts(c.id)}>
                            {c.name}
                        </Button>
                    </li>
                ))}
            </ul>
        </div>
        <div>
            <h2 className="font-bold">Contacts</h2>
            <pre className="bg-gray-100 p-2 rounded">{JSON.stringify(contacts, null, 2)}</pre>
        </div>
      </div>

      <div className="mt-8 border-t pt-4">
        <h2 className="font-bold">Logs</h2>
        <pre className="bg-black text-white p-4 rounded h-64 overflow-auto">
            {log.join('\n')}
        </pre>
      </div>
    </div>
  );
}
