import { NextResponse, type NextRequest } from "next/server";

// Lightweight guard: if there is no access-token cookie, bounce protected
// dashboard routes to /login. The authoritative check (token validity, refresh)
// happens client-side in AuthProvider; this just avoids flashing the shell.
const ACCESS_COOKIE = "revos_access";

export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(ACCESS_COOKIE);
  if (!hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
