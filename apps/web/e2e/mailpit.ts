import { MAILPIT_BASE_URL } from "../playwright.config";

type MailpitMessageSummary = { ID: string };
type MailpitSearchResponse = { messages: MailpitMessageSummary[] };
type MailpitMessage = { Text: string; HTML: string };

/** Attend l'e-mail transactionnel envoyé à `to` (Mailpit) et renvoie son corps texte. */
export async function waitForEmail(to: string, timeoutMs = 10_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const search = await fetch(
      `${MAILPIT_BASE_URL}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`
    );
    const { messages } = (await search.json()) as MailpitSearchResponse;

    const [first] = messages;
    if (first) {
      const message = await fetch(`${MAILPIT_BASE_URL}/api/v1/message/${first.ID}`);
      const body = (await message.json()) as MailpitMessage;
      return body.Text;
    }

    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  throw new Error(`Aucun e-mail reçu pour ${to} dans le délai imparti (Mailpit : ${MAILPIT_BASE_URL}).`);
}

/** Extrait le premier `token=...` d'un lien contenu dans le corps de l'e-mail. */
export function extractTokenFromEmail(body: string): string {
  const match = body.match(/token=([^\s&]+)/);
  const token = match?.[1];
  if (!token) throw new Error(`Aucun jeton trouvé dans l'e-mail : ${body}`);
  return token;
}
