import { Link } from "react-router-dom";
import { Award, ArrowRight, Landmark, ShoppingBag, Truck } from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { docUrl } from "@/lib/config";

const SECTIONS = {
    collectors: {
        title: "Recolectores",
        icon: Truck,
        heading: "Rutas de recolección trazables",
        intro: "El recolector abre el contenedor con su propia firma, retira la bolsa y la lleva al centro de acopio.",
        points: [
            "Cada bolsa lleva un código y se pesa al salir del contenedor y al llegar al acopio.",
            "El balance de masa compara los kilos verificados con los que de verdad llegaron.",
            "Rutas sugeridas según qué tan llenos están los contenedores.",
        ],
    },
    validator: {
        title: "Validadores",
        icon: Landmark,
        heading: "Venta al centro de acopio y liquidación",
        intro: "Cuando el centro de acopio paga por una bolsa, esos pesos entran a la tesorería y respaldan los ZYR.",
        points: [
            "El tiquete de venta y el pago bancario se concilian antes de registrar la venta en la cadena.",
            "La tesorería reparte la venta: residentes, recolector y operación.",
            "Cada residente recibe su parte menos el anticipo que ya cobró.",
        ],
    },
    marketplace: {
        title: "Marketplace",
        icon: ShoppingBag,
        heading: "Gastar tus ZYR cerca de casa",
        intro: "Mientras no exista la rampa a pesos, los ZYR circulan dentro del conjunto.",
        points: [
            "Tiendas aliadas que reciben ZYR al mismo valor del peso.",
            "Después, una rampa para pasar de ZYR a pesos en tu cuenta.",
        ],
    },
    certificates: {
        title: "Mis certificados",
        icon: Award,
        heading: "Certificados de aprovechamiento",
        intro: "La trazabilidad de cada kilo permite certificar lo que un conjunto o una empresa aprovechó.",
        points: [
            "Kilos por material, residencia y periodo, con las evidencias ancladas en la cadena.",
            "Pensado para los reportes de aprovechamiento y de responsabilidad extendida del productor.",
        ],
    },
} as const;

export type Section = keyof typeof SECTIONS;

/** Sections of the hackathon app whose new version comes after the deposit cycle (phase 4+). */
const ComingSoon = ({ section }: { section: Section }) => {
    const s = SECTIONS[section];
    const Icon = s.icon;
    return (
        <div className="min-h-screen flex flex-col">
            <Navbar />
            <PageHeader title={s.title} />
            <main className="flex-grow bg-gray-50">
                <div className="container mx-auto px-4 py-12">
                    <div className="max-w-2xl mx-auto bg-white rounded-2xl shadow-sm border border-eco-forest/10 p-8 md:p-10 space-y-6">
                        <div className="flex items-center gap-4">
                            <div className="h-14 w-14 flex items-center justify-center rounded-full bg-gradient-to-br from-eco-lime to-eco-emerald shrink-0">
                                <Icon className="h-7 w-7 text-white" />
                            </div>
                            <div>
                                <span className="inline-block px-3 py-1 rounded-full bg-eco-lime/20 text-eco-forest-dark text-xs font-semibold mb-1">
                                    Próximamente
                                </span>
                                <h2 className="text-2xl md:text-3xl font-bold text-eco-forest-dark">{s.heading}</h2>
                            </div>
                        </div>
                        <p className="text-eco-forest-dark/80 text-lg">{s.intro}</p>
                        <ul className="space-y-3">
                            {s.points.map((p) => (
                                <li key={p} className="flex items-start text-eco-forest-dark/70">
                                    <span className="inline-block w-3 h-0.5 bg-eco-emerald rounded-full mr-3 mt-3 shrink-0"></span>
                                    {p}
                                </li>
                            ))}
                        </ul>
                        <div className="flex flex-col sm:flex-row gap-4 pt-2">
                            <Button asChild className="bg-eco-emerald text-white hover:bg-eco-emerald/90 rounded-full px-6">
                                <Link to="/recycling">
                                    Probar el ciclo de depósito
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            <Button asChild variant="outline" className="border-eco-forest text-eco-forest hover:bg-eco-forest/5 rounded-full px-6">
                                <a href={docUrl("docs/architecture.md")} target="_blank" rel="noreferrer">
                                    Leer la arquitectura
                                </a>
                            </Button>
                        </div>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default ComingSoon;
