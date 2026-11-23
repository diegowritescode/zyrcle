import { Link } from "react-router-dom";
import { BookOpen, ChevronUp, Coins, Github, Landmark, Network } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CHAIN_ID, REPO_URL, TREASURY_ADDRESS, docUrl } from "@/lib/config";
import { shortHex } from "@zyrcle/client";

const PLATFORM = [
    { to: "/recycling", label: "Reciclar" },
    { to: "/sites", label: "Sedes" },
    { to: "/collectors", label: "Recolectores" },
];

const RESOURCES = [
    { href: docUrl("docs/architecture.md"), label: "Arquitectura" },
    { href: docUrl("docs/device-protocol.md"), label: "Protocolo del contenedor" },
    { href: `${REPO_URL}/tree/main/docs/adr`, label: "Decisiones técnicas" },
    { href: REPO_URL, label: "Código fuente" },
];

const bullet = <span className="inline-block w-3 h-0.5 bg-eco-emerald/30 rounded-full mr-2"></span>;

function Heading({ children }: { children: string }) {
    return (
        <h3 className="font-semibold text-lg mb-6 flex items-center space-x-2 text-eco-forest">
            <span className="inline-block w-8 h-0.5 bg-eco-emerald rounded-full mr-2"></span>
            {children}
        </h3>
    );
}

export function Footer() {
    return (
        <footer className="bg-emerald-50 text-eco-forest border-t border-eco-emerald/20">
            {/* Top button */}
            <div className="container mx-auto relative">
                <Button
                    onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
                    variant="outline"
                    size="icon"
                    aria-label="Volver arriba"
                    className="absolute -top-5 right-4 md:right-10 bg-eco-emerald text-white border-eco-emerald hover:bg-eco-emerald/90 hover:text-white rounded-full shadow-lg z-10"
                >
                    <ChevronUp className="h-5 w-5" />
                </Button>
            </div>

            {/* Main content */}
            <div className="container mx-auto px-4 py-16 shadow-sm">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-10">
                    <div className="space-y-5">
                        <div className="flex items-center space-x-2">
                            <img src="/favicon.svg" alt="Zyrcle" className="h-12 w-12" />
                            <span className="text-xl font-bold text-eco-forest">ZYRCLE</span>
                        </div>
                        <p className="text-eco-forest/80 max-w-xs leading-relaxed">
                            Reciclaje trazable con contenedores IoT y una blockchain propia en Avalanche: cada kilo verificado,
                            cada peso pagado a la vista.
                        </p>
                        <div className="flex space-x-3 pt-2">
                            <a
                                href={REPO_URL}
                                target="_blank"
                                rel="noreferrer"
                                aria-label="Código en GitHub"
                                className="flex h-9 w-9 items-center justify-center rounded-full bg-eco-emerald/20 hover:bg-eco-emerald/30 transition-all duration-300"
                            >
                                <Github size={18} className="text-eco-forest" />
                            </a>
                            <a
                                href={docUrl("docs/architecture.md")}
                                target="_blank"
                                rel="noreferrer"
                                aria-label="Documentación"
                                className="flex h-9 w-9 items-center justify-center rounded-full bg-eco-emerald/20 hover:bg-eco-emerald/30 transition-all duration-300"
                            >
                                <BookOpen size={18} className="text-eco-forest" />
                            </a>
                        </div>
                    </div>

                    <div className="md:ml-8">
                        <Heading>Plataforma</Heading>
                        <ul className="space-y-4">
                            {PLATFORM.map((link) => (
                                <li key={link.to}>
                                    <Link to={link.to} className="text-eco-forest/80 hover:text-eco-emerald transition-colors flex items-center rounded-md">
                                        {bullet}
                                        {link.label}
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    </div>

                    <div>
                        <Heading>Recursos</Heading>
                        <ul className="space-y-4">
                            {RESOURCES.map((link) => (
                                <li key={link.href}>
                                    <a
                                        href={link.href}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-eco-forest/80 hover:text-eco-emerald transition-colors flex items-center rounded-md"
                                    >
                                        {bullet}
                                        {link.label}
                                    </a>
                                </li>
                            ))}
                        </ul>
                    </div>

                    <div className="md:ml-4">
                        <Heading>Red</Heading>
                        <ul className="space-y-4">
                            <li className="flex items-start space-x-3">
                                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-eco-emerald/20">
                                    <Network className="h-4 w-4 text-eco-forest" />
                                </div>
                                <span className="text-eco-forest/80">ZyrcleChain · Chain ID {CHAIN_ID}</span>
                            </li>
                            <li className="flex items-start space-x-3">
                                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-eco-emerald/20">
                                    <Coins className="h-4 w-4 text-eco-forest" />
                                </div>
                                <span className="text-eco-forest/80">ZYR · 1 ZYR = 1 peso</span>
                            </li>
                            <li className="flex items-start space-x-3">
                                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-eco-emerald/20">
                                    <Landmark className="h-4 w-4 text-eco-forest" />
                                </div>
                                <span className="text-eco-forest/80">
                                    Tesorería <code title={TREASURY_ADDRESS}>{shortHex(TREASURY_ADDRESS)}</code>
                                </span>
                            </li>
                        </ul>
                    </div>
                </div>

                {/* Bottom section */}
                <div className="pt-8 mt-8 border-t border-eco-emerald/20">
                    <div className="flex flex-col md:flex-row justify-between items-center gap-4 text-eco-forest/60">
                        <p>
                            © {new Date().getFullYear()} ZYRCLE. Código público en GitHub.{" "}
                            <Link to="/privacidad" className="underline hover:text-eco-forest">Tratamiento de datos</Link>
                            {" · "}
                            <Link to="/terminos" className="underline hover:text-eco-forest">Términos</Link>
                        </p>
                        <p className="text-sm text-center md:text-right">
                            Testnet de Avalanche Fuji: ZYR no tiene valor real y los contenedores de la demo son simulados.
                        </p>
                    </div>
                </div>
            </div>
        </footer>
    );
}
