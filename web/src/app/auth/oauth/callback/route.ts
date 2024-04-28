import { getDomain } from "@/lib/redirectSS";
import { buildUrl } from "@/lib/utilsSS";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  // Wrapper around the FastAPI endpoint /auth/oauth/callback,
  // which adds back a redirect to the main app.
  const url = new URL(buildUrl("/auth/oauth/callback"));
  url.search = request.nextUrl.search;

  const response = await fetch(url.toString());
  const setCookieHeader = response.headers.get("set-cookie");

  if (!setCookieHeader) {
    return NextResponse.redirect(new URL("/auth/error", getDomain(request)));
  }

  //temporay solution for not having ssl
  let modifiedSetCookieHeader = setCookieHeader;
  if (setCookieHeader && setCookieHeader.includes("; Secure")) {
    const cookies = setCookieHeader.split(";");
    const modifiedCookies = cookies.map(cookie => cookie.trim().replace("Secure", ""));
    modifiedSetCookieHeader = modifiedCookies.join(";");
  }
  const redirectResponse = NextResponse.redirect(
    new URL("/", getDomain(request))
  );

  redirectResponse.headers.set("set-cookie", modifiedSetCookieHeader);
  return redirectResponse;
};
