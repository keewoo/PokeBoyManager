import { ValidationView } from "./validation-view";

export default async function ValidationPage({
  searchParams,
}: {
  searchParams: Promise<{ uploads?: string }>;
}) {
  const { uploads } = await searchParams;
  const uploadIds = (uploads ?? "").split(",").filter(Boolean);

  return <ValidationView uploadIds={uploadIds} />;
}
