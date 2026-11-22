import { Link } from "react-router-dom";
import { ArrowLeft, HomeIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

/** The hackathon's strip under the navbar: back, page title and the residence pill. */
export function PageHeader({ title, residence }: { title: string; residence?: string | null }) {
    return (
        <div className="bg-eco-forest-light/10 py-4 px-4 md:px-6">
            <div className="container mx-auto">
                <div className="flex justify-between items-center gap-4">
                    <div className="flex items-center space-x-4">
                        <Button variant="ghost" asChild>
                            <Link to="/" className="flex items-center">
                                <ArrowLeft className="h-4 w-4 mr-2" />
                                Volver
                            </Link>
                        </Button>
                        <h1 className="text-xl font-semibold">{title}</h1>
                    </div>
                    {residence && (
                        <div className="hidden sm:flex items-center gap-2">
                            <div className="flex items-center bg-white px-4 py-2 rounded-full shadow-sm">
                                <HomeIcon className="h-4 w-4 text-eco-forest mr-2" />
                                <span className="text-sm font-medium">{residence}</span>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
