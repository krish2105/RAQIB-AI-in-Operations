import { DocumentView } from "@/components/ask/document-view";

export default async function DocumentPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ chunk?: string }> }) {
  const { id } = await params;
  const { chunk } = await searchParams;
  return <DocumentView id={id} chunk={chunk} />;
}
