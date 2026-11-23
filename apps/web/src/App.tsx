import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import { WalletProvider } from "@/wallet/WalletProvider";
import Index from "./pages/Index";

// The landing page loads first; the rest (charts, QR scanner, QR drawing) load when visited.
const Sites = lazy(() => import("./pages/Sites"));
const Console = lazy(() => import("./pages/Console"));
const RecyclingPage = lazy(() => import("./pages/RecyclingPage"));
const ContainerScreen = lazy(() => import("./pages/ContainerScreen"));
const ComingSoon = lazy(() => import("./pages/ComingSoon"));
const NotFound = lazy(() => import("./pages/NotFound"));

const PageLoading = () => (
  <div className="min-h-screen flex items-center justify-center">
    <Loader2 className="h-10 w-10 animate-spin text-eco-emerald" aria-label="Cargando" />
  </div>
);

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 5_000 } },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <WalletProvider>
      <TooltipProvider>
        <Sonner richColors closeButton />
        <BrowserRouter>
          <Suspense fallback={<PageLoading />}>
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/sites" element={<Sites />} />
              <Route path="/console" element={<Console />} />
              {/* The mobile app links here (docs/adr/0011). */}
              <Route path="/residence" element={<Navigate to="/sites" replace />} />
              <Route path="/recycling" element={<RecyclingPage />} />
              <Route path="/container/:containerId" element={<ContainerScreen />} />
              <Route path="/collectors" element={<ComingSoon section="collectors" />} />
              <Route path="/validator" element={<Navigate to="/console" replace />} />
              <Route path="/marketplace" element={<ComingSoon section="marketplace" />} />
              <Route path="/my-certificates" element={<ComingSoon section="certificates" />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </TooltipProvider>
    </WalletProvider>
  </QueryClientProvider>
);

export default App;
