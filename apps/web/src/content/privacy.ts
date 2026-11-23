/**
 * The data-processing policy (Ley 1581 de 2012, Decreto 1377 de 2013). A DRAFT for legal review
 * (docs/adr/0028): the version below is what participants accept, and changing the text means a
 * new version, in this file and in the API's `privacy_version`.
 */
export const PRIVACY_VERSION = "2026-11-22";

export interface Section {
  title: string;
  paragraphs: string[];
}

export const PRIVACY: Section[] = [
  {
    title: "Quién trata tus datos",
    paragraphs: [
      "Zyrcle, el sistema de reciclaje trazable que funciona en las sedes que lo instalan. Para cualquier asunto sobre tus datos escribe al canal de contacto que publique Zyrcle antes del piloto [pendiente de definir].",
    ],
  },
  {
    title: "Qué datos usamos",
    paragraphs: [
      "La dirección de tu cuenta en ZyrcleChain y la llave de tu teléfono, que tu app crea sin pedirte nombre ni documento.",
      "Tus depósitos: contenedor, material, peso, fecha y lo que se te pagó. Tus turnos reservados.",
      "Si lo das, tu correo de recuperación. Si activas los avisos, el identificador de tu teléfono para enviarte notificaciones.",
      "No pedimos datos sensibles ni tu ubicación.",
    ],
  },
  {
    title: "Para qué",
    paragraphs: [
      "Abrir el contenedor, verificar lo que depositas, pagarte el anticipo y lo que te corresponde cuando se vende el material, y avisarte de esos pagos.",
      "Recuperar tu cuenta si pierdes el teléfono, con el correo que confirmaste.",
      "Publicar cifras agregadas (kilos, pagos, certificados de impacto) que no te identifican.",
    ],
  },
  {
    title: "Lo que queda en la cadena de bloques",
    paragraphs: [
      "Los pagos se hacen en ZyrcleChain. La dirección de tu cuenta y los montos que recibe son públicos y no se pueden borrar de la cadena. No contienen tu nombre ni tu correo; quien no sepa que esa dirección es tuya no puede asociarla contigo.",
    ],
  },
  {
    title: "Con quién se comparten",
    paragraphs: [
      "Con los proveedores que hacen funcionar el servicio, solo para eso: el envío de correos (Resend, en Estados Unidos), las notificaciones (Expo y Google Firebase) y el servidor donde corre Zyrcle. A la institución anfitriona solo le llegan cifras agregadas.",
    ],
  },
  {
    title: "Tus derechos",
    paragraphs: [
      "Conocer, actualizar, rectificar y pedir que se supriman tus datos, revocar esta autorización, pedir prueba de ella y quejarte ante la Superintendencia de Industria y Comercio. La supresión no alcanza lo que ya está escrito en la cadena de bloques.",
    ],
  },
  {
    title: "Menores de edad",
    paragraphs: [
      "Si tienes menos de 18 años, necesitas la autorización de tu madre, padre o acudiente para usar Zyrcle [pendiente de revisión legal para sedes con estudiantes menores].",
    ],
  },
  {
    title: "Vigencia",
    paragraphs: [
      `Versión ${PRIVACY_VERSION}. Borrador pendiente de revisión legal. Si cambia, la app te pedirá aceptar la nueva versión.`,
    ],
  },
];

export const TERMS: Section[] = [
  {
    title: "Qué es Zyrcle",
    paragraphs: [
      "Un servicio para depositar material reciclable en contenedores que lo pesan y verifican, y recibir pagos en ZYR, la moneda de ZyrcleChain: 1 ZYR equivale a 1 peso colombiano dentro del circuito de Zyrcle.",
    ],
  },
  {
    title: "Estado actual",
    paragraphs: [
      "Zyrcle funciona hoy en una red de pruebas: los contenedores de la demo son simulados y el ZYR no tiene valor real. Antes de un piloto con dinero real estos términos se completarán y revisarán [borrador].",
    ],
  },
  {
    title: "Tus depósitos",
    paragraphs: [
      "Deposita solo el material que declaras. Un depósito que la verificación no reconoce queda en revisión y una persona decide; nunca se rechaza en silencio. El anticipo es una parte del valor de referencia; el resto llega cuando se vende el material.",
    ],
  },
  {
    title: "Tu cuenta",
    paragraphs: [
      "La llave vive en tu teléfono. Si lo pierdes, puedes recuperar tu cuenta con el correo que confirmaste; la recuperación tarda 48 horas y tu teléfono anterior recibe aviso para cancelarla si no fuiste tú.",
    ],
  },
];
