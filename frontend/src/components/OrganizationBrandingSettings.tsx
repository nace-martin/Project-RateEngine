"use client";

import { useEffect, useState } from "react";

import { getOrganizationBrandingSettings, updateOrganizationBrandingSettings } from "@/lib/api";
import type { OrganizationBrandingSettings as BrandingSettings } from "@/lib/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type BrandingFormState = {
  display_name: string;
  legal_name: string;
  support_email: string;
  support_phone: string;
  website_url: string;
  address_lines: string;
  quote_footer_text: string;
  public_quote_tagline: string;
  email_signature_text: string;
  primary_color: string;
  accent_color: string;
  is_active: boolean;
};

const emptyForm: BrandingFormState = {
  display_name: "",
  legal_name: "",
  support_email: "",
  support_phone: "",
  website_url: "",
  address_lines: "",
  quote_footer_text: "",
  public_quote_tagline: "",
  email_signature_text: "",
  primary_color: "#0F2A56",
  accent_color: "#D71920",
  is_active: true,
};

function mapSettingsToForm(settings: BrandingSettings): BrandingFormState {
  return {
    display_name: settings.display_name || "",
    legal_name: settings.legal_name || "",
    support_email: settings.support_email || "",
    support_phone: settings.support_phone || "",
    website_url: settings.website_url || "",
    address_lines: settings.address_lines || "",
    quote_footer_text: settings.quote_footer_text || "",
    public_quote_tagline: settings.public_quote_tagline || "",
    email_signature_text: settings.email_signature_text || "",
    primary_color: settings.primary_color || "#0F2A56",
    accent_color: settings.accent_color || "#D71920",
    is_active: settings.is_active,
  };
}

export default function OrganizationBrandingSettings() {
  const [settings, setSettings] = useState<BrandingSettings | null>(null);
  const [form, setForm] = useState<BrandingFormState>(emptyForm);
  const [logoPrimaryFile, setLogoPrimaryFile] = useState<File | null>(null);
  const [logoSmallFile, setLogoSmallFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const next = await getOrganizationBrandingSettings();
        setSettings(next);
        setForm(mapSettingsToForm(next));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load branding settings.");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const updateField = (field: keyof BrandingFormState, value: string | boolean) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      const updated = await updateOrganizationBrandingSettings({
        ...form,
        logo_primary_file: logoPrimaryFile,
        logo_small_file: logoSmallFile,
      });
      setSettings(updated);
      setForm(mapSettingsToForm(updated));
      setLogoPrimaryFile(null);
      setLogoSmallFile(null);
      setSuccess("Branding updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update branding.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organization Branding</CardTitle>
        <CardDescription>
          Manage the logo and customer-facing branding used in PDFs, public quote pages, and branded quote previews.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading branding settings...</p>
        ) : (
          <>
            {settings && (
              <div className="rounded-lg border bg-slate-50 p-4 text-sm">
                <p className="font-medium text-slate-900">{settings.organization_name}</p>
                <p className="text-slate-500">Slug: {settings.organization_slug}</p>
              </div>
            )}

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {success && (
              <Alert>
                <AlertDescription>{success}</AlertDescription>
              </Alert>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="display_name">Display Name</Label>
                <Input id="display_name" value={form.display_name} onChange={(e) => updateField("display_name", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="legal_name">Legal Name</Label>
                <Input id="legal_name" value={form.legal_name} onChange={(e) => updateField("legal_name", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="support_email">Support Email</Label>
                <Input id="support_email" type="email" value={form.support_email} onChange={(e) => updateField("support_email", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="support_phone">Support Phone</Label>
                <Input id="support_phone" value={form.support_phone} onChange={(e) => updateField("support_phone", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="website_url">Website</Label>
                <Input id="website_url" value={form.website_url} onChange={(e) => updateField("website_url", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="public_quote_tagline">Public Quote Tagline</Label>
                <Input id="public_quote_tagline" value={form.public_quote_tagline} onChange={(e) => updateField("public_quote_tagline", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="primary_color">Primary Color</Label>
                <Input id="primary_color" type="color" value={form.primary_color} onChange={(e) => updateField("primary_color", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="accent_color">Accent Color</Label>
                <Input id="accent_color" type="color" value={form.accent_color} onChange={(e) => updateField("accent_color", e.target.value)} />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="logo_primary">Primary Logo</Label>
                <Input id="logo_primary" type="file" accept="image/*" onChange={(e) => setLogoPrimaryFile(e.target.files?.[0] || null)} />
                {settings?.logo_primary_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={settings.logo_primary_url} alt="Primary logo" className="h-12 w-auto rounded border bg-white p-2" />
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="logo_small">Small Logo</Label>
                <Input id="logo_small" type="file" accept="image/*" onChange={(e) => setLogoSmallFile(e.target.files?.[0] || null)} />
                {settings?.logo_small_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={settings.logo_small_url} alt="Small logo" className="h-12 w-auto rounded border bg-white p-2" />
                )}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="address_lines">Address Lines</Label>
              <Textarea id="address_lines" rows={3} value={form.address_lines} onChange={(e) => updateField("address_lines", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="quote_footer_text">Quote Footer Text</Label>
              <Textarea id="quote_footer_text" rows={3} value={form.quote_footer_text} onChange={(e) => updateField("quote_footer_text", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email_signature_text">Email Signature Text</Label>
              <Textarea id="email_signature_text" rows={4} value={form.email_signature_text} onChange={(e) => updateField("email_signature_text", e.target.value)} />
            </div>

            <div className="flex justify-end">
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : "Save Branding"}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

