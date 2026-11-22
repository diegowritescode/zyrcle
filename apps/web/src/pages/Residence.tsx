import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { IoTDashboard } from "@/components/residence/IoTDashboard";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useResidences } from "@/hooks/useResidences";
import { api } from "@/lib/api";

const Residence = () => {
    const [params] = useSearchParams();
    const { data: residences, isError: noList } = useResidences();
    const residenceId = params.get("r") ?? residences?.[0]?.id ?? null;
    const { data: dashboard, isError } = useQuery({
        queryKey: ["dashboard", residenceId],
        queryFn: () => api.dashboard(residenceId as string),
        enabled: residenceId !== null,
        refetchInterval: 10_000,
    });

    return (
        <div className="min-h-screen flex flex-col">
            <Navbar />
            <PageHeader title="Panel de la residencia" residence={dashboard?.residence.name} />
            <main className="flex-grow bg-gray-50">
                <div className="container mx-auto px-4 py-8">
                    <Tabs defaultValue="dashboard">
                        <div className="mb-6">
                            <TabsList className="bg-white p-1 shadow-sm border border-gray-100">
                                <TabsTrigger value="dashboard">Panel</TabsTrigger>
                            </TabsList>
                        </div>

                        <TabsContent value="dashboard" className="m-0">
                            {dashboard ? (
                                <IoTDashboard data={dashboard} />
                            ) : isError || noList || (residences && residences.length === 0) ? (
                                <p className="text-center text-eco-forest/70 py-20">No pudimos cargar el panel de la residencia.</p>
                            ) : (
                                <Loader2 className="h-10 w-10 mx-auto my-20 animate-spin text-eco-emerald" />
                            )}
                        </TabsContent>
                    </Tabs>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default Residence;
