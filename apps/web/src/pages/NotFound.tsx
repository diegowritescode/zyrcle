import { Link } from "react-router-dom";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { Button } from "@/components/ui/button";
import { ArrowLeftCircle, Recycle } from "lucide-react";
import { motion } from "framer-motion";

const NotFound = () => (
    <div className="min-h-screen flex flex-col">
        <Navbar />
        <main className="flex-grow flex items-center justify-center bg-eco-forest-light/10 px-4 py-16">
            <div className="bg-white shadow-md rounded-2xl p-10 text-center max-w-md flex flex-col items-center">
                <Recycle className="text-eco-forest w-12 h-12 mb-4 opacity-70" />
                <motion.h1
                    className="text-6xl font-extrabold text-eco-forest mb-4"
                    animate={{ scale: [1, 1.05, 1] }}
                    transition={{ duration: 2, repeat: Infinity, repeatType: "loop", ease: "easeInOut" }}
                >
                    404
                </motion.h1>
                <p className="text-lg text-gray-600 mb-6">Esta página se perdió en el contenedor de reciclaje.</p>
                <Button asChild variant="default" className="gap-2">
                    <Link to="/">
                        <ArrowLeftCircle className="h-5 w-5" />
                        Volver al inicio
                    </Link>
                </Button>
            </div>
        </main>
        <Footer />
    </div>
);

export default NotFound;
