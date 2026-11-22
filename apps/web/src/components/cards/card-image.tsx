import Image from "next/image";
import { cx } from "@/lib/cx";

const SCRYFALL_IMAGES = "https://cards.scryfall.io/";

/** Only Scryfall's image CDN is allowed, matching the CSP img-src. */
export function safeCardImage(uri: string | null | undefined): string | null {
  if (!uri) return null;
  try {
    const url = new URL(uri);
    return url.origin + "/" === SCRYFALL_IMAGES && url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

/** A card image at Scryfall's "normal" size (488 × 680), with a plain frame when there is no image. */
export function CardImage({
  uri,
  name,
  className,
  sizes,
  eager = false,
}: {
  uri: string | null | undefined;
  name: string;
  className?: string;
  sizes: string;
  eager?: boolean;
}) {
  const src = safeCardImage(uri);
  if (!src) {
    return (
      <div
        className={cx(
          "flex aspect-[488/680] items-center justify-center rounded-card border border-rule bg-placeholder p-3 text-center font-serif text-sm text-muted",
          className,
        )}
      >
        {name}
      </div>
    );
  }
  return (
    <Image
      src={src}
      alt={name}
      width={488}
      height={680}
      sizes={sizes}
      loading={eager ? "eager" : "lazy"}
      // Scryfall's CDN already serves sized JPEGs; skip the optimizer so img-src stays one origin.
      unoptimized
      className={cx("aspect-[488/680] h-auto rounded-card bg-placeholder", className)}
    />
  );
}
