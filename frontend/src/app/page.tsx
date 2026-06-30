import { redirect } from "next/navigation";

// Root simply forwards into the dashboard; middleware redirects to /login if
// there is no session cookie.
export default function Home() {
  redirect("/dashboard");
}
