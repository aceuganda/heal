import {
  AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { redirect } from "next/navigation";
import { fetchSS } from "@/lib/utilsSS";
import { DocumentSet, Tag, User, ValidSources } from "@/lib/types";
import {
  BackendMessage,
  ChatSession,
  Message,
  RetrievalType,
} from "./interfaces";
import { unstable_noStore as noStore } from "next/cache";
import { Persona } from "../admin/personas/interfaces";
import { InstantSSRAutoRefresh } from "@/components/SSRAutoRefresh";
import { ApiKeyModal } from "@/components/openai/ApiKeyModal";
import { cookies } from "next/headers";
import { DOCUMENT_SIDEBAR_WIDTH_COOKIE_NAME } from "@/components/resizable/contants";
import { personaComparator } from "../admin/personas/lib";
import { ChatLayout } from "./ChatPage";

export default async function Page({
  searchParams,
}: {
  searchParams: { [key: string]: string };
}) {
  noStore();

  const tasks = [
    getAuthTypeMetadataSS(),
    getCurrentUserSS(),
    fetchSS("/persona?include_default=true"),
    fetchSS("/chat/get-user-chat-sessions"),
  ];

  // catch cases where the backend is completely unreachable here
  // without try / catch, will just raise an exception and the page
  // will not render
  let results: (User | Response | AuthTypeMetadata | null)[] = [
    null,
    null,
    null,
    null,
  ];
  try {
    results = await Promise.all(tasks);
  } catch (e) {
    console.log(`Some fetch failed for the main search page - ${e}`);
  }
  const authTypeMetadata = results[0] as AuthTypeMetadata | null;
  const user = results[1] as User | null;
  const personasResponse = results[2] as Response | null;
  const chatSessionsResponse = results[3] as Response | null;

  const authDisabled = authTypeMetadata?.authType === "disabled";
  if (!authDisabled && !user) {
    return redirect("/auth/login");
  }

  if (user && !user.is_verified && authTypeMetadata?.requiresVerification) {
    return redirect("/auth/waiting-on-verification");
  }

  // The connector fleet is retired, so /manage/connector, /manage/document-set
  // and /query/valid-tags have no routers -- fetching them was three 404s per
  // page load. Passed empty rather than unpicked: the consumers already handle
  // it, and the filter UI that used them is commented out in Chat.tsx.
  const availableSources: ValidSources[] = [];
  const documentSets: DocumentSet[] = [];
  const tags: Tag[] = [];

  let chatSessions: ChatSession[] = [];
  if (chatSessionsResponse?.ok) {
    chatSessions = (await chatSessionsResponse.json()).sessions;
  } else {
    console.log(
      `Failed to fetch chat sessions - ${chatSessionsResponse?.text()}`
    );
  }
  // By time, not by id: ids are UUIDs now and carry no ordering at all, so
  // sorting on them shuffled the sidebar into a random order.
  chatSessions.sort(
    (a, b) =>
      new Date(b.time_created).getTime() - new Date(a.time_created).getTime()
  );

  let personas: Persona[] = [];
  if (personasResponse?.ok) {
    personas = await personasResponse.json();
  } else {
    console.log(`Failed to fetch personas - ${personasResponse?.status}`);
  }
  // remove those marked as hidden by an admin
  personas = personas.filter((persona) => persona.is_visible);
  // sort them in priority order
  personas.sort(personaComparator);

  const defaultPersonaIdRaw = searchParams["personaId"];
  const defaultPersonaId = defaultPersonaIdRaw
    ? parseInt(defaultPersonaIdRaw)
    : undefined;

  const documentSidebarCookieInitialWidth = cookies().get(
    DOCUMENT_SIDEBAR_WIDTH_COOKIE_NAME
  );
  const finalDocumentSidebarInitialWidth = documentSidebarCookieInitialWidth
    ? parseInt(documentSidebarCookieInitialWidth.value)
    : undefined;

  return (
    <>
      <InstantSSRAutoRefresh />
      <ApiKeyModal />


      <ChatLayout
        user={user}
        chatSessions={chatSessions}
        availableSources={availableSources}
        availableDocumentSets={documentSets}
        availablePersonas={personas}
        availableTags={tags}
        defaultSelectedPersonaId={defaultPersonaId}
        documentSidebarInitialWidth={finalDocumentSidebarInitialWidth}
      />
    </>
  );
}
