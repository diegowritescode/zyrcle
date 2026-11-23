import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MATERIALS, hourLabel, pesos } from "@zyrcle/client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { HostRow, OperatorAccount, SiteRow } from "@/console/api";
import { useConsole } from "@/console/context";
import { Empty, Loading, Section } from "./shared";
import { failed } from "@/console/format";

const KIND: Record<HostRow["kind"], string> = {
    university: "Universidad",
    residential: "Conjunto residencial",
    business: "Empresa",
    public: "Entidad pública",
};

/** Hosts (with where their share is paid) and their sites (docs/adr/0011, 0013). */
export function Places() {
    return (
        <div className="space-y-6">
            <Hosts />
            <Sites />
        </div>
    );
}

function Hosts() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const list = useQuery({ queryKey: ["op", "hosts"], queryFn: api.hosts });
    const [name, setName] = useState("");
    const [kind, setKind] = useState<HostRow["kind"]>("university");

    const create = async () => {
        try {
            await api.createHost(name.trim(), kind);
            setName("");
            await queryClient.invalidateQueries({ queryKey: ["op", "hosts"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <Section title="Anfitriones" description="La institución que presta sus sedes. Su parte de cada venta se paga a su dirección">
            <form
                className="flex flex-wrap items-end gap-2 mb-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    if (name.trim()) create();
                }}
            >
                <div className="space-y-1">
                    <Label htmlFor="host-name">Nombre</Label>
                    <Input id="host-name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label>Tipo</Label>
                    <Select value={kind} onValueChange={(v) => setKind(v as HostRow["kind"])}>
                        <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {Object.entries(KIND).map(([k, label]) => (
                                <SelectItem key={k} value={k}>{label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <Button type="submit" disabled={!name.trim()}>Agregar anfitrión</Button>
            </form>
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>No hay anfitriones.</Empty> : (
                <div className="space-y-3">
                    {list.data.map((h) => (
                        <HostRowEditor key={h.id} host={h} />
                    ))}
                </div>
            )}
        </Section>
    );
}

function HostRowEditor({ host }: { host: HostRow }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [address, setAddress] = useState(host.payout_address ?? "");
    const valid = address === "" || /^0x[0-9a-fA-F]{40}$/.test(address.trim());
    const save = async () => {
        try {
            await api.setHostAddress(host.id, address.trim() || null);
            toast.success(address ? "Dirección guardada: sus partes pendientes se pagan ahora" : "Dirección quitada");
            await queryClient.invalidateQueries({ queryKey: ["op", "hosts"] });
        } catch (e) {
            failed(e);
        }
    };
    return (
        <div className="rounded-xl border border-gray-100 p-4 flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1">
                <p className="font-semibold text-eco-forest">{host.name}</p>
                <p className="text-xs text-eco-forest/60">{KIND[host.kind]}</p>
            </div>
            <div className="space-y-1 sm:w-96">
                <Label htmlFor={`addr-${host.id}`}>Dirección de pago (ZyrcleChain)</Label>
                <Input id={`addr-${host.id}`} placeholder="0x… (sin dirección, su parte espera)" value={address} onChange={(e) => setAddress(e.target.value)} />
            </div>
            <Button variant="outline" disabled={!valid || address === (host.payout_address ?? "")} onClick={save}>Guardar</Button>
        </div>
    );
}

function Sites() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const sites = useQuery({ queryKey: ["op", "sites"], queryFn: api.sites });
    const hosts = useQuery({ queryKey: ["op", "hosts"], queryFn: api.hosts });
    const [hostId, setHostId] = useState<string>("");
    const [name, setName] = useState("");

    const create = async () => {
        try {
            await api.createSite(hostId, name.trim());
            setName("");
            await queryClient.invalidateQueries({ queryKey: ["op", "sites"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <Section title="Sedes" description="Cada sede tiene su horario y cupos por contenedor y hora">
            <form
                className="flex flex-wrap items-end gap-2 mb-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    if (hostId && name.trim()) create();
                }}
            >
                <div className="space-y-1">
                    <Label>Anfitrión</Label>
                    <Select value={hostId} onValueChange={setHostId}>
                        <SelectTrigger className="w-56"><SelectValue placeholder="Elige uno" /></SelectTrigger>
                        <SelectContent>
                            {(hosts.data ?? []).map((h) => (
                                <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="space-y-1">
                    <Label htmlFor="site-name">Nombre de la sede</Label>
                    <Input id="site-name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <Button type="submit" disabled={!hostId || !name.trim()}>Agregar sede</Button>
            </form>
            {!sites.data ? <Loading /> : (
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Sede</TableHead>
                            <TableHead>Abre</TableHead>
                            <TableHead>Cierra</TableHead>
                            <TableHead>Cupos por hora</TableHead>
                            <TableHead />
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {sites.data.map((s) => (
                            <ScheduleRow key={s.id} site={s} />
                        ))}
                    </TableBody>
                </Table>
            )}
        </Section>
    );
}

function ScheduleRow({ site }: { site: SiteRow }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [opens, setOpens] = useState(site.opens_hour);
    const [closes, setCloses] = useState(site.closes_hour);
    const [capacity, setCapacity] = useState(site.slot_capacity);
    const changed = opens !== site.opens_hour || closes !== site.closes_hour || capacity !== site.slot_capacity;
    const save = async () => {
        try {
            await api.setSchedule(site.id, opens, closes, capacity);
            toast.success(`Horario de ${site.name}: ${hourLabel(opens)} a ${hourLabel(closes)}`);
            await queryClient.invalidateQueries({ queryKey: ["op", "sites"] });
        } catch (e) {
            failed(e);
        }
    };
    return (
        <TableRow>
            <TableCell>
                <p className="font-medium">{site.name}</p>
                <p className="text-xs text-eco-forest/60">{site.host_name}</p>
            </TableCell>
            <TableCell><Input type="number" min={0} max={23} className="w-20" value={opens} onChange={(e) => setOpens(Number(e.target.value))} aria-label="Hora de apertura" /></TableCell>
            <TableCell><Input type="number" min={1} max={24} className="w-20" value={closes} onChange={(e) => setCloses(Number(e.target.value))} aria-label="Hora de cierre" /></TableCell>
            <TableCell><Input type="number" min={1} className="w-24" value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} aria-label="Cupos por hora" /></TableCell>
            <TableCell className="text-right"><Button size="sm" variant="outline" disabled={!changed || opens >= closes} onClick={save}>Guardar</Button></TableCell>
        </TableRow>
    );
}

/** Reference prices that size the advances (architecture, section 8). */
export function Prices() {
    const { api } = useConsole();
    const list = useQuery({ queryKey: ["op", "prices"], queryFn: api.prices });
    return (
        <Section title="Precios de referencia" description="Con ellos se calcula el anticipo: un porcentaje del precio por kilo. La venta real reparte lo que pagó el comprador">
            {!list.data ? <Loading /> : (
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Material</TableHead>
                            <TableHead>Precio por kilo</TableHead>
                            <TableHead />
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.data.map((p) => (
                            <PriceRow key={p.material} material={p.material} price={p.cop_per_kg} />
                        ))}
                    </TableBody>
                </Table>
            )}
        </Section>
    );
}

function PriceRow({ material, price }: { material: string; price: number | null }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [value, setValue] = useState(price === null ? "" : String(price));
    const save = async () => {
        try {
            await api.setPrice(material, Number(value));
            toast.success(`${MATERIALS[material] ?? material}: ${pesos(Number(value))} por kilo`);
            await queryClient.invalidateQueries({ queryKey: ["op", "prices"] });
        } catch (e) {
            failed(e);
        }
    };
    return (
        <TableRow>
            <TableCell className="font-medium">{MATERIALS[material] ?? material}</TableCell>
            <TableCell><Input type="number" min={0} className="w-32" value={value} onChange={(e) => setValue(e.target.value)} aria-label={`Precio de ${material}`} /></TableCell>
            <TableCell className="text-right"><Button size="sm" variant="outline" disabled={value === "" || Number(value) === price} onClick={save}>Guardar</Button></TableCell>
        </TableRow>
    );
}

/** Admins add operators and switch them off (docs/adr/0014). */
export function Operators() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const list = useQuery({ queryKey: ["op", "operators"], queryFn: api.operators });
    const [email, setEmail] = useState("");
    const [name, setName] = useState("");
    const [role, setRole] = useState<OperatorAccount["role"]>("operator");

    const add = async () => {
        try {
            await api.addOperator(email.trim(), name.trim(), role);
            toast.success(`${name} ya puede entrar con un código a ${email}`);
            setEmail("");
            setName("");
            await queryClient.invalidateQueries({ queryKey: ["op", "operators"] });
        } catch (e) {
            failed(e);
        }
    };
    const update = async (o: OperatorAccount, patch: Partial<Pick<OperatorAccount, "role" | "active">>) => {
        try {
            await api.updateOperator(o.id, patch);
            await queryClient.invalidateQueries({ queryKey: ["op", "operators"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <Section title="Operadores" description="Cada acción queda firmada con el correo de quien la hizo">
            <form
                className="flex flex-wrap items-end gap-2 mb-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    if (email.trim() && name.trim()) add();
                }}
            >
                <div className="space-y-1">
                    <Label htmlFor="op-new-email">Correo</Label>
                    <Input id="op-new-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="op-new-name">Nombre</Label>
                    <Input id="op-new-name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label>Rol</Label>
                    <Select value={role} onValueChange={(v) => setRole(v as OperatorAccount["role"])}>
                        <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="operator">Operador</SelectItem>
                            <SelectItem value="admin">Administrador</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <Button type="submit" disabled={!email.trim() || !name.trim()}>Agregar</Button>
            </form>
            {!list.data ? <Loading /> : (
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Nombre</TableHead>
                            <TableHead>Correo</TableHead>
                            <TableHead>Rol</TableHead>
                            <TableHead />
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.data.map((o) => (
                            <TableRow key={o.id} className={o.active ? "" : "opacity-60"}>
                                <TableCell className="font-medium">{o.name}</TableCell>
                                <TableCell>{o.email}</TableCell>
                                <TableCell>{o.role === "admin" ? "Administrador" : "Operador"}</TableCell>
                                <TableCell className="text-right space-x-2">
                                    <Button size="sm" variant="outline" onClick={() => update(o, { role: o.role === "admin" ? "operator" : "admin" })}>
                                        {o.role === "admin" ? "Quitar admin" : "Hacer admin"}
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => update(o, { active: !o.active })}>
                                        {o.active ? "Desactivar" : "Activar"}
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
        </Section>
    );
}
