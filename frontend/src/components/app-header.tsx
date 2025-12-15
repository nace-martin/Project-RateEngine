'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, FileText, Users, Database } from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { usePermissions } from '@/hooks/usePermissions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export default function AppHeader() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { canEditRateCards, role } = usePermissions();

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
      admin: { label: 'Admin', className: 'bg-purple-100 text-purple-700 border-purple-200' },
      manager: { label: 'Manager', className: 'bg-blue-100 text-blue-700 border-blue-200' },
      finance: { label: 'Finance', className: 'bg-green-100 text-green-700 border-green-200' },
      sales: { label: 'Sales', className: 'bg-orange-100 text-orange-700 border-orange-200' },
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
      </div>

      {user && (
        <div className="flex items-center gap-4">
          {getRoleBadge()}
          <span className="text-sm text-muted-foreground">{user.username}</span>
          <Button variant="outline" size="sm" onClick={logout}>
            Logout
          </Button>
        </div>
      )}
    </header>
  );
}
