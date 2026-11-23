import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Collection } from "@/components/console/Collection";
import { Incidents } from "@/components/console/Incidents";
import { Login } from "@/components/console/Login";
import { Operators, Places, Prices } from "@/components/console/Places";
import { Review } from "@/components/console/Review";
import { Sales } from "@/components/console/Sales";
import { Summary } from "@/components/console/Summary";
import { useConsole } from "@/console/context";
import { ConsoleSessionProvider } from "@/console/session";

/** The operations console (docs/adr/0014): everything a pilot needs without touching the API. */
const Console = () => (
    <ConsoleSessionProvider>
        <div className="min-h-screen flex flex-col">
            <Navbar />
            <ConsoleBody />
            <Footer />
        </div>
    </ConsoleSessionProvider>
);

function ConsoleBody() {
    const { token, api, signOut } = useConsole();
    const me = useQuery({ queryKey: ["op", "me", token], queryFn: api.me, enabled: token !== null, retry: false });

    return (
        <>
            <PageHeader title="Consola de operación" place={me.data?.name} />
            <main className="flex-grow bg-gray-50">
                <div className="container mx-auto px-4 py-8">
                    {!token ? (
                        <Login />
                    ) : (
                        <Tabs defaultValue="summary">
                            <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                <div className="overflow-x-auto -mx-4 px-4">
                                    <TabsList className="bg-white p-1 shadow-sm border border-gray-100 w-max">
                                        <TabsTrigger value="summary">Resumen</TabsTrigger>
                                        <TabsTrigger value="review">Revisión</TabsTrigger>
                                        <TabsTrigger value="incidents">Incidentes</TabsTrigger>
                                        <TabsTrigger value="collection">Recolección</TabsTrigger>
                                        <TabsTrigger value="sales">Ventas</TabsTrigger>
                                        <TabsTrigger value="places">Sedes</TabsTrigger>
                                        <TabsTrigger value="prices">Precios</TabsTrigger>
                                        {me.data?.role === "admin" && <TabsTrigger value="operators">Operadores</TabsTrigger>}
                                    </TabsList>
                                </div>
                                <Button variant="ghost" size="sm" className="self-start" onClick={signOut}>
                                    <LogOut className="h-4 w-4 mr-1" /> Salir
                                </Button>
                            </div>
                            <TabsContent value="summary" className="m-0"><Summary /></TabsContent>
                            <TabsContent value="review" className="m-0"><Review /></TabsContent>
                            <TabsContent value="incidents" className="m-0"><Incidents /></TabsContent>
                            <TabsContent value="collection" className="m-0"><Collection /></TabsContent>
                            <TabsContent value="sales" className="m-0"><Sales /></TabsContent>
                            <TabsContent value="places" className="m-0"><Places /></TabsContent>
                            <TabsContent value="prices" className="m-0"><Prices /></TabsContent>
                            {me.data?.role === "admin" && <TabsContent value="operators" className="m-0"><Operators /></TabsContent>}
                        </Tabs>
                    )}
                </div>
            </main>
        </>
    );
}

export default Console;
