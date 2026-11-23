import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { PRIVACY, PRIVACY_VERSION, TERMS, type Section } from "@/content/privacy";

/** The data-processing policy or the terms of use, both drafts for legal review (ADR 0028). */
const Legal = ({ kind }: { kind: "privacy" | "terms" }) => {
    const sections: Section[] = kind === "privacy" ? PRIVACY : TERMS;
    const title = kind === "privacy" ? "Política de tratamiento de datos" : "Términos de uso";
    return (
        <div className="min-h-screen flex flex-col">
            <Navbar />
            <PageHeader title={title} />
            <main className="flex-grow bg-gray-50">
                <div className="container mx-auto px-4 py-8 max-w-3xl">
                    <Card className="shadow-sm border-0 rounded-xl bg-white">
                        <CardContent className="p-6 space-y-6">
                            <p className="text-sm rounded-lg bg-amber-50 text-amber-900 p-3">
                                Borrador pendiente de revisión legal (versión {PRIVACY_VERSION}).
                            </p>
                            {sections.map((s) => (
                                <section key={s.title} className="space-y-2">
                                    <h2 className="text-lg font-semibold text-eco-forest">{s.title}</h2>
                                    {s.paragraphs.map((p) => (
                                        <p key={p} className="text-eco-forest/80 leading-relaxed">{p}</p>
                                    ))}
                                </section>
                            ))}
                        </CardContent>
                    </Card>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default Legal;
