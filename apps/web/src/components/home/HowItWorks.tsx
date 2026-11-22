import { ArrowRight } from "lucide-react";
import { docUrl } from "@/lib/config";
import { unsplash } from "@/lib/images";

const steps = [
    {
        number: "01",
        title: "Escanea el contenedor",
        description: "La pantalla del contenedor muestra un QR que cambia cada 30 segundos. La wallet viene integrada, así que no instalas nada; si prefieres, usa MetaMask o Core.",
        image: "photo-1615729947596-a598e5de0ab3",
    },
    {
        number: "02",
        title: "Deposita tu material",
        description: "Eliges qué vas a reciclar, la tapa se abre y la báscula te muestra el peso en vivo mientras depositas.",
        image: "photo-1482938289607-e9573fc25ebb",
    },
    {
        number: "03",
        title: "El contenedor verifica",
        description: "Al cerrar, compara peso, volumen y metal con lo que declaraste. Si algo no cuadra, una persona revisa el depósito antes de pagarlo.",
        image: "photo-1501854140801-50d01698950b",
    },
    {
        number: "04",
        title: "Recibe tus pesos",
        description: "El anticipo llega en segundos a tu wallet en ZYR. Cuando el material se vende al centro de acopio, recibes el resto de tu parte.",
        image: "photo-1506744038136-46273834b3fb",
    },
];

export function HowItWorks() {
    return (
        <section className="py-20">
            <div className="container mx-auto px-4">
                <div className="text-center max-w-2xl mx-auto mb-16">
                    <h2 className="text-3xl md:text-4xl font-bold text-eco-forest-dark mb-4">
                        Cómo funciona ZYRCLE
                    </h2>
                    <p className="text-eco-forest-dark/70">
                        Cuatro pasos entre tu botella y tus pesos, y cada uno deja rastro verificable.
                    </p>
                </div>

                <div className="space-y-20">
                    {steps.map((step, index) => (
                        <div key={step.number} className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
                            <div className={`${index % 2 === 1 ? "lg:order-2" : ""}`}>
                                <div className="flex items-baseline gap-4 mb-4">
                                    <span className="text-4xl font-bold text-eco-emerald">{step.number}</span>
                                    <div className="h-px bg-eco-emerald flex-grow"></div>
                                </div>
                                <h3 className="text-2xl md:text-3xl font-bold text-eco-forest-dark mb-4">{step.title}</h3>
                                <p className="text-eco-forest-dark/70 text-lg mb-6">{step.description}</p>
                                {index === steps.length - 1 && (
                                    <a
                                        href={docUrl("docs/architecture.md")}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="flex items-center text-eco-emerald font-medium"
                                    >
                                        Ver la arquitectura
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </a>
                                )}
                            </div>

                            <div className={`${index % 2 === 1 ? "lg:order-1" : ""}`}>
                                <div className="relative">
                                    <div className="absolute -inset-4 rounded-2xl bg-gradient-to-br from-eco-lime/20 to-eco-emerald/20 blur-lg"></div>
                                    <img
                                        src={unsplash(step.image)}
                                        alt=""
                                        loading="lazy"
                                        className="w-full h-[300px] lg:h-[400px] object-cover rounded-xl relative z-10 shadow-lg"
                                    />
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
