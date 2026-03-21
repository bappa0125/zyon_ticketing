import { redirect } from "next/navigation";

/** PR intelligence dashboard lives at `/reports/pr`; keep `/reports` for bookmarks and nav simplicity. */
export default function ReportsIndexPage() {
  redirect("/reports/pr");
}
