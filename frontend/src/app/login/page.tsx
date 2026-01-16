'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter
} from '@/components/ui/card';
import { useAuth } from '@/context/auth-context';
import { useToast } from '@/context/toast-context';
import { login as apiLogin } from '@/lib/api';
import { Mail, Lock, Eye, EyeOff, Box } from 'lucide-react';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login } = useAuth();
  const { toast } = useToast();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const { token, user } = await apiLogin({ username, password });
      const resolvedRole = user?.role ?? 'sales';
      const resolvedUsername = user?.username ?? username;
      login(token, resolvedRole, resolvedUsername);

      toast({
        title: "Welcome back!",
        description: "You have successfully signed in.",
        variant: "success",
      });

      router.push('/dashboard');
    } catch (err: unknown) {
      console.error('Login failed:', err);
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'An error occurred during login';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 p-4 font-sans text-gray-600">
      <Card className="w-full max-w-[440px] shadow-xl border-gray-100 bg-white">
        {/* ... existing header ... */}
        <CardHeader className="space-y-6 pt-12 pb-8 text-center">
          <div className="flex justify-center items-center gap-2 mb-2">
            <div className="bg-blue-50 p-2 rounded-lg">
              <Box className="w-6 h-6 text-blue-600" />
            </div>
            <span className="text-xl font-bold text-gray-900 tracking-tight">RateEngine</span>
          </div>
          <div className="space-y-2">
            <CardTitle className="text-2xl font-bold tracking-tight text-gray-900">
              Welcome back
            </CardTitle>
            <CardDescription className="text-gray-500 text-sm">
              Log in to access your quoting control center.
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username" className="text-sm font-medium text-gray-700">
                  Email address
                </Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                  <Input
                    id="username"
                    name="username"
                    type="text"
                    placeholder="sales@rateengine.com"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="pl-10 h-11 bg-white border-gray-200 focus-visible:ring-blue-500 focus-visible:border-blue-500 rounded-lg transition-colors"
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-sm font-medium text-gray-700">
                  Password
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                  <Input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-10 pr-10 h-11 bg-white border-gray-200 focus-visible:ring-blue-500 focus-visible:border-blue-500 rounded-lg transition-colors font-mono tracking-widest text-sm"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600 focus:outline-none"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="remember"
                  checked={rememberMe}
                  onCheckedChange={(checked) => setRememberMe(checked as boolean)}
                  className="bg-white border-gray-300 data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600 text-white rounded"
                />
                <Label htmlFor="remember" className="text-sm text-gray-600 font-normal cursor-pointer">
                  Remember me
                </Label>
              </div>
              <Link
                href="mailto:support@rateengine.com?subject=Password Reset Request"
                className="text-sm font-medium text-blue-600 hover:text-blue-500"
              >
                Forgot password?
              </Link>
            </div>

            {error && (
              <div className="p-3 text-sm text-red-600 bg-red-50 rounded-lg text-center" role="alert">
                {error}
              </div>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-sm hover:shadow transition-all duration-200"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>

          <div className="mt-8 relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-gray-100" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white px-3 text-gray-500">Need help?</span>
            </div>
          </div>

          <div className="mt-6 text-center text-sm">
            <p className="text-gray-500 mb-1">Contact your administrator to create an account.</p>
            <Link href="mailto:support@rateengine.com" className="font-medium text-gray-900 hover:text-gray-700 text-xs font-semibold">
              Support Center
            </Link>
          </div>
        </CardContent>
      </Card>

      <div className="mt-8 flex w-full max-w-[440px] items-center justify-between text-xs text-gray-400 px-2">
        <span>© 2024 RateEngine. All rights reserved.</span>
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2">
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-400"></span>
          </span>
          <span>System Normal</span>
        </div>
      </div>

    </div>
  );
}
