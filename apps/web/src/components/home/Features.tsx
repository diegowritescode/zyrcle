import { RecycleIcon, RefreshCw, ShieldCheck, Award, CircleDollarSign, Truck } from "lucide-react";

const features = [
    {
        title: "Transparencia en blockchain",
        description: "Cada pago queda registrado en ZyrcleChain, una L1 propia en Avalanche. La tesorería solo emite ZYR contra pesos que de verdad entraron.",
        icon: <RecycleIcon className="h-8 w-8 text-white" />,
    },
    {
        title: "Contenedores IoT firmados",
        description: "Báscula, sensor de llenado y detector de metal. Cada mensaje del contenedor va firmado: nadie puede inventarse un depósito.",
        icon: <RefreshCw className="h-8 w-8 text-white" />,
    },
    {
        title: "Verificación contra trampas",
        description: "El peso se compara con el volumen que ocupó el material. Una piedra o una botella llena de agua no pasan.",
        icon: <ShieldCheck className="h-8 w-8 text-white" />,
    },
    {
        title: "Pagos en ZYR = pesos",
        description: "Un anticipo apenas se verifica tu depósito y el resto cuando el material se vende al centro de acopio. Ves todo en pesos.",
        icon: <CircleDollarSign className="h-8 w-8 text-white" />,
    },
    {
        title: "Rutas de recolección",
        description: "Próximamente: bolsas trazables del contenedor al centro de acopio, con balance de masa en cada entrega.",
        icon: <Truck className="h-8 w-8 text-white" />,
    },
    {
        title: "Trazabilidad para reportes",
        description: "Kilos verificados por material y por residencia, públicos y auditables, listos para los reportes de aprovechamiento.",
        icon: <Award className="h-8 w-8 text-white" />,
    },
];

export function Features() {
    return (
        <section id="learn-more" className="py-20 bg-eco-forest/5">
            <div className="container mx-auto px-4">
                <div className="text-center max-w-2xl mx-auto mb-16">
                    <h2 className="text-3xl md:text-4xl font-bold text-eco-forest-dark mb-4">
                        El reciclaje, verificado de punta a punta
                    </h2>
                    <p className="text-eco-forest-dark/70">
                        Combinamos contenedores con sensores, un protocolo firmado y una blockchain propia para que cada kilo
                        reciclado sea medible, verificable y pagado.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {features.map((feature) => (
                        <div
                            key={feature.title}
                            className="bg-white rounded-xl p-6 shadow-sm border border-eco-forest/10 hover:shadow-md transition-shadow"
                        >
                            <div className="h-12 w-12 flex items-center justify-center rounded-full bg-gradient-to-br from-eco-lime to-eco-emerald mb-4">
                                {feature.icon}
                            </div>
                            <h3 className="text-xl font-semibold text-eco-forest-dark mb-2">{feature.title}</h3>
                            <p className="text-eco-forest-dark/70">{feature.description}</p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
