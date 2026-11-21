import { redirect } from "next/navigation";
import { AppShell } from "@/components/app/app-shell";
import { getCurrentUser } from "@/lib/auth/session";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const user = await getCurrentUser();
  // The proxy already redirects signed-out requests; this covers a session that expired since.
  if (!user) redirect("/sign-in");
  return <AppShell email={user.email}>{children}</AppShell>;
}
