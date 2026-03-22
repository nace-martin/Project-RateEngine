'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/auth-context';
import { usePermissions } from '@/hooks/usePermissions';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/context/toast-context';
import {
    Users, Plus, Search, Edit2, UserX, Shield,
    Building2, RefreshCw
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface User {
    id: number;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    role: string;
    department: string | null;
    organization: string | null;
    organization_name?: string | null;
    is_active: boolean;
    date_joined: string;
    last_login: string | null;
}

interface OrganizationOption {
    id: string;
    name: string;
    slug: string;
    is_active: boolean;
}

const ROLE_OPTIONS = [
    { value: 'sales', label: 'Sales' },
    { value: 'manager', label: 'Manager' },
    { value: 'finance', label: 'Finance' },
    { value: 'admin', label: 'Admin' },
];

const DEPARTMENT_OPTIONS = [
    { value: '', label: 'None' },
    { value: 'AIR', label: 'Air Freight' },
    { value: 'SEA', label: 'Sea Freight' },
    { value: 'LAND', label: 'Land Freight' },
];

const getRoleBadgeVariant = (role: string) => {
    switch (role) {
        case 'admin': return 'destructive';
        case 'manager': return 'default';
        case 'finance': return 'secondary';
        default: return 'outline';
    }
};

export default function UsersPage() {
    const { token, user: currentUser } = useAuth();
    const { isAdmin, isManager } = usePermissions();
    const { toast } = useToast();
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [organizations, setOrganizations] = useState<OrganizationOption[]>([]);

    // Modal state
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingUser, setEditingUser] = useState<User | null>(null);
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        first_name: '',
        last_name: '',
        role: 'sales',
        department: '',
        organization: '',
        password: '',
    });
    const [formLoading, setFormLoading] = useState(false);

    const canManageUsers = isAdmin || isManager;

    const fetchUsers = useCallback(async () => {
        if (!token) return;
        setLoading(true);
        try {
            const params = new URLSearchParams();
            if (searchQuery) params.set('search', searchQuery);

            const res = await fetch(`${API_BASE}/api/auth/users/?${params}`, {
                headers: { Authorization: `Token ${token}` },
            });

            if (!res.ok) {
                if (res.status === 403) {
                    toast({ description: 'You do not have permission to manage users.', variant: 'destructive' });
                    return;
                }
                throw new Error('Failed to fetch users');
            }

            const data = await res.json();
            setUsers(data);
        } catch {
            toast({ description: 'Failed to load users', variant: 'destructive' });
        } finally {
            setLoading(false);
        }
    }, [token, searchQuery, toast]);

    const fetchOrganizations = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(`${API_BASE}/api/auth/organizations/`, {
                headers: { Authorization: `Token ${token}` },
            });
            if (!res.ok) {
                throw new Error('Failed to fetch organizations');
            }
            const data = await res.json();
            setOrganizations(data);
        } catch {
            toast({ description: 'Failed to load organizations', variant: 'destructive' });
        }
    }, [token, toast]);

    useEffect(() => {
        if (!canManageUsers) return;
        fetchUsers();
        fetchOrganizations();
    }, [canManageUsers, fetchUsers, fetchOrganizations]);

    if (!canManageUsers) {
        return (
            <div className="container mx-auto max-w-7xl px-4 py-8">
                <Card className="border-slate-200 shadow-sm">
                    <CardHeader>
                        <CardTitle>User Management</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                        You do not have access to user management.
                    </CardContent>
                </Card>
            </div>
        );
    }

    const handleOpenCreate = () => {
        setEditingUser(null);
        setFormData({
            username: '',
            email: '',
            first_name: '',
            last_name: '',
            role: 'sales',
            department: '',
            organization: currentUser?.organization?.id || '',
            password: '',
        });
        setIsModalOpen(true);
    };

    const handleOpenEdit = (user: User) => {
        setEditingUser(user);
        setFormData({
            username: user.username,
            email: user.email || '',
            first_name: user.first_name || '',
            last_name: user.last_name || '',
            role: user.role,
            department: user.department || '',
            organization: user.organization || '',
            password: '', // Don't show password
        });
        setIsModalOpen(true);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!token) return;

        setFormLoading(true);
        try {
            const url = editingUser
                ? `${API_BASE}/api/auth/users/${editingUser.id}/`
                : `${API_BASE}/api/auth/users/`;

            const method = editingUser ? 'PUT' : 'POST';

            // Don't send empty password on edit
            const payload = { ...formData };
            if (editingUser && !payload.password) {
                delete (payload as Record<string, unknown>).password;
            }
            // Convert empty department to null
            if (!payload.department) {
                (payload as Record<string, unknown>).department = null;
            }
            if (!payload.organization) {
                (payload as Record<string, unknown>).organization = null;
            }

            const res = await fetch(url, {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Token ${token}`,
                },
                body: JSON.stringify(payload),
            });

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || JSON.stringify(errorData));
            }

            toast({ description: editingUser ? 'User updated successfully' : 'User created successfully', variant: 'success' });
            setIsModalOpen(false);
            fetchUsers();
        } catch (err) {
            toast({ description: err instanceof Error ? err.message : 'Failed to save user', variant: 'destructive' });
        } finally {
            setFormLoading(false);
        }
    };

    const handleDeactivate = async (user: User) => {
        if (!token) return;
        if (!confirm(`Are you sure you want to deactivate ${user.username}?`)) return;

        try {
            const res = await fetch(`${API_BASE}/api/auth/users/${user.id}/`, {
                method: 'DELETE',
                headers: { Authorization: `Token ${token}` },
            });

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || 'Failed to deactivate user');
            }

            toast({ description: `User ${user.username} has been deactivated`, variant: 'success' });
            fetchUsers();
        } catch (err) {
            toast({ description: err instanceof Error ? err.message : 'Failed to deactivate user', variant: 'destructive' });
        }
    };

    // Check permission
    const canManage = currentUser?.role === 'admin' || currentUser?.role === 'manager';

    if (!canManage) {
        return (
            <div className="container mx-auto py-8">
                <Card className="border-destructive">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-destructive">
                            <Shield className="h-5 w-5" />
                            Access Denied
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p>You do not have permission to manage users. Please contact an administrator.</p>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="container mx-auto py-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <Users className="h-6 w-6" />
                        User Management
                    </h1>
                    <p className="text-muted-foreground">
                        Manage user accounts, roles, and department assignments.
                    </p>
                </div>
                <Button onClick={handleOpenCreate}>
                    <Plus className="h-4 w-4 mr-2" />
                    Add User
                </Button>
            </div>

            {/* Filters */}
            <Card>
                <CardContent className="pt-6">
                    <div className="flex items-center gap-4">
                        <div className="relative flex-1 max-w-sm">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                placeholder="Search users..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="pl-10"
                            />
                        </div>
                        <Button variant="outline" size="icon" onClick={fetchUsers}>
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Users Table */}
            <Card>
                <CardContent className="p-0">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>User</TableHead>
                                <TableHead>Role</TableHead>
                                <TableHead>Department</TableHead>
                                <TableHead>Organization</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Last Login</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {loading ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-center py-8">
                                        Loading users...
                                    </TableCell>
                                </TableRow>
                            ) : users.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                                        No users found
                                    </TableCell>
                                </TableRow>
                            ) : (
                                users.map((user) => (
                                    <TableRow key={user.id}>
                                        <TableCell>
                                            <div>
                                                <div className="font-medium">{user.username}</div>
                                                <div className="text-sm text-muted-foreground">
                                                    {user.first_name} {user.last_name}
                                                    {user.email && ` • ${user.email}`}
                                                </div>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant={getRoleBadgeVariant(user.role)}>
                                                {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            {user.department ? (
                                                <span className="flex items-center gap-1">
                                                    <Building2 className="h-3 w-3" />
                                                    {user.department}
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground">—</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            {user.organization_name ? user.organization_name : (
                                                <span className="text-muted-foreground">—</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant={user.is_active ? 'default' : 'secondary'}>
                                                {user.is_active ? 'Active' : 'Inactive'}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-sm text-muted-foreground">
                                            {user.last_login
                                                ? new Date(user.last_login).toLocaleDateString()
                                                : 'Never'
                                            }
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <div className="flex items-center justify-end gap-2">
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    onClick={() => handleOpenEdit(user)}
                                                >
                                                    <Edit2 className="h-4 w-4" />
                                                </Button>
                                                {user.is_active && user.username !== currentUser?.username && (
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="text-destructive hover:text-destructive"
                                                        onClick={() => handleDeactivate(user)}
                                                    >
                                                        <UserX className="h-4 w-4" />
                                                    </Button>
                                                )}
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>

            {/* Add/Edit Modal */}
            <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
                <DialogContent className="sm:max-w-[500px]">
                    <DialogHeader>
                        <DialogTitle>
                            {editingUser ? 'Edit User' : 'Create New User'}
                        </DialogTitle>
                        <DialogDescription>
                            {editingUser
                                ? 'Update user details and permissions.'
                                : 'Add a new user to the system.'
                            }
                        </DialogDescription>
                    </DialogHeader>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="username">Username *</Label>
                                <Input
                                    id="username"
                                    value={formData.username}
                                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                                    required
                                    disabled={!!editingUser}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="email">Email</Label>
                                <Input
                                    id="email"
                                    type="email"
                                    value={formData.email}
                                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="first_name">First Name</Label>
                                <Input
                                    id="first_name"
                                    value={formData.first_name}
                                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="last_name">Last Name</Label>
                                <Input
                                    id="last_name"
                                    value={formData.last_name}
                                    onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="role">Role *</Label>
                                <Select
                                    value={formData.role}
                                    onValueChange={(value) => setFormData({ ...formData, role: value })}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {ROLE_OPTIONS.map((opt) => (
                                            <SelectItem key={opt.value} value={opt.value}>
                                                {opt.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="department">Department</Label>
                                <Select
                                    value={formData.department}
                                    onValueChange={(value) => setFormData({ ...formData, department: value })}
                                >
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select department" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {DEPARTMENT_OPTIONS.map((opt) => (
                                            <SelectItem key={opt.value || 'none'} value={opt.value}>
                                                {opt.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="organization">Organization</Label>
                            <Select
                                value={formData.organization}
                                onValueChange={(value) => setFormData({ ...formData, organization: value })}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder="Select organization" />
                                </SelectTrigger>
                                <SelectContent>
                                    {organizations.map((org) => (
                                        <SelectItem key={org.id} value={org.id}>
                                            {org.name}{!org.is_active ? ' (Inactive)' : ''}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="password">
                                Password {editingUser ? '(leave blank to keep current)' : '*'}
                            </Label>
                            <Input
                                id="password"
                                type="password"
                                value={formData.password}
                                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                required={!editingUser}
                                minLength={8}
                                placeholder={editingUser ? '••••••••' : 'Min. 8 characters'}
                            />
                        </div>

                        <DialogFooter>
                            <Button type="button" variant="outline" onClick={() => setIsModalOpen(false)}>
                                Cancel
                            </Button>
                            <Button type="submit" disabled={formLoading}>
                                {formLoading ? 'Saving...' : editingUser ? 'Update User' : 'Create User'}
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>
        </div>
    );
}
