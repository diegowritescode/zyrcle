import { History as HistoryIcon, Recycle } from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { RecyclingAccess } from "@/components/recycling/RecyclingAccess";
import { History } from "@/components/recycling/History";
import { PrivacyBanner } from "@/components/recycling/PrivacyBanner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useHosts } from "@/hooks/useHosts";
import { useWallet } from "@/wallet/context";

const RecyclingPage = () => {
    const { data: hosts } = useHosts();
    const { token } = useWallet();

    return (
        <div className="min-h-screen flex flex-col">
            <Navbar />
            <PageHeader title="Reciclar" place={hosts?.[0]?.name} />
            <main className="flex-grow bg-gray-50">
                <div className="container mx-auto px-4 py-8">
                    <PrivacyBanner token={token} />
                    <Tabs defaultValue="access">
                        <div className="mb-6">
                            <TabsList className="bg-white p-1 shadow-sm border border-gray-100">
                                <TabsTrigger value="access" className="flex items-center">
                                    <Recycle className="h-4 w-4 mr-2" />
                                    Acceso al contenedor
                                </TabsTrigger>
                                <TabsTrigger value="history" className="flex items-center">
                                    <HistoryIcon className="h-4 w-4 mr-2" />
                                    Mis depósitos
                                </TabsTrigger>
                            </TabsList>
                        </div>

                        {/* forceMount keeps a deposit in progress alive while the resident looks at the history */}
                        <TabsContent value="access" className="m-0 data-[state=inactive]:hidden" forceMount>
                            <RecyclingAccess />
                        </TabsContent>
                        <TabsContent value="history" className="m-0">
                            <History token={token} />
                        </TabsContent>
                    </Tabs>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default RecyclingPage;
