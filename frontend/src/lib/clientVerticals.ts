import type { ClientRow } from "@/context/ClientContext";

/** UI bucket: political vs trading (corporate_pr counts as trading for this screen). */
export type ClientsVerticalUi = "political" | "trading";

export function verticalFromClient(c: ClientRow): ClientsVerticalUi {
  return c.vertical === "political" ? "political" : "trading";
}

export function firstClientForVertical(
  clients: ClientRow[],
  v: ClientsVerticalUi
): ClientRow | undefined {
  if (v === "political") return clients.find((c) => c.vertical === "political");
  return (
    clients.find((c) => c.vertical === "trading") ??
    clients.find((c) => c.vertical === "corporate_pr")
  );
}

export function clientsInVerticalUi(
  clients: ClientRow[],
  v: ClientsVerticalUi
): ClientRow[] {
  if (v === "political") return clients.filter((c) => c.vertical === "political");
  return clients.filter(
    (c) => c.vertical === "trading" || c.vertical === "corporate_pr"
  );
}
