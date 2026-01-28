"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";

export default function RootPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      if (user) {
        // Use window.location for robust redirection from root
        window.location.href = "/dashboard";
      } else {
        window.location.href = "/login";
      }
    }
  }, [user, loading, router]);

  if (loading) return null;
  return null; // Will redirect via window.location
}
