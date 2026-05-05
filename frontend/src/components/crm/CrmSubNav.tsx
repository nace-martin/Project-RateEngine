'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export function CrmSubNav() {
  const pathname = usePathname();

  const links = [
    { href: '/crm', label: 'Dashboard' },
    { href: '/crm/activities', label: 'Activities' },
    { href: '/crm/reports', label: 'Reports' },
    { href: '/crm/opportunities', label: 'Opportunities' },
    { href: '/customers', label: 'Accounts' },
  ];

  return (
    <nav className="flex items-center gap-6 border-b mb-6 pb-2 overflow-x-auto no-scrollbar">
      {links.map((link) => {
        const isActive = link.href === '/crm' 
          ? pathname === '/crm' 
          : pathname.startsWith(link.href);
        
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`text-sm font-medium transition-colors whitespace-nowrap pb-1 border-b-2 ${
              isActive
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
