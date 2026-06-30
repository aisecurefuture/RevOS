"use client";

// Selected-brand context for the multi-brand dashboard. Fetches the brand list
// from /api/brands; until that endpoint exists (Module 5) it degrades to an
// empty list and an "All Brands" selection.

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { apiFetch } from "./api";
import type { Brand } from "./types";

const STORAGE_KEY = "revos.selectedBrandId";

interface BrandState {
  brands: Brand[];
  selectedBrandId: string | null; // null = all brands
  setSelectedBrandId: (id: string | null) => void;
  loading: boolean;
}

const BrandContext = createContext<BrandState | null>(null);

export function BrandProvider({ children }: { children: ReactNode }) {
  const [brands, setBrands] = useState<Brand[]>([]);
  const [selectedBrandId, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored =
      typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    if (stored) setSelected(stored);

    apiFetch<Brand[]>("/brands")
      .then((data) => setBrands(Array.isArray(data) ? data : []))
      .catch(() => setBrands([])) // endpoint not available yet -> graceful
      .finally(() => setLoading(false));
  }, []);

  const setSelectedBrandId = (id: string | null) => {
    setSelected(id);
    if (typeof window !== "undefined") {
      if (id) window.localStorage.setItem(STORAGE_KEY, id);
      else window.localStorage.removeItem(STORAGE_KEY);
    }
  };

  return (
    <BrandContext.Provider
      value={{ brands, selectedBrandId, setSelectedBrandId, loading }}
    >
      {children}
    </BrandContext.Provider>
  );
}

export function useBrand(): BrandState {
  const ctx = useContext(BrandContext);
  if (!ctx) throw new Error("useBrand must be used within a BrandProvider");
  return ctx;
}
