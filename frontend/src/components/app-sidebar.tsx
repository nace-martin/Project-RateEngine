'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/auth-context';
import {
    LayoutDashboard,
    FileText,
    Users,
    Settings,
    LogOut,
    Plane,
    ChevronLeft
} from 'lucide-react';
import { useState } from 'react';

export function AppSidebar() {
    const pathname = usePathname();
    const { user, logout } = useAuth();
    const [collapsed, setCollapsed] = useState(false);

    const routes = [
        {
            label: 'Dashboard',
            icon: LayoutDashboard,
            href: '/',
            color: 'text-sky-500',
        },
        {
            label: 'Quotes',
            icon: FileText,
            href: '/quotes',
            color: 'text-violet-500',
        },
        {
            label: 'Customers',
            icon: Users,
            href: '/customers',
            color: 'text-pink-700',
        },
        {
            label: 'Settings',
            icon: Settings,
            href: '/settings',
            color: 'text-gray-500',
            role: ['manager', 'finance']
        },
    ];

    return (
        <div className={cn(
            "relative flex flex-col h-full bg-sidebar border-r border-sidebar-border transition-all duration-300",
            collapsed ? "w-[80px]" : "w-72"
        )}>
            <div className="px-3 py-4 flex items-center">
                <Link href="/" className="flex items-center pl-3 mb-14">
                    <div className="relative w-8 h-8 mr-4">
                        <Plane className="w-8 h-8 text-primary" />
                    </div>
                    {!collapsed && (
                        <h1 className="text-2xl font-bold bg-gradient-to-r from-primary to-blue-600 bg-clip-text text-transparent">
                            RateEngine
                        </h1>
                    )}
                </Link>
                <Button
                    variant="ghost"
                    size="icon"
                    className="absolute right-[-12px] top-8 h-6 w-6 rounded-full border bg-background shadow-md z-50"
                    onClick={() => setCollapsed(!collapsed)}
                >
                    <ChevronLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
                </Button>
            </div>

            <div className="space-y-1 px-3 flex-1">
                {routes.map((route) => {
                    if (route.role && (!user || !route.role.includes(user.role))) return null;

                    return (
                        <Link
                            key={route.href}
                            href={route.href}
                            className={cn(
                                "text-sm group flex p-3 w-full justify-start font-medium cursor-pointer hover:text-primary hover:bg-primary/10 rounded-lg transition",
                                pathname === route.href ? "bg-primary/10 text-primary" : "text-muted-foreground",
                                collapsed && "justify-center"
                            )}
                        >
                            <div className="flex items-center flex-1">
                                <route.icon className={cn("h-5 w-5 mr-3", route.color)} />
                                {!collapsed && route.label}
                            </div>
                        </Link>
                    );
                })}
            </div>

            <div className="px-3 py-4 mt-auto border-t">
                <div className={cn("flex items-center gap-x-4", collapsed && "justify-center")}>
                    {!collapsed && (
                        <div className="flex flex-col">
                            <p className="text-sm font-medium text-foreground">{user?.username}</p>
                            <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
                        </div>
                    )}
                    <Button variant="ghost" size="icon" onClick={logout} title="Logout">
                        <LogOut className="h-5 w-5 text-muted-foreground hover:text-destructive" />
                    </Button>
                </div>
            </div>
        </div>
    );
}
