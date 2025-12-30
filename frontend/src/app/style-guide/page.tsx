"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";

export default function StyleGuidePage() {
    return (
        <div className="max-w-5xl mx-auto space-y-12 py-10">
            <div>
                <h1 className="text-4xl font-bold tracking-tight text-primary">Design System & Style Guide</h1>
                <p className="text-lg text-muted-foreground mt-2">
                    Core visual elements and components for the EFM RateEngine.
                </p>
            </div>

            <Separator />

            <section className="space-y-6">
                <h2 className="text-2xl font-semibold">Color Palette</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    <ColorCard name="Primary (EFM Blue)" variable="--primary" hex="#1E40AF" className="bg-primary text-primary-foreground" />
                    <ColorCard name="Accent (EFM Orange)" variable="--accent" hex="#F97316" className="bg-accent text-accent-foreground" />
                    <ColorCard name="Secondary (Slate)" variable="--secondary" hex="#F1F5F9" className="bg-secondary text-secondary-foreground border" />
                    <ColorCard name="Muted" variable="--muted" hex="#F1F5F9" className="bg-muted text-muted-foreground border" />
                    <ColorCard name="Success" variable="--success" hex="#16A34A" className="bg-[hsl(var(--success))] text-white" />
                    <ColorCard name="Warning" variable="--warning" hex="#F59E0B" className="bg-[hsl(var(--warning))] text-white" />
                    <ColorCard name="Destructive" variable="--destructive" hex="#DC2626" className="bg-destructive text-destructive-foreground" />
                    <ColorCard name="Background" variable="--background" hex="#F8FAFC" className="bg-background text-foreground border" />
                </div>
            </section>

            <Separator />

            <section className="space-y-6">
                <h2 className="text-2xl font-semibold">Typography (Inter)</h2>
                <Card>
                    <CardContent className="pt-6 space-y-8">
                        <div className="space-y-2">
                            <span className="text-xs font-mono text-muted-foreground uppercase tracking-widest">Display / H1</span>
                            <h1 className="text-4xl font-extrabold tracking-tight">The quick brown fox jumps over the lazy dog</h1>
                        </div>
                        <div className="space-y-2">
                            <span className="text-xs font-mono text-muted-foreground uppercase tracking-widest">Header / H2</span>
                            <h2 className="text-3xl font-bold tracking-tight">The quick brown fox jumps over the lazy dog</h2>
                        </div>
                        <div className="space-y-2">
                            <span className="text-xs font-mono text-muted-foreground uppercase tracking-widest">Subhead / H3</span>
                            <h3 className="text-2xl font-semibold tracking-tight">The quick brown fox jumps over the lazy dog</h3>
                        </div>
                        <div className="space-y-2">
                            <span className="text-xs font-mono text-muted-foreground uppercase tracking-widest">Body / Regular</span>
                            <p className="text-base leading-7">
                                RateEngine is a mission-critical tool for air freight logistics. It requires high precision,
                                clarity, and speed. Typography plays a vital role in ensuring that complex pricing data
                                is readable and actionable at a glance.
                            </p>
                        </div>
                        <div className="space-y-2">
                            <span className="text-xs font-mono text-muted-foreground uppercase tracking-widest">Small / Caption</span>
                            <p className="text-sm text-muted-foreground leading-none">
                                Valid until 31 Dec 2024 • Created by Admin
                            </p>
                        </div>
                    </CardContent>
                </Card>
            </section>

            <Separator />

            <section className="space-y-6">
                <h2 className="text-2xl font-semibold">Common Components</h2>
                <Tabs defaultValue="buttons" className="w-full">
                    <TabsList className="grid w-full grid-cols-3 lg:w-[400px]">
                        <TabsTrigger value="buttons">Buttons</TabsTrigger>
                        <TabsTrigger value="inputs">Inputs</TabsTrigger>
                        <TabsTrigger value="cards">Cards</TabsTrigger>
                    </TabsList>

                    <TabsContent value="buttons" className="space-y-8 py-6">
                        <div className="flex flex-wrap gap-4 items-center">
                            <Button>Primary Action</Button>
                            <Button variant="secondary">Secondary Action</Button>
                            <Button variant="outline">Outline Button</Button>
                            <Button variant="ghost">Ghost Button</Button>
                            <Button variant="destructive">Destructive Action</Button>
                        </div>
                        <div className="flex flex-wrap gap-4 items-center">
                            <Button size="sm">Small</Button>
                            <Button>Default Size</Button>
                            <Button size="lg">Large Scale</Button>
                        </div>
                    </TabsContent>

                    <TabsContent value="inputs" className="space-y-6 py-6 max-w-sm">
                        <div className="space-y-2">
                            <Label htmlFor="email">Email Address</Label>
                            <Input id="email" type="email" placeholder="example@rateengine.ai" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="search">Search Cargo</Label>
                            <Input id="search" placeholder="Enter keywords..." />
                            <p className="text-xs text-muted-foreground">Press enter to search the database.</p>
                        </div>
                    </TabsContent>

                    <TabsContent value="cards" className="py-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Shipment Overview</CardTitle>
                                    <CardDescription>Consolidated details for POM -&gt; HKG</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-muted-foreground">Weight:</span>
                                        <span className="font-medium">100.00 kg</span>
                                    </div>
                                    <div className="flex justify-between text-sm">
                                        <span className="text-muted-foreground">Volume:</span>
                                        <span className="font-medium">0.50 cbm</span>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="border-accent/20 bg-accent/5">
                                <CardHeader>
                                    <CardTitle className="text-accent">Special Promotion</CardTitle>
                                    <CardDescription>New year export discounts applied</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-sm font-medium">Enjoy 15% discount on all terminal handling charges.</p>
                                </CardContent>
                            </Card>
                        </div>
                    </TabsContent>
                </Tabs>
            </section>
        </div>
    );
}

function ColorCard({ name, variable, hex, className }: { name: string; variable: string; hex: string; className?: string }) {
    return (
        <Card className="overflow-hidden">
            <div className={`h-24 ${className}`} />
            <CardContent className="p-4 space-y-1">
                <p className="font-semibold text-sm">{name}</p>
                <div className="flex justify-between items-center text-xs font-mono text-muted-foreground">
                    <span>{variable}</span>
                    <span>{hex}</span>
                </div>
            </CardContent>
        </Card>
    );
}
