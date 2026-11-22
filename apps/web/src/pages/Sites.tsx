import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { IoTDashboard, type DashboardData } from "@/components/dashboard/IoTDashboard";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { useHosts } from "@/hooks/useHosts";
import { api } from "@/lib/api";

/** A host's dashboard, across its sites or for one of them (docs/adr/0011).
 * `?host=<id>` picks the host (the first one by default) and `?site=<id>` one of its sites. */
const Sites = () => {
    const [params, setParams] = useSearchParams();
    const { data: hosts, isError: noList } = useHosts();
    const host = hosts?.find((h) => h.id === params.get("host")) ?? hosts?.[0] ?? null;
    const siteId = host?.sites.some((s) => s.id === params.get("site")) ? params.get("site") : null;

    const hostDash = useQuery({
        queryKey: ["host-dashboard", host?.id],
        queryFn: () => api.hostDashboard(host!.id),
        enabled: host !== null && siteId === null,
        refetchInterval: 10_000,
    });
    const siteDash = useQuery({
        queryKey: ["dashboard", siteId],
        queryFn: () => api.dashboard(siteId!),
        enabled: siteId !== null,
        refetchInterval: 10_000,
    });

    const pick = (site: string | null) => {
        const next = new URLSearchParams(params);
        if (host) next.set("host", host.id);
        if (site) next.set("site", site);
        else next.delete("site");
        setParams(next);
    };

    let data: DashboardData | null = null;
    if (siteId !== null && siteDash.data) {
        const d = siteDash.data;
        data = { name: `${d.site.name} · ${d.host.name}`, totals: d.totals, containers: d.containers, activity: d.activity, payouts: d.payouts };
    } else if (siteId === null && hostDash.data) {
        const d = hostDash.data;
        data = { name: d.host.name, totals: d.totals, sites: d.sites, activity: d.activity, payouts: d.payouts };
    }
    const failed = noList || (hosts && hosts.length === 0) || (siteId ? siteDash.isError : hostDash.isError);

    return (
        <div className="min-h-screen flex flex-col">
            <Navbar />
            <PageHeader title="Panel de reciclaje" place={host?.name} />
            <main className="flex-grow bg-gray-50">
                <div className="container mx-auto px-4 py-8">
                    <Tabs defaultValue="dashboard">
                        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <TabsList className="bg-white p-1 shadow-sm border border-gray-100 self-start">
                                <TabsTrigger value="dashboard">Panel</TabsTrigger>
                            </TabsList>
                            {host && host.sites.length > 1 && (
                                <div className="flex flex-wrap gap-2" role="group" aria-label="Sede">
                                    <Button size="sm" variant={siteId === null ? "default" : "outline"} onClick={() => pick(null)}>
                                        Todas las sedes
                                    </Button>
                                    {host.sites.map((s) => (
                                        <Button key={s.id} size="sm" variant={siteId === s.id ? "default" : "outline"} onClick={() => pick(s.id)}>
                                            {s.name}
                                        </Button>
                                    ))}
                                </div>
                            )}
                        </div>

                        <TabsContent value="dashboard" className="m-0">
                            {data ? (
                                <IoTDashboard data={data} onSite={pick} />
                            ) : failed ? (
                                <p className="text-center text-eco-forest/70 py-20">No pudimos cargar el panel.</p>
                            ) : (
                                <Loader2 className="h-10 w-10 mx-auto my-20 animate-spin text-eco-emerald" aria-label="Cargando" />
                            )}
                        </TabsContent>
                    </Tabs>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default Sites;
