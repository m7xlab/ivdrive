import { redirect } from "next/navigation";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function VehicleStatisticsRedirectPage({ params }: PageProps): Promise<never> {
  const { id } = await params;
  redirect(`/vehicles/${id}/statistics/car-overview`);
}
