import { redirect } from "next/navigation";

/** Narrative briefing lives under /reports with CXO tabs; keep old URL working. */
export default function SocialNarrativeBriefingRedirectPage() {
  redirect("/reports/narrative-briefing");
}
