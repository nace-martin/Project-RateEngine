'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/navigation';

interface User {
  username: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (token: string, role: string, username: string) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    console.log('AuthProvider mounted');
    try {
      const storedToken = localStorage.getItem('authToken');
      const role = localStorage.getItem('userRole');
      const username = localStorage.getItem('username');

      if (storedToken && role && username) {
        console.log('Restoring session for:', username);
        setUser({ username, role });
        setToken(storedToken);
      } else {
        console.log('No session found');
      }
    } catch (e) {
      console.error('Error in AuthProvider effect:', e);
    } finally {
      console.log('Setting loading to false');
      setLoading(false);
    }
  }, []);

  const login = (newToken: string, role: string, username: string) => {
    localStorage.setItem('authToken', newToken);
    localStorage.setItem('userRole', role);
    localStorage.setItem('username', username);
    setUser({ username, role });
    setToken(newToken);
  };

  const logout = () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('userRole');
    localStorage.removeItem('username');
    setUser(null);
    setToken(null);
    router.push('/login');
  };

  const isAuthenticated = !!user;

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, isAuthenticated }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}