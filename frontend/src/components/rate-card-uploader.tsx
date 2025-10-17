"use client";

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/auth-context';
import { uploadRateCard, getRateCards } from '@/lib/api';
import { RatecardFile } from '@/lib/types';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';

export default function RateCardUploader() {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [rateCards, setRateCards] = useState<RatecardFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchRateCards = useCallback(async () => {
    if (token) {
      setIsLoading(true);
      try {
        const data = await getRateCards(token);
        setRateCards(data);
      } catch (err) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('Failed to fetch rate cards');
        }
      } finally {
        setIsLoading(false);
      }
    }
  }, [token]);

  useEffect(() => {
    fetchRateCards();
  }, [fetchRateCards]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !token) {
      setError('Please select a file and ensure you are logged in.');
      return;
    }

    const fileType = file.name.split('.').pop()?.toUpperCase();
    if (fileType !== 'CSV' && fileType !== 'HTML') {
        setError('Invalid file type. Please upload a CSV or HTML file.');
        return;
    }
    
    try {
      await uploadRateCard(token, file, file.name, fileType);
      setFile(null);
      fetchRateCards(); // Refresh the list after upload
      setError(null)
    } catch {
      setError('Failed to upload file');
    }
  };

  return (
    <Card>
        <CardHeader>
            <CardTitle>Upload Rate Card</CardTitle>
        </CardHeader>
        <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
            <Input type="file" onChange={handleFileChange} />
            <Button type="submit" disabled={!file}>Upload</Button>
            {error && <p className="text-red-500">{error}</p>}
            </form>

            <h3 className="text-lg font-semibold mt-6">Uploaded Rate Cards</h3>
            {isLoading ? (
              <p>Loading rate cards...</p>
            ) : (
              <ul className="space-y-2 mt-4">
              {rateCards.map((rateCard) => (
                  <li key={rateCard.id} className="border p-2 rounded-md">
                  {rateCard.name} ({rateCard.file_type})
                  </li>
              ))}
              </ul>
            )}
        </CardContent>
    </Card>

  );
}