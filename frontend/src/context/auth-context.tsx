'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface User {
  username: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (token: string, role: string, username: string) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    console.log("Auth provider useEffect running");
    const storedToken = localStorage.getItem('authToken');
    const role = localStorage.getItem('userRole');
    const username = localStorage.getItem('username');
    
    console.log("Stored Token:", storedToken);

    if (storedToken && role && username) {
      console.log("Token and user info found, setting user.");
      setUser({ username, role });
      setToken(storedToken);
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
  };

  const isAuthenticated = !!user;

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isAuthenticated }}>
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