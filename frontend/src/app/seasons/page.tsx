import { redirect } from "next/navigation";
import { currentSeason } from "@/lib/seasons";

/** The season airing now. */
export default function SeasonsPage() {
  const { year, season } = currentSeason();
  redirect(`/seasons/${year}/${season}`);
}
