import Image from "next/image";
import { allowedImage } from "@/lib/images";
import type { Person } from "@/lib/types";

export function Avatar({ person, size = 40 }: { person: Person; size?: number }) {
  const src = allowedImage(person.picture);
  return src ? (
    <Image src={src} alt="" width={size} height={size} className="shrink-0 rounded-full" />
  ) : (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className="grid shrink-0 place-items-center rounded-full bg-brand font-bold uppercase"
    >
      {person.name.slice(0, 1)}
    </span>
  );
}
