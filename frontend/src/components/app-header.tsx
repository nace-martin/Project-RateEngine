'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Home, FileText, Users, Database, Plus, Settings, LogOut, User, ChevronDown, Menu, Building2, Settings2 } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
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
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useState } from 'react';

type AppHeaderProps = {
  onLogActivity?: () => void;
};

export default function AppHeader({ onLogActivity }: AppHeaderProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { canEditRateCards, canEditFXRates, canEditQuotes, role, isAdmin, isFinance, isManager } = usePermissions();
  const [open, setOpen] = useState(false);
  const brandName = user?.organization?.branding?.display_name || user?.organization?.name || 'RateEngine';
  const brandLogoUrl = user?.organization?.branding?.logo_url || null;
  const productSubLabel = brandName === 'RateEngine' ? null : 'Powered by RateEngine';

  // Hide header on login page
  if (pathname === '/login') {
    return null;
  }

  // 1. Primary Navigation (Top Level)
  const navItems = [
    { href: '/', label: 'Dashboard', icon: Home },
    { href: '/quotes', label: 'Quotes', icon: FileText },
  ];

  // Customers - only for non-Finance roles
  if (!isFinance) {
    navItems.push({ href: '/customers', label: 'Customers', icon: Users });
    navItems.push({ href: '/crm', label: 'CRM', icon: FileText });
  }

  // 2. Secondary/Configuration Navigation (Dropdown)
  const moreItems: { href: string; label: string; icon: LucideIcon }[] = [];

  // Pricing Engine
  if (canEditFXRates) {
    moreItems.push({ href: '/pricing/engine', label: 'Pricing Engine', icon: Settings2 });
  }

  // Rate Management
  if (canEditRateCards) {
    moreItems.push({ href: '/pricing/rate-cards', label: 'Rate Management', icon: Database });
  }

  // Branding
  if (isAdmin) {
    moreItems.push({ href: '/company/branding', label: 'Branding', icon: Building2 });
  }

  // Admin hub
  if (isAdmin) {
    moreItems.push({ href: '/settings', label: 'Admin Hub', icon: Settings });
  }

  // User Management (Manager/Admin only)
  if (isManager || isAdmin) {
    moreItems.push({ href: '/settings/users', label: 'Users', icon: Users });
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
    <header className="w-full h-14 border-b bg-white flex items-center px-4 md:px-6 sticky top-0 z-50 gap-4">
      <div className="flex items-center gap-6 flex-1">

        {/* Mobile Menu Trigger */}
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden">
              <Menu className="h-5 w-5" />
              <span className="sr-only">Toggle menu</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[240px]">
            <SheetHeader>
              <SheetTitle>Menu</SheetTitle>
            </SheetHeader>
            <div className="flex flex-col gap-4 py-4">
              <nav className="flex flex-col gap-1">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = item.href === '/'
                    ? pathname === item.href
                    : item.href === '/crm'
                      ? pathname === item.href
                      : pathname === item.href || pathname.startsWith(`${item.href}/`);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setOpen(false)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-md transition-colors text-sm font-medium ${isActive
                        ? 'bg-primary/10 text-primary'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                        }`}
                    >
                      <Icon className="w-4 h-4" />
                      {item.label}
                    </Link>
                  )
                })}
                {(onLogActivity || moreItems.length > 0) && <div className="border-t my-2" />}
                {onLogActivity ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="mx-3 justify-start"
                    onClick={() => {
                      onLogActivity();
                      setOpen(false);
                    }}
                  >
                    Log Activity
                  </Button>
                ) : null}
                {onLogActivity && moreItems.length > 0 && <div className="border-t my-2" />}
                {moreItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setOpen(false)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-md transition-colors text-sm font-medium ${isActive
                        ? 'bg-primary/10 text-primary'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                        }`}
                    >
                      <Icon className="w-4 h-4" />
                      {item.label}
                    </Link>
                  )
                })}
              </nav>
            </div>
          </SheetContent>
        </Sheet>

        <Link href="/" className="flex items-center gap-3 text-lg font-bold text-primary mr-2">
          {brandLogoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={brandLogoUrl} alt={`${brandName} logo`} className="h-8 w-auto max-w-24 object-contain" />
          ) : (
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
          )}
          <span className="hidden sm:flex flex-col leading-tight">
            <span>{brandName}</span>
            {productSubLabel && (
              <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {productSubLabel}
              </span>
            )}
          </span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-6">
          {navItems.map((item) => {
            // Priority: Text First. Icons Removed for desktop as per "Icons optional but de-emphasized" (or kept separate but small)
            // User request: "Icons optional but de-emphasized (text-first priority)"
            // I will keep generic active logic but styling: text-muted-foreground vs text-primary
            const isActive = item.href === '/'
              ? pathname === item.href
              : item.href === '/crm'
                ? pathname === item.href
                : pathname === item.href || pathname.startsWith(`${item.href}/`);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`text-sm font-medium transition-colors ${isActive
                  ? 'text-primary font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
                  }`}
              >
                {item.label}
              </Link>
            );
          })}

          {/* More Dropdown */}
          {moreItems.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className={`flex items-center gap-1 h-auto py-0 px-0 text-sm font-medium hover:bg-transparent ${moreItems.some(i => pathname.startsWith(i.href)) ? 'text-primary font-semibold' : 'text-muted-foreground hover:text-foreground'
                  }`}>
                  More
                  <ChevronDown className="w-3 h-3 ml-0.5 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-48">
                {moreItems.map((item) => (
                  <DropdownMenuItem key={item.href} asChild>
                    <Link href={item.href} className="cursor-pointer">
                      <item.icon className="w-4 h-4 mr-2 text-slate-400" />
                      {item.label}
                    </Link>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </nav>

        {/* New Quote Action Button - Hide for Finance (they can't edit quotes) */}
        {onLogActivity ? (
          <Button
            type="button"
            variant="outline"
            onClick={onLogActivity}
            className="hidden md:flex ml-auto"
          >
            Log Activity
          </Button>
        ) : null}
        {canEditQuotes && (
          <Button
            variant="success"
            onClick={() => router.push('/quotes/new')}
            className={`hidden md:flex ${onLogActivity ? '' : 'ml-auto'}`}
          >
            <Plus className="w-4 h-4 mr-2" />
            New Quote
          </Button>
        )}
      </div>

      {user && (
        <div className="flex items-center gap-4">
          <div className="hidden sm:block">
            {getRoleBadge()}
          </div>

          {/* User Settings Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
                <User className="w-4 h-4" />
                <span className="hidden sm:inline-block">{user.username}</span>
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
                  Admin Hub
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

