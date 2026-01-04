'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Home, FileText, Users, Database, Plus, Settings, LogOut, User, ChevronDown } from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { usePermissions } from '@/hooks/usePermissions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export default function AppHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { canEditRateCards, role, isAdmin } = usePermissions();

  // Core navigation items (visible to all authenticated users)
  const navItems = [
    { href: '/', label: 'Dashboard', icon: Home },
    { href: '/quotes', label: 'Quotes', icon: FileText },
    { href: '/customers', label: 'Customers', icon: Users },
  ];

  // Conditional navigation items based on role
  if (canEditRateCards) {
    navItems.push({ href: '/rate-cards', label: 'Rate Cards', icon: Database });
  }

  // Role badge styling
  const getRoleBadge = () => {
    if (!role) return null;
    const roleConfig: Record<string, { label: string; className: string }> = {
      admin: { label: 'Admin', className: 'bg-indigo-100 text-indigo-700 border-indigo-200' },
      manager: { label: 'Manager', className: 'bg-primary/10 text-primary border-primary/20' },
      finance: { label: 'Finance', className: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
      sales: { label: 'Sales', className: 'bg-accent/10 text-accent border-accent/20' },
    };
    const config = roleConfig[role] || { label: role, className: 'bg-gray-100 text-gray-700' };
    return <Badge variant="outline" className={config.className}>{config.label}</Badge>;
  };

  return (
    <header className="w-full h-16 border-b bg-white flex items-center px-6">
      <div className="flex items-center gap-8 flex-1">
        <Link href="/" className="flex items-center gap-2 text-xl font-bold text-primary">
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
          RateEngine
        </Link>

        <nav className="flex items-center gap-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(item.href + '/');

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${isActive
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* New Quote Action Button */}
        <Button
          onClick={() => router.push('/quotes/new')}
          className="ml-4 bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
        >
          <Plus className="w-4 h-4 mr-2" />
          New Quote
        </Button>
      </div>

      {user && (
        <div className="flex items-center gap-4">
          {getRoleBadge()}

          {/* User Settings Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
                <User className="w-4 h-4" />
                {user.username}
                <ChevronDown className="w-3 h-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel>My Account</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => router.push('/settings/profile')} className="cursor-pointer">
                <User className="w-4 h-4 mr-2" />
                Profile
              </DropdownMenuItem>
              {isAdmin && (
                <DropdownMenuItem onClick={() => router.push('/settings')} className="cursor-pointer">
                  <Settings className="w-4 h-4 mr-2" />
                  Settings
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout} className="cursor-pointer text-destructive focus:text-destructive">
                <LogOut className="w-4 h-4 mr-2" />
                Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </header>
  );
}

