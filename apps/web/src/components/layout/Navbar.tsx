import { useState } from "react";
import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { WalletMenu } from "@/components/wallet/WalletMenu";

const GROUPS = [
    {
        key: "residents",
        label: "Residentes",
        heading: "Para residentes",
        links: [
            { to: "/recycling", label: "Reciclar" },
            { to: "/sites", label: "Sedes" },
            { to: "/marketplace", label: "Marketplace" },
        ],
    },
    {
        key: "collectors",
        label: "Recolectores",
        heading: "Para recolectores",
        links: [{ to: "/collectors", label: "Rutas de recolección" }],
    },
    {
        key: "validators",
        label: "Validadores",
        heading: "Para validadores",
        links: [{ to: "/validator", label: "Ventas y liquidación" }],
    },
];

export function Navbar() {
    const [isMenuOpen, setIsMenuOpen] = useState(false);

    return (
        <nav className="sticky top-0 z-50 w-full bg-white/95 backdrop-blur-md border-b border-eco-emerald/20">
            <div className="container mx-auto px-4 py-3">
                <div className="flex items-center justify-between">
                    {/* Logo */}
                    <Link to="/" className="flex items-center space-x-2 transition-transform hover:scale-110">
                        <img src="/favicon.svg" alt="Zyrcle" className="h-10 w-10" />
                        <span className="text-xl font-bold text-eco-forest">ZYRCLE</span>
                    </Link>

                    {/* Desktop Navigation */}
                    <div className="hidden md:flex items-center space-x-4">
                        <Link to="/" className="text-eco-forest hover:text-eco-emerald/80 font-medium px-3 py-2 rounded-md transition-colors">
                            Inicio
                        </Link>
                        {GROUPS.map((group) => (
                            <DropdownMenu key={group.key}>
                                <DropdownMenuTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        className="text-eco-forest hover:text-white font-medium px-3 py-2 rounded-md"
                                    >
                                        {group.label}
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent className="bg-white rounded-xl shadow-sm border-eco-emerald/20">
                                    <DropdownMenuLabel className="text-eco-forest">{group.heading}</DropdownMenuLabel>
                                    <DropdownMenuSeparator />
                                    {group.links.map((link) => (
                                        <DropdownMenuItem asChild key={link.to}>
                                            <Link to={link.to} className="text-eco-forest hover:bg-eco-emerald/5">
                                                {link.label}
                                            </Link>
                                        </DropdownMenuItem>
                                    ))}
                                </DropdownMenuContent>
                            </DropdownMenu>
                        ))}
                        <Link to="/my-certificates" className="text-eco-forest hover:bg-eco-emerald/5">
                            Mis certificados
                        </Link>
                        <WalletMenu />
                    </div>

                    {/* Mobile Menu Button */}
                    <div className="md:hidden flex items-center space-x-3">
                        <WalletMenu compact />
                        <button
                            onClick={() => setIsMenuOpen(!isMenuOpen)}
                            className="p-2 rounded-md text-eco-forest"
                            aria-label={isMenuOpen ? "Cerrar menú" : "Abrir menú"}
                            aria-expanded={isMenuOpen}
                        >
                            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-eco-emerald">
                                {isMenuOpen ? <X size={16} className="text-white" /> : <Menu size={16} className="text-white" />}
                            </div>
                        </button>
                    </div>
                </div>

                {/* Mobile Menu */}
                {isMenuOpen && (
                    <div className="md:hidden pt-3 pb-4">
                        <Accordion type="single" collapsible className="space-y-2">
                            <Link to="/" className="block px-3 py-2 rounded-md hover:bg-eco-emerald/5 text-eco-forest">
                                Inicio
                            </Link>
                            {GROUPS.map((group) => (
                                <AccordionItem value={group.key} key={group.key}>
                                    <AccordionTrigger className="px-3 py-2 text-eco-forest hover:bg-eco-emerald/5">
                                        {group.label}
                                    </AccordionTrigger>
                                    <AccordionContent className="pl-6 space-y-2">
                                        {group.links.map((link) => (
                                            <Link
                                                key={link.to}
                                                to={link.to}
                                                className="block px-3 py-2 rounded-md hover:bg-eco-emerald/5 text-eco-forest"
                                            >
                                                {link.label}
                                            </Link>
                                        ))}
                                    </AccordionContent>
                                </AccordionItem>
                            ))}
                            <Link to="/my-certificates" className="block px-3 py-2 rounded-md hover:bg-eco-emerald/5 text-eco-forest">
                                Mis certificados
                            </Link>
                        </Accordion>
                    </div>
                )}
            </div>
        </nav>
    );
}
