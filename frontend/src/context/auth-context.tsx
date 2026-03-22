'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { getMe } from '@/lib/api/auth';
import type { User } from '@/lib/types';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (token: string, user: User) => void;
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
    const load = async () => {
      const storedToken = localStorage.getItem('authToken');
      const storedUserJson = localStorage.getItem('authUser');
      const legacyRole = localStorage.getItem('userRole');
      const legacyUsername = localStorage.getItem('username');

      if (!storedToken) {
        setLoading(false);
        return;
      }

      setToken(storedToken);

      try {
        if (storedUserJson) {
          const parsed = JSON.parse(storedUserJson) as User;
          setUser(parsed);
        } else if (legacyRole && legacyUsername) {
          setUser({ username: legacyUsername, role: legacyRole });
        }

        const refreshedUser = await getMe();
        setUser(refreshedUser);
        localStorage.setItem('authUser', JSON.stringify(refreshedUser));
        localStorage.setItem('userRole', refreshedUser.role);
        localStorage.setItem('username', refreshedUser.username);
      } catch (e) {
        console.error('Error in AuthProvider effect:', e);
        localStorage.removeItem('authToken');
        localStorage.removeItem('authUser');
        localStorage.removeItem('userRole');
        localStorage.removeItem('username');
        setUser(null);
        setToken(null);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const login = (newToken: string, nextUser: User) => {
    localStorage.setItem('authToken', newToken);
    localStorage.setItem('authUser', JSON.stringify(nextUser));
    localStorage.setItem('userRole', nextUser.role);
    localStorage.setItem('username', nextUser.username);
    setUser(nextUser);
    setToken(newToken);
  };

  const logout = () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser');
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
